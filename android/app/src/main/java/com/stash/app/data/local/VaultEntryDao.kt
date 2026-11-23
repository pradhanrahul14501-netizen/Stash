package com.stash.app.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query

@Dao
interface VaultEntryDao {
    @Query("SELECT * FROM vault_entries ORDER BY savedAt DESC")
    suspend fun getAll(): List<VaultEntryEntity>

    @Insert
    suspend fun insert(entry: VaultEntryEntity)

    @Insert
    suspend fun insertAll(entries: List<VaultEntryEntity>)

    @Query("DELETE FROM vault_entries WHERE id = :id")
    suspend fun deleteById(id: String)

    @Query("DELETE FROM vault_entries")
    suspend fun deleteAll()
}
