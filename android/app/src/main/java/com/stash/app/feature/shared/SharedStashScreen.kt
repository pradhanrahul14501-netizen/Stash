package com.stash.app.feature.shared

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import com.stash.app.data.shared.SharedStashRepository
import com.stash.app.data.shared.SharedSyncPreview
import kotlinx.coroutines.launch

@Composable
fun SharedStashScreen(repository: SharedStashRepository, onBack: () -> Unit) {
    BackHandler(onBack = onBack)
    val scope = rememberCoroutineScope()
    var serverUrl by remember { mutableStateOf(repository.serverUrl()) }
    var email by remember { mutableStateOf(repository.identity()) }
    var password by remember { mutableStateOf("") }
    var connected by remember { mutableStateOf(repository.isConnected()) }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf<String?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var syncPreview by remember { mutableStateOf<SharedSyncPreview?>(null) }

    Scaffold(containerColor = MaterialTheme.colorScheme.background) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding).padding(horizontal = 20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Column(modifier = Modifier.padding(top = 18.dp)) {
                    TextButton(onClick = onBack) { Text("‹  Library") }
                    Text("Shared Stash", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                    Text(
                        "Connect this phone to your Shared Stash account and sync saved library items.",
                        modifier = Modifier.padding(top = 6.dp),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            if (connected) {
                item {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("Connected as ${repository.identity()}", fontWeight = FontWeight.SemiBold)
                        OutlinedTextField(
                            value = serverUrl,
                            onValueChange = { serverUrl = it },
                            modifier = Modifier.fillMaxWidth(),
                            readOnly = true,
                            label = { Text("Shared Stash address") },
                        )
                        Button(
                            onClick = {
                                busy = true
                                error = null
                                message = null
                                scope.launch {
                                    try {
                                        syncPreview = repository.previewSync()
                                    } catch (failure: Exception) {
                                        error = failure.message ?: "Could not prepare the sync."
                                    } finally {
                                        busy = false
                                    }
                                }
                            },
                            modifier = Modifier.fillMaxWidth(),
                            enabled = !busy,
                        ) { Text("Review sync") }
                        TextButton(
                            onClick = {
                                busy = true
                                scope.launch {
                                    runCatching { repository.signOut() }
                                    connected = false
                                    message = "Disconnected from Shared Stash."
                                    busy = false
                                }
                            },
                            enabled = !busy,
                        ) { Text("Disconnect account") }
                    }
                }
            } else {
                item {
                    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        OutlinedTextField(
                            value = serverUrl,
                            onValueChange = { serverUrl = it },
                            modifier = Modifier.fillMaxWidth(),
                            singleLine = true,
                            label = { Text("Shared Stash HTTPS address") },
                            placeholder = { Text("https://stash.example.com") },
                        )
                        OutlinedTextField(
                            value = email,
                            onValueChange = { email = it },
                            modifier = Modifier.fillMaxWidth(),
                            singleLine = true,
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                            label = { Text("Verified email") },
                        )
                        OutlinedTextField(
                            value = password,
                            onValueChange = { password = it },
                            modifier = Modifier.fillMaxWidth(),
                            singleLine = true,
                            visualTransformation = PasswordVisualTransformation(),
                            label = { Text("Password") },
                        )
                        Button(
                            onClick = {
                                busy = true
                                error = null
                                message = null
                                scope.launch {
                                    try {
                                        repository.signIn(serverUrl, email, password)
                                        connected = true
                                        password = ""
                                        message = "Connected. Review the items before syncing."
                                    } catch (failure: Exception) {
                                        error = failure.message ?: "Could not connect to Shared Stash."
                                    } finally {
                                        busy = false
                                    }
                                }
                            },
                            modifier = Modifier.fillMaxWidth(),
                            enabled = !busy && serverUrl.isNotBlank() && email.isNotBlank() && password.isNotBlank(),
                        ) { Text("Connect account") }
                    }
                }
                item {
                    Text(
                        "Sign-in uses Shared Stash’s verified Firebase email account. Your password is used only to sign in; Stash stores an encrypted session token on this phone.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            if (busy) item { CircularProgressIndicator() }
            message?.let { item { Text(it, color = MaterialTheme.colorScheme.primary) } }
            error?.let { item { Text(it, color = MaterialTheme.colorScheme.error) } }
            item {
                Spacer(Modifier.height(20.dp))
                Text(
                    "Sync sends saved library text and file contents to the connected Shared Stash account. Vault entries are never synced. Bin items are left in the local Bin.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }

    syncPreview?.let { preview ->
        AlertDialog(
            onDismissRequest = { syncPreview = null },
            title = { Text("Sync saved items?") },
            text = {
                Text(
                    "Your phone has ${preview.savedItems} active library items, including ${preview.fileCount} files (${formatBytes(preview.fileBytes)}). Sync will upload these and download items already saved in ${repository.identity()}’s Shared Stash. Item text, folders, tags, and Favorites are included. Vault and Bin items are excluded.",
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    syncPreview = null
                    busy = true
                    error = null
                    message = null
                    scope.launch {
                        try {
                            val result = repository.syncNow()
                            message = "Sync complete: ${result.uploaded} uploaded, ${result.downloaded} downloaded, ${result.updated} updated."
                        } catch (failure: Exception) {
                            error = failure.message ?: "Shared Stash sync did not finish."
                        } finally {
                            busy = false
                        }
                    }
                }) { Text("Sync now") }
            },
            dismissButton = {
                TextButton(onClick = { syncPreview = null }) { Text("Cancel") }
            },
        )
    }
}

private fun formatBytes(bytes: Long): String {
    if (bytes < 1_000) return "$bytes B"
    val units = listOf("KB", "MB", "GB", "TB")
    var value = bytes.toDouble()
    var index = -1
    do {
        value /= 1_000.0
        index += 1
    } while (value >= 1_000 && index < units.lastIndex)
    return "%.1f %s".format(value, units[index])
}
