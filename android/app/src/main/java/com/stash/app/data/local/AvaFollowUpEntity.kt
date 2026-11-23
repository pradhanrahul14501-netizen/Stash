package com.stash.app.data.local

import androidx.room.Entity
import androidx.room.ColumnInfo
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "ava_follow_ups",
    indices = [
        Index(value = ["remindAt"]),
        Index(value = ["sourceItemId", "eventAt"], unique = true),
    ],
    foreignKeys = [
        ForeignKey(
            entity = LibraryItemEntity::class,
            parentColumns = ["id"],
            childColumns = ["sourceItemId"],
            onDelete = ForeignKey.CASCADE,
        ),
    ],
)
data class AvaFollowUpEntity(
    @PrimaryKey val id: String,
    val sourceItemId: String,
    val sourceTitle: String,
    val eventLabel: String,
    val sourceExcerpt: String,
    val eventAt: Long,
    val remindAt: Long,
    val createdAt: Long,
    val notifiedAt: Long? = null,
    @ColumnInfo(defaultValue = "0") val updatedAt: Long = createdAt,
    val deletedAt: Long? = null,
)
