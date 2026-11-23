package com.stash.app.data.local

import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

val MIGRATION_1_2 = object : Migration(1, 2) {
    override fun migrate(database: SupportSQLiteDatabase) {
        database.execSQL(
            """CREATE TABLE IF NOT EXISTS `vault_entries` (
                `id` TEXT NOT NULL,
                `savedAt` INTEGER NOT NULL,
                `iv` TEXT NOT NULL,
                `encryptedPayload` TEXT NOT NULL,
                PRIMARY KEY(`id`)
            )""".trimIndent(),
        )
        database.execSQL(
            "CREATE INDEX IF NOT EXISTS `index_vault_entries_savedAt` " +
                "ON `vault_entries` (`savedAt`)"
        )
    }
}

val MIGRATION_2_3 = object : Migration(2, 3) {
    override fun migrate(database: SupportSQLiteDatabase) {
        database.execSQL(
            "ALTER TABLE `library_items` ADD COLUMN `mode` TEXT NOT NULL DEFAULT 'GENERAL'",
        )
    }
}

val MIGRATION_3_4 = object : Migration(3, 4) {
    override fun migrate(database: SupportSQLiteDatabase) {
        database.execSQL("ALTER TABLE `library_items` ADD COLUMN `deletedAt` INTEGER")
    }
}

val MIGRATION_4_5 = object : Migration(4, 5) {
    override fun migrate(database: SupportSQLiteDatabase) {
        database.execSQL("ALTER TABLE `library_items` ADD COLUMN `ocrText` TEXT")
    }
}

val MIGRATION_5_6 = object : Migration(5, 6) {
    override fun migrate(database: SupportSQLiteDatabase) {
        database.execSQL("ALTER TABLE `library_items` ADD COLUMN `folderName` TEXT")
        database.execSQL("ALTER TABLE `library_items` ADD COLUMN `tagsJson` TEXT NOT NULL DEFAULT '[]'")
        database.execSQL("ALTER TABLE `library_items` ADD COLUMN `isFavorite` INTEGER NOT NULL DEFAULT 0")
        database.execSQL("ALTER TABLE `library_items` ADD COLUMN `sharedItemId` INTEGER")
        database.execSQL(
            """CREATE TABLE IF NOT EXISTS `library_folders` (
                `name` TEXT NOT NULL,
                `createdAt` INTEGER NOT NULL,
                PRIMARY KEY(`name`)
            )""".trimIndent(),
        )
    }
}

val MIGRATION_6_7 = object : Migration(6, 7) {
    override fun migrate(database: SupportSQLiteDatabase) {
        database.execSQL(
            """CREATE TABLE IF NOT EXISTS `ava_follow_ups` (
                `id` TEXT NOT NULL,
                `sourceItemId` TEXT NOT NULL,
                `sourceTitle` TEXT NOT NULL,
                `eventLabel` TEXT NOT NULL,
                `sourceExcerpt` TEXT NOT NULL,
                `eventAt` INTEGER NOT NULL,
                `remindAt` INTEGER NOT NULL,
                `createdAt` INTEGER NOT NULL,
                `notifiedAt` INTEGER,
                PRIMARY KEY(`id`),
                FOREIGN KEY(`sourceItemId`) REFERENCES `library_items`(`id`) ON UPDATE NO ACTION ON DELETE CASCADE
            )""".trimIndent(),
        )
        database.execSQL(
            "CREATE INDEX IF NOT EXISTS `index_ava_follow_ups_remindAt` " +
                "ON `ava_follow_ups` (`remindAt`)"
        )
        database.execSQL(
            "CREATE UNIQUE INDEX IF NOT EXISTS `index_ava_follow_ups_sourceItemId_eventAt` " +
                "ON `ava_follow_ups` (`sourceItemId`, `eventAt`)"
        )
    }
}

val MIGRATION_7_8 = object : Migration(7, 8) {
    override fun migrate(database: SupportSQLiteDatabase) {
        database.execSQL("ALTER TABLE `ava_follow_ups` ADD COLUMN `updatedAt` INTEGER NOT NULL DEFAULT 0")
        database.execSQL("ALTER TABLE `ava_follow_ups` ADD COLUMN `deletedAt` INTEGER")
        database.execSQL("UPDATE `ava_follow_ups` SET `updatedAt` = `createdAt` WHERE `updatedAt` = 0")
    }
}
