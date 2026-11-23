package com.stash.app.data.vault

import android.app.Activity
import android.hardware.biometrics.BiometricManager
import android.hardware.biometrics.BiometricPrompt
import android.os.CancellationSignal
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import java.util.concurrent.CancellationException
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** Wraps the Vault's data key with a strong-biometric-only Android Keystore key. */
class VaultBiometricAccess {
    fun isAvailable(activity: Activity): Boolean = runCatching {
        val manager = activity.getSystemService(BiometricManager::class.java)
        manager.canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_STRONG) ==
            BiometricManager.BIOMETRIC_SUCCESS
    }.getOrDefault(false)

    suspend fun wrapDataKey(activity: Activity, dataKey: ByteArray): String {
        check(isAvailable(activity)) { "Set up a fingerprint or face unlock before enabling this option." }
        val cipher = Cipher.getInstance(TRANSFORMATION).apply {
            init(Cipher.ENCRYPT_MODE, biometricKey(create = true))
        }
        val authenticatedCipher = authenticate(
            activity = activity,
            cipher = cipher,
            title = "Enable biometric Vault unlock",
            subtitle = "Verify your identity to enable this device's biometric unlock.",
            negativeButton = "Cancel",
        )
        val iv = authenticatedCipher.iv
        val encryptedKey = authenticatedCipher.doFinal(dataKey)
        return try {
            Base64.encodeToString(iv + encryptedKey, Base64.NO_WRAP)
        } finally {
            iv.fill(0)
            encryptedKey.fill(0)
        }
    }

    suspend fun unwrapDataKey(activity: Activity, wrappedDataKey: String): ByteArray {
        check(isAvailable(activity)) { "Strong biometric unlock is unavailable. Use your Vault password." }
        val envelope = Base64.decode(wrappedDataKey, Base64.NO_WRAP)
        if (envelope.size <= IV_BYTES + TAG_BYTES) {
            envelope.fill(0)
            throw IllegalStateException("Biometric unlock data is damaged. Use your Vault password.")
        }
        val iv = envelope.copyOfRange(0, IV_BYTES)
        val ciphertext = envelope.copyOfRange(IV_BYTES, envelope.size)
        envelope.fill(0)
        return try {
            val cipher = Cipher.getInstance(TRANSFORMATION).apply {
                init(
                    Cipher.DECRYPT_MODE,
                    biometricKey(create = false),
                    GCMParameterSpec(TAG_BITS, iv),
                )
            }
            authenticate(
                activity = activity,
                cipher = cipher,
                title = "Unlock Stash Vault",
                subtitle = "Verify your identity to open your Vault.",
                negativeButton = "Use password",
            ).doFinal(ciphertext)
        } finally {
            iv.fill(0)
            ciphertext.fill(0)
        }
    }

    fun deleteBiometricKey() {
        runCatching {
            KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
                .deleteEntry(BIOMETRIC_KEY_ALIAS)
        }
    }

    private fun biometricKey(create: Boolean): SecretKey {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        (keyStore.getKey(BIOMETRIC_KEY_ALIAS, null) as? SecretKey)?.let { return it }
        check(create) { "Biometric unlock is unavailable. Use your Vault password." }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE)
        generator.init(
            KeyGenParameterSpec.Builder(
                BIOMETRIC_KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setKeySize(256)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .setUserAuthenticationRequired(true)
                .setUserAuthenticationParameters(0, KeyProperties.AUTH_BIOMETRIC_STRONG)
                .setInvalidatedByBiometricEnrollment(true)
                .build(),
        )
        return generator.generateKey()
    }

    private suspend fun authenticate(
        activity: Activity,
        cipher: Cipher,
        title: String,
        subtitle: String,
        negativeButton: String,
    ): Cipher = suspendCancellableCoroutine { continuation ->
        val cancellationSignal = CancellationSignal()
        val prompt = BiometricPrompt.Builder(activity)
            .setTitle(title)
            .setSubtitle(subtitle)
            .setNegativeButton(negativeButton, activity.mainExecutor) { _, _ ->
                if (continuation.isActive) {
                    continuation.cancel(CancellationException("Biometric prompt dismissed."))
                }
            }
            .setAllowedAuthenticators(BiometricManager.Authenticators.BIOMETRIC_STRONG)
            .build()
        continuation.invokeOnCancellation { cancellationSignal.cancel() }
        prompt.authenticate(
            BiometricPrompt.CryptoObject(cipher),
            cancellationSignal,
            activity.mainExecutor,
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    val authenticatedCipher = result.cryptoObject?.cipher
                    if (authenticatedCipher == null) {
                        if (continuation.isActive) {
                            continuation.resumeWithException(
                                IllegalStateException("The biometric prompt did not return a secure operation."),
                            )
                        }
                    } else if (continuation.isActive) {
                        continuation.resume(authenticatedCipher)
                    }
                }

                override fun onAuthenticationError(errorCode: Int, errorString: CharSequence) {
                    if (!continuation.isActive) return
                    if (errorCode == BiometricPrompt.BIOMETRIC_ERROR_USER_CANCELED ||
                        errorCode == BiometricPrompt.BIOMETRIC_ERROR_CANCELED
                    ) {
                        continuation.cancel(CancellationException("Biometric prompt dismissed."))
                    } else {
                        continuation.resumeWithException(IllegalStateException(errorString.toString()))
                    }
                }
            },
        )
    }

    private companion object {
        const val ANDROID_KEYSTORE = "AndroidKeyStore"
        const val BIOMETRIC_KEY_ALIAS = "stash-vault-biometric-wrap-v1"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val IV_BYTES = 12
        const val TAG_BITS = 128
        const val TAG_BYTES = TAG_BITS / 8
    }
}
