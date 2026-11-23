package com.stash.app.feature.library

import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.stash.app.data.IncomingShare
import com.stash.app.data.LibraryRepository
import com.stash.app.data.StorageAuditReport
import com.stash.app.data.LibraryStorageOverview
import com.stash.app.data.bin.BinEmptyScheduler
import com.stash.app.data.local.LibraryItemEntity
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

enum class LibraryFilter(val label: String, private val categories: Set<String>?) {
    ALL("All", null),
    TEXT("Text", setOf("TEXT")),
    LINKS("Links", setOf("LINK")),
    IMAGES("Images", setOf("IMAGE")),
    AUDIO("Audio", setOf("AUDIO")),
    VIDEOS("Videos", setOf("VIDEO")),
    FILES("Files", setOf("FILE"));

    fun includes(category: String): Boolean = categories == null || category in categories
}

enum class LibraryModeFilter(val label: String, private val modes: Set<String>?) {
    ALL("All modes", null),
    DEVELOPER("Developer", setOf("DEVELOPER")),
    EDITOR("Editor", setOf("EDITOR")),
    STUDENT("Student", setOf("STUDENT"));

    fun includes(mode: String): Boolean = modes == null || mode in modes
}

class LibraryViewModel(
    private val repository: LibraryRepository,
    private val binEmptyScheduler: BinEmptyScheduler,
) : ViewModel() {
    private val selectedFilter = MutableStateFlow(LibraryFilter.ALL)
    private val selectedModeFilter = MutableStateFlow(LibraryModeFilter.ALL)
    private val searchQuery = MutableStateFlow("")
    private val selectedFolder = MutableStateFlow<String?>(null)
    private val favoritesOnly = MutableStateFlow(false)
    private val selectionModeState = MutableStateFlow(false)
    private val selectedItemIdsState = MutableStateFlow<Set<String>>(emptySet())
    private val eventChannel = Channel<String>(Channel.BUFFERED)
    private val mutableStorageOverview = MutableStateFlow<LibraryStorageOverview?>(null)
    private val mutableStorageError = MutableStateFlow<String?>(null)
    private val mutableStorageAudit = MutableStateFlow<StorageAuditReport?>(null)
    private val mutableStorageAuditError = MutableStateFlow<String?>(null)
    val events = eventChannel.receiveAsFlow()
    val storageOverview = mutableStorageOverview
    val storageError = mutableStorageError
    val storageAudit = mutableStorageAudit
    val storageAuditError = mutableStorageAuditError

    val filter = selectedFilter
    val modeFilter = selectedModeFilter
    val query = searchQuery
    val folderFilter = selectedFolder
    val favoriteFilter = favoritesOnly
    val folders = repository.observeFolders()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
    val selectionMode = selectionModeState
    val selectedItemIds = selectedItemIdsState

    private val filters = combine(selectedFilter, selectedModeFilter, searchQuery, selectedFolder, favoritesOnly) {
            type, mode, query, folder, favoriteOnly ->
        LibraryFilters(type, mode, query, folder, favoriteOnly)
    }

    val items = combine(repository.observeItems(), filters) { saved, filter ->
        val normalizedQuery = filter.query.trim().lowercase()
        saved.filter { item ->
            filter.type.includes(item.category) &&
                filter.mode.includes(item.mode) &&
                (filter.folder == null || if (filter.folder.isEmpty()) item.folderName.isNullOrEmpty() else item.folderName == filter.folder) &&
                (!filter.favoriteOnly || item.isFavorite) &&
                (normalizedQuery.isBlank() ||
                    item.title.contains(normalizedQuery, ignoreCase = true) ||
                    item.contentText.orEmpty().contains(normalizedQuery, ignoreCase = true) ||
                    item.ocrText.orEmpty().contains(normalizedQuery, ignoreCase = true) ||
                    item.mimeType.contains(normalizedQuery, ignoreCase = true) ||
                    item.tagsJson.contains(normalizedQuery, ignoreCase = true))
        }
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    val totalCount = repository.observeItems()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    val binItems = repository.observeBin()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
    val binReviewAt = MutableStateFlow(binEmptyScheduler.scheduledAt())

    init {
        viewModelScope.launch {
            try {
                repository.indexExistingImagesAndPdfs()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                // Library browsing remains available if background text indexing fails.
            }
        }
    }

    fun selectFilter(value: LibraryFilter) {
        selectedFilter.value = value
    }

    fun selectModeFilter(value: LibraryModeFilter) {
        selectedModeFilter.value = value
    }

    fun updateQuery(value: String) {
        searchQuery.value = value
    }

    fun selectFolder(value: String?) {
        selectedFolder.value = value
    }

    fun showFavoritesOnly(value: Boolean) {
        favoritesOnly.value = value
    }

    fun createFolder(name: String) {
        viewModelScope.launch {
            runCatching { repository.createFolder(name) }
                .onSuccess { eventChannel.send("Folder “$it” is ready.") }
                .onFailure { errorChannelMessage(it) }
        }
    }

    fun moveToFolder(ids: List<String>, folderName: String?) {
        viewModelScope.launch {
            runCatching { repository.moveToFolder(ids, folderName) }
                .onSuccess { count ->
                    val destination = folderName ?: "Unfiled"
                    eventChannel.send("Moved $count ${if (count == 1) "item" else "items"} to $destination.")
                    clearSelectedItems()
                }
                .onFailure { errorChannelMessage(it) }
        }
    }

    fun updateTags(item: LibraryItemEntity, rawTags: String) {
        viewModelScope.launch {
            runCatching { repository.updateTags(item.id, rawTags.split(',')) }
                .onSuccess { eventChannel.send("Tags updated.") }
                .onFailure { errorChannelMessage(it) }
        }
    }

    fun toggleFavorite(item: LibraryItemEntity) {
        viewModelScope.launch {
            runCatching { repository.setFavorite(item.id, !item.isFavorite) }
                .onFailure { errorChannelMessage(it) }
        }
    }

    fun refreshStorageOverview() {
        mutableStorageError.value = null
        viewModelScope.launch {
            runCatching { repository.storageOverview() }
                .onSuccess { mutableStorageOverview.value = it }
                .onFailure { mutableStorageError.value = "Could not load storage details. Please try again." }
        }
    }

    fun refreshStorageAudit() {
        mutableStorageAuditError.value = null
        viewModelScope.launch {
            runCatching { repository.storageAudit() }
                .onSuccess { mutableStorageAudit.value = it }
                .onFailure { mutableStorageAuditError.value = "Could not check saved files. Please try again." }
        }
    }

    fun setSelectionMode(enabled: Boolean) {
        selectionModeState.value = enabled
        if (!enabled) selectedItemIdsState.value = emptySet()
    }

    fun toggleSelectedItem(id: String) {
        selectedItemIdsState.value = selectedItemIdsState.value.toMutableSet().apply {
            if (!add(id)) remove(id)
        }
    }

    fun selectVisibleItems(items: List<LibraryItemEntity>) {
        selectedItemIdsState.value = items.map(LibraryItemEntity::id).toSet()
    }

    fun clearSelectedItems() {
        selectedItemIdsState.value = emptySet()
    }

    fun moveSelectedToBin() {
        val ids = selectedItemIdsState.value.toList()
        if (ids.isEmpty()) return
        viewModelScope.launch {
            runCatching { repository.moveToBin(ids) }
                .onSuccess { count ->
                    selectedItemIdsState.value = emptySet()
                    selectionModeState.value = false
                    val label = if (count == 1) "item" else "items"
                    eventChannel.send("Moved $count $label to Bin.")
                }
                .onFailure {
                    eventChannel.send("Could not move the selected items. Please try again.")
                }
        }
    }

    fun moveToBin(id: String) = runItemAction("Moved to Bin.") {
        repository.moveToBin(id)
    }

    fun restoreFromBin(id: String) = runItemAction("Restored to your library.") {
        repository.restoreFromBin(id)
    }

    fun scheduleBinReview(timestamp: Long) = runItemAction("Bin review was scheduled.") {
        binEmptyScheduler.scheduleFor(timestamp)
        binReviewAt.value = timestamp
    }

    fun cancelBinReview() = runItemAction("Scheduled Bin review was cancelled.") {
        binEmptyScheduler.cancel()
        binReviewAt.value = null
    }

    fun refreshBinReviewSchedule() {
        binReviewAt.value = binEmptyScheduler.scheduledAt()
    }

    fun emptyBinNow() {
        viewModelScope.launch {
            runCatching { repository.emptyBin() }
                .onSuccess { result ->
                    if (result.failedCount == 0) {
                        binEmptyScheduler.cancel()
                        binReviewAt.value = null
                        eventChannel.send("Permanently deleted ${result.removedCount} items from Stash Bin.")
                    } else {
                        eventChannel.send(
                            "Permanently deleted ${result.removedCount} items. ${result.failedCount} could not be deleted.",
                        )
                    }
                }
                .onFailure { eventChannel.send("Could not empty the Bin. Please try again.") }
        }
    }

    fun importUris(uris: List<Uri>) = import(IncomingShare(uris = uris))

    fun importSharedContent(text: String?, uris: List<Uri>) =
        import(IncomingShare(text = text, uris = uris))

    private fun import(share: IncomingShare) {
        if (share.uris.isEmpty() && share.text.isNullOrBlank()) {
            eventChannel.trySend("Nothing was shared with Stash.")
            return
        }
        viewModelScope.launch {
            runCatching { repository.importShare(share) }
                .onSuccess { count ->
                    val label = if (count == 1) "item" else "items"
                    eventChannel.send("Saved $count $label to Stash.")
                }
                .onFailure { error ->
                    val reason = error.message
                        ?.takeIf(String::isNotBlank)
                        ?.take(120)
                        ?: "Please try sharing it again."
                    eventChannel.send("Could not save this item. $reason")
                }
        }
    }

    private fun runItemAction(successMessage: String, action: suspend () -> Unit) {
        viewModelScope.launch {
            runCatching { action() }
                .onSuccess { eventChannel.send(successMessage) }
                .onFailure { eventChannel.send("Could not update this item. Please try again.") }
        }
    }

    private fun errorChannelMessage(error: Throwable) {
        val message = error.message?.takeIf(String::isNotBlank)?.take(120)
            ?: "Please try again."
        eventChannel.trySend(message)
    }

    class Factory(
        private val repository: LibraryRepository,
        private val binEmptyScheduler: BinEmptyScheduler,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            if (modelClass.isAssignableFrom(LibraryViewModel::class.java)) {
                return LibraryViewModel(repository, binEmptyScheduler) as T
            }
            throw IllegalArgumentException("Unknown ViewModel: ${modelClass.name}")
        }
    }
}

private data class LibraryFilters(
    val type: LibraryFilter,
    val mode: LibraryModeFilter,
    val query: String,
    val folder: String?,
    val favoriteOnly: Boolean,
)
