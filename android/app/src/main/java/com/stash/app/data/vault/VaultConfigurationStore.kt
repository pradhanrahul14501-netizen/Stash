package com.stash.app.data.vault

import android.content.Context
import java.io.IOException

class VaultConfigurationStore(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)

    fun hasVault(): Boolean = preferences.contains(ENVELOPE_KEY)

    fun envelope(): String? = preferences.getString(ENVELOPE_KEY, null)

    fun biometricEnvelope(): String? = preferences.getString(BIOMETRIC_ENVELOPE_KEY, null)

    @Throws(IOException::class)
    fun saveBiometricEnvelope(value: String) {
        val saved = preferences.edit().putString(BIOMETRIC_ENVELOPE_KEY, value).commit()
        if (!saved) throw IOException("Could not save biometric Vault unlock.")
    }

    @Throws(IOException::class)
    fun clearBiometricEnvelope() {
        val saved = preferences.edit().remove(BIOMETRIC_ENVELOPE_KEY).commit()
        if (!saved) throw IOException("Could not remove biometric Vault unlock.")
    }

    @Throws(IOException::class)
    fun saveEnvelope(value: String) {
        val saved = preferences.edit().putString(ENVELOPE_KEY, value).commit()
        if (!saved) throw IOException("Could not save the Vault setup.")
    }

    @Throws(IOException::class)
    fun clearEnvelope() {
        val saved = preferences.edit().remove(ENVELOPE_KEY).commit()
        if (!saved) throw IOException("Could not clear the Vault setup.")
    }

    private companion object {
        const val PREFERENCES_NAME = "stash_vault_config"
        const val ENVELOPE_KEY = "protected_key_envelope_v1"
        const val BIOMETRIC_ENVELOPE_KEY = "biometric_wrapped_data_key_v1"
    }
}
