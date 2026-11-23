package com.stash.app.data.video

import java.io.File

data class VideoDownloadProgress(
    val percent: Int,
    val etaSeconds: Long,
)

data class ExtractedVideo(
    val file: File,
)

/** Replaceable boundary for resolving and downloading user-authorized video URLs. */
interface VideoExtractor {
    suspend fun download(
        url: String,
        outputDirectory: File,
        onProgress: (VideoDownloadProgress) -> Unit,
    ): ExtractedVideo
}
