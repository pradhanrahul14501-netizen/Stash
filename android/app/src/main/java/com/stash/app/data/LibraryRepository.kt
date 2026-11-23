package com.stash.app.data

import android.content.ContentResolver
import android.net.Uri
import com.stash.app.data.local.LibraryFolderEntity
import com.stash.app.data.local.LibraryItemDao
import com.stash.app.data.local.LibraryItemEntity
import com.stash.app.data.storage.PrivateItemStore
import java.io.BufferedInputStream
import java.io.File
import java.io.FileInputStream
import java.io.InputStream
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.util.Locale
import java.util.UUID
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.withContext
import org.json.JSONArray

data class IncomingShare(
    val text: String? = null,
    val uris: List<Uri> = emptyList(),
)

data class BinEmptyResult(
    val removedCount: Int,
    val failedCount: Int,
)

data class StoredItemSize(
    val title: String,
    val category: String,
    val bytes: Long,
    val isInBin: Boolean,
)

data class LibraryStorageOverview(
    val appDataBytes: Long,
    val libraryBytes: Long,
    val binBytes: Long,
    val categoryBytes: Map<String, Long>,
    val largestItems: List<StoredItemSize>,
    val missingFileCount: Int,
) {
    val totalBytes: Long get() = libraryBytes + binBytes
}

data class SensitiveFinding(val title: String, val types: List<String>)

data class StorageAuditReport(
    val checkedAt: Long,
    val emptyFiles: List<String>,
    val corruptFiles: List<String>,
    val missingFiles: List<String>,
    val duplicateGroups: List<List<String>>,
    val sensitiveFindings: List<SensitiveFinding>,
    val largestItems: List<StoredItemSize>,
    val oldestItems: List<String>,
    val newestItems: List<String>,
)

class LibraryRepository(
    private val contentResolver: ContentResolver,
    private val dao: LibraryItemDao,
    private val privateItemStore: PrivateItemStore,
    private val textIndexer: LibraryTextIndexer = LibraryTextIndexer(),
) {
    fun observeItems(): Flow<List<LibraryItemEntity>> = dao.observeAll()

    fun observeBin(): Flow<List<LibraryItemEntity>> = dao.observeBin()

    fun observeFolders(): Flow<List<LibraryFolderEntity>> = dao.observeFolders()

    suspend fun folders(): List<LibraryFolderEntity> = withContext(Dispatchers.IO) {
        dao.getFolders()
    }

    suspend fun createFolder(rawName: String): String = withContext(Dispatchers.IO) {
        val name = rawName.trim().replace(Regex("\\s+"), " ")
        require(name.length in 1..40 && name.matches(Regex("[\\p{L}\\p{N} _-]+"))) {
            "Use 1–40 letters, numbers, spaces, hyphens, or underscores for a folder name."
        }
        val existing = dao.getFolders().firstOrNull { it.name.equals(name, ignoreCase = true) }
        if (existing != null) return@withContext existing.name
        dao.createFolder(LibraryFolderEntity(name, System.currentTimeMillis()))
        name
    }

    suspend fun deleteFolderIfEmpty(name: String): Boolean = withContext(Dispatchers.IO) {
        dao.deleteFolderIfEmpty(name) > 0
    }

    suspend fun restoreOrganization(items: List<LibraryItemEntity>) = withContext(Dispatchers.IO) {
        items.forEach { item ->
            dao.restoreOrganization(item.id, item.folderName, item.tagsJson, item.isFavorite)
        }
    }

    suspend fun updateFromShared(
        localId: String,
        remoteId: Long,
        folderName: String?,
        tags: List<String>,
        favorite: Boolean,
    ) = withContext(Dispatchers.IO) {
        if (folderName != null) createFolder(folderName)
        val safeTags = tags.map(String::trim).filter(String::isNotBlank)
            .map { it.take(24) }.distinctBy(String::lowercase).take(12)
        dao.updateSharedMetadata(localId, folderName, JSONArray(safeTags).toString(), favorite, remoteId)
    }

    suspend fun importFromShared(
        requestedLocalId: String?,
        remoteId: Long,
        title: String,
        category: String,
        mimeType: String,
        contentText: String,
        savedAt: Long,
        folderName: String?,
        tags: List<String>,
        favorite: Boolean,
        fileInput: InputStream?,
    ): LibraryItemEntity = withContext(Dispatchers.IO) {
        val candidateId = requestedLocalId?.takeIf { it.matches(Regex("[A-Za-z0-9._-]{1,128}")) }
            ?: UUID.randomUUID().toString()
        val existing = dao.getItem(candidateId)
        if (existing != null) {
            dao.setSharedItemId(existing.id, remoteId)
            return@withContext existing.copy(sharedItemId = remoteId)
        }

        if (folderName != null) createFolder(folderName)
        val stored = fileInput?.let { input ->
            privateItemStore.copyFrom(input, title, mimeType)
        }
        val safeTags = tags.map(String::trim).filter(String::isNotBlank)
            .map { it.take(24) }.distinctBy(String::lowercase).take(12)
        val item = LibraryItemEntity(
            id = candidateId,
            title = title.take(180).ifBlank { "Shared item" },
            category = category.uppercase(Locale.ROOT),
            mimeType = mimeType.ifBlank { "text/plain" },
            savedAt = savedAt.takeIf { it > 0L } ?: System.currentTimeMillis(),
            contentText = contentText.takeIf(String::isNotBlank),
            relativePath = stored?.relativePath,
            byteSize = stored?.byteSize ?: 0L,
            mode = modeFor(mimeType, title, contentText),
            folderName = folderName,
            tagsJson = JSONArray(safeTags).toString(),
            isFavorite = favorite,
            sharedItemId = remoteId,
        )
        try {
            dao.insertAll(listOf(item))
        } catch (error: Exception) {
            stored?.relativePath?.let(privateItemStore::delete)
            throw error
        }
        if (stored != null && textIndexer.isSupported(item.mimeType, item.title)) {
            val ocr = extractTextOrBlank(
                privateItemStore.fileFor(stored.relativePath) ?: return@withContext item,
                item.mimeType,
                item.title,
            )
            updateOcrTextSafely(item.id, ocr)
        }
        item
    }

    suspend fun moveToFolder(ids: List<String>, folderName: String?): Int = withContext(Dispatchers.IO) {
        if (folderName != null) {
            require(dao.getFolders().any { it.name == folderName }) { "That Stash folder no longer exists." }
        }
        dao.moveToFolder(ids.distinct(), folderName)
    }

    suspend fun updateTags(id: String, rawTags: List<String>) = withContext(Dispatchers.IO) {
        val tags = rawTags.map(String::trim).filter(String::isNotBlank)
            .map { it.take(24) }.distinctBy(String::lowercase).take(12)
        dao.updateTags(id, JSONArray(tags).toString())
    }

    suspend fun setFavorite(id: String, favorite: Boolean) = withContext(Dispatchers.IO) {
        dao.setFavorite(id, favorite)
    }

    suspend fun allItemsForBackup(): List<LibraryItemEntity> = withContext(Dispatchers.IO) {
        dao.getAllForBackup()
    }

    suspend fun setSharedItemId(id: String, sharedItemId: Long?) = withContext(Dispatchers.IO) {
        dao.setSharedItemId(id, sharedItemId)
    }

    suspend fun folderNamesForBackup(): List<String> = withContext(Dispatchers.IO) {
        dao.getFolders().map(LibraryFolderEntity::name)
    }

    suspend fun storageOverview(): LibraryStorageOverview = withContext(Dispatchers.IO) {
        val sizes = mutableListOf<StoredItemSize>()
        var missingFileCount = 0
        dao.getAllForBackup().forEach { item ->
            if (item.relativePath.isNullOrBlank()) return@forEach
            val file = privateItemStore.fileFor(item.relativePath)
            if (file == null) {
                missingFileCount += 1
                return@forEach
            }
            sizes += StoredItemSize(
                title = item.title,
                category = item.category,
                bytes = file.length(),
                isInBin = item.deletedAt != null,
            )
        }
        val libraryBytes = sizes.filterNot(StoredItemSize::isInBin).sumOf(StoredItemSize::bytes)
        val binBytes = sizes.filter(StoredItemSize::isInBin).sumOf(StoredItemSize::bytes)
        LibraryStorageOverview(
            appDataBytes = privateItemStore.appDataSizeBytes(),
            libraryBytes = libraryBytes,
            binBytes = binBytes,
            categoryBytes = sizes.groupBy(StoredItemSize::category)
                .mapValues { (_, rows) -> rows.sumOf(StoredItemSize::bytes) },
            largestItems = sizes.sortedByDescending(StoredItemSize::bytes).take(5),
            missingFileCount = missingFileCount,
        )
    }

    suspend fun storageAudit(): StorageAuditReport = withContext(Dispatchers.IO) {
        val items = dao.getAllForBackup().filter { it.deletedAt == null }
        val empty = mutableListOf<String>()
        val corrupt = mutableListOf<String>()
        val missing = mutableListOf<String>()
        val hashes = mutableMapOf<String, MutableList<String>>()
        val sensitive = mutableListOf<SensitiveFinding>()
        val sizes = mutableListOf<StoredItemSize>()

        items.forEach { item ->
            val text = listOfNotNull(item.contentText, item.ocrText).joinToString("\n")
            val sensitiveTypes = sensitiveTypes(text)
            if (sensitiveTypes.isNotEmpty()) sensitive += SensitiveFinding(item.title, sensitiveTypes)

            val file = privateItemStore.fileFor(item.relativePath)
            if (!item.relativePath.isNullOrBlank() && file == null) {
                missing += item.title
                return@forEach
            }
            if (file != null) {
                sizes += StoredItemSize(item.title, item.category, file.length(), false)
                if (file.length() == 0L) empty += item.title
                if (isCorruptFile(file, item.mimeType, item.title)) corrupt += item.title
                hashes.getOrPut(sha256(file)) { mutableListOf() }.add(item.title)
            } else if (text.isNotBlank()) {
                val hash = MessageDigest.getInstance("SHA-256")
                    .digest(text.toByteArray(StandardCharsets.UTF_8)).toHex()
                hashes.getOrPut(hash) { mutableListOf() }.add(item.title)
            }
        }

        StorageAuditReport(
            checkedAt = System.currentTimeMillis(),
            emptyFiles = empty.distinct(),
            corruptFiles = corrupt.distinct(),
            missingFiles = missing.distinct(),
            duplicateGroups = hashes.values.filter { it.size > 1 }.map { it.distinct() },
            sensitiveFindings = sensitive,
            largestItems = sizes.sortedByDescending(StoredItemSize::bytes).take(5),
            oldestItems = items.sortedBy(LibraryItemEntity::savedAt).take(5).map(LibraryItemEntity::title),
            newestItems = items.sortedByDescending(LibraryItemEntity::savedAt).take(5).map(LibraryItemEntity::title),
        )
    }

    suspend fun readableTextForAva(item: LibraryItemEntity): String = withContext(Dispatchers.IO) {
        val stored = listOfNotNull(item.contentText, item.ocrText)
            .filter(String::isNotBlank).joinToString("\n\n")
        if (stored.isNotBlank()) return@withContext stored.take(MAX_AVA_DOCUMENT_CHARS)
        val file = privateItemStore.fileFor(item.relativePath) ?: return@withContext ""
        if (item.mimeType.startsWith("text/") || item.title.substringAfterLast('.', "").lowercase() in TEXT_EXTENSIONS) {
            val decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
            return@withContext runCatching {
                FileInputStream(file).use { input ->
                    val bytes = input.readNBytes(MAX_AVA_DOCUMENT_CHARS)
                    decoder.decode(ByteBuffer.wrap(bytes)).toString()
                }
            }.getOrDefault("")
        }
        if (textIndexer.isSupported(item.mimeType, item.title)) {
            return@withContext runCatching { textIndexer.extract(file, item.mimeType, item.title) }
                .getOrDefault("").take(MAX_AVA_DOCUMENT_CHARS)
        }
        ""
    }

    suspend fun indexExistingImagesAndPdfs() = withContext(Dispatchers.IO) {
        dao.getAllForBackup().forEach { item ->
            if (item.ocrText != null || !textIndexer.isSupported(item.mimeType, item.title)) {
                return@forEach
            }
            val text = privateItemStore.fileFor(item.relativePath)?.let { file ->
                extractTextOrBlank(file, item.mimeType, item.title)
            }.orEmpty()
            updateOcrTextSafely(item.id, text)
        }
    }

    suspend fun isEmpty(): Boolean = withContext(Dispatchers.IO) {
        dao.countAll() == 0
    }

    suspend fun restoreFromBackup(
        items: List<LibraryItemEntity>,
        filesByItemId: Map<String, File>,
        fileNamesByItemId: Map<String, String>,
        folderNames: List<String> = emptyList(),
    ): List<String> = withContext(Dispatchers.IO) {
        val createdPaths = mutableListOf<String>()
        val createdFolders = mutableListOf<String>()
        try {
            folderNames.forEach { name ->
                val safeName = name.trim().replace(Regex("\\s+"), " ")
                if (safeName.length in 1..40 && safeName.matches(Regex("[\\p{L}\\p{N} _-]+"))) {
                    dao.createFolder(LibraryFolderEntity(safeName, System.currentTimeMillis()))
                    createdFolders += safeName
                }
            }
            val restoredItems = items.map { item ->
                val source = filesByItemId[item.id]
                if (source == null) {
                    item
                } else {
                    val stored = privateItemStore.adoptRestoredFile(
                        source,
                        fileNamesByItemId[item.id] ?: item.title,
                    )
                    createdPaths += stored.relativePath
                    item.copy(
                        relativePath = stored.relativePath,
                        byteSize = stored.byteSize,
                    )
                }
            }
            dao.insertAll(restoredItems)
            restoredItems.map(LibraryItemEntity::id)
        } catch (error: Exception) {
            createdPaths.forEach(privateItemStore::delete)
            for (folderName in createdFolders) dao.deleteFolder(folderName)
            throw error
        }
    }

    suspend fun rollbackRestoredItems(ids: List<String>, folderNames: List<String> = emptyList()) = withContext(Dispatchers.IO) {
        if (ids.isNotEmpty()) {
            val storedItems = dao.getAllForBackup().filter { it.id in ids }
            storedItems.forEach { privateItemStore.delete(it.relativePath) }
            dao.deleteByIds(ids)
        }
        folderNames.forEach { dao.deleteFolder(it) }
    }

    suspend fun moveToBin(id: String) = withContext(Dispatchers.IO) {
        dao.moveToBin(id, System.currentTimeMillis())
    }

    suspend fun moveToBin(ids: List<String>): Int = withContext(Dispatchers.IO) {
        val distinctIds = ids.distinct()
        if (distinctIds.isEmpty()) return@withContext 0
        dao.moveItemsToBin(distinctIds, System.currentTimeMillis())
    }

    suspend fun restoreFromBin(id: String) = withContext(Dispatchers.IO) {
        dao.restoreFromBin(id)
    }

    suspend fun emptyBin(): BinEmptyResult = withContext(Dispatchers.IO) {
        var deletedCount = 0
        var failedCount = 0
        dao.getBinItems().forEach { item ->
            val fileRemoved = runCatching { privateItemStore.delete(item.relativePath) }
                .getOrDefault(false)
            if (!fileRemoved) {
                failedCount += 1
                return@forEach
            }
            runCatching { dao.deleteBinnedItem(item.id) }
                .onSuccess { deletedCount += 1 }
                .onFailure { failedCount += 1 }
        }
        BinEmptyResult(deletedCount, failedCount)
    }

    suspend fun importShare(share: IncomingShare): Int = withContext(Dispatchers.IO) {
        val text = share.text?.trim()?.takeIf(String::isNotEmpty)
        val importedFiles = mutableListOf<String>()
        val rows = try {
            val rows = share.uris.distinct().map { uri ->
                val storedFile = privateItemStore.copyFrom(contentResolver, uri)
                importedFiles += storedFile.relativePath
                LibraryItemEntity(
                    id = UUID.randomUUID().toString(),
                    title = storedFile.displayName,
                    category = categoryFor(storedFile.mimeType, storedFile.displayName),
                    mimeType = storedFile.mimeType,
                    savedAt = System.currentTimeMillis(),
                    contentText = text,
                    relativePath = storedFile.relativePath,
                    byteSize = storedFile.byteSize,
                    mode = modeFor(storedFile.mimeType, storedFile.displayName, text),
                )
            }.toMutableList()

            if (rows.isEmpty() && text != null) {
                val isLink = URL_PATTERN.matches(text)
                rows += LibraryItemEntity(
                    id = UUID.randomUUID().toString(),
                    title = if (isLink) {
                        "Saved link"
                    } else {
                        text.lineSequence().firstOrNull(String::isNotBlank)?.take(100) ?: "Text copy"
                    },
                    category = if (isLink) "LINK" else "TEXT",
                    mimeType = "text/plain",
                    savedAt = System.currentTimeMillis(),
                    contentText = text,
                    mode = modeFor("text/plain", "", text),
                )
            }

            if (rows.isEmpty()) throw IllegalArgumentException("Nothing was shared with Stash.")
            dao.insertAll(rows)
            rows
        } catch (error: Exception) {
            importedFiles.forEach { path -> privateItemStore.delete(path) }
            throw error
        }

        rows.forEach { item ->
            if (!textIndexer.isSupported(item.mimeType, item.title)) return@forEach
            val indexedText = privateItemStore.fileFor(item.relativePath)?.let { file ->
                extractTextOrBlank(file, item.mimeType, item.title)
            }.orEmpty()
            updateOcrTextSafely(item.id, indexedText)
        }
        rows.size
    }

    suspend fun importDownloadedVideo(
        source: File,
        title: String,
        sourceUrl: String,
    ): LibraryItemEntity = withContext(Dispatchers.IO) {
        val storedFile = privateItemStore.adoptDownloadedVideo(source, "$title.mp4")
        val item = LibraryItemEntity(
            id = UUID.randomUUID().toString(),
            title = storedFile.displayName.removeSuffix(".mp4"),
            category = "VIDEO",
            mimeType = "video/mp4",
            savedAt = System.currentTimeMillis(),
            contentText = sourceUrl,
            relativePath = storedFile.relativePath,
            byteSize = storedFile.byteSize,
            mode = "EDITOR",
        )
        try {
            dao.insertAll(listOf(item))
            item
        } catch (error: Exception) {
            privateItemStore.delete(storedFile.relativePath)
            throw error
        }
    }

    fun fileFor(item: LibraryItemEntity): File? = privateItemStore.fileFor(item.relativePath)

    private suspend fun extractTextOrBlank(file: File, mimeType: String, title: String): String =
        try {
            textIndexer.extract(file, mimeType, title)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: Exception) {
            ""
        }

    private suspend fun updateOcrTextSafely(id: String, text: String) {
        try {
            dao.updateOcrText(id, text)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: Exception) {
            // OCR is an optional search aid; keep imported files even if indexing cannot be saved.
        }
    }

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        BufferedInputStream(FileInputStream(file)).use { input ->
            val buffer = ByteArray(64 * 1024)
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                digest.update(buffer, 0, count)
            }
        }
        return digest.digest().toHex()
    }

    private fun ByteArray.toHex(): String = joinToString("") { "%02x".format(it) }

    private fun isCorruptFile(file: File, mimeType: String, title: String): Boolean = try {
        val extension = title.substringAfterLast('.', "").lowercase()
        when {
            mimeType.equals("application/pdf", true) || extension == "pdf" -> {
                val header = ByteArray(5)
                FileInputStream(file).use { it.read(header) }
                String(header, StandardCharsets.US_ASCII) != "%PDF-"
            }
            mimeType.equals("image/png", true) || extension == "png" -> {
                val expected = byteArrayOf(0x89.toByte(), 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a)
                val actual = ByteArray(expected.size)
                FileInputStream(file).use { it.read(actual) }
                !actual.contentEquals(expected)
            }
            mimeType.equals("image/jpeg", true) || extension in setOf("jpg", "jpeg") -> {
                val header = ByteArray(2)
                FileInputStream(file).use { it.read(header) }
                !header.contentEquals(byteArrayOf(0xff.toByte(), 0xd8.toByte()))
            }
            mimeType.startsWith("text/", true) -> {
                val decoder = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                FileInputStream(file).use { input ->
                    decoder.decode(ByteBuffer.wrap(input.readNBytes(64 * 1024)))
                }
                false
            }
            else -> false
        }
    } catch (_: Exception) {
        true
    }

    private fun sensitiveTypes(text: String): List<String> = buildList {
        if (Regex("(?i)\\b(password|passcode|secret|api[_ -]?key)\\s*[:=]").containsMatchIn(text)) add("Password or key")
        if (Regex("-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----").containsMatchIn(text)) add("Private key")
        if (Regex("(?<!\\d)(?:\\d[ -]?){13,19}(?!\\d)").containsMatchIn(text)) add("Possible payment-card number")
        if (Regex("(?i)\\b(ssn|social security number)\\s*[:=]").containsMatchIn(text)) add("Government identifier")
    }

    private fun categoryFor(mimeType: String, name: String): String = when {
        mimeType.startsWith("image/", ignoreCase = true) -> "IMAGE"
        mimeType.startsWith("audio/", ignoreCase = true) -> "AUDIO"
        mimeType.startsWith("video/", ignoreCase = true) -> "VIDEO"
        mimeType.startsWith("text/", ignoreCase = true) ||
            name.substringAfterLast('.', "").lowercase() in TEXT_EXTENSIONS -> "TEXT"
        else -> "FILE"
    }

    private fun modeFor(mimeType: String, name: String, text: String?): String {
        val extension = name.substringAfterLast('.', "").lowercase()
        if (
            mimeType.startsWith("image/", ignoreCase = true) ||
            mimeType.startsWith("audio/", ignoreCase = true) ||
            mimeType.startsWith("video/", ignoreCase = true) ||
            extension in MEDIA_EXTENSIONS
        ) {
            return "EDITOR"
        }

        val content = text.orEmpty()
        if (extension in CODE_EXTENSIONS || CODE_SYNTAX.containsMatchIn(content)) {
            return "DEVELOPER"
        }
        if (STUDY_TERMS.containsMatchIn("$name\n$content")) return "STUDENT"
        return "GENERAL"
    }

    private companion object {
        const val MAX_AVA_DOCUMENT_CHARS = 24_000
        val URL_PATTERN = Regex("https?://\\S+", RegexOption.IGNORE_CASE)
        val TEXT_EXTENSIONS = setOf("txt", "md", "csv", "json", "xml", "log", "yaml", "yml")
        val MEDIA_EXTENSIONS = setOf(
            "png", "jpg", "jpeg", "gif", "webp", "bmp", "heic", "svg",
            "mp3", "m4a", "wav", "ogg", "flac", "aac",
            "mp4", "m4v", "mov", "webm", "mkv", "avi", "3gp",
        )
        val CODE_EXTENSIONS = setOf(
            "c", "h", "cc", "cpp", "cs", "go", "java", "js", "jsx", "kt", "kts",
            "php", "py", "rb", "rs", "sh", "swift", "ts", "tsx", "sql", "html",
            "css", "scss", "json", "xml", "yaml", "yml", "toml",
        )
        val CODE_SYNTAX = Regex(
            "(?m)^\\s*(?:fun|class|def|function|const|let|var|import|package|#include|return)\\b|=>",
        )
        val STUDY_TERMS = Regex(
            "\\b(?:study|studies|studying|student|students|exam|homework|assignment|lecture|chapter|notes|syllabus|quiz|revision|lesson|formula|textbook|question paper)\\b",
            RegexOption.IGNORE_CASE,
        )
    }
}
