package com.stash.app.data.backup

import android.content.ContentResolver
import android.net.Uri
import com.stash.app.data.LibraryRepository
import com.stash.app.data.ava.AvaFollowUpRepository
import com.stash.app.data.storage.PrivateItemStore
import com.stash.app.data.vault.VaultRepository
import java.io.IOException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

data class BackupResult(
    val libraryItemCount: Int,
    val vaultItemCount: Int,
    val followUpCount: Int = 0,
)

class EncryptedBackupRepository(
    private val contentResolver: ContentResolver,
    private val cacheDirectory: java.io.File,
    private val privateItemStore: PrivateItemStore,
    private val libraryRepository: LibraryRepository,
    private val avaFollowUpRepository: AvaFollowUpRepository,
    private val vaultRepository: VaultRepository,
) {
    private val codec = EncryptedBackupCodec(cacheDirectory, privateItemStore)

    suspend fun canRestore(): Boolean =
        !vaultRepository.hasVault() && libraryRepository.isEmpty()

    suspend fun export(
        destination: Uri,
        backupPassword: String,
        currentVaultPassword: String?,
    ): BackupResult = withContext(Dispatchers.IO) {
        val libraryItems = libraryRepository.allItemsForBackup()
        val folderNames = libraryRepository.folderNamesForBackup()
        val avaFollowUps = avaFollowUpRepository.allForSync()
        val vaultConfigured = vaultRepository.hasVault()
        val vaultEntries = if (vaultConfigured) {
            val password = currentVaultPassword?.takeIf(String::isNotBlank)
                ?: throw IllegalArgumentException("Enter your current Vault password to back it up.")
            val key = vaultRepository.unlock(password)
            try {
                vaultRepository.entries(key)
            } finally {
                key.fill(0)
            }
        } else {
            emptyList()
        }
        val output = contentResolver.openOutputStream(destination, "wt")
            ?: throw IOException("Stash could not create the backup file.")
        output.use { codec.write(it, backupPassword, libraryItems, folderNames, vaultEntries, avaFollowUps, vaultConfigured) }
        BackupResult(libraryItems.size, vaultEntries.size, avaFollowUps.count { it.deletedAt == null })
    }

    suspend fun restore(
        source: Uri,
        backupPassword: String,
        newVaultPassword: String,
    ): BackupResult = withContext(Dispatchers.IO) {
        if (!libraryRepository.isEmpty() || vaultRepository.hasVault()) {
            throw IllegalStateException("Restore is available only on a new or empty Stash installation.")
        }
        val input = contentResolver.openInputStream(source)
            ?: throw IOException("Stash could not open this backup file.")
        val snapshot = input.use { codec.read(it, backupPassword) }
        var restoredItemIds = emptyList<String>()
        try {
            if (snapshot.vaultConfigured && newVaultPassword.length < MIN_VAULT_PASSWORD_LENGTH) {
                throw IllegalArgumentException("Choose a new Vault password with at least 12 characters.")
            }
            if (!snapshot.vaultConfigured && snapshot.vaultEntries.isNotEmpty()) {
                throw IOException("The backup contains Vault items but no Vault setup.")
            }
            restoredItemIds = libraryRepository.restoreFromBackup(
                snapshot.libraryItems,
                snapshot.filesByItemId,
                snapshot.fileNamesByItemId,
                snapshot.folderNames,
            )
            avaFollowUpRepository.restoreFromBackup(snapshot.avaFollowUps)
            if (snapshot.vaultConfigured) {
                vaultRepository.restore(newVaultPassword, snapshot.vaultEntries)
            }
            BackupResult(snapshot.libraryItems.size, snapshot.vaultEntries.size, snapshot.avaFollowUps.count { it.deletedAt == null })
        } catch (error: Exception) {
            runCatching { libraryRepository.rollbackRestoredItems(restoredItemIds, snapshot.folderNames) }
            throw error
        } finally {
            snapshot.deleteStagingFiles()
        }
    }

    private companion object {
        const val MIN_VAULT_PASSWORD_LENGTH = 12
    }
}
