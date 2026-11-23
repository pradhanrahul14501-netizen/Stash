package com.stash.app.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "library_folders")
data class LibraryFolderEntity(
    @PrimaryKey val name: String,
    val createdAt: Long,
)
