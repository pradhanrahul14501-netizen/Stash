package com.stash.app.data.storage

import android.content.ContentResolver
import android.net.Uri
import android.provider.OpenableColumns
import android.webkit.MimeTypeMap
import java.io.File
import java.io.InputStream
import java.io.IOException
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.util.UUID

data class StoredFile(
    val relativePath: String,
    val displayName: String,
    val mimeType: String,
    val byteSize: Long,
)

class PrivateItemStore(private val filesDirectory: File) {
    @Throws(IOException::class)
    fun copyFrom(
        resolver: ContentResolver,
        uri: Uri,
    ): StoredFile {
        val sourceName = queryDisplayName(resolver, uri)
            ?: uri.lastPathSegment?.substringAfterLast('/')
            ?: "shared_file"
        val mimeType = resolver.getType(uri)
            ?.takeIf(String::isNotBlank)
            ?: MimeTypeMap.getSingleton()
                .getMimeTypeFromExtension(sourceName.substringAfterLast('.', "").lowercase())
            ?: "application/octet-stream"
        val safeName = sourceName
            .replace(Regex("[^A-Za-z0-9._-]"), "_")
            .trim('.', '_')
            .take(100)
            .ifBlank { "shared_file" }
        val mediaDirectory = File(filesDirectory, "library").apply {
            if (!exists() && !mkdirs()) throw IOException("Could not create Stash storage.")
        }
        val id = UUID.randomUUID().toString()
        val destination = File(mediaDirectory, "$id-$safeName")
        try {
            val input = resolver.openInputStream(uri)
                ?: throw IOException("The selected item could not be opened.")
            input.use { source ->
                destination.outputStream().use { output -> source.copyTo(output) }
            }
        } catch (error: Exception) {
            destination.delete()
            if (error is IOException) throw error
            throw IOException("The selected item could not be copied.", error)
        }
        return StoredFile(
            relativePath = "library/${destination.name}",
            displayName = sourceName,
            mimeType = mimeType,
            byteSize = destination.length(),
        )
    }

    @Throws(IOException::class)
    fun copyFrom(input: InputStream, displayName: String, mimeType: String): StoredFile {
        val safeName = displayName
            .replace(Regex("[^A-Za-z0-9._-]"), "_")
            .trim('.', '_')
            .take(100)
            .ifBlank { "shared_file" }
        val mediaDirectory = File(filesDirectory, "library").apply {
            if (!exists() && !mkdirs()) throw IOException("Could not create Stash storage.")
        }.canonicalFile
        val destination = File(mediaDirectory, "${UUID.randomUUID()}-$safeName")
        try {
            destination.outputStream().use { output -> input.copyTo(output) }
        } catch (error: Exception) {
            destination.delete()
            if (error is IOException) throw error
            throw IOException("The shared file could not be copied into Stash.", error)
        }
        if (destination.length() <= 0L) {
            destination.delete()
            throw IOException("The shared file was empty.")
        }
        return StoredFile(
            relativePath = "library/${destination.name}",
            displayName = displayName,
            mimeType = mimeType.ifBlank { "application/octet-stream" },
            byteSize = destination.length(),
        )
    }

    @Throws(IOException::class)
    fun adoptDownloadedVideo(source: File, displayName: String): StoredFile {
        val stagingRoot = File(filesDirectory, "video-downloads").canonicalFile
        val sourceFile = source.canonicalFile
        if (sourceFile.parentFile?.parentFile != stagingRoot || !sourceFile.isFile) {
            throw IOException("The downloaded video is not in Stash's temporary folder.")
        }
        if (!sourceFile.name.endsWith(".mp4", ignoreCase = true) || sourceFile.length() <= 0L) {
            throw IOException("The downloaded video is not a valid MP4 file.")
        }

        val mediaDirectory = File(filesDirectory, "library").apply {
            if (!exists() && !mkdirs()) throw IOException("Could not create Stash storage.")
        }.canonicalFile
        val safeName = displayName
            .replace(Regex("[^A-Za-z0-9._-]"), "_")
            .trim('.', '_')
            .take(100)
            .ifBlank { "video" }
            .let { if (it.endsWith(".mp4", ignoreCase = true)) it else "$it.mp4" }
        val destination = File(mediaDirectory, "${UUID.randomUUID()}-$safeName")
        try {
            Files.move(sourceFile.toPath(), destination.toPath())
        } catch (error: Exception) {
            throw IOException("Could not save the downloaded video to Stash.", error)
        }

        return StoredFile(
            relativePath = "library/${destination.name}",
            displayName = safeName,
            mimeType = "video/mp4",
            byteSize = destination.length(),
        )
    }

    @Throws(IOException::class)
    fun adoptRestoredFile(source: File, displayName: String): StoredFile {
        if (!source.isFile) throw IOException("A file in the backup could not be restored.")
        val mediaDirectory = File(filesDirectory, "library").apply {
            if (!exists() && !mkdirs()) throw IOException("Could not create Stash storage.")
        }.canonicalFile
        val safeName = displayName
            .replace(Regex("[^A-Za-z0-9._-]"), "_")
            .trim('.', '_')
            .take(100)
            .ifBlank { "restored_file" }
        val destination = File(mediaDirectory, "${UUID.randomUUID()}-$safeName")
        try {
            Files.copy(source.toPath(), destination.toPath(), StandardCopyOption.REPLACE_EXISTING)
        } catch (error: Exception) {
            destination.delete()
            throw IOException("Could not restore a saved file.", error)
        }
        return StoredFile(
            relativePath = "library/${destination.name}",
            displayName = safeName,
            mimeType = MimeTypeMap.getSingleton()
                .getMimeTypeFromExtension(safeName.substringAfterLast('.', "").lowercase())
                ?: "application/octet-stream",
            byteSize = destination.length(),
        )
    }

    fun fileFor(relativePath: String?): File? {
        if (relativePath.isNullOrBlank()) return null
        val root = File(filesDirectory, "library").canonicalFile
        val target = File(filesDirectory, relativePath).canonicalFile
        return target.takeIf { it.parentFile == root && it.isFile }
    }

    fun appDataSizeBytes(): Long {
        val root = filesDirectory.parentFile ?: return 0L
        return root.walkTopDown().filter { it.isFile }.sumOf { it.length() }
    }

    fun delete(relativePath: String?): Boolean {
        if (relativePath.isNullOrBlank()) return true
        val root = File(filesDirectory, "library").canonicalFile
        val target = File(filesDirectory, relativePath).canonicalFile
        if (target.parentFile != root) return false
        return !target.exists() || target.delete()
    }

    private fun queryDisplayName(resolver: ContentResolver, uri: Uri): String? =
        resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
            if (cursor.moveToFirst()) {
                val column = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                if (column >= 0) cursor.getString(column) else null
            } else {
                null
            }
        }
}
