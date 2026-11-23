package com.stash.app.data.mobilecompanion

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import org.json.JSONObject

data class MobileCompanionConnection(val baseUrl: String, val token: String)

/** Encrypts the paired phone's private-LAN token with an Android Keystore key. */
class MobileCompanionSessionStore(context: Context) {
    private val preferences = context.applicationContext.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    fun save(baseUrl: String, token: String) {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val plaintext = JSONObject().put("base_url", baseUrl).put("token", token)
            .toString().toByteArray(Charsets.UTF_8)
        val encrypted = cipher.doFinal(plaintext)
        val packed = cipher.iv + encrypted
        preferences.edit().putString(KEY_CONNECTION, Base64.encodeToString(packed, Base64.NO_WRAP)).apply()
        plaintext.fill(0)
        encrypted.fill(0)
        packed.fill(0)
    }

    fun connection(): MobileCompanionConnection? {
        val encoded = preferences.getString(KEY_CONNECTION, null) ?: return null
        return runCatching {
            val packed = Base64.decode(encoded, Base64.NO_WRAP)
            require(packed.size > IV_BYTES)
            val iv = packed.copyOfRange(0, IV_BYTES)
            val ciphertext = packed.copyOfRange(IV_BYTES, packed.size)
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(TAG_BITS, iv))
            val json = JSONObject(cipher.doFinal(ciphertext).toString(Charsets.UTF_8))
            packed.fill(0)
            iv.fill(0)
            ciphertext.fill(0)
            MobileCompanionConnection(json.getString("base_url"), json.getString("token"))
        }.getOrElse {
            clear()
            null
        }
    }

    fun clear() {
        preferences.edit().remove(KEY_CONNECTION).apply()
    }

    private fun key(): SecretKey {
        val store = KeyStore.getInstance(ANDROID_KEY_STORE).apply { load(null) }
        (store.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEY_STORE)
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build(),
        )
        return generator.generateKey()
    }

    private companion object {
        const val PREFERENCES = "stash_mobile_companion"
        const val KEY_CONNECTION = "encrypted_connection"
        const val KEY_ALIAS = "stash.mobile.companion.v1"
        const val ANDROID_KEY_STORE = "AndroidKeyStore"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val IV_BYTES = 12
        const val TAG_BITS = 128
    }
}
