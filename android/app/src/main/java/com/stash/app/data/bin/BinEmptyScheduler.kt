package com.stash.app.data.bin

import android.content.Context
import androidx.work.Data
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

class BinEmptyScheduler(context: Context) {
    private val appContext = context.applicationContext
    private val preferences = appContext.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
    private val workManager by lazy { WorkManager.getInstance(appContext) }

    fun scheduledAt(): Long? = preferences.getLong(KEY_SCHEDULED_AT, 0L).takeIf { it > 0L }

    fun scheduleFor(timestamp: Long) {
        require(timestamp > System.currentTimeMillis()) { "Choose a future date." }
        val manager = workManager
        preferences.edit().putLong(KEY_SCHEDULED_AT, timestamp).apply()

        val emptyRequest = OneTimeWorkRequestBuilder<EmptyBinWorker>()
            .setInputData(Data.Builder().putLong(KEY_SCHEDULED_AT, timestamp).build())
            .setInitialDelay(timestamp - System.currentTimeMillis(), TimeUnit.MILLISECONDS)
            .build()
        val reminderAt = timestamp - REMINDER_LEAD_MILLIS
        val reminderRequest = OneTimeWorkRequestBuilder<BinReminderWorker>()
            .setInputData(Data.Builder().putLong(KEY_SCHEDULED_AT, timestamp).build())
            .setInitialDelay(
                (reminderAt - System.currentTimeMillis()).coerceAtLeast(0L),
                TimeUnit.MILLISECONDS,
            )
            .build()
        try {
            manager.enqueueUniqueWork(EMPTY_WORK, ExistingWorkPolicy.REPLACE, emptyRequest)
            manager.enqueueUniqueWork(REMINDER_WORK, ExistingWorkPolicy.REPLACE, reminderRequest)
        } catch (error: Exception) {
            preferences.edit().remove(KEY_SCHEDULED_AT).apply()
            manager.cancelUniqueWork(EMPTY_WORK)
            manager.cancelUniqueWork(REMINDER_WORK)
            throw error
        }
    }

    fun cancel() {
        preferences.edit().remove(KEY_SCHEDULED_AT).apply()
        workManager.cancelUniqueWork(EMPTY_WORK)
        workManager.cancelUniqueWork(REMINDER_WORK)
    }

    fun clearAfterReview(expectedTimestamp: Long): Boolean {
        if (scheduledAt() != expectedTimestamp) return false
        preferences.edit().remove(KEY_SCHEDULED_AT).apply()
        workManager.cancelUniqueWork(REMINDER_WORK)
        return true
    }

    companion object {
        const val KEY_SCHEDULED_AT = "scheduled_empty_bin_at"

        private const val PREFERENCES = "stash_bin_schedule"
        private const val EMPTY_WORK = "stash_empty_bin"
        private const val REMINDER_WORK = "stash_empty_bin_reminder"
        private const val REMINDER_LEAD_MILLIS = 24L * 60L * 60L * 1000L
    }
}
