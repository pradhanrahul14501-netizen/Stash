package com.stash.app.data.vault

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import com.stash.app.data.local.VaultEntryEntity
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.DataInputStream
import java.io.DataOutputStream
import java.nio.charset.StandardCharsets
import java.security.KeyStore
import java.security.SecureRandom
import javax.crypto.AEADBadTagException
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.PBEKeySpec
import javax.crypto.spec.SecretKeySpec
import org.json.JSONObject

class VaultCrypto {
    fun createEnvelope(password: String): KeyEnvelope {
        val dataKey = ByteArray(DATA_KEY_BYTES).also(SecureRandom()::nextBytes)
        val salt = ByteArray(SALT_BYTES).also(SecureRandom()::nextBytes)
        var derivedKey: ByteArray? = null
        var innerPlaintext: ByteArray? = null
        var passwordWrappedKey: ByteArray? = null
        try {
            val passwordKey = derivePasswordKey(password, salt)
            derivedKey = passwordKey
            val passwordCipher = Cipher.getInstance(AES_GCM)
            passwordCipher.init(Cipher.ENCRYPT_MODE, SecretKeySpec(passwordKey, AES))
            passwordCipher.updateAAD(PASSWORD_WRAP_AAD)
            val wrappedKeyBytes = passwordCipher.doFinal(dataKey)
            passwordWrappedKey = wrappedKeyBytes
            val envelopePlaintext = encodePasswordWrappedKey(salt, passwordCipher.iv, wrappedKeyBytes)
            innerPlaintext = envelopePlaintext

            val deviceCipher = Cipher.getInstance(AES_GCM)
            deviceCipher.init(Cipher.ENCRYPT_MODE, deviceWrappingKey(create = true))
            deviceCipher.updateAAD(DEVICE_WRAP_AAD)
            val deviceWrappedEnvelope = deviceCipher.doFinal(envelopePlaintext)
            val outerEnvelope = deviceCipher.iv + deviceWrappedEnvelope
            val encodedEnvelope = encode(outerEnvelope)
            deviceWrappedEnvelope.fill(0)
            outerEnvelope.fill(0)
            return KeyEnvelope(encodedEnvelope, dataKey)
        } catch (error: Exception) {
            dataKey.fill(0)
            throw VaultStorageException("Could not create the encrypted Vault key.", error)
        } finally {
            derivedKey?.fill(0)
            salt.fill(0)
            passwordWrappedKey?.fill(0)
            innerPlaintext?.fill(0)
        }
    }

    @Throws(VaultPasswordException::class, VaultStorageException::class)
    fun unlock(envelope: String, password: String): ByteArray {
        val outer = try {
            decode(envelope)
        } catch (error: Exception) {
            throw VaultStorageException("The saved Vault key is damaged.", error)
        }
        if (outer.size <= GCM_IV_BYTES + GCM_TAG_BYTES) {
            throw VaultStorageException("The saved Vault key is damaged.")
        }

        val innerPlaintext = try {
            val deviceCipher = Cipher.getInstance(AES_GCM)
            deviceCipher.init(
                Cipher.DECRYPT_MODE,
                deviceWrappingKey(create = false),
                GCMParameterSpec(GCM_TAG_BITS, outer.copyOfRange(0, GCM_IV_BYTES)),
            )
            deviceCipher.updateAAD(DEVICE_WRAP_AAD)
            deviceCipher.doFinal(outer, GCM_IV_BYTES, outer.size - GCM_IV_BYTES)
        } catch (error: Exception) {
            throw VaultStorageException(
                "This Vault key is unavailable on this device. It cannot be recovered from a backup.",
                error,
            )
        }

        var derivedKey: ByteArray? = null
        var wrappedKey: PasswordWrappedKey? = null
        try {
            val parsedWrappedKey = decodePasswordWrappedKey(innerPlaintext)
            wrappedKey = parsedWrappedKey
            val passwordKey = derivePasswordKey(password, parsedWrappedKey.salt)
            derivedKey = passwordKey
            val passwordCipher = Cipher.getInstance(AES_GCM)
            passwordCipher.init(
                Cipher.DECRYPT_MODE,
                SecretKeySpec(passwordKey, AES),
                GCMParameterSpec(GCM_TAG_BITS, parsedWrappedKey.iv),
            )
            passwordCipher.updateAAD(PASSWORD_WRAP_AAD)
            return passwordCipher.doFinal(parsedWrappedKey.ciphertext).also {
                if (it.size != DATA_KEY_BYTES) {
                    it.fill(0)
                    throw VaultStorageException("The saved Vault key is damaged.")
                }
            }
        } catch (error: AEADBadTagException) {
            throw VaultPasswordException()
        } catch (error: VaultPasswordException) {
            throw error
        } catch (error: VaultStorageException) {
            throw error
        } catch (error: Exception) {
            throw VaultStorageException("Could not open the encrypted Vault key.", error)
        } finally {
            derivedKey?.fill(0)
            wrappedKey?.salt?.fill(0)
            wrappedKey?.iv?.fill(0)
            wrappedKey?.ciphertext?.fill(0)
            innerPlaintext.fill(0)
            outer.fill(0)
        }
    }

    fun encryptSecret(key: ByteArray, secret: VaultSecret): VaultEntryEntity {
        val plaintext = JSONObject()
            .put("title", secret.title)
            .put("account", secret.account)
            .put("secret", secret.secret)
            .put("notes", secret.notes)
            .toString()
            .toByteArray(StandardCharsets.UTF_8)
        val cipher = Cipher.getInstance(AES_GCM)
        cipher.init(Cipher.ENCRYPT_MODE, SecretKeySpec(key, AES))
        cipher.updateAAD(itemAad(secret.id, secret.savedAt))
        val iv = cipher.iv
        return try {
            val encryptedPayload = cipher.doFinal(plaintext)
            VaultEntryEntity(
                id = secret.id,
                savedAt = secret.savedAt,
                iv = encode(iv),
                encryptedPayload = encode(encryptedPayload),
            ).also { encryptedPayload.fill(0) }
        } finally {
            plaintext.fill(0)
            iv.fill(0)
        }
    }

    fun decryptSecret(key: ByteArray, entity: VaultEntryEntity): VaultSecret {
        val iv = decode(entity.iv)
        val ciphertext = decode(entity.encryptedPayload)
        val plaintext = try {
            val cipher = Cipher.getInstance(AES_GCM)
            cipher.init(
                Cipher.DECRYPT_MODE,
                SecretKeySpec(key, AES),
                GCMParameterSpec(GCM_TAG_BITS, iv),
            )
            cipher.updateAAD(itemAad(entity.id, entity.savedAt))
            cipher.doFinal(ciphertext)
        } catch (error: Exception) {
            throw VaultStorageException("A Vault item could not be decrypted.", error)
        } finally {
            iv.fill(0)
            ciphertext.fill(0)
        }

        return try {
            val json = JSONObject(String(plaintext, StandardCharsets.UTF_8))
            VaultSecret(
                id = entity.id,
                savedAt = entity.savedAt,
                title = json.getString("title"),
                account = json.optString("account"),
                secret = json.getString("secret"),
                notes = json.optString("notes"),
            )
        } catch (error: Exception) {
            throw VaultStorageException("A Vault item is damaged.", error)
        } finally {
            plaintext.fill(0)
        }
    }

    private fun derivePasswordKey(password: String, salt: ByteArray): ByteArray {
        val passwordCharacters = password.toCharArray()
        val spec = PBEKeySpec(passwordCharacters, salt, PBKDF2_ITERATIONS, DATA_KEY_BYTES * 8)
        return try {
            SecretKeyFactory.getInstance(PBKDF2).generateSecret(spec).encoded
        } finally {
            spec.clearPassword()
            passwordCharacters.fill('\u0000')
        }
    }

    private fun deviceWrappingKey(create: Boolean): SecretKey {
        try {
            val keyStore = KeyStore.getInstance(ANDROID_KEY_STORE).apply { load(null) }
            (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
            if (!create) throw IllegalStateException("Device Vault key is missing.")

            val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEY_STORE)
            generator.init(
                KeyGenParameterSpec.Builder(
                    KEY_ALIAS,
                    KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
                )
                    .setKeySize(256)
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setRandomizedEncryptionRequired(true)
                    .build(),
            )
            return generator.generateKey()
        } catch (error: Exception) {
            throw VaultStorageException("Android could not access its secure key store.", error)
        }
    }

    private fun encodePasswordWrappedKey(salt: ByteArray, iv: ByteArray, ciphertext: ByteArray): ByteArray =
        ByteArrayOutputStream().use { bytes ->
            DataOutputStream(bytes).use { output ->
                output.writeInt(ENVELOPE_MAGIC)
                output.writeInt(ENVELOPE_VERSION)
                output.writeInt(salt.size)
                output.write(salt)
                output.writeInt(iv.size)
                output.write(iv)
                output.writeInt(ciphertext.size)
                output.write(ciphertext)
            }
            bytes.toByteArray()
        }

    private fun decodePasswordWrappedKey(bytes: ByteArray): PasswordWrappedKey =
        DataInputStream(ByteArrayInputStream(bytes)).use { input ->
            if (input.readInt() != ENVELOPE_MAGIC || input.readInt() != ENVELOPE_VERSION) {
                throw VaultStorageException("The saved Vault key uses an unknown format.")
            }
            val salt = input.readSizedBytes(SALT_BYTES)
            val iv = input.readSizedBytes(GCM_IV_BYTES)
            val ciphertext = input.readSizedBytes(DATA_KEY_BYTES + GCM_TAG_BYTES)
            if (salt.size != SALT_BYTES || iv.size != GCM_IV_BYTES ||
                ciphertext.size != DATA_KEY_BYTES + GCM_TAG_BYTES || input.available() != 0
            ) {
                throw VaultStorageException("The saved Vault key is damaged.")
            }
            PasswordWrappedKey(salt, iv, ciphertext)
        }

    private fun DataInputStream.readSizedBytes(maxBytes: Int): ByteArray {
        val size = readInt()
        if (size !in 1..maxBytes || size > available()) {
            throw VaultStorageException("The saved Vault key is damaged.")
        }
        return ByteArray(size).also(::readFully)
    }

    private fun itemAad(id: String, savedAt: Long): ByteArray =
        "stash-vault-item-v1|$id|$savedAt".toByteArray(StandardCharsets.UTF_8)

    private fun encode(bytes: ByteArray): String = Base64.encodeToString(bytes, Base64.NO_WRAP)

    private fun decode(value: String): ByteArray = Base64.decode(value, Base64.NO_WRAP)

    data class KeyEnvelope(val encoded: String, val dataKey: ByteArray)

    private data class PasswordWrappedKey(val salt: ByteArray, val iv: ByteArray, val ciphertext: ByteArray)

    private companion object {
        const val AES = "AES"
        const val AES_GCM = "AES/GCM/NoPadding"
        const val ANDROID_KEY_STORE = "AndroidKeyStore"
        const val KEY_ALIAS = "com.stash.app.vault.device-wrap.v1"
        const val PBKDF2 = "PBKDF2WithHmacSHA256"
        const val PBKDF2_ITERATIONS = 600_000
        const val DATA_KEY_BYTES = 32
        const val SALT_BYTES = 16
        const val GCM_IV_BYTES = 12
        const val GCM_TAG_BITS = 128
        const val GCM_TAG_BYTES = 16
        const val ENVELOPE_MAGIC = 0x53544153
        const val ENVELOPE_VERSION = 1
        val PASSWORD_WRAP_AAD = "stash-vault-key-v1".toByteArray(StandardCharsets.UTF_8)
        val DEVICE_WRAP_AAD = "stash-vault-device-v1".toByteArray(StandardCharsets.UTF_8)
    }
}
