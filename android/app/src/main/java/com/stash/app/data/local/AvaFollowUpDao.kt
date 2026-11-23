package com.stash.app.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface AvaFollowUpDao {
    @Query("SELECT * FROM ava_follow_ups WHERE deletedAt IS NULL ORDER BY remindAt ASC")
    fun observeAll(): Flow<List<AvaFollowUpEntity>>

    @Query("SELECT * FROM ava_follow_ups ORDER BY updatedAt ASC")
    suspend fun getAllForSync(): List<AvaFollowUpEntity>

    @Query("SELECT * FROM ava_follow_ups WHERE id = :id LIMIT 1")
    suspend fun getById(id: String): AvaFollowUpEntity?

    @Query("SELECT * FROM ava_follow_ups WHERE sourceItemId = :itemId AND eventAt = :eventAt LIMIT 1")
    suspend fun getForItemDate(itemId: String, eventAt: Long): AvaFollowUpEntity?

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insert(followUp: AvaFollowUpEntity): Long

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(followUp: AvaFollowUpEntity)

    @Query("UPDATE ava_follow_ups SET notifiedAt = :notifiedAt WHERE id = :id AND notifiedAt IS NULL")
    suspend fun markNotified(id: String, notifiedAt: Long)

    @Query("UPDATE ava_follow_ups SET deletedAt = :deletedAt, updatedAt = :deletedAt WHERE id = :id AND deletedAt IS NULL")
    suspend fun delete(id: String, deletedAt: Long)
}
