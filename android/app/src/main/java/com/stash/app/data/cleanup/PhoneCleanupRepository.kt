package com.stash.app.data.cleanup

import android.content.Context
import android.net.Uri
import android.provider.DocumentsContract
import androidx.documentfile.provider.DocumentFile
import java.io.IOException
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

data class PhoneCleanupFile(
    val uri: String,
    val parentUri: String,
    val relativePath: String,
    val name: String,
    val mimeType: String,
    val sizeBytes: Long,
    val modifiedAt: Long,
)

data class PhoneCleanupPreview(
    val id: String,
    val treeUri: String,
    val createdAt: Long,
    val scheduledAt: Long,
    val ageDays: Int,
    val files: List<PhoneCleanupFile>,
)

data class PhoneBinEntry(
    val id: String,
    val name: String,
    val fileUri: String,
    val binParentUri: String,
    val originalParentUri: String,
    val mimeType: String,
    val sizeBytes: Long,
    val movedAt: Long,
)

data class PhoneCleanupMoveResult(val moved: Int, val skipped: Int)

/** User-authorized folder cleanup. Files are moved to a restorable folder only after approval. */
class PhoneCleanupRepository(context: Context) {
    private val appContext = context.applicationContext
    private val preferences = appContext.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    fun selectedTreeUri(): Uri? = preferences.getString(KEY_TREE_URI, null)?.let(Uri::parse)

    fun folderName(uri: Uri): String = DocumentFile.fromTreeUri(appContext, uri)?.name ?: "Selected phone folder"

    fun setSelectedTreeUri(uri: Uri) {
        preferences.edit().putString(KEY_TREE_URI, uri.toString()).apply()
    }

    fun scheduledAt(): Long = preferences.getLong(KEY_SCHEDULED_AT, 0L)

    fun scheduledAgeDays(): Int = preferences.getInt(KEY_AGE_DAYS, DEFAULT_AGE_DAYS)

    fun saveSchedule(timestamp: Long, ageDays: Int, treeUri: Uri) {
        require(timestamp > System.currentTimeMillis()) { "Choose a future date and time." }
        require(ageDays in 1..3650) { "Choose an age between 1 and 3650 days." }
        preferences.edit()
            .putLong(KEY_SCHEDULED_AT, timestamp)
            .putInt(KEY_AGE_DAYS, ageDays)
            .putString(KEY_TREE_URI, treeUri.toString())
            .apply()
    }

    fun cancelSchedule() {
        preferences.edit().remove(KEY_SCHEDULED_AT).apply()
    }

    suspend fun scanForPreview(treeUri: Uri, ageDays: Int, scheduledAt: Long): PhoneCleanupPreview =
        withContext(Dispatchers.IO) {
            require(ageDays in 1..3650)
            val root = DocumentFile.fromTreeUri(appContext, treeUri)
                ?.takeIf(DocumentFile::isDirectory)
                ?: throw IOException("Choose a folder Stash can access, then try again.")
            val cutoff = System.currentTimeMillis() - ageDays.toLong() * DAY_MILLIS
            val found = mutableListOf<PhoneCleanupFile>()
            var inspected = 0

            fun visit(directory: DocumentFile, relative: String) {
                if (inspected >= MAX_SCANNED_DOCUMENTS) return
                directory.listFiles().forEach { child ->
                    if (inspected >= MAX_SCANNED_DOCUMENTS) return@forEach
                    inspected += 1
                    val name = child.name.orEmpty()
                    if (name.isBlank() || name.startsWith('.') || name.equals(BIN_FOLDER, true)) {
                        return@forEach
                    }
                    val childPath = if (relative.isBlank()) name else "$relative/$name"
                    if (child.isDirectory) {
                        visit(child, childPath)
                    } else if (child.isFile) {
                        val modifiedAt = child.lastModified()
                        if (modifiedAt > 0L && modifiedAt <= cutoff) {
                            found += PhoneCleanupFile(
                                uri = child.uri.toString(),
                                parentUri = directory.uri.toString(),
                                relativePath = childPath,
                                name = name,
                                mimeType = child.type.orEmpty(),
                                sizeBytes = child.length().coerceAtLeast(0L),
                                modifiedAt = modifiedAt,
                            )
                        }
                    }
                }
            }

            visit(root, "")
            PhoneCleanupPreview(
                id = UUID.randomUUID().toString(),
                treeUri = treeUri.toString(),
                createdAt = System.currentTimeMillis(),
                scheduledAt = scheduledAt,
                ageDays = ageDays,
                files = found.sortedBy(PhoneCleanupFile::modifiedAt),
            )
        }

    fun savePendingPreview(preview: PhoneCleanupPreview) {
        preferences.edit().putString(KEY_PENDING_PREVIEW, encodePreview(preview).toString()).apply()
    }

    fun pendingPreview(): PhoneCleanupPreview? = preferences.getString(KEY_PENDING_PREVIEW, null)
        ?.let { raw -> runCatching { decodePreview(JSONObject(raw)) }.getOrNull() }

    fun clearPendingPreview(expectedId: String? = null): Boolean {
        val preview = pendingPreview() ?: return false
        if (expectedId != null && preview.id != expectedId) return false
        preferences.edit().remove(KEY_PENDING_PREVIEW).apply()
        return true
    }

    suspend fun approvePendingPreview(expectedId: String): PhoneCleanupMoveResult = withContext(Dispatchers.IO) {
        val preview = pendingPreview()?.takeIf { it.id == expectedId }
            ?: throw IOException("That cleanup preview has expired. Ask Ava to scan again.")
        val rootUri = Uri.parse(preview.treeUri)
        val root = DocumentFile.fromTreeUri(appContext, rootUri)
            ?.takeIf(DocumentFile::isDirectory)
            ?: throw IOException("The selected phone folder is no longer available.")
        val bin = root.listFiles().firstOrNull { it.isDirectory && it.name.equals(BIN_FOLDER, true) }
            ?: root.createDirectory(BIN_FOLDER)
            ?: throw IOException("Stash could not create its Bin inside the selected folder.")

        var moved = 0
        var skipped = 0
        preview.files.forEach { candidate ->
            val sourceUri = Uri.parse(candidate.uri)
            val source = DocumentFile.fromSingleUri(appContext, sourceUri)
            if (source?.isFile != true || source.name != candidate.name ||
                source.lastModified() != candidate.modifiedAt || source.length() != candidate.sizeBytes
            ) {
                skipped += 1
                return@forEach
            }
            val movedUri = runCatching {
                DocumentsContract.moveDocument(
                    appContext.contentResolver,
                    sourceUri,
                    Uri.parse(candidate.parentUri),
                    bin.uri,
                )
            }.getOrNull()
            if (movedUri == null) {
                skipped += 1
                return@forEach
            }

            val entryId = UUID.randomUUID().toString()
            val storedName = "$entryId--${candidate.name}"
            val renamedUri = runCatching {
                DocumentsContract.renameDocument(appContext.contentResolver, movedUri, storedName)
            }.getOrNull() ?: movedUri
            saveBinEntry(
                PhoneBinEntry(
                    id = entryId,
                    name = candidate.name,
                    fileUri = renamedUri.toString(),
                    binParentUri = bin.uri.toString(),
                    originalParentUri = candidate.parentUri,
                    mimeType = candidate.mimeType,
                    sizeBytes = candidate.sizeBytes,
                    movedAt = System.currentTimeMillis(),
                ),
            )
            moved += 1
        }
        clearPendingPreview(expectedId)
        PhoneCleanupMoveResult(moved, skipped)
    }

    fun binEntries(): List<PhoneBinEntry> = preferences.getString(KEY_BIN_ENTRIES, "[]")
        .let { raw ->
            runCatching {
                val array = JSONArray(raw)
                (0 until array.length()).mapNotNull { index ->
                    array.optJSONObject(index)?.let(::decodeBinEntry)
                }
            }.getOrDefault(emptyList())
        }

    suspend fun restoreFromPhoneBin(id: String): Boolean = withContext(Dispatchers.IO) {
        val entry = binEntries().firstOrNull { it.id == id } ?: return@withContext false
        val movedUri = runCatching {
            DocumentsContract.moveDocument(
                appContext.contentResolver,
                Uri.parse(entry.fileUri),
                Uri.parse(entry.binParentUri),
                Uri.parse(entry.originalParentUri),
            )
        }.getOrNull() ?: return@withContext false
        runCatching {
            DocumentsContract.renameDocument(appContext.contentResolver, movedUri, entry.name)
        }
        removeBinEntry(id)
        true
    }

    suspend fun permanentlyDeleteFromPhoneBin(id: String): Boolean = withContext(Dispatchers.IO) {
        val entry = binEntries().firstOrNull { it.id == id } ?: return@withContext false
        val deleted = runCatching {
            DocumentsContract.deleteDocument(appContext.contentResolver, Uri.parse(entry.fileUri))
        }.getOrDefault(false)
        if (deleted) removeBinEntry(id)
        deleted
    }

    private fun saveBinEntry(entry: PhoneBinEntry) {
        val entries = binEntries().filterNot { it.id == entry.id } + entry
        preferences.edit().putString(
            KEY_BIN_ENTRIES,
            JSONArray().apply { entries.forEach { put(encodeBinEntry(it)) } }.toString(),
        ).apply()
    }

    private fun removeBinEntry(id: String) {
        val entries = binEntries().filterNot { it.id == id }
        preferences.edit().putString(
            KEY_BIN_ENTRIES,
            JSONArray().apply { entries.forEach { put(encodeBinEntry(it)) } }.toString(),
        ).apply()
    }

    private fun encodePreview(preview: PhoneCleanupPreview): JSONObject = JSONObject()
        .put("id", preview.id)
        .put("treeUri", preview.treeUri)
        .put("createdAt", preview.createdAt)
        .put("scheduledAt", preview.scheduledAt)
        .put("ageDays", preview.ageDays)
        .put("files", JSONArray().apply { preview.files.forEach { put(encodeFile(it)) } })

    private fun decodePreview(json: JSONObject): PhoneCleanupPreview {
        val files = json.optJSONArray("files") ?: JSONArray()
        return PhoneCleanupPreview(
            id = json.getString("id"),
            treeUri = json.getString("treeUri"),
            createdAt = json.optLong("createdAt"),
            scheduledAt = json.optLong("scheduledAt"),
            ageDays = json.optInt("ageDays", DEFAULT_AGE_DAYS),
            files = (0 until files.length()).mapNotNull { files.optJSONObject(it)?.let(::decodeFile) },
        )
    }

    private fun encodeFile(file: PhoneCleanupFile): JSONObject = JSONObject()
        .put("uri", file.uri)
        .put("parentUri", file.parentUri)
        .put("relativePath", file.relativePath)
        .put("name", file.name)
        .put("mimeType", file.mimeType)
        .put("sizeBytes", file.sizeBytes)
        .put("modifiedAt", file.modifiedAt)

    private fun decodeFile(json: JSONObject): PhoneCleanupFile = PhoneCleanupFile(
        uri = json.getString("uri"),
        parentUri = json.getString("parentUri"),
        relativePath = json.optString("relativePath"),
        name = json.getString("name"),
        mimeType = json.optString("mimeType"),
        sizeBytes = json.optLong("sizeBytes"),
        modifiedAt = json.optLong("modifiedAt"),
    )

    private fun encodeBinEntry(entry: PhoneBinEntry): JSONObject = JSONObject()
        .put("id", entry.id)
        .put("name", entry.name)
        .put("fileUri", entry.fileUri)
        .put("binParentUri", entry.binParentUri)
        .put("originalParentUri", entry.originalParentUri)
        .put("mimeType", entry.mimeType)
        .put("sizeBytes", entry.sizeBytes)
        .put("movedAt", entry.movedAt)

    private fun decodeBinEntry(json: JSONObject): PhoneBinEntry = PhoneBinEntry(
        id = json.getString("id"),
        name = json.getString("name"),
        fileUri = json.getString("fileUri"),
        binParentUri = json.getString("binParentUri"),
        originalParentUri = json.getString("originalParentUri"),
        mimeType = json.optString("mimeType"),
        sizeBytes = json.optLong("sizeBytes"),
        movedAt = json.optLong("movedAt"),
    )

    private companion object {
        const val PREFERENCES = "stash_phone_cleanup"
        const val KEY_TREE_URI = "selected_tree_uri"
        const val KEY_AGE_DAYS = "cleanup_age_days"
        const val KEY_SCHEDULED_AT = "cleanup_scheduled_at"
        const val KEY_PENDING_PREVIEW = "cleanup_pending_preview"
        const val KEY_BIN_ENTRIES = "phone_bin_entries"
        const val BIN_FOLDER = "Stash Bin"
        const val DEFAULT_AGE_DAYS = 30
        const val MAX_SCANNED_DOCUMENTS = 5_000
        const val DAY_MILLIS = 24L * 60L * 60L * 1000L
    }
}
