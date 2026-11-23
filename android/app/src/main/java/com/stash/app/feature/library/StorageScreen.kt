package com.stash.app.feature.library

import androidx.activity.compose.BackHandler
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
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.stash.app.data.LibraryStorageOverview
import com.stash.app.data.StorageAuditReport
import com.stash.app.data.StoredItemSize
import java.util.Locale

@Composable
fun StorageScreen(viewModel: LibraryViewModel, onBack: () -> Unit) {
    val overview by viewModel.storageOverview.collectAsStateWithLifecycle()
    val error by viewModel.storageError.collectAsStateWithLifecycle()
    val audit by viewModel.storageAudit.collectAsStateWithLifecycle()
    val auditError by viewModel.storageAuditError.collectAsStateWithLifecycle()
    BackHandler(onBack = onBack)
    LaunchedEffect(viewModel) { viewModel.refreshStorageOverview() }

    Scaffold(
        modifier = Modifier.fillMaxSize(),
        containerColor = MaterialTheme.colorScheme.background,
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 20.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(top = 18.dp, bottom = 16.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TextButton(onClick = onBack) { Text("‹  Library") }
                Text(
                    "Storage overview",
                    modifier = Modifier.padding(start = 10.dp),
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary,
                )
            }

            overview?.let { data ->
                StorageOverviewContent(
                    data = data,
                    audit = audit,
                    auditError = auditError,
                    onRunAudit = viewModel::refreshStorageAudit,
                )
            } ?: Column(
                modifier = Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.Center,
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                if (error != null) {
                    Text(error!!, color = MaterialTheme.colorScheme.error)
                    Spacer(Modifier.height(12.dp))
                    Button(onClick = viewModel::refreshStorageOverview) { Text("Try again") }
                } else {
                    CircularProgressIndicator()
                    Spacer(Modifier.height(12.dp))
                    Text("Checking saved files…", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}

@Composable
private fun StorageOverviewContent(
    data: LibraryStorageOverview,
    audit: StorageAuditReport?,
    auditError: String?,
    onRunAudit: () -> Unit,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Button(onClick = onRunAudit, modifier = Modifier.fillMaxWidth()) {
                Text(if (audit == null) "Run file health check" else "Run check again")
            }
            Text(
                "Checks run on this phone. Sensitive findings list types, not secret values.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (auditError != null) {
                Text(auditError, color = MaterialTheme.colorScheme.error)
            }
            audit?.let { report ->
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                    Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("File health check", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                        Text("Checked ${formatAuditDate(report.checkedAt)}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        AuditLine("Empty", report.emptyFiles)
                        AuditLine("Possibly damaged", report.corruptFiles)
                        AuditLine("Missing from app storage", report.missingFiles)
                        Text("Duplicates", fontWeight = FontWeight.Medium)
                        if (report.duplicateGroups.isEmpty()) {
                            Text("None found", style = MaterialTheme.typography.bodySmall)
                        } else {
                            report.duplicateGroups.forEach { group ->
                                Text(group.joinToString(" ↔ "), style = MaterialTheme.typography.bodySmall)
                            }
                        }
                        Text("Sensitive patterns", fontWeight = FontWeight.Medium)
                        if (report.sensitiveFindings.isEmpty()) {
                            Text("None found", style = MaterialTheme.typography.bodySmall)
                        } else {
                            report.sensitiveFindings.forEach { finding ->
                                Text("${finding.title}: ${finding.types.joinToString(", ")}", style = MaterialTheme.typography.bodySmall)
                            }
                        }
                        AuditLine("Oldest", report.oldestItems)
                        AuditLine("Newest", report.newestItems)
                    }
                }
            }
        }
        item {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                Column(Modifier.fillMaxWidth().padding(16.dp)) {
                    Text("Saved files", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.height(10.dp))
                    SizeRow("Stash app data", data.appDataBytes, emphasize = true)
                    SizeRow("Library", data.libraryBytes)
                    SizeRow("Bin", data.binBytes)
                    Spacer(Modifier.height(6.dp))
                    SizeRow("Saved files total", data.totalBytes, emphasize = true)
                    Text(
                        "App data includes saved files, Ava's model, and local data. Bin files still use space until removed.",
                        modifier = Modifier.padding(top = 10.dp),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
        if (data.categoryBytes.isNotEmpty()) {
            item {
                Text("By type · Library and Bin", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            }
            items(data.categoryBytes.entries.sortedByDescending { it.value }) { (category, bytes) ->
                SizeRow(category.lowercase().replaceFirstChar { it.uppercase() }, bytes)
            }
        }
        if (data.largestItems.isNotEmpty()) {
            item {
                Text("Largest files", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            }
            items(data.largestItems) { item -> LargestItemRow(item) }
        }
        if (data.missingFileCount > 0) {
            item {
                Text(
                    "${data.missingFileCount} saved file${if (data.missingFileCount == 1) " is" else "s are"} unavailable, so ${if (data.missingFileCount == 1) "its size is" else "their sizes are"} not included.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        item { Spacer(Modifier.height(16.dp)) }
    }
}

@Composable
private fun AuditLine(label: String, values: List<String>) {
    Text("$label · ${values.size}", fontWeight = FontWeight.Medium)
    if (values.isEmpty()) Text("None found", style = MaterialTheme.typography.bodySmall)
    else values.forEach { Text(it, style = MaterialTheme.typography.bodySmall) }
}

private fun formatAuditDate(timestamp: Long): String =
    java.text.DateFormat.getDateTimeInstance(java.text.DateFormat.MEDIUM, java.text.DateFormat.SHORT)
        .format(java.util.Date(timestamp))

@Composable
private fun SizeRow(label: String, bytes: Long, emphasize: Boolean = false) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(label, fontWeight = if (emphasize) FontWeight.SemiBold else FontWeight.Normal)
        Text(
            formatStorageSize(bytes),
            fontWeight = if (emphasize) FontWeight.SemiBold else FontWeight.Normal,
        )
    }
}

@Composable
private fun LargestItemRow(item: StoredItemSize) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(14.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f).padding(end = 12.dp)) {
                Text(item.title, maxLines = 1, overflow = TextOverflow.Ellipsis, fontWeight = FontWeight.Medium)
                Text(
                    "${item.category.lowercase().replaceFirstChar { it.uppercase() }}${if (item.isInBin) " · Bin" else ""}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Text(formatStorageSize(item.bytes), style = MaterialTheme.typography.labelLarge)
        }
    }
}

private fun formatStorageSize(bytes: Long): String {
    if (bytes < 1_000) return "$bytes B"
    val units = listOf("KB", "MB", "GB", "TB")
    var value = bytes.toDouble()
    var unitIndex = -1
    do {
        value /= 1_000.0
        unitIndex += 1
    } while (value >= 1_000.0 && unitIndex < units.lastIndex)
    return String.format(Locale.getDefault(), "%.1f %s", value, units[unitIndex])
}
