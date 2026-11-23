package com.stash.app.data.video

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.work.CoroutineWorker
import androidx.work.ForegroundInfo
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.stash.app.MainActivity
import com.stash.app.StashApplication
import com.stash.app.data.IncomingShare
import java.io.File
import java.io.IOException
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class VideoDownloadWorker(context: Context, parameters: WorkerParameters) :
    CoroutineWorker(context, parameters) {

    private val notificationManager =
        applicationContext.getSystemService(NotificationManager::class.java)

    override suspend fun doWork(): Result {
        val url = inputData.getString(KEY_URL)
            ?: return Result.failure(workDataOfMessage("This video link is missing."))
        val app = applicationContext as? StashApplication
            ?: return Result.failure(workDataOfMessage("Stash could not start the video download."))
        val notificationId = notificationIdFor(id.toString())
        val resultNotificationId = notificationId + 1
        val stagingDirectory = File(applicationContext.filesDir, "video-downloads/$id")
        var savedItem = false

        try {
            createNotificationChannel()
            setForeground(foregroundInfo(notificationId, "Preparing video download…", null))

            if (!hasInternetConnection()) {
                if (runAttemptCount < MAX_RETRIES) {
                    updateForeground(notificationId, "Waiting for an internet connection…", null)
                    return Result.retry()
                }
                return failAndKeepLink(
                    app,
                    url,
                    resultNotificationId,
                    "No internet connection. Retry when you're online.",
                )
            }

            if (applicationContext.filesDir.usableSpace < MIN_FREE_BYTES) {
                return failAndKeepLink(
                    app,
                    url,
                    resultNotificationId,
                    "Your phone is low on storage. Free up space and try again.",
                )
            }

            updateForeground(notificationId, "Resolving video…", null)
            val progressChannel = Channel<VideoDownloadProgress>(Channel.CONFLATED)
            val progressReporter = CoroutineScope(currentCoroutineContext()).launch {
                for (progress in progressChannel) {
                    updateForeground(
                        notificationId,
                        "Downloading video · ${progress.percent}%",
                        progress.percent,
                    )
                }
            }
            val extracted = try {
                app.videoExtractor.download(url, stagingDirectory) { progress ->
                    progressChannel.trySend(progress)
                }
            } finally {
                progressChannel.close()
                progressReporter.join()
            }
            val title = "Video from ${runCatching { java.net.URI(url).host }.getOrNull() ?: "shared link"}"
            val item = app.libraryRepository.importDownloadedVideo(extracted.file, title, url)
            savedItem = true

            val copyFailure = runCatching { app.videoClipboard.copyVideo(item) }.exceptionOrNull()
            if (copyFailure == null) {
                showResultNotification(
                    resultNotificationId,
                    "Video copied",
                    "The video is saved in Stash and ready to paste.",
                    NotificationCompat.PRIORITY_DEFAULT,
                )
            } else {
                showResultNotification(
                    resultNotificationId,
                    "Video saved",
                    "Stash saved it, but couldn't copy it. Open Stash and tap Copy video to retry.",
                    NotificationCompat.PRIORITY_DEFAULT,
                )
            }
            return Result.success()
        } catch (cancelled: CancellationException) {
            showResultNotification(
                resultNotificationId,
                "Video download canceled",
                "Stash stopped the download and removed its partial file.",
                NotificationCompat.PRIORITY_LOW,
            )
            throw cancelled
        } catch (error: Exception) {
            val transientNetwork = isNetworkFailure(error)
            if (transientNetwork && runAttemptCount < MAX_RETRIES) {
                updateForeground(notificationId, "Connection interrupted · retrying…", null)
                return Result.retry()
            }

            val message = if (savedItem) {
                "The video is saved in Stash, but the clipboard copy failed. Open Stash to retry."
            } else {
                failureMessage(error)
            }
            return failAndKeepLink(app, url, resultNotificationId, message)
        } finally {
            withContext(Dispatchers.IO) {
                if (stagingDirectory.exists()) stagingDirectory.deleteRecursively()
            }
        }
    }

    private suspend fun failAndKeepLink(
        app: StashApplication,
        url: String,
        resultNotificationId: Int,
        message: String,
    ): Result {
        val linkSaved = runCatching {
            app.libraryRepository.importShare(IncomingShare(text = url))
        }.isSuccess
        val finalMessage = "$message ${if (linkSaved) "The link was saved to Stash." else "Stash couldn't save the link."}"
        showResultNotification(
            resultNotificationId,
            "Couldn't copy this video",
            finalMessage,
            NotificationCompat.PRIORITY_DEFAULT,
        )
        return Result.failure(workDataOfMessage(finalMessage))
    }

    private suspend fun updateForeground(notificationId: Int, text: String, progress: Int?) {
        val notification = progressNotification(text, progress)
        setForeground(foregroundInfo(notificationId, text, progress))
        notificationManager.notify(notificationId, notification)
    }

    private fun foregroundInfo(notificationId: Int, text: String, progress: Int?): ForegroundInfo {
        val notification = progressNotification(text, progress)
        return ForegroundInfo(
            notificationId,
            notification,
            ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC,
        )
    }

    private fun progressNotification(text: String, progress: Int?): Notification {
        val cancelIntent = WorkManager.getInstance(applicationContext).createCancelPendingIntent(id)
        return baseNotification("Downloading video", text)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setProgress(100, progress ?: 0, progress == null)
            .addAction(
                android.R.drawable.ic_menu_close_clear_cancel,
                "Cancel",
                cancelIntent,
            )
            .build()
    }

    private fun showResultNotification(id: Int, title: String, text: String, priority: Int) {
        notificationManager.notify(
            id,
            baseNotification(title, text)
                .setAutoCancel(true)
                .setOngoing(false)
                .setPriority(priority)
                .build(),
        )
    }

    private fun baseNotification(title: String, text: String): NotificationCompat.Builder {
        val openApp = PendingIntent.getActivity(
            applicationContext,
            0,
            Intent(applicationContext, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(applicationContext, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setContentIntent(openApp)
            .setCategory(NotificationCompat.CATEGORY_PROGRESS)
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            notificationManager.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID,
                    "Video downloads",
                    NotificationManager.IMPORTANCE_LOW,
                ).apply { description = "Progress and results for videos Stash is saving." },
            )
        }
    }

    private fun hasInternetConnection(): Boolean {
        val manager = applicationContext.getSystemService(ConnectivityManager::class.java)
            ?: return false
        val network = manager.activeNetwork ?: return false
        val capabilities = manager.getNetworkCapabilities(network) ?: return false
        return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
            capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
    }

    private fun isNetworkFailure(error: Throwable): Boolean {
        var current: Throwable? = error
        while (current != null) {
            if (current is UnknownHostException || current is ConnectException ||
                current is SocketTimeoutException
            ) return true
            val message = current.message.orEmpty().lowercase()
            if ("network is unreachable" in message || "connection timed out" in message ||
                "unable to connect" in message || "connection reset" in message
            ) return true
            current = current.cause
        }
        return false
    }

    private fun failureMessage(error: Throwable): String {
        val messages = generateSequence(error as Throwable?) { it.cause }
            .mapNotNull { it.message }
            .joinToString(" ")
            .lowercase()
        return when {
            "drm" in messages || "widevine" in messages || "protected video" in messages ||
                "encrypted stream" in messages ->
                "This video is DRM-protected. Stash can't download protected video."
            error is IOException && ("space" in messages || "enospc" in messages) ->
                "Your phone is low on storage. Free up space and try again."
            "unsupported url" in messages || "no suitable formats" in messages ||
                "requested format is not available" in messages || "did not provide a downloadable mp4" in messages ->
                "This site didn't provide a downloadable MP4 video."
            else ->
                "Stash couldn't download this video. It may be private, unavailable, or blocked by its site."
        }
    }

    private fun workDataOfMessage(message: String) =
        androidx.work.workDataOf(KEY_FAILURE_MESSAGE to message.take(MAX_MESSAGE_LENGTH))

    private fun notificationIdFor(value: String): Int = (value.hashCode() and 0x3ffffffe).coerceAtLeast(1)

    companion object {
        const val KEY_URL = "video_url"
        const val KEY_FAILURE_MESSAGE = "failure_message"
        const val TAG = "stash-video-download"

        private const val CHANNEL_ID = "stash_video_downloads"
        private const val MAX_RETRIES = 2
        private const val MIN_FREE_BYTES = 100L * 1024L * 1024L
        private const val MAX_MESSAGE_LENGTH = 180
    }
}
