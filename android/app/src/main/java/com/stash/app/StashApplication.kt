package com.stash.app

import android.app.Application
import androidx.room.Room
import com.stash.app.data.LibraryRepository
import com.stash.app.data.LibraryTextIndexer
import com.stash.app.data.backup.EncryptedBackupRepository
import com.stash.app.data.ai.OnDeviceAvaRepository
import com.stash.app.data.ava.AvaFollowUpRepository
import com.stash.app.data.ava.AvaFollowUpScheduler
import com.stash.app.data.bin.BinEmptyScheduler
import com.stash.app.data.cleanup.PhoneCleanupRepository
import com.stash.app.data.cleanup.PhoneCleanupScheduler
import com.stash.app.data.local.MIGRATION_1_2
import com.stash.app.data.local.MIGRATION_2_3
import com.stash.app.data.local.MIGRATION_3_4
import com.stash.app.data.local.MIGRATION_4_5
import com.stash.app.data.local.MIGRATION_5_6
import com.stash.app.data.local.MIGRATION_6_7
import com.stash.app.data.local.MIGRATION_7_8
import com.stash.app.data.local.StashDatabase
import com.stash.app.data.storage.PrivateItemStore
import com.stash.app.data.shared.SharedStashRepository
import com.stash.app.data.mobilecompanion.MobileCompanionRepository
import com.stash.app.data.vault.VaultConfigurationStore
import com.stash.app.data.vault.VaultRepository
import com.stash.app.data.video.VideoClipboard
import com.stash.app.data.video.VideoDownloadScheduler
import com.stash.app.data.video.VideoExtractor
import com.stash.app.data.video.YtDlpVideoExtractor

class StashApplication : Application() {
    private val database by lazy {
        Room.databaseBuilder(this, StashDatabase::class.java, "stash-library.db")
            .addMigrations(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4, MIGRATION_4_5, MIGRATION_5_6, MIGRATION_6_7, MIGRATION_7_8)
            .build()
    }

    val libraryRepository by lazy {
        LibraryRepository(
            contentResolver = contentResolver,
            dao = database.libraryItemDao(),
            privateItemStore = PrivateItemStore(filesDir),
            textIndexer = LibraryTextIndexer(),
        )
    }

    val vaultRepository by lazy {
        VaultRepository(
            dao = database.vaultEntryDao(),
            configurationStore = VaultConfigurationStore(this),
        )
    }

    val backupRepository by lazy {
        EncryptedBackupRepository(
            contentResolver = contentResolver,
            cacheDirectory = cacheDir,
            privateItemStore = PrivateItemStore(filesDir),
            libraryRepository = libraryRepository,
            avaFollowUpRepository = avaFollowUpRepository,
            vaultRepository = vaultRepository,
        )
    }

    val avaRepository by lazy {
        OnDeviceAvaRepository(this)
    }

    val sharedStashRepository by lazy {
        SharedStashRepository(this, libraryRepository)
    }

    val mobileCompanionRepository by lazy {
        MobileCompanionRepository(this, avaFollowUpRepository, libraryRepository)
    }

    val binEmptyScheduler by lazy {
        BinEmptyScheduler(this)
    }

    val phoneCleanupRepository by lazy {
        PhoneCleanupRepository(this)
    }

    val phoneCleanupScheduler by lazy {
        PhoneCleanupScheduler(this)
    }

    val avaFollowUpRepository by lazy {
        AvaFollowUpRepository(database.avaFollowUpDao())
    }

    val avaFollowUpScheduler by lazy {
        AvaFollowUpScheduler(this, avaFollowUpRepository)
    }

    val videoExtractor: VideoExtractor by lazy {
        YtDlpVideoExtractor(this)
    }

    val videoClipboard by lazy {
        VideoClipboard(this, PrivateItemStore(filesDir))
    }

    val videoDownloadScheduler by lazy {
        VideoDownloadScheduler(this)
    }
}
