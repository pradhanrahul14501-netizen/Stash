package com.stash.app.data.video

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.core.content.FileProvider
import com.stash.app.data.local.LibraryItemEntity
import com.stash.app.data.storage.PrivateItemStore
import java.io.File
import java.io.IOException
import java.net.URI

class VideoClipboard(
    private val context: Context,
    private val privateItemStore: PrivateItemStore,
) {
    fun copyVideo(item: LibraryItemEntity) {
        val uri = uriFor(item)
        val clip = ClipData.newUri(context.contentResolver, item.title, uri)
        val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        clipboard.setPrimaryClip(clip)
    }

    fun shareIntent(item: LibraryItemEntity): Intent {
        val uri = uriFor(item)
        return Intent(Intent.ACTION_SEND).apply {
            type = context.contentResolver.getType(uri) ?: "video/mp4"
            putExtra(Intent.EXTRA_STREAM, uri)
            clipData = ClipData.newUri(context.contentResolver, item.title, uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
    }

    fun copyText(item: LibraryItemEntity) {
        val text = item.contentText?.takeIf(String::isNotBlank)
            ?: throw IOException("This item does not contain text to copy.")
        val clip = ClipData.newPlainText(item.title, text)
        val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        clipboard.setPrimaryClip(clip)
    }

    fun openIntent(item: LibraryItemEntity): Intent {
        if (item.category.equals("LINK", ignoreCase = true)) {
            val link = item.contentText?.trim()
                ?: throw IOException("This saved link is empty.")
            val parsed = runCatching { URI(link) }.getOrNull()
                ?: throw IOException("This saved link is invalid.")
            if (!parsed.scheme.equals("https", ignoreCase = true) &&
                !parsed.scheme.equals("http", ignoreCase = true) ||
                parsed.host.isNullOrBlank() || parsed.userInfo != null
            ) {
                throw IOException("Only ordinary web links can be opened from Stash.")
            }
            return Intent(Intent.ACTION_VIEW, Uri.parse(parsed.toASCIIString()))
        }

        val file = privateItemStore.fileFor(item.relativePath)
            ?: throw IOException("The saved file is no longer available.")
        val uri = uriForFile(file)
        return Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, item.mimeType.ifBlank { "*/*" })
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
    }

    fun shareItemIntent(item: LibraryItemEntity): Intent {
        if (item.relativePath.isNullOrBlank()) {
            val text = item.contentText?.takeIf(String::isNotBlank)
                ?: throw IOException("This item does not contain anything to share.")
            return Intent(Intent.ACTION_SEND).apply {
                type = "text/plain"
                putExtra(Intent.EXTRA_TEXT, text)
            }
        }

        val file = privateItemStore.fileFor(item.relativePath)
            ?: throw IOException("The saved file is no longer available.")
        val uri = uriForFile(file)
        return Intent(Intent.ACTION_SEND).apply {
            type = item.mimeType.ifBlank { "*/*" }
            putExtra(Intent.EXTRA_STREAM, uri)
            clipData = ClipData.newUri(context.contentResolver, item.title, uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
    }

    fun uriForFile(file: File): Uri {
        if (!file.isFile) throw IOException("The video file is no longer available.")
        return FileProvider.getUriForFile(
            context,
            "${context.packageName}.fileprovider",
            file,
        )
    }

    private fun uriFor(item: LibraryItemEntity): Uri {
        if (!item.category.equals("VIDEO", ignoreCase = true)) {
            throw IOException("Only saved videos can be copied this way.")
        }
        val file = privateItemStore.fileFor(item.relativePath)
            ?: throw IOException("The video file is no longer available.")
        return uriForFile(file)
    }
}
