package com.stash.app.data.backup

import com.stash.app.data.local.LibraryItemEntity
import com.stash.app.data.storage.PrivateItemStore
import com.stash.app.data.vault.VaultSecret
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class EncryptedBackupCodecTest {
    @get:Rule
    val temporaryFolder = TemporaryFolder()

    @Test
    fun roundTripsLibraryFilesAndVaultItemsThroughEncryptedBackup() {
        val filesDirectory = temporaryFolder.newFolder("app-files")
        val libraryDirectory = File(filesDirectory, "library").apply { mkdirs() }
        File(libraryDirectory, "saved.txt").writeText("private file content")
        val libraryItem = LibraryItemEntity(
            id = "item-1",
            title = "Saved note",
            category = "TEXT",
            mimeType = "text/plain",
            savedAt = 123L,
            contentText = "saved text",
            relativePath = "library/saved.txt",
            byteSize = 20L,
            deletedAt = 456L,
        )
        val vaultItem = VaultSecret("vault-1", 789L, "Email", "user", "secret", "notes")
        val codec = EncryptedBackupCodec(temporaryFolder.newFolder("cache"), PrivateItemStore(filesDirectory))
        val backupBytes = ByteArrayOutputStream()

        codec.write(backupBytes, BACKUP_PASSWORD, listOf(libraryItem), listOf(vaultItem), vaultConfigured = true)

        val encoded = backupBytes.toByteArray()
        assertFalse(encoded.containsContent("secret"))
        val restored = codec.read(ByteArrayInputStream(encoded), BACKUP_PASSWORD)
        try {
            assertEquals(listOf(libraryItem.copy(relativePath = null)), restored.libraryItems)
            assertEquals(listOf(vaultItem), restored.vaultEntries)
            assertTrue(restored.vaultConfigured)
            assertEquals("private file content", restored.filesByItemId.getValue("item-1").readText())
        } finally {
            restored.deleteStagingFiles()
        }
        assertThrows(Exception::class.java) {
            codec.read(ByteArrayInputStream(encoded), "a different backup password")
        }
    }

    @Test
    fun rejectsWeakBackupPasswordsBeforeWriting() {
        val codec = EncryptedBackupCodec(
            temporaryFolder.newFolder("cache"),
            PrivateItemStore(temporaryFolder.newFolder("app-files")),
        )
        assertThrows(IllegalArgumentException::class.java) {
            codec.write(ByteArrayOutputStream(), "short", emptyList(), emptyList(), vaultConfigured = false)
        }
    }

    private fun ByteArray.containsContent(value: String): Boolean =
        String(this, Charsets.ISO_8859_1).contains(value)

    private companion object {
        const val BACKUP_PASSWORD = "Correct horse battery"
    }
}
