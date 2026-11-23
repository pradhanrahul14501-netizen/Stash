package com.stash.app.feature.vault

import android.app.Activity
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.stash.app.data.vault.VaultSecret
import com.stash.app.data.vault.VaultBiometricAccess
import java.text.DateFormat
import java.util.Date

@Composable
fun VaultScreen(viewModel: VaultViewModel, activity: Activity, onBack: () -> Unit) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val biometricAccess = remember(activity) { VaultBiometricAccess() }
    val biometricAvailable = remember(activity) { biometricAccess.isAvailable(activity) }
    BackHandler(onBack = onBack)

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
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 18.dp, bottom = 16.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TextButton(onClick = onBack) { Text("‹  Library") }
                Spacer(Modifier.width(10.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        "Vault",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    Text(
                        "Encrypted on this device",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                if (state.isUnlocked) {
                    if (state.isBiometricEnabled) {
                        TextButton(
                            onClick = { viewModel.disableBiometric(biometricAccess) },
                            enabled = !state.isBusy,
                        ) { Text("Disable bio") }
                    } else if (biometricAvailable) {
                        TextButton(
                            onClick = { viewModel.enableBiometric(activity, biometricAccess) },
                            enabled = !state.isBusy,
                        ) { Text("Enable bio") }
                    }
                    TextButton(onClick = viewModel::lock) { Text("Lock") }
                }
            }

            state.error?.let { NoticeBox(text = it, isError = true) }
            state.message?.let { NoticeBox(text = it, isError = false) }

            when {
                state.isBusy && !state.isUnlocked -> Column(
                    modifier = Modifier.weight(1f).fillMaxWidth(),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center,
                ) {
                    CircularProgressIndicator(color = MaterialTheme.colorScheme.primary)
                    Spacer(Modifier.height(12.dp))
                    Text("Securing Vault…", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                !state.hasVault -> CreateVaultForm(
                    modifier = Modifier.weight(1f),
                    onCreate = viewModel::createVault,
                )
                !state.isUnlocked -> UnlockVaultForm(
                    modifier = Modifier.weight(1f),
                    onUnlock = viewModel::unlock,
                    canUnlockWithBiometric = state.isBiometricEnabled && biometricAvailable,
                    onUnlockWithBiometric = { viewModel.unlockWithBiometric(activity, biometricAccess) },
                )
                else -> UnlockedVault(
                    modifier = Modifier.weight(1f),
                    entries = state.entries,
                    saveMessage = state.message,
                    isBusy = state.isBusy,
                    onSave = viewModel::saveSecret,
                    onDelete = viewModel::deleteSecret,
                )
            }
        }
    }
}

@Composable
private fun CreateVaultForm(
    modifier: Modifier,
    onCreate: (String, String) -> Unit,
) {
    var password by remember { mutableStateOf("") }
    var confirmation by remember { mutableStateOf("") }

    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.Center,
    ) {
        Text("Create your Vault password", style = MaterialTheme.typography.headlineSmall)
        Spacer(Modifier.height(8.dp))
        Text(
            "Use at least 12 characters. Stash cannot reset or recover this password.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(18.dp))
        SecretTextField(
            value = password,
            onValueChange = { password = it },
            label = "Vault password",
            isPassword = true,
        )
        Spacer(Modifier.height(10.dp))
        SecretTextField(
            value = confirmation,
            onValueChange = { confirmation = it },
            label = "Confirm password",
            isPassword = true,
        )
        Spacer(Modifier.height(16.dp))
        Button(
            onClick = {
                onCreate(password, confirmation)
                if (password.length >= 12 && password == confirmation) {
                    password = ""
                    confirmation = ""
                }
            },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Create Vault")
        }
    }
}

@Composable
private fun UnlockVaultForm(
    modifier: Modifier,
    onUnlock: (String) -> Unit,
    canUnlockWithBiometric: Boolean,
    onUnlockWithBiometric: () -> Unit,
) {
    var password by remember { mutableStateOf("") }
    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.Center,
    ) {
        Text("Vault is locked", style = MaterialTheme.typography.headlineSmall)
        Spacer(Modifier.height(8.dp))
        Text(
            "Enter your Vault password to see saved details. If you forget it, the data cannot be recovered.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(18.dp))
        SecretTextField(
            value = password,
            onValueChange = { password = it },
            label = "Vault password",
            isPassword = true,
        )
        Spacer(Modifier.height(16.dp))
        Button(
            onClick = {
                onUnlock(password)
                password = ""
            },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Unlock Vault")
        }
        if (canUnlockWithBiometric) {
            Spacer(Modifier.height(8.dp))
            TextButton(onClick = onUnlockWithBiometric, modifier = Modifier.fillMaxWidth()) {
                Text("Unlock with fingerprint or face")
            }
        }
    }
}

@Composable
private fun UnlockedVault(
    modifier: Modifier,
    entries: List<VaultSecret>,
    saveMessage: String?,
    isBusy: Boolean,
    onSave: (String, String, String, String) -> Unit,
    onDelete: (String) -> Unit,
) {
    var title by remember { mutableStateOf("") }
    var account by remember { mutableStateOf("") }
    var secret by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }

    androidx.compose.runtime.LaunchedEffect(saveMessage) {
        if (saveMessage == "Saved securely in Vault.") {
            title = ""
            account = ""
            secret = ""
            notes = ""
        }
    }

    LazyColumn(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (isBusy) item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            ) {
                Column(Modifier.padding(16.dp)) {
                    Text("Save a protected detail", style = MaterialTheme.typography.titleMedium)
                    Spacer(Modifier.height(10.dp))
                    SecretTextField(title, { title = it }, "Name (for example, Bank account)")
                    Spacer(Modifier.height(8.dp))
                    SecretTextField(account, { account = it }, "Account or website")
                    Spacer(Modifier.height(8.dp))
                    SecretTextField(secret, { secret = it }, "Password or private detail", isPassword = true)
                    Spacer(Modifier.height(8.dp))
                    SecretTextField(notes, { notes = it }, "Notes")
                    Spacer(Modifier.height(12.dp))
                    Button(
                        onClick = {
                            onSave(title, account, secret, notes)
                        },
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !isBusy,
                    ) {
                        Text("Save in Vault")
                    }
                }
            }
        }

        if (entries.isEmpty()) {
            item {
                Text(
                    "No protected details saved yet.",
                    modifier = Modifier.padding(vertical = 14.dp),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        } else {
            item {
                Text(
                    "${entries.size} saved ${if (entries.size == 1) "detail" else "details"}",
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.padding(top = 4.dp),
                )
            }
            items(entries, key = VaultSecret::id) { entry ->
                VaultSecretCard(entry = entry, enabled = !isBusy, onDelete = onDelete)
            }
        }
        item { Spacer(Modifier.height(24.dp)) }
    }
}

@Composable
private fun VaultSecretCard(entry: VaultSecret, enabled: Boolean, onDelete: (String) -> Unit) {
    var revealSecret by remember(entry.id) { mutableStateOf(false) }
    var confirmDelete by remember(entry.id) { mutableStateOf(false) }
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
    ) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    entry.title,
                    modifier = Modifier.weight(1f),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                TextButton(onClick = { confirmDelete = true }, enabled = enabled) { Text("Delete") }
            }
            if (entry.account.isNotBlank()) {
                Text(entry.account, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    if (revealSecret) entry.secret else "••••••••",
                    modifier = Modifier.weight(1f),
                    style = MaterialTheme.typography.bodyLarge,
                )
                TextButton(onClick = { revealSecret = !revealSecret }) {
                    Text(if (revealSecret) "Hide" else "Show")
                }
            }
            if (entry.notes.isNotBlank()) {
                Text(
                    entry.notes,
                    modifier = Modifier.padding(top = 4.dp),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Text(
                "Saved ${DateFormat.getDateTimeInstance(DateFormat.MEDIUM, DateFormat.SHORT).format(Date(entry.savedAt))}",
                modifier = Modifier.padding(top = 8.dp),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }

    if (confirmDelete) {
        AlertDialog(
            onDismissRequest = { confirmDelete = false },
            title = { Text("Delete this Vault item?") },
            text = { Text("This removes the encrypted item from this device.") },
            confirmButton = {
                TextButton(
                    onClick = {
                        confirmDelete = false
                        onDelete(entry.id)
                    },
                ) { Text("Delete") }
            },
            dismissButton = {
                TextButton(onClick = { confirmDelete = false }) { Text("Cancel") }
            },
        )
    }
}

@Composable
private fun SecretTextField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    isPassword: Boolean = false,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        modifier = Modifier.fillMaxWidth(),
        label = { Text(label) },
        singleLine = !label.contains("Notes", ignoreCase = true),
        visualTransformation = if (isPassword) PasswordVisualTransformation() else androidx.compose.ui.text.input.VisualTransformation.None,
        keyboardOptions = if (isPassword) {
            KeyboardOptions(keyboardType = KeyboardType.Password)
        } else {
            KeyboardOptions.Default
        },
    )
}

@Composable
private fun NoticeBox(text: String, isError: Boolean) {
    Text(
        text = text,
        modifier = Modifier.padding(bottom = 8.dp),
        style = MaterialTheme.typography.bodyMedium,
        color = if (isError) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary,
    )
}
