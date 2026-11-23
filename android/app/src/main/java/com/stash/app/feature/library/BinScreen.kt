package com.stash.app.feature.library

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
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
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.stash.app.data.local.LibraryItemEntity
import java.text.DateFormat
import java.util.Date
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch

@Composable
fun BinScreen(viewModel: LibraryViewModel, onBack: () -> Unit) {
    val items by viewModel.binItems.collectAsStateWithLifecycle()
    val binReviewAt by viewModel.binReviewAt.collectAsStateWithLifecycle()
    val snackbarHostState = remember { SnackbarHostState() }
    val context = LocalContext.current
    val coroutineScope = rememberCoroutineScope()
    var showDatePicker by remember { mutableStateOf(false) }
    var proposedReviewAt by remember { mutableStateOf<Long?>(null) }
    var confirmEmptyBin by remember { mutableStateOf(false) }
    var scheduleAfterPermission by remember { mutableStateOf<Long?>(null) }
    val datePickerState = rememberDatePickerState(initialSelectedDateMillis = tomorrowUtcMillis())
    val notificationPermissionRequest = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        val timestamp = scheduleAfterPermission
        scheduleAfterPermission = null
        if (timestamp != null) {
            viewModel.scheduleBinReview(timestamp)
            if (!granted) {
                coroutineScope.launch {
                    snackbarHostState.showSnackbar(
                        "Scheduled. Turn on notifications to receive the reminder.",
                    )
                }
            }
        }
    }

    LaunchedEffect(viewModel) {
        viewModel.refreshBinReviewSchedule()
        viewModel.events.collect { message -> snackbarHostState.showSnackbar(message) }
    }

    Scaffold(
        modifier = Modifier.fillMaxSize(),
        containerColor = MaterialTheme.colorScheme.background,
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { contentPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(contentPadding)
                .padding(horizontal = 20.dp),
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 22.dp, bottom = 18.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TextButton(onClick = onBack) { Text("Back") }
                Column(modifier = Modifier.padding(start = 8.dp)) {
                    Text(
                        text = "Bin",
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    Text(
                        text = "Restore anything you moved here.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            Text(
                text = "${items.size} items",
                modifier = Modifier.padding(bottom = 10.dp),
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Card(
                modifier = Modifier.fillMaxWidth().padding(bottom = 14.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    if (binReviewAt == null) {
                        Text(
                            text = "Schedule a Bin review",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold,
                        )
                        Text(
                            text = "Stash will remind you to review the Bin. It will never empty it automatically.",
                            modifier = Modifier.padding(top = 5.dp),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    } else {
                        Text(
                            text = "Bin review reminder: ${formatBinDate(binReviewAt!!)}",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold,
                        )
                        Text(
                            text = "Stash will notify you then. You can cancel or change this reminder.",
                            modifier = Modifier.padding(top = 5.dp),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    Text(
                        text = "Only copies stored in Stash can be emptied. Originals elsewhere stay untouched.",
                        modifier = Modifier.padding(top = 5.dp),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                        horizontalArrangement = Arrangement.End,
                    ) {
                        if (binReviewAt != null) {
                            TextButton(onClick = viewModel::cancelBinReview) { Text("Cancel reminder") }
                        }
                        Button(
                            onClick = { showDatePicker = true },
                            enabled = items.isNotEmpty(),
                        ) {
                            Text(if (binReviewAt == null) "Set review date" else "Change date")
                        }
                    }
                }
            }

            if (items.isNotEmpty()) {
                Button(
                    onClick = { confirmEmptyBin = true },
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                ) { Text("Empty Bin now") }
            }

            if (items.isEmpty()) {
                Column(
                    modifier = Modifier
                        .weight(1f)
                        .fillMaxWidth()
                        .padding(bottom = 48.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center,
                ) {
                    Text(
                        text = "Your Bin is empty",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Spacer(Modifier.height(8.dp))
                    Text(
                        text = "Items you move here can be restored at any time.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            } else {
                LazyColumn(
                    modifier = Modifier.weight(1f).fillMaxWidth(),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    items(items = items, key = LibraryItemEntity::id) { item ->
                        BinItemCard(item, onRestore = { viewModel.restoreFromBin(item.id) })
                    }
                    item { Spacer(Modifier.height(20.dp)) }
                }
            }
        }
    }

    if (showDatePicker) {
        DatePickerDialog(
            onDismissRequest = { showDatePicker = false },
            confirmButton = {
                TextButton(
                    onClick = {
                        showDatePicker = false
                        val dateMillis = datePickerState.selectedDateMillis
                        val timestamp = dateMillis?.let(::localStartOfDay)
                        if (timestamp == null || timestamp <= System.currentTimeMillis()) {
                            coroutineScope.launch {
                                snackbarHostState.showSnackbar("Choose a future date.")
                            }
                        } else {
                            proposedReviewAt = timestamp
                        }
                    },
                ) { Text("Continue") }
            },
            dismissButton = {
                TextButton(onClick = { showDatePicker = false }) { Text("Cancel") }
            },
        ) {
            DatePicker(state = datePickerState)
        }
    }

    proposedReviewAt?.let { timestamp ->
        AlertDialog(
            onDismissRequest = { proposedReviewAt = null },
            title = { Text("Schedule a Bin review?") },
            text = {
                Text(
                    "Stash will remind you to review the Bin on ${formatBinDate(timestamp)}. Nothing will be deleted automatically.",
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        proposedReviewAt = null
                        val needsNotificationPermission = Build.VERSION.SDK_INT >= 33 &&
                            context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
                            PackageManager.PERMISSION_GRANTED
                        if (needsNotificationPermission) {
                            scheduleAfterPermission = timestamp
                            notificationPermissionRequest.launch(Manifest.permission.POST_NOTIFICATIONS)
                        } else {
                            viewModel.scheduleBinReview(timestamp)
                        }
                    },
                ) { Text("Schedule reminder") }
            },
            dismissButton = {
                TextButton(onClick = { proposedReviewAt = null }) { Text("Cancel") }
            },
        )
    }

    if (confirmEmptyBin) {
        AlertDialog(
            onDismissRequest = { confirmEmptyBin = false },
            title = { Text("Permanently empty Stash Bin?") },
            text = {
                Text("This immediately deletes the saved copies in Stash Bin and cannot be undone. Originals elsewhere are not affected.")
            },
            confirmButton = {
                TextButton(onClick = {
                    confirmEmptyBin = false
                    viewModel.emptyBinNow()
                }) { Text("Delete permanently") }
            },
            dismissButton = {
                TextButton(onClick = { confirmEmptyBin = false }) { Text("Keep items") }
            },
        )
    }
}

@Composable
private fun BinItemCard(item: LibraryItemEntity, onRestore: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        shape = MaterialTheme.shapes.large,
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = item.title,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                text = listOf(
                    item.category.lowercase().replaceFirstChar { it.uppercase() },
                    item.mode.lowercase().replaceFirstChar { it.uppercase() },
                    item.deletedAt?.let(::formatBinDate).orEmpty(),
                ).filter(String::isNotBlank).joinToString(" · "),
                modifier = Modifier.padding(top = 5.dp),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            item.contentText?.takeIf(String::isNotBlank)?.let { content ->
                Text(
                    text = content,
                    modifier = Modifier.padding(top = 10.dp),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 3,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            TextButton(onClick = onRestore, modifier = Modifier.align(Alignment.End)) {
                Text("Restore")
            }
        }
    }
}

private fun formatBinDate(timeMillis: Long): String =
    DateFormat.getDateInstance(DateFormat.MEDIUM).format(Date(timeMillis))

private fun tomorrowUtcMillis(): Long =
    java.time.LocalDate.now(java.time.ZoneId.systemDefault())
        .plusDays(1)
        .atStartOfDay(java.time.ZoneOffset.UTC)
        .toInstant()
        .toEpochMilli()

private fun localStartOfDay(utcDateMillis: Long): Long =
    java.time.Instant.ofEpochMilli(utcDateMillis)
        .atZone(java.time.ZoneOffset.UTC)
        .toLocalDate()
        .atStartOfDay(java.time.ZoneId.systemDefault())
        .toInstant()
        .toEpochMilli()
