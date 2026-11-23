package com.stash.app.data.local

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey
import androidx.room.ColumnInfo

@Entity(
    tableName = "library_items",
    indices = [Index(value = ["savedAt"])],
)
data class LibraryItemEntity(
    @PrimaryKey val id: String,
    val title: String,
    val category: String,
    val mimeType: String,
    val savedAt: Long,
    val contentText: String? = null,
    val relativePath: String? = null,
    val byteSize: Long = 0L,
    @ColumnInfo(defaultValue = "'GENERAL'") val mode: String = "GENERAL",
    val deletedAt: Long? = null,
    val ocrText: String? = null,
    val folderName: String? = null,
    @ColumnInfo(defaultValue = "'[]'") val tagsJson: String = "[]",
    @ColumnInfo(defaultValue = "0") val isFavorite: Boolean = false,
    val sharedItemId: Long? = null,
)
