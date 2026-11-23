package com.stash.app.data.backup

import com.stash.app.data.local.LibraryItemEntity
import com.stash.app.data.local.AvaFollowUpEntity
import com.stash.app.data.storage.PrivateItemStore
import com.stash.app.data.vault.VaultSecret
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.DataInputStream
import java.io.DataOutputStream
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.CipherInputStream
import javax.crypto.CipherOutputStream
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.PBEKeySpec
import javax.crypto.spec.SecretKeySpec
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID
import java.util.zip.ZipEntry
import java.util.zip.ZipInputStream
import java.util.zip.ZipOutputStream

internal data class BackupSnapshot(
    val libraryItems: List<LibraryItemEntity>,
    val folderNames: List<String>,
    val vaultEntries: List<VaultSecret>,
    val avaFollowUps: List<AvaFollowUpEntity>,
    val vaultConfigured: Boolean,
    val filesByItemId: Map<String, File>,
    val fileNamesByItemId: Map<String, String>,
    val stagingDirectory: File,
) {
    fun deleteStagingFiles() {
        stagingDirectory.deleteRecursively()
    }
}

internal class EncryptedBackupCodec(
    private val cacheDirectory: File,
    private val privateItemStore: PrivateItemStore,
) {
    fun write(
        destination: OutputStream,
        password: String,
        libraryItems: List<LibraryItemEntity>,
        folderNames: List<String>,
        vaultEntries: List<VaultSecret>,
        avaFollowUps: List<AvaFollowUpEntity>,
        vaultConfigured: Boolean,
    ) {
        validatePassword(password)
        val salt = ByteArray(SALT_BYTES).also(SecureRandom()::nextBytes)
        val iv = ByteArray(GCM_IV_BYTES).also(SecureRandom()::nextBytes)
        val key = deriveKey(password, salt)
        try {
            val cipher = Cipher.getInstance(AES_GCM)
            cipher.init(Cipher.ENCRYPT_MODE, SecretKeySpec(key, AES), GCMParameterSpec(GCM_TAG_BITS, iv))
            DataOutputStream(destination).apply {
                writeInt(MAGIC)
                writeInt(VERSION)
                write(salt)
                write(iv)
                flush()
            }
            writeArchive(CipherOutputStream(destination, cipher), libraryItems, folderNames, vaultEntries, avaFollowUps, vaultConfigured)
        } finally {
            key.fill(0)
            salt.fill(0)
            iv.fill(0)
        }
    }

    fun read(source: InputStream, password: String): BackupSnapshot {
        validatePassword(password)
        val stagingDirectory = File(cacheDirectory, "stash-restore-${UUID.randomUUID()}")
        if (!stagingDirectory.mkdirs()) throw IOException("Could not prepare a private restore folder.")
        val archive = File(stagingDirectory, "backup.zip")
        try {
            decryptArchive(source, password, archive)
            val extractedFiles = extractArchive(archive, stagingDirectory)
            val manifest = File(stagingDirectory, "manifest.json")
            if (!manifest.isFile || manifest.length() > MAX_MANIFEST_BYTES) {
                throw IOException("The backup manifest is missing or too large.")
            }
            return parseManifest(manifest, extractedFiles, stagingDirectory)
        } catch (error: Exception) {
            stagingDirectory.deleteRecursively()
            if (error is IOException) throw error
            throw IOException("The backup could not be opened. Check its password and file integrity.", error)
        }
    }

    private fun writeArchive(
        destination: OutputStream,
        libraryItems: List<LibraryItemEntity>,
        folderNames: List<String>,
        vaultEntries: List<VaultSecret>,
        avaFollowUps: List<AvaFollowUpEntity>,
        vaultConfigured: Boolean,
    ) {
        val itemJson = JSONArray()
        val files = mutableListOf<Pair<String, File>>()
        libraryItems.forEachIndexed { index, item ->
            val fileEntry = if (item.relativePath.isNullOrBlank()) {
                null
            } else {
                val file = privateItemStore.fileFor(item.relativePath)
                    ?: throw IOException("A saved file is missing; Stash could not back it up.")
                "files/$index".also { files += it to file }
            }
            itemJson.put(
                JSONObject()
                    .put("id", item.id)
                    .put("title", item.title)
                    .put("category", item.category)
                    .put("mimeType", item.mimeType)
                    .put("savedAt", item.savedAt)
                    .put("contentText", item.contentText ?: JSONObject.NULL)
                    .put("ocrText", item.ocrText ?: JSONObject.NULL)
                    .put("fileEntry", fileEntry ?: JSONObject.NULL)
                    .put("fileName", item.relativePath?.substringAfterLast('/') ?: JSONObject.NULL)
                    .put("byteSize", item.byteSize)
                    .put("mode", item.mode)
                    .put("deletedAt", item.deletedAt ?: JSONObject.NULL)
                    .put("folderName", item.folderName ?: JSONObject.NULL)
                    .put("tagsJson", item.tagsJson)
                    .put("isFavorite", item.isFavorite)
                    .put("sharedItemId", item.sharedItemId ?: JSONObject.NULL),
            )
        }

        val folderJson = JSONArray().apply { folderNames.distinct().forEach(::put) }

        val vaultJson = JSONArray()
        vaultEntries.forEach { entry ->
            vaultJson.put(
                JSONObject()
                    .put("id", entry.id)
                    .put("savedAt", entry.savedAt)
                    .put("title", entry.title)
                    .put("account", entry.account)
                    .put("secret", entry.secret)
                    .put("notes", entry.notes),
            )
        }
        val followUpJson = JSONArray()
        avaFollowUps.forEach { followUp ->
            followUpJson.put(
                JSONObject()
                    .put("id", followUp.id)
                    .put("sourceItemId", followUp.sourceItemId)
                    .put("sourceTitle", followUp.sourceTitle)
                    .put("eventLabel", followUp.eventLabel)
                    .put("sourceExcerpt", followUp.sourceExcerpt)
                    .put("eventAt", followUp.eventAt)
                    .put("remindAt", followUp.remindAt)
                    .put("createdAt", followUp.createdAt)
                    .put("notifiedAt", followUp.notifiedAt ?: JSONObject.NULL)
                    .put("updatedAt", followUp.updatedAt)
                    .put("deletedAt", followUp.deletedAt ?: JSONObject.NULL),
            )
        }
        val manifestBytes = JSONObject()
            .put("version", VERSION)
            .put("createdAt", System.currentTimeMillis())
            .put("vaultConfigured", vaultConfigured)
            .put("libraryItems", itemJson)
            .put("folders", folderJson)
            .put("vaultEntries", vaultJson)
            .put("avaFollowUps", followUpJson)
            .toString()
            .toByteArray(Charsets.UTF_8)

        ZipOutputStream(BufferedOutputStream(destination)).use { zip ->
            zip.putNextEntry(ZipEntry(MANIFEST_ENTRY))
            zip.write(manifestBytes)
            zip.closeEntry()
            files.forEach { (entryName, file) ->
                zip.putNextEntry(ZipEntry(entryName))
                FileInputStream(file).use { it.copyTo(zip) }
                zip.closeEntry()
            }
        }
    }

    private fun decryptArchive(source: InputStream, password: String, archive: File) {
        val input = DataInputStream(BufferedInputStream(source))
        if (input.readInt() != MAGIC || input.readInt() != VERSION) {
            throw IOException("This file is not a supported Stash backup.")
        }
        val salt = ByteArray(SALT_BYTES).also(input::readFully)
        val iv = ByteArray(GCM_IV_BYTES).also(input::readFully)
        val key = deriveKey(password, salt)
        try {
            val cipher = Cipher.getInstance(AES_GCM)
            cipher.init(Cipher.DECRYPT_MODE, SecretKeySpec(key, AES), GCMParameterSpec(GCM_TAG_BITS, iv))
            CipherInputStream(input, cipher).use { decrypted ->
                FileOutputStream(archive).use { output ->
                    decrypted.copyTo(output)
                    output.fd.sync()
                }
            }
        } catch (error: Exception) {
            throw IOException("The backup password is incorrect or the backup is damaged.", error)
        } finally {
            key.fill(0)
            salt.fill(0)
            iv.fill(0)
        }
    }

    private fun extractArchive(archive: File, stagingDirectory: File): Map<String, File> {
        val extracted = mutableMapOf<String, File>()
        var totalBytes = 0L
        var entryCount = 0
        var manifestSeen = false
        ZipInputStream(BufferedInputStream(FileInputStream(archive))).use { zip ->
            while (true) {
                val entry = zip.nextEntry ?: break
                entryCount += 1
                if (entryCount > MAX_ARCHIVE_ENTRIES) {
                    throw IOException("The backup contains too many archive entries.")
                }
                if (entry.isDirectory) throw IOException("The backup contains an unexpected folder.")
                if (entry.name == MANIFEST_ENTRY) {
                    if (manifestSeen) throw IOException("The backup contains multiple manifests.")
                    manifestSeen = true
                    val manifest = File(stagingDirectory, MANIFEST_ENTRY)
                    FileOutputStream(manifest).use { output ->
                        totalBytes += zip.copyBoundedTo(
                            output,
                            minOf(MAX_MANIFEST_BYTES, MAX_TOTAL_FILE_BYTES - totalBytes),
                        )
                    }
                } else {
                    if (!FILE_ENTRY_PATTERN.matches(entry.name) || entry.name in extracted) {
                        throw IOException("The backup contains an invalid file entry.")
                    }
                    val file = File(stagingDirectory, "file-${extracted.size}")
                    FileOutputStream(file).use { output ->
                        val copied = zip.copyBoundedTo(output, MAX_TOTAL_FILE_BYTES - totalBytes)
                        totalBytes += copied
                    }
                    extracted[entry.name] = file
                }
                if (totalBytes > MAX_TOTAL_FILE_BYTES) {
                    throw IOException("The backup is larger than Stash can restore.")
                }
                zip.closeEntry()
            }
        }
        return extracted
    }

    private fun parseManifest(
        manifestFile: File,
        extractedFiles: Map<String, File>,
        stagingDirectory: File,
    ): BackupSnapshot {
        val root = JSONObject(manifestFile.readText(Charsets.UTF_8))
        if (root.optInt("version") != VERSION) throw IOException("This backup version is not supported.")
        val folderArray = root.optJSONArray("folders") ?: JSONArray()
        val folderNames = (0 until folderArray.length()).mapNotNull { index ->
            folderArray.optString(index).trim().takeIf { name ->
                name.length in 1..40 && name.matches(Regex("[\\p{L}\\p{N} _-]+"))
            }
        }.distinctBy(String::lowercase)
        val items = mutableListOf<LibraryItemEntity>()
        val filesByItemId = mutableMapOf<String, File>()
        val fileNamesByItemId = mutableMapOf<String, String>()
        val itemArray = root.getJSONArray("libraryItems")
        if (itemArray.length() > MAX_LIBRARY_ITEMS) throw IOException("The backup contains too many library items.")
        val usedIds = mutableSetOf<String>()
        for (index in 0 until itemArray.length()) {
            val item = itemArray.getJSONObject(index)
            val id = item.getString("id")
            if (id.isBlank() || !usedIds.add(id)) throw IOException("The backup contains duplicate item IDs.")
            val fileEntry = item.optString("fileEntry").takeUnless { it.isBlank() || it == "null" }
            if (fileEntry != null) {
                val file = extractedFiles[fileEntry] ?: throw IOException("A saved file is missing from the backup.")
                filesByItemId[id] = file
                fileNamesByItemId[id] = item.optString("fileName").takeUnless { it.isBlank() || it == "null" }
                    ?: item.getString("title")
            }
            items += LibraryItemEntity(
                id = id,
                title = item.getString("title"),
                category = item.getString("category"),
                mimeType = item.getString("mimeType"),
                savedAt = item.getLong("savedAt"),
                contentText = item.optString("contentText").takeUnless { it == "null" },
                ocrText = item.optString("ocrText").takeUnless { it.isBlank() || it == "null" },
                relativePath = null,
                byteSize = item.optLong("byteSize"),
                mode = item.optString("mode", "GENERAL"),
                deletedAt = if (item.isNull("deletedAt")) null else item.getLong("deletedAt"),
                folderName = item.optString("folderName").takeUnless { it.isBlank() || it == "null" },
                tagsJson = item.optString("tagsJson", "[]"),
                isFavorite = item.optBoolean("isFavorite", false),
                sharedItemId = if (item.isNull("sharedItemId")) null else item.optLong("sharedItemId"),
            )
        }
        val followUpArray = root.optJSONArray("avaFollowUps") ?: JSONArray()
        if (followUpArray.length() > MAX_LIBRARY_ITEMS) throw IOException("The backup contains too many Ava reminders.")
        val validItemIds = items.mapTo(mutableSetOf(), LibraryItemEntity::id)
        val followUpIds = mutableSetOf<String>()
        val avaFollowUps = (0 until followUpArray.length()).mapNotNull { index ->
            val followUp = followUpArray.getJSONObject(index)
            val id = followUp.getString("id")
            val sourceItemId = followUp.getString("sourceItemId")
            if (id.isBlank() || !followUpIds.add(id)) throw IOException("The backup contains duplicate Ava reminder IDs.")
            if (sourceItemId !in validItemIds) return@mapNotNull null
            val eventAt = followUp.optLong("eventAt")
            val remindAt = followUp.optLong("remindAt")
            if (eventAt <= 0L || remindAt <= 0L) throw IOException("The backup contains an invalid Ava reminder date.")
            AvaFollowUpEntity(
                id = id,
                sourceItemId = sourceItemId,
                sourceTitle = followUp.optString("sourceTitle"),
                eventLabel = followUp.optString("eventLabel"),
                sourceExcerpt = followUp.optString("sourceExcerpt"),
                eventAt = eventAt,
                remindAt = remindAt,
                createdAt = followUp.optLong("createdAt"),
                notifiedAt = if (followUp.isNull("notifiedAt")) null else followUp.optLong("notifiedAt"),
                updatedAt = followUp.optLong("updatedAt", followUp.optLong("createdAt")),
                deletedAt = if (followUp.isNull("deletedAt")) null else followUp.optLong("deletedAt"),
            )
        }
        val vaultArray = root.getJSONArray("vaultEntries")
        if (vaultArray.length() > MAX_VAULT_ITEMS) throw IOException("The backup contains too many Vault items.")
        val vaultIds = mutableSetOf<String>()
        val vaultEntries = (0 until vaultArray.length()).map { index ->
            val entry = vaultArray.getJSONObject(index)
            val id = entry.getString("id")
            if (id.isBlank() || !vaultIds.add(id)) throw IOException("The backup contains duplicate Vault item IDs.")
            VaultSecret(
                id = id,
                savedAt = entry.getLong("savedAt"),
                title = entry.getString("title"),
                account = entry.optString("account"),
                secret = entry.getString("secret"),
                notes = entry.optString("notes"),
            )
        }
        val referencedFiles = itemArrayFileEntries(itemArray)
        if (referencedFiles.size != filesByItemId.size) {
            throw IOException("The backup references a saved file more than once.")
        }
        if (extractedFiles.keys.any { fileEntry -> fileEntry !in referencedFiles }) {
            throw IOException("The backup contains an unreferenced file.")
        }
        val vaultConfigured = root.optBoolean("vaultConfigured")
        if (!vaultConfigured && vaultEntries.isNotEmpty()) {
            throw IOException("The backup contains Vault items without a Vault setup.")
        }
        return BackupSnapshot(
            libraryItems = items,
            folderNames = folderNames,
            vaultEntries = vaultEntries,
            avaFollowUps = avaFollowUps,
            vaultConfigured = vaultConfigured,
            filesByItemId = filesByItemId,
            fileNamesByItemId = fileNamesByItemId,
            stagingDirectory = stagingDirectory,
        )
    }

    private fun itemArrayFileEntries(items: JSONArray): Set<String> =
        (0 until items.length()).mapNotNull { index ->
            items.getJSONObject(index).optString("fileEntry").takeUnless { it.isBlank() || it == "null" }
        }.toSet()

    private fun validatePassword(password: String) {
        require(password.length >= MIN_PASSWORD_LENGTH) { "Use a backup password with at least 12 characters." }
        require(password.length <= MAX_PASSWORD_LENGTH) { "The backup password is too long." }
    }

    private fun deriveKey(password: String, salt: ByteArray): ByteArray {
        val characters = password.toCharArray()
        val spec = PBEKeySpec(characters, salt, PBKDF2_ITERATIONS, KEY_BYTES * 8)
        return try {
            SecretKeyFactory.getInstance(PBKDF2).generateSecret(spec).encoded
        } finally {
            spec.clearPassword()
            characters.fill('\u0000')
        }
    }

    private fun InputStream.copyBoundedTo(destination: OutputStream, limit: Long): Long {
        if (limit < 0L) throw IOException("The backup is larger than Stash can restore.")
        val buffer = ByteArray(COPY_BUFFER_SIZE)
        var copied = 0L
        while (true) {
            val count = read(buffer)
            if (count < 0) break
            copied += count
            if (copied > limit) throw IOException("The backup is larger than Stash can restore.")
            destination.write(buffer, 0, count)
        }
        return copied
    }

    private companion object {
        const val MAGIC = 0x5354424B
        const val VERSION = 1
        const val MANIFEST_ENTRY = "manifest.json"
        const val PBKDF2 = "PBKDF2WithHmacSHA256"
        const val AES = "AES"
        const val AES_GCM = "AES/GCM/NoPadding"
        const val PBKDF2_ITERATIONS = 600_000
        const val KEY_BYTES = 32
        const val SALT_BYTES = 16
        const val GCM_IV_BYTES = 12
        const val GCM_TAG_BITS = 128
        const val MIN_PASSWORD_LENGTH = 12
        const val MAX_PASSWORD_LENGTH = 1_024
        const val MAX_MANIFEST_BYTES = 16L * 1024L * 1024L
        const val MAX_TOTAL_FILE_BYTES = 20L * 1024L * 1024L * 1024L
        const val MAX_LIBRARY_ITEMS = 100_000
        const val MAX_VAULT_ITEMS = 10_000
        const val MAX_ARCHIVE_ENTRIES = MAX_LIBRARY_ITEMS + 1
        const val COPY_BUFFER_SIZE = 128 * 1024
        val FILE_ENTRY_PATTERN = Regex("files/[0-9]+")
    }
}
