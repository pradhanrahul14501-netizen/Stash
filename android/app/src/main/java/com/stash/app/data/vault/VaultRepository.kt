package com.stash.app.data.vault

import com.stash.app.data.local.VaultEntryDao
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class VaultRepository(
    private val dao: VaultEntryDao,
    private val configurationStore: VaultConfigurationStore,
    private val crypto: VaultCrypto = VaultCrypto(),
) {
    fun hasVault(): Boolean = configurationStore.hasVault()

    fun hasBiometricUnlock(): Boolean = configurationStore.biometricEnvelope() != null

    fun biometricEnvelope(): String? = configurationStore.biometricEnvelope()

    fun saveBiometricEnvelope(value: String) = configurationStore.saveBiometricEnvelope(value)

    fun clearBiometricEnvelope() = configurationStore.clearBiometricEnvelope()

    suspend fun create(password: String): ByteArray = withContext(Dispatchers.IO) {
        if (configurationStore.hasVault()) {
            throw IllegalStateException("The Vault is already set up.")
        }
        val envelope = crypto.createEnvelope(password)
        try {
            configurationStore.saveEnvelope(envelope.encoded)
            envelope.dataKey
        } catch (error: Exception) {
            envelope.dataKey.fill(0)
            throw error
        }
    }

    suspend fun restore(password: String, entries: List<VaultSecret>) = withContext(Dispatchers.IO) {
        if (configurationStore.hasVault()) {
            throw IllegalStateException("A Vault is already set up on this device.")
        }
        val envelope = crypto.createEnvelope(password)
        try {
            val encryptedEntries = entries.map { crypto.encryptSecret(envelope.dataKey, it) }
            configurationStore.saveEnvelope(envelope.encoded)
            dao.insertAll(encryptedEntries)
        } catch (error: Exception) {
            runCatching { dao.deleteAll() }
            runCatching { configurationStore.clearEnvelope() }
            throw error
        } finally {
            envelope.dataKey.fill(0)
        }
    }

    suspend fun unlock(password: String): ByteArray = withContext(Dispatchers.IO) {
        val envelope = configurationStore.envelope()
            ?: throw IllegalStateException("The Vault has not been set up.")
        crypto.unlock(envelope, password)
    }

    suspend fun entries(key: ByteArray): List<VaultSecret> = withContext(Dispatchers.IO) {
        dao.getAll().map { crypto.decryptSecret(key, it) }
    }

    suspend fun save(
        key: ByteArray,
        title: String,
        account: String,
        secret: String,
        notes: String,
    ): VaultSecret = withContext(Dispatchers.IO) {
        val value = VaultSecret(
            id = UUID.randomUUID().toString(),
            savedAt = System.currentTimeMillis(),
            title = title.trim(),
            account = account.trim(),
            secret = secret,
            notes = notes.trim(),
        )
        dao.insert(crypto.encryptSecret(key, value))
        value
    }

    suspend fun delete(id: String) = withContext(Dispatchers.IO) {
        dao.deleteById(id)
    }
}
