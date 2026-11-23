package com.stash.app.data.vault

data class VaultSecret(
    val id: String,
    val savedAt: Long,
    val title: String,
    val account: String,
    val secret: String,
    val notes: String,
)

class VaultPasswordException : Exception("That password did not unlock the Vault.")

class VaultStorageException(message: String, cause: Throwable? = null) :
    Exception(message, cause)
