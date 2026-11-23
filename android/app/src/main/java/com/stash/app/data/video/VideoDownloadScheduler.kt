package com.stash.app.data.video

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Data
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

class VideoDownloadScheduler(context: Context) {
    private val workManager = WorkManager.getInstance(context.applicationContext)

    fun enqueue(url: String) {
        require(url.length <= MAX_URL_LENGTH) { "That video link is too long." }
        val request = OneTimeWorkRequestBuilder<VideoDownloadWorker>()
            .setInputData(Data.Builder().putString(VideoDownloadWorker.KEY_URL, url).build())
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, RETRY_DELAY_SECONDS, TimeUnit.SECONDS)
            .addTag(VideoDownloadWorker.TAG)
            .build()

        workManager.enqueueUniqueWork(
            DOWNLOAD_QUEUE,
            ExistingWorkPolicy.APPEND_OR_REPLACE,
            request,
        )
    }

    companion object {
        private const val DOWNLOAD_QUEUE = "stash-video-download-queue"
        private const val RETRY_DELAY_SECONDS = 15L
        private const val MAX_URL_LENGTH = 4_096

        fun extractHttpsUrl(sharedText: String): String? = SharedUrlValidator.extractHttpsUrl(sharedText)
    }
}
