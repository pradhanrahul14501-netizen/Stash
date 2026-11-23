package com.stash.app.feature.mobilecompanion

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
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.stash.app.data.mobilecompanion.MobileAction
import com.stash.app.data.mobilecompanion.MobileCompanionRepository
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay

@Composable
fun MobileCompanionScreen(
    repository: MobileCompanionRepository,
    onBack: () -> Unit,
) {
    BackHandler(onBack = onBack)
    val scope = rememberCoroutineScope()
    var address by remember { mutableStateOf("") }
    var code by remember { mutableStateOf("") }
    var connected by remember { mutableStateOf(repository.connection() != null) }
    var actions by remember { mutableStateOf<List<MobileAction>>(emptyList()) }
    var status by remember { mutableStateOf<String?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var syncedFollowUpCount by remember { mutableStateOf<Int?>(null) }

    fun refresh() {
        if (busy) return
        busy = true
        error = null
        scope.launch {
            runCatching {
                val count = repository.syncFollowUps()
                val pending = repository.actions()
                count to pending
            }.onSuccess { (count, pending) ->
                syncedFollowUpCount = count
                actions = pending
                status = "Reminders synced. ${pending.size} Ava file ${if (pending.size == 1) "preview is" else "previews are"} waiting for review."
            }.onFailure {
                error = it.message ?: "Could not refresh the desktop link."
            }
            busy = false
        }
    }

    LaunchedEffect(connected) {
        if (!connected) return@LaunchedEffect
        refresh()
        while (true) {
            delay(5_000)
            if (!busy) {
                runCatching { repository.actions() }.onSuccess { actions = it }
            }
        }
    }

    Scaffold { insets ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(insets)
                .padding(horizontal = 20.dp, vertical = 18.dp),
        ) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Connect desktop", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                TextButton(onClick = onBack) { Text("Back") }
            }
            Text(
                "Pair on the same private Wi-Fi. Ava file changes still run on desktop Stash after you approve the exact preview here.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(18.dp))

            if (!connected) {
                OutlinedTextField(
                    value = address,
                    onValueChange = { address = it.trim() },
                    label = { Text("Desktop address") },
                    placeholder = { Text("http://192.168.1.20:5052") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(
                    value = code,
                    onValueChange = { code = it.uppercase().take(16) },
                    label = { Text("One-time pairing code") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(12.dp))
                Button(
                    enabled = !busy && address.isNotBlank() && code.isNotBlank(),
                    onClick = {
                        busy = true
                        error = null
                        scope.launch {
                            runCatching { repository.pair(address, code) }
                                .onSuccess {
                                    connected = true
                                    code = ""
                                    status = "Android Stash is paired with desktop Stash."
                                }
                                .onFailure { error = it.message ?: "Could not pair with desktop Stash." }
                            busy = false
                        }
                    },
                ) { Text(if (busy) "Connecting…" else "Connect phone") }
            } else {
                Text("Paired with desktop Stash", fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.primary)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(enabled = !busy, onClick = ::refresh) { Text(if (busy) "Syncing…" else "Refresh inbox + reminders") }
                    OutlinedButton(
                        enabled = !busy,
                        onClick = {
                            busy = true
                            scope.launch {
                                repository.unpair()
                                actions = emptyList()
                                connected = false
                                syncedFollowUpCount = null
                                status = "This phone has been unpaired."
                                busy = false
                            }
                        },
                    ) { Text("Unpair") }
                }
                syncedFollowUpCount?.let { count ->
                    Text("$count Ava Follow-ups are synced with desktop Stash.", style = MaterialTheme.typography.bodySmall)
                }
                Spacer(Modifier.height(10.dp))
                Text("Ava Action Inbox", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
                if (actions.isEmpty()) {
                    Text("No file previews are waiting. When Ava asks for desktop approval, the preview will appear here.", modifier = Modifier.padding(vertical = 10.dp))
                }
                LazyColumn(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    items(actions, key = MobileAction::id) { action ->
                        ActionCard(
                            action = action,
                            enabled = !busy,
                            onDecision = { approved ->
                                busy = true
                                scope.launch {
                                    runCatching { repository.decide(action.id, approved) }
                                        .onSuccess {
                                            actions = actions.filterNot { it.id == action.id }
                                            status = if (approved) "Approved. Desktop Stash is carrying out this preview." else "Declined. Desktop Stash will leave the files unchanged."
                                            if (approved) {
                                                scope.launch {
                                                    runCatching { repository.awaitActionResult(action.id) }
                                                        .onSuccess { result ->
                                                            status = result.message.ifBlank {
                                                                if (result.status == "executed") "The approved action is complete."
                                                                else "Desktop Stash could not complete the approved action."
                                                            }
                                                            if (result.status == "error") error = status
                                                        }
                                                        .onFailure { error = it.message ?: "Desktop Stash has not reported the action result yet." }
                                                }
                                            }
                                        }
                                        .onFailure { error = it.message ?: "This preview could not be sent to desktop Stash." }
                                    busy = false
                                }
                            },
                        )
                    }
                }
            }

            status?.let { Text(it, modifier = Modifier.padding(top = 10.dp), color = MaterialTheme.colorScheme.primary) }
            error?.let { Text(it, modifier = Modifier.padding(top = 8.dp), color = MaterialTheme.colorScheme.error) }
        }
    }
}

@Composable
private fun ActionCard(action: MobileAction, enabled: Boolean, onDecision: (Boolean) -> Unit) {
    val context = LocalContext.current
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerHigh)) {
        Column(Modifier.fillMaxWidth().padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(action.preview.operation.replace('_', ' ').replaceFirstChar { it.titlecase() }, fontWeight = FontWeight.Bold)
            action.preview.message.takeIf(String::isNotBlank)?.let { Text(it) }
            if (action.preview.itemsTotal > 0) {
                Text("${action.preview.itemsTotal} ${if (action.preview.itemsTotal == 1) "item" else "items"} in this preview", style = MaterialTheme.typography.bodySmall)
            }
            if (action.preview.itemsTruncated) {
                Text(
                    "This preview is too large to show completely on the phone. Review it in desktop Stash before approving.",
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            action.preview.items.forEach { item ->
                Column {
                    item.path?.let { Text("From: $it", style = MaterialTheme.typography.bodySmall) }
                    item.destination?.let { Text("To: $it", style = MaterialTheme.typography.bodySmall) }
                    item.size?.let { Text("Size: ${android.text.format.Formatter.formatFileSize(context, it)}", style = MaterialTheme.typography.bodySmall) }
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(enabled = enabled && !action.preview.itemsTruncated, onClick = { onDecision(true) }) { Text("Approve on desktop") }
                OutlinedButton(enabled = enabled, onClick = { onDecision(false) }) { Text("Decline") }
            }
        }
    }
}
