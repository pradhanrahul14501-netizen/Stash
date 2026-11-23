package com.stash.app.data.local

import androidx.room.Database
import androidx.room.RoomDatabase
import com.stash.app.data.local.MIGRATION_1_2

@Database(
    entities = [LibraryItemEntity::class, LibraryFolderEntity::class, VaultEntryEntity::class, AvaFollowUpEntity::class],
    version = 8,
    exportSchema = false,
)
abstract class StashDatabase : RoomDatabase() {
    abstract fun libraryItemDao(): LibraryItemDao
    abstract fun vaultEntryDao(): VaultEntryDao
    abstract fun avaFollowUpDao(): AvaFollowUpDao
}
