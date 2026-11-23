package com.stash.app.data.bin

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.stash.app.MainActivity
import com.stash.app.StashApplication
import java.text.DateFormat
import java.util.Date

class BinReminderWorker(context: Context, parameters: WorkerParameters) :
    CoroutineWorker(context, parameters) {
    override suspend fun doWork(): Result {
        val app = applicationContext as? StashApplication ?: return Result.failure()
        val scheduledAt = inputData.getLong(BinEmptyScheduler.KEY_SCHEDULED_AT, 0L)
        if (scheduledAt <= 0L || app.binEmptyScheduler.scheduledAt() != scheduledAt) {
            return Result.success()
        }

        postBinNotification(
            applicationContext,
            "Stash Bin review is coming up",
            "Your Stash Bin is scheduled for a review on ${formatDate(scheduledAt)}. Stash will not delete anything automatically.",
            NOTIFICATION_REMINDER_ID,
        )
        return Result.success()
    }
}

class EmptyBinWorker(context: Context, parameters: WorkerParameters) :
    CoroutineWorker(context, parameters) {
    override suspend fun doWork(): Result {
        val app = applicationContext as? StashApplication ?: return Result.failure()
        val scheduledAt = inputData.getLong(BinEmptyScheduler.KEY_SCHEDULED_AT, 0L)
        if (scheduledAt <= 0L || app.binEmptyScheduler.scheduledAt() != scheduledAt) {
            return Result.success()
        }
        if (System.currentTimeMillis() < scheduledAt) return Result.retry()

        if (!app.binEmptyScheduler.clearAfterReview(scheduledAt)) return Result.success()
        postBinNotification(
            applicationContext,
            "Stash Bin review is ready",
            "Open Stash Bin to restore items or empty it yourself. Nothing was deleted.",
            NOTIFICATION_REVIEW_ID,
        )
        return Result.success()
    }
}

private fun postBinNotification(context: Context, title: String, message: String, id: Int) {
    if (
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
        context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
        PackageManager.PERMISSION_GRANTED
    ) {
        return
    }

    val manager = context.getSystemService(NotificationManager::class.java) ?: return
    manager.createNotificationChannel(
        NotificationChannel(
            BIN_CHANNEL_ID,
            "Bin reminders",
            NotificationManager.IMPORTANCE_DEFAULT,
        ),
    )
    val openIntent = Intent(context, MainActivity::class.java)
        .putExtra(EXTRA_OPEN_BIN, true)
        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
    val contentIntent = PendingIntent.getActivity(
        context,
        id,
        openIntent,
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )
    val notification = Notification.Builder(context, BIN_CHANNEL_ID)
        .setSmallIcon(android.R.drawable.ic_menu_delete)
        .setContentTitle(title)
        .setContentText(message)
        .setStyle(Notification.BigTextStyle().bigText(message))
        .setContentIntent(contentIntent)
        .setAutoCancel(true)
        .build()
    manager.notify(id, notification)
}

private fun formatDate(timestamp: Long): String =
    DateFormat.getDateInstance(DateFormat.MEDIUM).format(Date(timestamp))

private const val BIN_CHANNEL_ID = "stash_bin"
private const val NOTIFICATION_REMINDER_ID = 4101
private const val NOTIFICATION_REVIEW_ID = 4102
private const val EXTRA_OPEN_BIN = "open_bin"
