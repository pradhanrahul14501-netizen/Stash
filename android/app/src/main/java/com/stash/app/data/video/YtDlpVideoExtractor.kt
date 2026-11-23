package com.stash.app.data.video

import android.content.Context
import com.yausername.ffmpeg.FFmpeg
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLRequest
import java.io.File
import java.io.IOException
import java.util.UUID
import java.util.concurrent.Executors
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext

class YtDlpVideoExtractor(context: Context) : VideoExtractor {
    private val appContext = context.applicationContext

    override suspend fun download(
        url: String,
        outputDirectory: File,
        onProgress: (VideoDownloadProgress) -> Unit,
    ): ExtractedVideo = withContext(Dispatchers.IO) {
        if (!outputDirectory.exists() && !outputDirectory.mkdirs()) {
            throw IOException("Could not create a temporary video folder.")
        }
        if (!outputDirectory.isDirectory) throw IOException("The video folder is not available.")

        YoutubeDL.getInstance().init(appContext)
        FFmpeg.getInstance().init(appContext)

        val outputTemplate = File(outputDirectory, "stash-video.%(ext)s").absolutePath
        val request = YoutubeDLRequest(url).apply {
            addOption("--no-playlist")
            addOption("--no-mtime")
            addOption("--no-warnings")
            addOption(
                "-f",
                "bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a][acodec^=mp4a]/" +
                    "best[ext=mp4][vcodec^=avc1][acodec^=mp4a]",
            )
            addOption("--merge-output-format", "mp4")
            addOption("--remux-video", "mp4")
            addOption("-o", outputTemplate)
        }

        val processId = "stash-${UUID.randomUUID()}"
        executeCancellable(request, processId, onProgress)

        val video = File(outputDirectory, "stash-video.mp4")
        if (!video.isFile || video.length() <= 0L) {
            throw IOException("The source did not provide a downloadable MP4 video.")
        }
        ExtractedVideo(video)
    }

    private suspend fun executeCancellable(
        request: YoutubeDLRequest,
        processId: String,
        onProgress: (VideoDownloadProgress) -> Unit,
    ) = suspendCancellableCoroutine { continuation ->
        val executor = Executors.newSingleThreadExecutor { runnable ->
            Thread(runnable, "stash-video-extractor").apply { isDaemon = true }
        }
        val future = executor.submit {
            try {
                YoutubeDL.getInstance().execute(request, processId) { percent, eta, _ ->
                    val safePercent = percent.takeIf(Float::isFinite)?.toInt()?.coerceIn(0, 100) ?: 0
                    onProgress(VideoDownloadProgress(safePercent, eta.coerceAtLeast(0L)))
                    kotlin.Unit
                }
                if (continuation.isActive) continuation.resume(kotlin.Unit)
            } catch (error: Throwable) {
                if (continuation.isActive) continuation.resumeWithException(error)
            } finally {
                executor.shutdown()
            }
        }

        continuation.invokeOnCancellation {
            runCatching { YoutubeDL.getInstance().destroyProcessById(processId) }
            future.cancel(true)
            executor.shutdownNow()
        }
    }
}
