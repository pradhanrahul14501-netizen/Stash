package com.stash.app.data.local

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "vault_entries",
    indices = [Index(value = ["savedAt"])],
)
data class VaultEntryEntity(
    @PrimaryKey val id: String,
    val savedAt: Long,
    val iv: String,
    val encryptedPayload: String,
)
