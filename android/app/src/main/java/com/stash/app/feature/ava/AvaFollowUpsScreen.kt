package com.stash.app.feature.ava

import android.Manifest
import android.app.DatePickerDialog
import android.app.TimePickerDialog
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.stash.app.data.LibraryRepository
import com.stash.app.data.ava.AvaDateSuggestion
import com.stash.app.data.ava.AvaFollowUpDateDetector
import com.stash.app.data.ava.AvaFollowUpRepository
import com.stash.app.data.ava.AvaFollowUpScheduler
import com.stash.app.data.local.AvaFollowUpEntity
import com.stash.app.data.mobilecompanion.MobileCompanionRepository
import com.stash.app.data.local.LibraryItemEntity
import java.text.DateFormat
import java.util.Calendar
import java.util.Date
import kotlinx.coroutines.launch
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Composable
fun AvaFollowUpsScreen(
    libraryRepository: LibraryRepository,
    followUpRepository: AvaFollowUpRepository,
    scheduler: AvaFollowUpScheduler,
    mobileCompanionRepository: MobileCompanionRepository,
    sourceItemId: String?,
    onBack: () -> Unit,
) {
    BackHandler(onBack = onBack)
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val libraryItems by libraryRepository.observeItems().collectAsStateWithLifecycle(initialValue = emptyList())
    val followUps by followUpRepository.observeAll().collectAsStateWithLifecycle(initialValue = emptyList())
    var selectedSuggestion by remember { mutableStateOf<AvaDateSuggestion?>(null) }
    var selectedReminderAt by remember { mutableStateOf(0L) }
    var showConfirmation by remember { mutableStateOf(false) }
    var pendingPermissionRequest by remember { mutableStateOf<Pair<AvaDateSuggestion, Long>?>(null) }
    var message by remember { mutableStateOf<String?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }

    val candidates by produceState(emptyList<AvaDateSuggestion>(), libraryItems, followUps, sourceItemId) {
        value = withContext(Dispatchers.Default) {
            val alreadyScheduled = followUps.map { it.sourceItemId to it.eventAt }.toSet()
            libraryItems.asSequence()
                .filter { sourceItemId == null || it.id == sourceItemId }
                .flatMap { AvaFollowUpDateDetector.detect(it).asSequence() }
                .filterNot { (it.sourceItemId to it.eventAt) in alreadyScheduled }
                .toList()
        }
    }

    fun saveReminder(suggestion: AvaDateSuggestion, remindAt: Long) {
        busy = true
        error = null
        scope.launch {
            runCatching { scheduler.schedule(suggestion, remindAt) }
                .onSuccess {
                    selectedSuggestion = null
                    message = "Reminder saved. Stash will notify you around the chosen time."
                    if (mobileCompanionRepository.connection() != null) {
                        scope.launch {
                            runCatching { mobileCompanionRepository.syncFollowUps() }
                                .onFailure { message = "Reminder saved on this phone. Open Connect desktop to sync it when Wi-Fi is available." }
                        }
                    }
                }
                .onFailure { error = it.message ?: "Could not save that reminder." }
            busy = false
        }
    }

    val notificationPermission = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        val pending = pendingPermissionRequest
        pendingPermissionRequest = null
        if (granted && pending != null) {
            saveReminder(pending.first, pending.second)
        } else if (!granted) {
            error = "Notifications are off, so Stash did not save the reminder."
        }
    }

    fun requestReminder(suggestion: AvaDateSuggestion, remindAt: Long) {
        if (remindAt <= System.currentTimeMillis()) {
            error = "Choose a reminder time in the future."
            return
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            pendingPermissionRequest = suggestion to remindAt
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        } else {
            saveReminder(suggestion, remindAt)
        }
    }

    fun chooseReminderTime(suggestion: AvaDateSuggestion, initialTimestamp: Long) {
        val initial = Calendar.getInstance().apply { timeInMillis = initialTimestamp }
        DatePickerDialog(
            context,
            { _, year, month, day ->
                TimePickerDialog(
                    context,
                    { _, hour, minute ->
                        val chosen = Calendar.getInstance().apply {
                            set(year, month, day, hour, minute, 0)
                            set(Calendar.MILLISECOND, 0)
                        }.timeInMillis
                        if (chosen <= System.currentTimeMillis()) {
                            error = "Choose a reminder time in the future."
                        } else {
                            selectedSuggestion = suggestion
                            selectedReminderAt = chosen
                            showConfirmation = true
                        }
                    },
                    initial.get(Calendar.HOUR_OF_DAY),
                    initial.get(Calendar.MINUTE),
                    false,
                ).show()
            },
            initial.get(Calendar.YEAR),
            initial.get(Calendar.MONTH),
            initial.get(Calendar.DAY_OF_MONTH),
        ).apply {
            datePicker.minDate = Calendar.getInstance().apply {
                set(Calendar.HOUR_OF_DAY, 0)
                set(Calendar.MINUTE, 0)
                set(Calendar.SECOND, 0)
                set(Calendar.MILLISECOND, 0)
            }.timeInMillis
        }.show()
    }

    LaunchedEffect(sourceItemId, candidates) {
        if (sourceItemId != null && selectedSuggestion == null) {
            candidates.firstOrNull()?.let { suggestion ->
                selectedSuggestion = suggestion
                selectedReminderAt = defaultReminderTime(suggestion.eventAt)
                showConfirmation = true
            }
        }
    }

    Scaffold(containerColor = MaterialTheme.colorScheme.background) { contentPadding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(contentPadding).padding(horizontal = 20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Column(modifier = Modifier.padding(top = 18.dp)) {
                    TextButton(onClick = onBack) { Text("‹ Library") }
                    Text("Ava Follow-ups", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                    Text(
                        "Ava looks for clear dates in saved text, screenshots, and PDFs. Review the source and confirm before a reminder is scheduled.",
                        modifier = Modifier.padding(top = 6.dp),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            if (candidates.isNotEmpty()) {
                item {
                    Text("Possible dates", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                }
                items(candidates, key = { "${it.sourceItemId}:${it.eventAt}" }) { suggestion ->
                    SuggestionCard(
                        suggestion = suggestion,
                        enabled = !busy,
                        onSetReminder = {
                            selectedSuggestion = suggestion
                            selectedReminderAt = defaultReminderTime(suggestion.eventAt)
                            showConfirmation = true
                        },
                    )
                }
            } else {
                item {
                    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                        Text(
                            text = if (sourceItemId == null) {
                                "No new future dates found. Save a text note, screenshot, or PDF with a clear date and check here again."
                            } else {
                                "Ava did not find a new future date in this saved item."
                            },
                            modifier = Modifier.fillMaxWidth().padding(16.dp),
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }

            if (followUps.isNotEmpty()) {
                item {
                    Text("Your reminders", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                }
                items(followUps, key = AvaFollowUpEntity::id) { followUp ->
                    FollowUpCard(
                        followUp = followUp,
                        onCancel = {
                            busy = true
                            scope.launch {
                                runCatching { scheduler.cancel(followUp.id) }
                                    .onSuccess {
                                        message = "Reminder cancelled. The saved item is unchanged."
                                        if (mobileCompanionRepository.connection() != null) {
                                            runCatching { mobileCompanionRepository.syncFollowUps() }
                                                .onFailure { message = "Reminder cancelled on this phone. Reconnect to desktop Stash to sync the change." }
                                        }
                                    }
                                    .onFailure { error = "Could not cancel that reminder." }
                                busy = false
                            }
                        },
                        enabled = !busy,
                    )
                }
            }

            message?.let { item { Text(it, color = MaterialTheme.colorScheme.primary) } }
            error?.let { item { Text(it, color = MaterialTheme.colorScheme.error) } }
            if (busy) item { CircularProgressIndicator() }
            item {
                Spacer(Modifier.height(12.dp))
                Text(
                    "Date matching runs on this phone. Dates are suggestions; Stash never creates a reminder or changes a file without your confirmation. Android may deliver reminders a little later than scheduled.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(20.dp))
            }
        }
    }

    if (showConfirmation) {
        selectedSuggestion?.let { suggestion ->
            AlertDialog(
                onDismissRequest = { showConfirmation = false },
                title = { Text("Ava found a possible date") },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("${suggestion.eventLabel}: ${formatDate(suggestion.eventAt)}")
                        Text("Saved item: ${suggestion.sourceTitle}", style = MaterialTheme.typography.bodySmall)
                        Text("“${suggestion.sourceExcerpt}”", style = MaterialTheme.typography.bodySmall)
                        Text("Reminder: ${formatDateTime(selectedReminderAt)}")
                    }
                },
                confirmButton = {
                    TextButton(
                        onClick = {
                            showConfirmation = false
                            requestReminder(suggestion, selectedReminderAt)
                        },
                        enabled = !busy,
                    ) { Text("Confirm reminder") }
                },
                dismissButton = {
                    Row {
                        TextButton(onClick = {
                            showConfirmation = false
                            chooseReminderTime(suggestion, selectedReminderAt)
                        }) { Text("Change time") }
                        TextButton(onClick = { showConfirmation = false }) { Text("Cancel") }
                    }
                },
            )
        }
    }
}

@Composable
private fun SuggestionCard(
    suggestion: AvaDateSuggestion,
    enabled: Boolean,
    onSetReminder: () -> Unit,
) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Column(modifier = Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(suggestion.eventLabel, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
            Text("${formatDate(suggestion.eventAt)} · ${suggestion.sourceTitle}", style = MaterialTheme.typography.bodySmall)
            Text("“${suggestion.sourceExcerpt}”", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Button(onClick = onSetReminder, enabled = enabled) { Text("Review and set reminder") }
        }
    }
}

@Composable
private fun FollowUpCard(
    followUp: AvaFollowUpEntity,
    enabled: Boolean,
    onCancel: () -> Unit,
) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Column(modifier = Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Text(followUp.eventLabel, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
            Text(followUp.sourceTitle)
            Text("Event date: ${formatDate(followUp.eventAt)}", style = MaterialTheme.typography.bodySmall)
            Text(
                when {
                    followUp.notifiedAt != null -> "Notification sent: ${formatDateTime(followUp.notifiedAt)}"
                    followUp.remindAt <= System.currentTimeMillis() -> "Reminder time passed; check notification access."
                    else -> "Reminder: ${formatDateTime(followUp.remindAt)}"
                },
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            TextButton(onClick = onCancel, enabled = enabled) { Text("Cancel reminder") }
        }
    }
}

private fun defaultReminderTime(eventAt: Long): Long {
    val zone = java.time.ZoneId.systemDefault()
    val eventDate = Date(eventAt).toInstant().atZone(zone).toLocalDate()
    val oneDayBeforeAtNine = eventDate.minusDays(1).atTime(9, 0).atZone(zone).toInstant().toEpochMilli()
    return oneDayBeforeAtNine.takeIf { it > System.currentTimeMillis() }
        ?: System.currentTimeMillis() + DEFAULT_SHORT_NOTICE_MILLIS
}

private fun formatDate(timestamp: Long): String =
    DateFormat.getDateInstance(DateFormat.MEDIUM).format(Date(timestamp))

private fun formatDateTime(timestamp: Long): String =
    DateFormat.getDateTimeInstance(DateFormat.MEDIUM, DateFormat.SHORT).format(Date(timestamp))

private const val DEFAULT_SHORT_NOTICE_MILLIS = 60L * 60L * 1000L
