package com.stash.app.data.shared

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Keeps only the server address and an encrypted, revocable session cookie. */
class SharedStashSessionStore(context: Context) {
    private val preferences = context.applicationContext.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    fun serverUrl(): String = preferences.getString(KEY_SERVER_URL, "").orEmpty()

    fun identity(): String = preferences.getString(KEY_IDENTITY, "").orEmpty()

    fun saveServerUrl(value: String) {
        preferences.edit().putString(KEY_SERVER_URL, value).apply()
    }

    fun saveSession(serverUrl: String, identity: String, cookie: String) {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val encrypted = cipher.doFinal(cookie.toByteArray(Charsets.UTF_8))
        val packed = cipher.iv + encrypted
        preferences.edit()
            .putString(KEY_SERVER_URL, serverUrl)
            .putString(KEY_IDENTITY, identity)
            .putString(KEY_SESSION, Base64.encodeToString(packed, Base64.NO_WRAP))
            .apply()
        packed.fill(0)
        encrypted.fill(0)
    }

    fun sessionCookie(): String? {
        val encoded = preferences.getString(KEY_SESSION, null) ?: return null
        return runCatching {
            val packed = Base64.decode(encoded, Base64.NO_WRAP)
            require(packed.size > IV_BYTES)
            val iv = packed.copyOfRange(0, IV_BYTES)
            val ciphertext = packed.copyOfRange(IV_BYTES, packed.size)
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(TAG_BITS, iv))
            String(cipher.doFinal(ciphertext), Charsets.UTF_8).also {
                packed.fill(0)
                iv.fill(0)
                ciphertext.fill(0)
            }
        }.getOrElse {
            clearSession()
            null
        }
    }

    fun clearSession() {
        preferences.edit().remove(KEY_SESSION).remove(KEY_IDENTITY).apply()
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
        const val PREFERENCES = "stash_shared_connection"
        const val KEY_SERVER_URL = "server_url"
        const val KEY_IDENTITY = "identity"
        const val KEY_SESSION = "encrypted_session_cookie"
        const val KEY_ALIAS = "stash.shared.session.v1"
        const val ANDROID_KEY_STORE = "AndroidKeyStore"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val IV_BYTES = 12
        const val TAG_BITS = 128
    }
}
