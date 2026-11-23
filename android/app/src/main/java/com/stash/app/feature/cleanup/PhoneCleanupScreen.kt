package com.stash.app.feature.cleanup

import android.Manifest
import android.app.DatePickerDialog
import android.app.TimePickerDialog
import android.content.pm.PackageManager
import android.net.Uri
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
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.stash.app.data.cleanup.PhoneBinEntry
import com.stash.app.data.cleanup.PhoneCleanupFile
import com.stash.app.data.cleanup.PhoneCleanupPreview
import com.stash.app.data.cleanup.PhoneCleanupRepository
import com.stash.app.data.cleanup.PhoneCleanupScheduler
import java.text.DateFormat
import java.util.Calendar
import java.util.Date
import kotlinx.coroutines.launch

@Composable
fun PhoneCleanupScreen(
    repository: PhoneCleanupRepository,
    scheduler: PhoneCleanupScheduler,
    treeUri: Uri?,
    onChooseFolder: () -> Unit,
    onBack: () -> Unit,
) {
    BackHandler(onBack = onBack)
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var ageDays by remember { mutableStateOf(repository.scheduledAgeDays().toString()) }
    var scheduledAt by remember { mutableStateOf(repository.scheduledAt()) }
    var pendingPreview by remember { mutableStateOf(repository.pendingPreview()) }
    var binEntries by remember { mutableStateOf(repository.binEntries()) }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf<String?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var confirmApproval by remember { mutableStateOf(false) }
    var deleteBinEntry by remember { mutableStateOf<PhoneBinEntry?>(null) }
    var pendingScheduleTimestamp by remember { mutableStateOf<Long?>(null) }

    val notificationPermission = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        val timestamp = pendingScheduleTimestamp
        pendingScheduleTimestamp = null
        if (granted && timestamp != null && treeUri != null) {
            runCatching {
                scheduler.schedule(timestamp, ageDays.toInt(), treeUri)
            }.onSuccess {
                scheduledAt = timestamp
                message = "Cleanup scheduled. Stash will show a preview; it will not move files without your approval."
            }.onFailure { error = it.message ?: "Could not schedule cleanup." }
        } else if (!granted) {
            error = "Turn on notifications before scheduling cleanup so Ava can ask you to review the preview."
        }
    }

    fun scheduleCleanup(timestamp: Long) {
        val selectedTree = treeUri ?: run {
            error = "Choose a phone folder first."
            return
        }
        val days = ageDays.toIntOrNull()
        if (days == null || days !in 1..3650) {
            error = "Enter an age between 1 and 3650 days."
            return
        }
        error = null
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            pendingScheduleTimestamp = timestamp
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
            return
        }
        runCatching { scheduler.schedule(timestamp, days, selectedTree) }
            .onSuccess {
                scheduledAt = timestamp
                message = "Cleanup scheduled. Stash will show a preview; it will not move files without your approval."
            }
            .onFailure { error = it.message ?: "Could not schedule cleanup." }
    }

    fun chooseDateAndTime() {
        val current = Calendar.getInstance().apply {
            timeInMillis = maxOf(System.currentTimeMillis() + 60L * 60L * 1000L, scheduledAt)
        }
        DatePickerDialog(
            context,
            { _, year, month, day ->
                TimePickerDialog(
                    context,
                    { _, hour, minute ->
                        val selected = Calendar.getInstance().apply {
                            set(year, month, day, hour, minute, 0)
                            set(Calendar.MILLISECOND, 0)
                        }.timeInMillis
                        scheduleCleanup(selected)
                    },
                    current.get(Calendar.HOUR_OF_DAY),
                    current.get(Calendar.MINUTE),
                    true,
                ).show()
            },
            current.get(Calendar.YEAR),
            current.get(Calendar.MONTH),
            current.get(Calendar.DAY_OF_MONTH),
        ).show()
    }

    Scaffold(containerColor = MaterialTheme.colorScheme.background) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Column(modifier = Modifier.padding(top = 18.dp)) {
                    TextButton(onClick = onBack) { Text("‹ Library") }
                    Text("Ava cleanup", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                    Text(
                        "Choose a folder and an age rule. Ava will ask you to review matching files at the time you choose.",
                        modifier = Modifier.padding(top = 6.dp),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            item {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                    Column(modifier = Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text("Phone folder", fontWeight = FontWeight.SemiBold)
                        Text(
                            treeUri?.let(repository::folderName) ?: "No folder selected",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Button(onClick = onChooseFolder, modifier = Modifier.fillMaxWidth()) {
                            Text(if (treeUri == null) "Choose a folder" else "Choose a different folder")
                        }
                    }
                }
            }
            item {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                    Column(modifier = Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text("Your cleanup rule", fontWeight = FontWeight.SemiBold)
                        OutlinedTextField(
                            value = ageDays,
                            onValueChange = { ageDays = it.filter(Char::isDigit).take(4) },
                            modifier = Modifier.fillMaxWidth(),
                            singleLine = true,
                            label = { Text("Files not changed for this many days") },
                            supportingText = { Text("Hidden files and Stash Bin are always excluded.") },
                        )
                        Text(
                            "Ava scans the selected folder and its subfolders. A preview is created at the scheduled time. Android may deliver it a little later when battery saving is active.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Button(
                            onClick = ::chooseDateAndTime,
                            modifier = Modifier.fillMaxWidth(),
                            enabled = treeUri != null && pendingPreview == null && !busy,
                        ) { Text("Choose review date and time") }
                        if (scheduledAt > System.currentTimeMillis()) {
                            Text("Next review: ${formatSchedule(scheduledAt)}")
                            TextButton(onClick = {
                                scheduler.cancelSchedule()
                                scheduledAt = 0L
                                message = "Scheduled cleanup cancelled."
                            }) { Text("Cancel schedule") }
                        }
                    }
                }
            }
            pendingPreview?.let { preview ->
                item {
                    CleanupPreviewCard(
                        preview = preview,
                        busy = busy,
                        onApprove = { confirmApproval = true },
                        onSnooze = {
                            val next = scheduler.snoozeOneDay(preview.id)
                            if (next != null) {
                                pendingPreview = null
                                scheduledAt = next
                                message = "Snoozed until tomorrow. No files were moved."
                            }
                        },
                        onSkip = {
                            repository.clearPendingPreview(preview.id)
                            scheduler.resolvePreview(preview.id)
                            pendingPreview = null
                            message = "Skipped. No files were changed."
                        },
                    )
                }
            }
            if (binEntries.isNotEmpty()) {
                item {
                    Text("Phone-file Bin", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                }
                items(binEntries, key = PhoneBinEntry::id) { entry ->
                    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(12.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(entry.name, fontWeight = FontWeight.Medium)
                                Text(formatBytes(entry.sizeBytes), style = MaterialTheme.typography.bodySmall)
                            }
                            TextButton(onClick = {
                                busy = true
                                scope.launch {
                                    val restored = runCatching { repository.restoreFromPhoneBin(entry.id) }.getOrDefault(false)
                                    binEntries = repository.binEntries()
                                    message = if (restored) "Restored ${entry.name}." else "Could not restore ${entry.name}."
                                    busy = false
                                }
                            }, enabled = !busy) { Text("Restore") }
                            TextButton(onClick = { deleteBinEntry = entry }, enabled = !busy) { Text("Delete") }
                        }
                    }
                }
            }
            if (busy) item { CircularProgressIndicator() }
            message?.let { item { Text(it, color = MaterialTheme.colorScheme.primary) } }
            error?.let { item { Text(it, color = MaterialTheme.colorScheme.error) } }
            item {
                Spacer(Modifier.height(18.dp))
                Text(
                    "A missed preview only creates another reminder about a day later. Stash never moves files without your approval. Permanent deletion from this Bin requires a separate confirmation.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }

    if (confirmApproval) {
        AlertDialog(
            onDismissRequest = { confirmApproval = false },
            title = { Text("Move these files to Stash Bin?") },
            text = {
                val preview = pendingPreview
                Text(
                    preview?.let {
                        "Move ${it.files.size} files (${formatBytes(it.files.sumOf { file -> file.sizeBytes })}) to the Stash Bin inside ${repository.folderName(Uri.parse(it.treeUri))}. You can restore them later."
                    } ?: "This preview is no longer available.",
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    val preview = pendingPreview ?: return@TextButton
                    confirmApproval = false
                    busy = true
                    scope.launch {
                        val result = runCatching { repository.approvePendingPreview(preview.id) }
                        scheduler.resolvePreview(preview.id)
                        pendingPreview = repository.pendingPreview()
                        binEntries = repository.binEntries()
                        message = result.fold(
                            { "Moved ${it.moved} files to Stash Bin. ${it.skipped} changed or unsupported files were left in place." },
                            { it.message ?: "Could not finish the cleanup." },
                        )
                        busy = false
                    }
                }) { Text("Approve move") }
            },
            dismissButton = { TextButton(onClick = { confirmApproval = false }) { Text("Cancel") } },
        )
    }

    deleteBinEntry?.let { entry ->
        AlertDialog(
            onDismissRequest = { deleteBinEntry = null },
            title = { Text("Permanently delete ${entry.name}?") },
            text = { Text("This cannot be undone. The file will be deleted from Stash Bin.") },
            confirmButton = {
                TextButton(onClick = {
                    deleteBinEntry = null
                    busy = true
                    scope.launch {
                        val deleted = runCatching { repository.permanentlyDeleteFromPhoneBin(entry.id) }.getOrDefault(false)
                        binEntries = repository.binEntries()
                        message = if (deleted) "Permanently deleted ${entry.name}." else "Could not delete ${entry.name}."
                        busy = false
                    }
                }) { Text("Delete permanently") }
            },
            dismissButton = { TextButton(onClick = { deleteBinEntry = null }) { Text("Keep file") } },
        )
    }
}

@Composable
private fun CleanupPreviewCard(
    preview: PhoneCleanupPreview,
    busy: Boolean,
    onApprove: () -> Unit,
    onSnooze: () -> Unit,
    onSkip: () -> Unit,
) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Column(modifier = Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Review cleanup", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            Text("${preview.files.size} matching files · ${formatBytes(preview.files.sumOf(PhoneCleanupFile::sizeBytes))}")
            Text("Not changed since at least ${preview.ageDays} days ago.", style = MaterialTheme.typography.bodySmall)
            preview.files.take(8).forEach { file ->
                Text("• ${file.relativePath}", style = MaterialTheme.typography.bodySmall)
            }
            if (preview.files.size > 8) {
                Text("and ${preview.files.size - 8} more", style = MaterialTheme.typography.bodySmall)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = onApprove, enabled = !busy) { Text("Approve") }
                TextButton(onClick = onSnooze, enabled = !busy) { Text("Tomorrow") }
                TextButton(onClick = onSkip, enabled = !busy) { Text("Skip") }
            }
        }
    }
}

private fun formatSchedule(timestamp: Long): String =
    DateFormat.getDateTimeInstance(DateFormat.MEDIUM, DateFormat.SHORT).format(Date(timestamp))

private fun formatBytes(bytes: Long): String = when {
    bytes < 1_000_000L -> "${bytes / 1_000} KB"
    bytes < 1_000_000_000L -> "%.1f MB".format(bytes / 1_000_000.0)
    else -> "%.1f GB".format(bytes / 1_000_000_000.0)
}
