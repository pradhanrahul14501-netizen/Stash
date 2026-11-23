package com.stash.app.data.cleanup

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.work.Data
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.CoroutineWorker
import com.stash.app.MainActivity
import com.stash.app.StashApplication
import java.util.concurrent.TimeUnit

class PhoneCleanupScheduler(context: Context) {
    private val appContext = context.applicationContext
    private val workManager by lazy { WorkManager.getInstance(appContext) }

    fun schedule(timestamp: Long, ageDays: Int, treeUri: android.net.Uri) {
        val repository = (appContext as StashApplication).phoneCleanupRepository
        repository.saveSchedule(timestamp, ageDays, treeUri)
        val request = OneTimeWorkRequestBuilder<PhoneCleanupPreviewWorker>()
            .setInputData(Data.Builder().putLong(KEY_SCHEDULED_AT, timestamp).build())
            .setInitialDelay((timestamp - System.currentTimeMillis()).coerceAtLeast(0L), TimeUnit.MILLISECONDS)
            .addTag(PREVIEW_TAG)
            .build()
        workManager.enqueueUniqueWork(PREVIEW_WORK, ExistingWorkPolicy.REPLACE, request)
    }

    fun cancelSchedule() {
        (appContext as StashApplication).phoneCleanupRepository.cancelSchedule()
        workManager.cancelUniqueWork(PREVIEW_WORK)
    }

    fun onPreviewReady(previewId: String, fileCount: Int, totalBytes: Long) {
        CleanupNotifications.showPreview(appContext, fileCount, totalBytes)
        scheduleReminder(previewId, 1)
    }

    fun onNoMatches() {
        CleanupNotifications.showNoMatches(appContext)
    }

    fun resolvePreview(previewId: String) {
        workManager.cancelAllWorkByTag(reminderTag(previewId))
    }

    fun snoozeOneDay(previewId: String): Long? {
        val repository = (appContext as StashApplication).phoneCleanupRepository
        val preview = repository.pendingPreview()?.takeIf { it.id == previewId } ?: return null
        resolvePreview(previewId)
        repository.clearPendingPreview(previewId)
        val nextTime = System.currentTimeMillis() + DAY_MILLIS
        schedule(nextTime, preview.ageDays, android.net.Uri.parse(preview.treeUri))
        return nextTime
    }

    internal fun scheduleReminder(previewId: String, reminderNumber: Int) {
        val request = OneTimeWorkRequestBuilder<PhoneCleanupReminderWorker>()
            .setInputData(
                Data.Builder()
                    .putString(KEY_PREVIEW_ID, previewId)
                    .putInt(KEY_REMINDER_NUMBER, reminderNumber)
                    .build(),
            )
            .setInitialDelay(DAY_MILLIS, TimeUnit.MILLISECONDS)
            .addTag(reminderTag(previewId))
            .build()
        workManager.enqueueUniqueWork(
            "phone-cleanup-reminder-$previewId-$reminderNumber",
            ExistingWorkPolicy.REPLACE,
            request,
        )
    }

    internal fun reminderWorkManager(): WorkManager = workManager

    private fun reminderTag(previewId: String): String = "$REMINDER_TAG-$previewId"

    companion object {
        const val KEY_SCHEDULED_AT = "phone_cleanup_scheduled_at"
        const val KEY_PREVIEW_ID = "phone_cleanup_preview_id"
        const val KEY_REMINDER_NUMBER = "phone_cleanup_reminder_number"
        const val PREVIEW_WORK = "phone_cleanup_preview"
        private const val PREVIEW_TAG = "phone_cleanup_preview_work"
        private const val REMINDER_TAG = "phone_cleanup_reminder"
        private const val DAY_MILLIS = 24L * 60L * 60L * 1000L
    }
}

class PhoneCleanupPreviewWorker(context: Context, parameters: WorkerParameters) :
    CoroutineWorker(context, parameters) {
    override suspend fun doWork(): Result {
        val app = applicationContext as? StashApplication ?: return Result.failure()
        val scheduledAt = inputData.getLong(PhoneCleanupScheduler.KEY_SCHEDULED_AT, 0L)
        val repository = app.phoneCleanupRepository
        if (scheduledAt <= 0L || repository.scheduledAt() != scheduledAt) return Result.success()
        if (System.currentTimeMillis() < scheduledAt) return Result.retry()

        return try {
            val treeUri = repository.selectedTreeUri() ?: return Result.failure()
            val preview = repository.scanForPreview(treeUri, repository.scheduledAgeDays(), scheduledAt)
            repository.cancelSchedule()
            if (preview.files.isEmpty()) {
                app.phoneCleanupScheduler.onNoMatches()
            } else {
                repository.savePendingPreview(preview)
                app.phoneCleanupScheduler.onPreviewReady(
                    preview.id,
                    preview.files.size,
                    preview.files.sumOf(PhoneCleanupFile::sizeBytes),
                )
            }
            Result.success()
        } catch (_: Exception) {
            Result.retry()
        }
    }
}

class PhoneCleanupReminderWorker(context: Context, parameters: WorkerParameters) :
    CoroutineWorker(context, parameters) {
    override suspend fun doWork(): Result {
        val app = applicationContext as? StashApplication ?: return Result.failure()
        val previewId = inputData.getString(PhoneCleanupScheduler.KEY_PREVIEW_ID) ?: return Result.failure()
        val reminderNumber = inputData.getInt(PhoneCleanupScheduler.KEY_REMINDER_NUMBER, 1)
        val preview = app.phoneCleanupRepository.pendingPreview()
        if (preview?.id != previewId) return Result.success()
        CleanupNotifications.showReminder(applicationContext, preview.files.size)
        app.phoneCleanupScheduler.scheduleReminder(previewId, reminderNumber + 1)
        return Result.success()
    }
}

private object CleanupNotifications {
    private const val CHANNEL_ID = "phone_cleanup"
    private const val NOTIFICATION_ID = 4301
    private const val EXTRA_OPEN_CLEANUP = "open_phone_cleanup"

    fun showPreview(context: Context, count: Int, bytes: Long) = show(
        context,
        "Ava cleanup is ready to review",
        "$count older files (${formatBytes(bytes)}). Nothing has been moved. Tap to preview.",
    )

    fun showReminder(context: Context, count: Int) = show(
        context,
        "Ava cleanup is still waiting",
        "$count files are waiting for your review. Stash has not changed them.",
    )

    fun showNoMatches(context: Context) = show(
        context,
        "Ava cleanup scan finished",
        "No files matched your rule. Nothing was changed.",
    )

    private fun show(context: Context, title: String, message: String) {
        if (
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) return
        val manager = context.getSystemService(NotificationManager::class.java) ?: return
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "Ava file cleanup", NotificationManager.IMPORTANCE_DEFAULT),
        )
        val openIntent = Intent(context, MainActivity::class.java)
            .putExtra(EXTRA_OPEN_CLEANUP, true)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        val contentIntent = PendingIntent.getActivity(
            context,
            NOTIFICATION_ID,
            openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val notification = Notification.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_menu_manage)
            .setContentTitle(title)
            .setContentText(message)
            .setStyle(Notification.BigTextStyle().bigText(message))
            .setContentIntent(contentIntent)
            .setAutoCancel(true)
            .build()
        manager.notify(NOTIFICATION_ID, notification)
    }

    private fun formatBytes(bytes: Long): String = when {
        bytes < 1_000_000L -> "${bytes / 1_000} KB"
        bytes < 1_000_000_000L -> "%.1f MB".format(bytes / 1_000_000.0)
        else -> "%.1f GB".format(bytes / 1_000_000_000.0)
    }
}

private const val DAY_MILLIS = 24L * 60L * 60L * 1000L
