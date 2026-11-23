package com.stash.app

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.content.pm.PackageManager
import android.view.WindowManager
import android.widget.Toast
import android.Manifest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.stash.app.data.SensitiveShareClassifier
import com.stash.app.feature.library.LibraryScreen
import com.stash.app.feature.library.BinScreen
import com.stash.app.feature.library.StorageScreen
import com.stash.app.feature.library.LibraryViewModel
import com.stash.app.feature.backup.BackupScreen
import com.stash.app.feature.shared.SharedStashScreen
import com.stash.app.feature.cleanup.PhoneCleanupScreen
import com.stash.app.feature.ava.AvaFollowUpsScreen
import com.stash.app.feature.ava.AvaScreen
import com.stash.app.feature.mobilecompanion.MobileCompanionScreen
import com.stash.app.feature.ava.AvaViewModel
import com.stash.app.feature.vault.VaultScreen
import com.stash.app.feature.vault.VaultViewModel
import com.stash.app.ui.theme.StashTheme

class MainActivity : ComponentActivity() {
    private var isVaultOpen by mutableStateOf(false)
    private var isAvaOpen by mutableStateOf(false)
    private var isBinOpen by mutableStateOf(false)
    private var isBackupOpen by mutableStateOf(false)
    private var isStorageOpen by mutableStateOf(false)
    private var isSharedStashOpen by mutableStateOf(false)
    private var isPhoneCleanupOpen by mutableStateOf(false)
    private var isAvaFollowUpsOpen by mutableStateOf(false)
    private var isMobileCompanionOpen by mutableStateOf(false)
    private var avaFollowUpSourceItemId by mutableStateOf<String?>(null)
    private var phoneCleanupTreeUri by mutableStateOf<Uri?>(null)
    private var pendingVideoUrl: String? = null

    private val phoneCleanupFolderPicker = registerForActivityResult(
        ActivityResultContracts.OpenDocumentTree(),
    ) { uri ->
        if (uri != null) {
            runCatching {
                contentResolver.takePersistableUriPermission(
                    uri,
                    Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION,
                )
                (application as StashApplication).phoneCleanupRepository.setSelectedTreeUri(uri)
                phoneCleanupTreeUri = uri
            }.onFailure {
                Toast.makeText(this, "Stash couldn't keep access to that folder. Choose another folder.", Toast.LENGTH_LONG).show()
            }
        }
    }

    private val notificationPermissionRequest = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        val url = pendingVideoUrl ?: return@registerForActivityResult
        pendingVideoUrl = null
        enqueueVideoDownload(url)
        if (!granted) {
            Toast.makeText(
                this,
                "Download started. Allow notifications to see its progress.",
                Toast.LENGTH_LONG,
            ).show()
        }
    }

    private val viewModel: LibraryViewModel by viewModels {
        val stashApplication = application as StashApplication
        LibraryViewModel.Factory(
            stashApplication.libraryRepository,
            stashApplication.binEmptyScheduler,
        )
    }
    private val vaultViewModel: VaultViewModel by viewModels {
        VaultViewModel.Factory((application as StashApplication).vaultRepository)
    }
    private val avaViewModel: AvaViewModel by viewModels {
        AvaViewModel.Factory(
            libraryRepository = (application as StashApplication).libraryRepository,
            avaRepository = (application as StashApplication).avaRepository,
        )
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val cleanupRepository = (application as StashApplication).phoneCleanupRepository
        phoneCleanupTreeUri = cleanupRepository.selectedTreeUri()
        isPhoneCleanupOpen = intent?.getBooleanExtra("open_phone_cleanup", false) == true
        isBinOpen = intent?.getBooleanExtra("open_bin", false) == true
        isAvaFollowUpsOpen = intent?.getBooleanExtra("open_ava_follow_ups", false) == true
        avaFollowUpSourceItemId = intent?.getStringExtra("ava_follow_up_item_id")
        setContent {
            SideEffect {
                if (isVaultOpen) {
                    window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
                } else {
                    window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE)
                }
            }
            StashTheme {
                if (isVaultOpen) {
                    VaultScreen(
                        viewModel = vaultViewModel,
                        activity = this@MainActivity,
                        onBack = {
                            vaultViewModel.lock()
                            isVaultOpen = false
                        },
                    )
                } else if (isAvaOpen) {
                    AvaScreen(
                        viewModel = avaViewModel,
                        onBack = { isAvaOpen = false },
                    )
                } else if (isBinOpen) {
                    BinScreen(
                        viewModel = viewModel,
                        onBack = { isBinOpen = false },
                    )
                } else if (isBackupOpen) {
                    BackupScreen(
                        repository = (application as StashApplication).backupRepository,
                        hasVault = (application as StashApplication).vaultRepository.hasVault(),
                        onBack = { isBackupOpen = false },
                    )
                } else if (isStorageOpen) {
                    StorageScreen(
                        viewModel = viewModel,
                        onBack = { isStorageOpen = false },
                    )
                } else if (isSharedStashOpen) {
                    SharedStashScreen(
                        repository = (application as StashApplication).sharedStashRepository,
                        onBack = { isSharedStashOpen = false },
                    )
                } else if (isPhoneCleanupOpen) {
                    PhoneCleanupScreen(
                        repository = (application as StashApplication).phoneCleanupRepository,
                        scheduler = (application as StashApplication).phoneCleanupScheduler,
                        treeUri = phoneCleanupTreeUri,
                        onChooseFolder = { phoneCleanupFolderPicker.launch(phoneCleanupTreeUri) },
                        onBack = { isPhoneCleanupOpen = false },
                    )
                } else if (isAvaFollowUpsOpen) {
                    AvaFollowUpsScreen(
                        libraryRepository = (application as StashApplication).libraryRepository,
                        followUpRepository = (application as StashApplication).avaFollowUpRepository,
                        scheduler = (application as StashApplication).avaFollowUpScheduler,
                        mobileCompanionRepository = (application as StashApplication).mobileCompanionRepository,
                        sourceItemId = avaFollowUpSourceItemId,
                        onBack = {
                            isAvaFollowUpsOpen = false
                            avaFollowUpSourceItemId = null
                        },
                    )
                } else if (isMobileCompanionOpen) {
                    MobileCompanionScreen(
                        repository = (application as StashApplication).mobileCompanionRepository,
                        onBack = { isMobileCompanionOpen = false },
                    )
                } else {
                    LibraryScreen(
                        viewModel = viewModel,
                        onImportUris = viewModel::importUris,
                        onCopyVideo = ::copyVideo,
                        onShareVideo = ::shareVideo,
                        onCopyText = ::copyText,
                        onOpenItem = ::openItem,
                        onShareItem = ::shareItem,
                        onOpenVault = { isVaultOpen = true },
                        onOpenAva = { isAvaOpen = true },
                        onOpenBin = {
                            viewModel.refreshBinReviewSchedule()
                            isBinOpen = true
                        },
                        onOpenBackup = { isBackupOpen = true },
                        onOpenStorage = { isStorageOpen = true },
                        onOpenSharedStash = { isSharedStashOpen = true },
                        onOpenPhoneCleanup = { isPhoneCleanupOpen = true },
                        onOpenAvaFollowUps = { sourceItemId ->
                            openDestination(Destination.AVA_FOLLOW_UPS, sourceItemId)
                        },
                        onOpenMobileCompanion = { openDestination(Destination.MOBILE_COMPANION) },
                    )
                }
            }
        }
        handleIncomingShare(intent)
    }

    override fun onStop() {
        vaultViewModel.lock()
        super.onStop()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (intent.getBooleanExtra("open_phone_cleanup", false)) {
            phoneCleanupTreeUri = (application as StashApplication).phoneCleanupRepository.selectedTreeUri()
            openDestination(Destination.PHONE_CLEANUP)
        } else if (intent.getBooleanExtra("open_bin", false)) {
            openDestination(Destination.BIN)
        } else if (intent.getBooleanExtra("open_ava_follow_ups", false)) {
            openDestination(
                Destination.AVA_FOLLOW_UPS,
                intent.getStringExtra("ava_follow_up_item_id"),
            )
        }
        handleIncomingShare(intent)
    }

    private fun openDestination(destination: Destination, sourceItemId: String? = null) {
        if (isVaultOpen) vaultViewModel.lock()
        if (destination == Destination.BIN) viewModel.refreshBinReviewSchedule()
        isVaultOpen = false
        isAvaOpen = false
        isBinOpen = destination == Destination.BIN
        isBackupOpen = false
        isStorageOpen = false
        isSharedStashOpen = false
        isPhoneCleanupOpen = destination == Destination.PHONE_CLEANUP
        isAvaFollowUpsOpen = destination == Destination.AVA_FOLLOW_UPS
        isMobileCompanionOpen = destination == Destination.MOBILE_COMPANION
        avaFollowUpSourceItemId = sourceItemId.takeIf { destination == Destination.AVA_FOLLOW_UPS }
    }

    private enum class Destination { BIN, PHONE_CLEANUP, AVA_FOLLOW_UPS, MOBILE_COMPANION }

    private fun handleIncomingShare(incomingIntent: Intent?) {
        val shareIntent = incomingIntent ?: return
        if (shareIntent.action != Intent.ACTION_SEND &&
            shareIntent.action != Intent.ACTION_SEND_MULTIPLE
        ) return

        val uris = linkedSetOf<Uri>()
        when (shareIntent.action) {
            Intent.ACTION_SEND -> {
                @Suppress("DEPRECATION")
                val stream = shareIntent.getParcelableExtra(Intent.EXTRA_STREAM) as? Uri
                stream?.let(uris::add)
            }
            Intent.ACTION_SEND_MULTIPLE -> {
                @Suppress("DEPRECATION")
                val streams = shareIntent.getParcelableArrayListExtra<Uri>(Intent.EXTRA_STREAM)
                streams?.let(uris::addAll)
            }
        }

        shareIntent.clipData?.let { clipData ->
            for (index in 0 until clipData.itemCount) {
                clipData.getItemAt(index).uri?.let(uris::add)
            }
        }

        val sharedText = shareIntent.getCharSequenceExtra(Intent.EXTRA_TEXT)?.toString()
        val sensitive = sharedText?.let(SensitiveShareClassifier::classify)
        val sharedVideoUrl = if (sensitive == null) {
            sharedText?.let(com.stash.app.data.video.VideoDownloadScheduler::extractHttpsUrl)
        } else {
            null
        }
        if (uris.isEmpty() && sharedVideoUrl != null) {
            shareIntent.removeExtra(Intent.EXTRA_TEXT)
            shareIntent.removeExtra(Intent.EXTRA_STREAM)
            shareIntent.clipData = null
            requestNotificationsAndDownload(sharedVideoUrl)
            return
        }
        if (sensitive != null) {
            isVaultOpen = true
            vaultViewModel.receiveSensitiveShare(sharedText, sensitive.title)
            if (uris.isNotEmpty()) {
                viewModel.importSharedContent(null, uris.toList())
            }
        } else {
            viewModel.importSharedContent(sharedText, uris.toList())
        }

        // Do not leave shared plaintext in the Activity's retained launch Intent.
        shareIntent.removeExtra(Intent.EXTRA_TEXT)
        shareIntent.removeExtra(Intent.EXTRA_STREAM)
        shareIntent.clipData = null
    }

    private fun requestNotificationsAndDownload(url: String) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            pendingVideoUrl = url
            notificationPermissionRequest.launch(Manifest.permission.POST_NOTIFICATIONS)
            return
        }
        enqueueVideoDownload(url)
    }

    private fun enqueueVideoDownload(url: String) {
        runCatching { (application as StashApplication).videoDownloadScheduler.enqueue(url) }
            .onSuccess {
                Toast.makeText(this, "Video download started.", Toast.LENGTH_SHORT).show()
            }
            .onFailure { error ->
                Toast.makeText(
                    this,
                    error.message ?: "Stash couldn't start the video download.",
                    Toast.LENGTH_LONG,
                ).show()
            }
    }

    private fun copyVideo(item: com.stash.app.data.local.LibraryItemEntity) {
        runCatching { (application as StashApplication).videoClipboard.copyVideo(item) }
            .onSuccess {
                Toast.makeText(this, "Video copied. Paste it into another app.", Toast.LENGTH_SHORT).show()
            }
            .onFailure { error ->
                Toast.makeText(this, error.message ?: "Stash couldn't copy this video.", Toast.LENGTH_LONG).show()
            }
    }

    private fun shareVideo(item: com.stash.app.data.local.LibraryItemEntity) {
        runCatching {
            val shareIntent = (application as StashApplication).videoClipboard.shareIntent(item)
            startActivity(Intent.createChooser(shareIntent, "Share video file"))
        }.onFailure { error ->
            Toast.makeText(this, error.message ?: "Stash couldn't share this video.", Toast.LENGTH_LONG).show()
        }
    }

    private fun copyText(item: com.stash.app.data.local.LibraryItemEntity) {
        runCatching { (application as StashApplication).videoClipboard.copyText(item) }
            .onSuccess {
                Toast.makeText(this, "Copied to clipboard.", Toast.LENGTH_SHORT).show()
            }
            .onFailure { error ->
                Toast.makeText(this, error.message ?: "Stash couldn't copy this item.", Toast.LENGTH_LONG).show()
            }
    }

    private fun openItem(item: com.stash.app.data.local.LibraryItemEntity) {
        runCatching {
            startActivity((application as StashApplication).videoClipboard.openIntent(item))
        }.onFailure { error ->
            Toast.makeText(this, error.message ?: "No app could open this item.", Toast.LENGTH_LONG).show()
        }
    }

    private fun shareItem(item: com.stash.app.data.local.LibraryItemEntity) {
        runCatching {
            val shareIntent = (application as StashApplication).videoClipboard.shareItemIntent(item)
            startActivity(Intent.createChooser(shareIntent, "Share saved item"))
        }.onFailure { error ->
            Toast.makeText(this, error.message ?: "Stash couldn't share this item.", Toast.LENGTH_LONG).show()
        }
    }
}
