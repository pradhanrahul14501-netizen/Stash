package com.stash.app.feature.vault

import android.app.Activity
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.stash.app.data.vault.VaultPasswordException
import com.stash.app.data.vault.VaultRepository
import com.stash.app.data.vault.VaultSecret
import com.stash.app.data.vault.VaultBiometricAccess
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class VaultUiState(
    val hasVault: Boolean,
    val isUnlocked: Boolean = false,
    val isBusy: Boolean = false,
    val entries: List<VaultSecret> = emptyList(),
    val error: String? = null,
    val message: String? = null,
    val isBiometricEnabled: Boolean = false,
)

class VaultViewModel(private val repository: VaultRepository) : ViewModel() {
    private val mutableState = MutableStateFlow(
        VaultUiState(
            hasVault = repository.hasVault(),
            isBiometricEnabled = repository.hasBiometricUnlock(),
        ),
    )
    val state = mutableState.asStateFlow()
    private var sessionKey: ByteArray? = null
    private val sessionGeneration = VaultSessionGeneration()
    private var isDrainingShares = false
    private val pendingSharedItems = mutableListOf<PendingSharedItem>()

    fun createVault(password: String, confirmation: String) {
        when {
            password.length < MIN_PASSWORD_LENGTH -> {
                setError("Choose a password with at least 12 characters.")
                return
            }
            password != confirmation -> {
                setError("The passwords do not match.")
                return
            }
            else -> Unit
        }

        val operationGeneration = sessionGeneration.capture()
        mutableState.value = mutableState.value.copy(isBusy = true, error = null, message = null)
        viewModelScope.launch {
            var key: ByteArray? = null
            try {
                val createdKey = repository.create(password)
                key = createdKey
                val savedEntries = repository.entries(createdKey)
                if (!sessionGeneration.isCurrent(operationGeneration)) {
                    createdKey.fill(0)
                    mutableState.value = lockedState()
                    return@launch
                }
                sessionKey?.fill(0)
                sessionKey = createdKey
                sessionGeneration.advance()
                mutableState.value = VaultUiState(
                    hasVault = true,
                    isUnlocked = true,
                    entries = savedEntries,
                    message = "Vault created. Keep your password safe; it cannot be reset.",
                )
                drainPendingShares()
            } catch (error: Exception) {
                key?.fill(0)
                if (!sessionGeneration.isCurrent(operationGeneration)) return@launch
                mutableState.value = mutableState.value.copy(
                    hasVault = repository.hasVault(),
                    isUnlocked = false,
                    isBusy = false,
                    entries = emptyList(),
                    error = error.message ?: "Could not create the Vault.",
                )
            }
        }
    }

    fun unlock(password: String) {
        if (password.isBlank()) {
            setError("Enter your Vault password.")
            return
        }
        unlockUsing { repository.unlock(password) }
    }

    fun unlockWithBiometric(activity: Activity, biometricAccess: VaultBiometricAccess) {
        val envelope = repository.biometricEnvelope()
        if (envelope == null) {
            setError("Biometric unlock is not set up. Use your Vault password.")
            return
        }
        unlockUsing { biometricAccess.unwrapDataKey(activity, envelope) }
    }

    private fun unlockUsing(loadDataKey: suspend () -> ByteArray) {
        val operationGeneration = sessionGeneration.capture()
        mutableState.value = mutableState.value.copy(isBusy = true, error = null, message = null)
        viewModelScope.launch {
            var key: ByteArray? = null
            try {
                val unlockedKey = loadDataKey()
                key = unlockedKey
                val savedEntries = repository.entries(unlockedKey)
                if (!sessionGeneration.isCurrent(operationGeneration)) {
                    unlockedKey.fill(0)
                    mutableState.value = lockedState()
                    return@launch
                }
                sessionKey?.fill(0)
                sessionKey = unlockedKey
                sessionGeneration.advance()
                mutableState.value = VaultUiState(
                    hasVault = true,
                    isUnlocked = true,
                    entries = savedEntries,
                    isBiometricEnabled = repository.hasBiometricUnlock(),
                )
                drainPendingShares()
            } catch (cancelled: kotlinx.coroutines.CancellationException) {
                key?.fill(0)
                if (sessionGeneration.isCurrent(operationGeneration)) {
                    mutableState.value = lockedState()
                }
            } catch (error: Exception) {
                key?.fill(0)
                if (!sessionGeneration.isCurrent(operationGeneration)) return@launch
                mutableState.value = mutableState.value.copy(
                    hasVault = repository.hasVault(),
                    isUnlocked = false,
                    isBusy = false,
                    entries = emptyList(),
                    isBiometricEnabled = repository.hasBiometricUnlock(),
                    error = if (error is VaultPasswordException) {
                        "Wrong password. Try again."
                    } else {
                        error.message ?: "Could not unlock the Vault."
                    },
                )
            }
        }
    }

    fun enableBiometric(activity: Activity, biometricAccess: VaultBiometricAccess) {
        val activeKey = sessionKey?.copyOf() ?: run {
            lock()
            return
        }
        val operationGeneration = sessionGeneration.capture()
        mutableState.value = mutableState.value.copy(isBusy = true, error = null, message = null)
        viewModelScope.launch {
            try {
                val envelope = biometricAccess.wrapDataKey(activity, activeKey)
                if (!sessionGeneration.isCurrent(operationGeneration) || sessionKey == null) return@launch
                repository.saveBiometricEnvelope(envelope)
                mutableState.value = mutableState.value.copy(
                    isBusy = false,
                    isBiometricEnabled = true,
                    message = "Biometric Vault unlock is enabled on this device.",
                )
            } catch (cancelled: kotlinx.coroutines.CancellationException) {
                if (sessionGeneration.isCurrent(operationGeneration)) {
                    mutableState.value = mutableState.value.copy(isBusy = false)
                }
            } catch (error: Exception) {
                if (!sessionGeneration.isCurrent(operationGeneration)) return@launch
                mutableState.value = mutableState.value.copy(
                    isBusy = false,
                    error = error.message ?: "Could not enable biometric Vault unlock.",
                )
            } finally {
                activeKey.fill(0)
            }
        }
    }

    fun disableBiometric(biometricAccess: VaultBiometricAccess) {
        runCatching {
            repository.clearBiometricEnvelope()
            biometricAccess.deleteBiometricKey()
            mutableState.value = mutableState.value.copy(
                isBiometricEnabled = false,
                message = "Biometric Vault unlock is disabled.",
            )
        }.onFailure { error ->
            mutableState.value = mutableState.value.copy(
                error = error.message ?: "Could not disable biometric Vault unlock.",
            )
        }
    }

    fun saveSecret(title: String, account: String, secret: String, notes: String) {
        if (title.isBlank()) {
            setError("Add a name for this item.")
            return
        }
        if (secret.isBlank()) {
            setError("Add the password or detail you want to protect.")
            return
        }
        val key = sessionKey?.copyOf() ?: run {
            lock()
            return
        }
        mutableState.value = mutableState.value.copy(isBusy = true, error = null, message = null)
        viewModelScope.launch {
            try {
                repository.save(key, title, account, secret, notes)
                val savedEntries = repository.entries(key)
                mutableState.value = mutableState.value.copy(
                    isBusy = false,
                    entries = savedEntries,
                    message = "Saved securely in Vault.",
                )
            } catch (error: Exception) {
                mutableState.value = mutableState.value.copy(
                    isBusy = false,
                    error = error.message ?: "Could not save this Vault item.",
                )
            } finally {
                key.fill(0)
            }
        }
    }

    /** Keeps incoming secrets only in memory until the user creates or unlocks Vault. */
    fun receiveSensitiveShare(text: String?, suggestedTitle: String) {
        val secret = text?.trim()?.takeIf(String::isNotEmpty) ?: return
        pendingSharedItems += PendingSharedItem(
            id = java.util.UUID.randomUUID().toString(),
            title = suggestedTitle,
            secret = secret,
        )
        mutableState.value = mutableState.value.copy(
            isBusy = mutableState.value.isBusy,
            error = null,
            message = if (sessionKey == null) {
                "Sensitive text is waiting in memory. Create or unlock Vault to save it."
            } else {
                "Saving shared detail securely in Vault…"
            },
        )
        drainPendingShares()
    }

    private fun drainPendingShares() {
        if (isDrainingShares || pendingSharedItems.isEmpty()) return
        val activeKey = sessionKey?.copyOf() ?: return
        val activeGeneration = sessionGeneration.capture()
        isDrainingShares = true
        mutableState.value = mutableState.value.copy(isBusy = true, error = null)
        viewModelScope.launch {
            var savedCount = 0
            var saveFailed = false
            try {
                while (pendingSharedItems.isNotEmpty() && sessionGeneration.isCurrent(activeGeneration)) {
                    val pending = pendingSharedItems.first()
                    repository.save(
                        key = activeKey,
                        title = pending.title,
                        account = "",
                        secret = pending.secret,
                        notes = "",
                    )
                    if (pendingSharedItems.firstOrNull()?.id == pending.id) {
                        pendingSharedItems.removeAt(0)
                    } else {
                        pendingSharedItems.removeAll { it.id == pending.id }
                    }
                    savedCount += 1
                }

                if (sessionGeneration.isCurrent(activeGeneration) && sessionKey != null) {
                    val savedEntries = repository.entries(activeKey)
                    mutableState.value = mutableState.value.copy(
                        isBusy = false,
                        entries = savedEntries,
                        error = null,
                        message = when {
                            pendingSharedItems.isNotEmpty() -> "Some shared details are still waiting to be saved."
                            savedCount > 0 -> "Shared detail saved securely in Vault."
                            else -> mutableState.value.message
                        },
                    )
                }
            } catch (error: Exception) {
                saveFailed = true
                if (sessionGeneration.isCurrent(activeGeneration) && sessionKey != null) {
                    val failureMessage = if (pendingSharedItems.isNotEmpty()) {
                        "Could not save shared text to Vault. It is still waiting here and was not added to Library."
                    } else {
                        "Shared text was saved, but Vault could not refresh its list. Reopen Vault to check it."
                    }
                    mutableState.value = mutableState.value.copy(
                        isBusy = false,
                        error = failureMessage,
                        message = null,
                    )
                }
            } finally {
                activeKey.fill(0)
                isDrainingShares = false
                if (!saveFailed && sessionKey != null && pendingSharedItems.isNotEmpty()) {
                    drainPendingShares()
                }
            }
        }
    }

    fun deleteSecret(id: String) {
        val key = sessionKey?.copyOf() ?: run {
            lock()
            return
        }
        mutableState.value = mutableState.value.copy(isBusy = true, error = null, message = null)
        viewModelScope.launch {
            try {
                repository.delete(id)
                val savedEntries = repository.entries(key)
                mutableState.value = mutableState.value.copy(
                    isBusy = false,
                    entries = savedEntries,
                    message = "Vault item deleted.",
                )
            } catch (error: Exception) {
                mutableState.value = mutableState.value.copy(
                    isBusy = false,
                    error = error.message ?: "Could not delete this Vault item.",
                )
            } finally {
                key.fill(0)
            }
        }
    }

    fun clearNotice() {
        mutableState.value = mutableState.value.copy(error = null, message = null)
    }

    fun lock() {
        sessionGeneration.advance()
        sessionKey?.fill(0)
        sessionKey = null
        mutableState.value = lockedState()
    }

    private fun lockedState() = VaultUiState(
        hasVault = repository.hasVault(),
        isBiometricEnabled = repository.hasBiometricUnlock(),
        message = if (pendingSharedItems.isNotEmpty()) {
            "Sensitive text is waiting in memory. Unlock Vault to save it."
        } else {
            null
        },
    )

    private fun setError(message: String) {
        mutableState.value = mutableState.value.copy(isBusy = false, error = message, message = null)
    }

    class Factory(private val repository: VaultRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            if (modelClass.isAssignableFrom(VaultViewModel::class.java)) {
                return VaultViewModel(repository) as T
            }
            throw IllegalArgumentException("Unknown ViewModel: ${modelClass.name}")
        }
    }

    private companion object {
        const val MIN_PASSWORD_LENGTH = 12
    }

    private data class PendingSharedItem(
        val id: String,
        val title: String,
        val secret: String,
    )
}
