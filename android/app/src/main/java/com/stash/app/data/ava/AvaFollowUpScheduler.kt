package com.stash.app.data.ava

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
import java.text.DateFormat
import java.util.Date
import java.util.concurrent.TimeUnit

class AvaFollowUpScheduler(
    context: Context,
    private val repository: AvaFollowUpRepository,
) {
    private val appContext = context.applicationContext
    private val workManager by lazy { WorkManager.getInstance(appContext) }

    suspend fun schedule(suggestion: AvaDateSuggestion, remindAt: Long) {
        require(remindAt > System.currentTimeMillis()) { "Choose a future reminder time." }
        val followUp = repository.add(suggestion, remindAt)
            ?: throw IllegalArgumentException("A reminder already exists for this date.")
        try {
            val request = OneTimeWorkRequestBuilder<AvaFollowUpWorker>()
                .setInputData(Data.Builder().putString(KEY_FOLLOW_UP_ID, followUp.id).build())
                .setInitialDelay(remindAt - System.currentTimeMillis(), TimeUnit.MILLISECONDS)
                .build()
            workManager.enqueueUniqueWork(workName(followUp.id), ExistingWorkPolicy.REPLACE, request)
        } catch (error: Exception) {
            repository.delete(followUp.id)
            throw error
        }
    }

    suspend fun cancel(id: String) {
        workManager.cancelUniqueWork(workName(id))
        repository.delete(id)
    }

    private fun workName(id: String) = "ava_follow_up_$id"

    companion object {
        const val KEY_FOLLOW_UP_ID = "ava_follow_up_id"
    }
}

class AvaFollowUpWorker(context: Context, parameters: WorkerParameters) :
    CoroutineWorker(context, parameters) {
    override suspend fun doWork(): Result {
        val app = applicationContext as? StashApplication ?: return Result.failure()
        val id = inputData.getString(AvaFollowUpScheduler.KEY_FOLLOW_UP_ID) ?: return Result.failure()
        val followUp = app.avaFollowUpRepository.getById(id) ?: return Result.success()
        if (followUp.deletedAt != null || followUp.notifiedAt != null) return Result.success()
        if (System.currentTimeMillis() < followUp.remindAt) return Result.retry()
        if (
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            applicationContext.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            return Result.success()
        }

        val manager = applicationContext.getSystemService(NotificationManager::class.java)
            ?: return Result.retry()
        if (!manager.areNotificationsEnabled()) return Result.success()
        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_ID,
                "Ava follow-up reminders",
                NotificationManager.IMPORTANCE_DEFAULT,
            ),
        )
        val openIntent = Intent(applicationContext, MainActivity::class.java)
            .putExtra(EXTRA_OPEN_FOLLOW_UPS, true)
            .putExtra(EXTRA_FOLLOW_UP_ITEM_ID, followUp.sourceItemId)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        val notificationId = followUp.id.hashCode()
        val contentIntent = PendingIntent.getActivity(
            applicationContext,
            notificationId,
            openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val eventDate = DateFormat.getDateInstance(DateFormat.MEDIUM).format(Date(followUp.eventAt))
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
            manager.getNotificationChannel(CHANNEL_ID)?.importance == NotificationManager.IMPORTANCE_NONE
        ) {
            return Result.success()
        }
        val body = "${followUp.eventLabel} for ${followUp.sourceTitle} is on $eventDate. Tap to review the saved item."
        val notification = Notification.Builder(applicationContext, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_menu_my_calendar)
            .setContentTitle("Ava reminder")
            .setContentText(body)
            .setStyle(Notification.BigTextStyle().bigText(body))
            .setContentIntent(contentIntent)
            .setAutoCancel(true)
            .build()
        manager.notify(notificationId, notification)
        app.avaFollowUpRepository.markNotified(id)
        return Result.success()
    }
}

private const val CHANNEL_ID = "ava_follow_ups"
private const val EXTRA_OPEN_FOLLOW_UPS = "open_ava_follow_ups"
private const val EXTRA_FOLLOW_UP_ITEM_ID = "ava_follow_up_item_id"
