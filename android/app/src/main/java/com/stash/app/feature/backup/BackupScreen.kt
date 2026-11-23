package com.stash.app.feature.backup

import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.text.KeyboardOptions
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
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.stash.app.data.backup.EncryptedBackupRepository
import kotlinx.coroutines.launch

@Composable
fun BackupScreen(
    repository: EncryptedBackupRepository,
    hasVault: Boolean,
    onBack: () -> Unit,
) {
    BackHandler(onBack = onBack)
    val scope = rememberCoroutineScope()
    var canRestore by remember { mutableStateOf(false) }
    var selectedAction by remember { mutableStateOf<BackupAction?>(null) }
    var selectedUri by remember { mutableStateOf<Uri?>(null) }
    var isBusy by remember { mutableStateOf(false) }
    var statusMessage by remember { mutableStateOf<String?>(null) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var backupPassword by remember { mutableStateOf("") }
    var backupPasswordConfirmation by remember { mutableStateOf("") }
    var currentVaultPassword by remember { mutableStateOf("") }
    var restorePassword by remember { mutableStateOf("") }
    var newVaultPassword by remember { mutableStateOf("") }
    var newVaultPasswordConfirmation by remember { mutableStateOf("") }

    LaunchedEffect(repository) { canRestore = repository.canRestore() }

    val createBackup = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.CreateDocument(MIME_TYPE),
    ) { uri ->
        if (uri != null) {
            selectedUri = uri
            selectedAction = BackupAction.EXPORT
            errorMessage = null
        }
    }
    val chooseBackup = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenDocument(),
    ) { uri ->
        if (uri != null) {
            selectedUri = uri
            selectedAction = BackupAction.RESTORE
            errorMessage = null
        }
    }

    Scaffold(containerColor = MaterialTheme.colorScheme.background) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 20.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            item {
                Column(modifier = Modifier.padding(top = 20.dp)) {
                    TextButton(onClick = onBack) { Text("‹  Library") }
                    Text(
                        "Backup and restore",
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    Text(
                        "Create a password-protected copy of this phone’s Stash library and Vault.",
                        modifier = Modifier.padding(top = 6.dp),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            item {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                    Column(Modifier.padding(16.dp)) {
                        Text("Encrypted backup", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                        Text(
                            "Stash encrypts the backup with a password you choose. Keep that password separately; Stash cannot recover it.",
                            modifier = Modifier.padding(top = 6.dp),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Button(
                            onClick = { createBackup.launch("stash-backup.stashbackup") },
                            enabled = !isBusy,
                            modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                        ) {
                            Text("Export encrypted backup")
                        }
                    }
                }
            }
            item {
                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                    Column(Modifier.padding(16.dp)) {
                        Text("Restore on a new or empty install", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                        Text(
                            "Restore adds your saved files and creates a new Vault key protected by the new Vault password you choose. Existing Stash data is never overwritten.",
                            modifier = Modifier.padding(top = 6.dp),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Button(
                            onClick = { chooseBackup.launch(arrayOf("*/*")) },
                            enabled = canRestore && !isBusy,
                            modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                        ) {
                            Text(if (canRestore) "Choose backup to restore" else "Restore requires an empty install")
                        }
                    }
                }
            }
            if (isBusy) {
                item { CircularProgressIndicator() }
            }
            statusMessage?.let { message ->
                item { Text(message, color = MaterialTheme.colorScheme.primary) }
            }
            errorMessage?.let { message ->
                item { Text(message, color = MaterialTheme.colorScheme.error) }
            }
            item { Spacer(Modifier.height(24.dp)) }
        }
    }

    selectedAction?.let { action ->
        AlertDialog(
            onDismissRequest = { if (!isBusy) selectedAction = null },
            title = { Text(if (action == BackupAction.EXPORT) "Protect this backup" else "Restore Stash data") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (action == BackupAction.EXPORT) {
                        Text("Use at least 12 characters. You’ll need this password to restore the backup.")
                        PasswordField(backupPassword, { backupPassword = it }, "Backup password")
                        PasswordField(backupPasswordConfirmation, { backupPasswordConfirmation = it }, "Confirm backup password")
                        if (hasVault) {
                            PasswordField(currentVaultPassword, { currentVaultPassword = it }, "Current Vault password")
                        }
                    } else {
                        Text("Restore is allowed only when this installation has no saved items or Vault.")
                        PasswordField(restorePassword, { restorePassword = it }, "Backup password")
                        PasswordField(newVaultPassword, { newVaultPassword = it }, "New Vault password, if included")
                        PasswordField(newVaultPasswordConfirmation, { newVaultPasswordConfirmation = it }, "Confirm new Vault password")
                    }
                    errorMessage?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    val uri = selectedUri ?: return@TextButton
                    errorMessage = when {
                        action == BackupAction.EXPORT && backupPassword.length < MIN_PASSWORD_LENGTH ->
                            "Use at least 12 characters for the backup password."
                        action == BackupAction.EXPORT && backupPassword != backupPasswordConfirmation ->
                            "The backup passwords do not match."
                        action == BackupAction.EXPORT && hasVault && currentVaultPassword.isBlank() ->
                            "Enter your current Vault password."
                        action == BackupAction.RESTORE && restorePassword.length < MIN_PASSWORD_LENGTH ->
                            "Enter the backup password."
                        action == BackupAction.RESTORE &&
                            (newVaultPassword.isNotEmpty() || newVaultPasswordConfirmation.isNotEmpty()) &&
                            newVaultPassword != newVaultPasswordConfirmation ->
                            "The new Vault passwords do not match."
                        else -> null
                    }
                    if (errorMessage != null) return@TextButton

                    isBusy = true
                    scope.launch {
                        try {
                            val result = if (action == BackupAction.EXPORT) {
                                repository.export(uri, backupPassword, currentVaultPassword.takeIf { hasVault })
                            } else {
                                repository.restore(uri, restorePassword, newVaultPassword)
                            }
                            statusMessage = if (action == BackupAction.EXPORT) {
                                "Backup saved: ${result.libraryItemCount} library items, ${result.vaultItemCount} Vault items, and ${result.followUpCount} Ava reminders."
                            } else {
                                "Restore complete: ${result.libraryItemCount} library items, ${result.vaultItemCount} Vault items, and ${result.followUpCount} Ava reminders."
                            }
                            canRestore = repository.canRestore()
                            selectedAction = null
                            errorMessage = null
                        } catch (error: Exception) {
                            errorMessage = error.message ?: "Stash could not complete this backup operation."
                        } finally {
                            isBusy = false
                            backupPassword = ""
                            backupPasswordConfirmation = ""
                            currentVaultPassword = ""
                            restorePassword = ""
                            newVaultPassword = ""
                            newVaultPasswordConfirmation = ""
                        }
                    }
                }, enabled = !isBusy) {
                    Text(if (isBusy) "Working…" else if (action == BackupAction.EXPORT) "Create backup" else "Restore")
                }
            },
            dismissButton = {
                TextButton(onClick = { selectedAction = null }, enabled = !isBusy) { Text("Cancel") }
            },
        )
    }
}

@Composable
private fun PasswordField(value: String, onValueChange: (String) -> Unit, label: String) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        modifier = Modifier.fillMaxWidth(),
        label = { Text(label) },
        singleLine = true,
        visualTransformation = PasswordVisualTransformation(),
        keyboardOptions = KeyboardOptions(keyboardType = androidx.compose.ui.text.input.KeyboardType.Password),
    )
}

private enum class BackupAction { EXPORT, RESTORE }

private const val MIME_TYPE = "application/vnd.com.stash.backup"
private const val MIN_PASSWORD_LENGTH = 12
