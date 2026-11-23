package com.stash.app.feature.library

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.stash.app.data.ava.AvaFollowUpDateDetector
import com.stash.app.data.local.LibraryItemEntity
import java.text.DateFormat
import java.util.Date
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Composable
fun LibraryScreen(
    viewModel: LibraryViewModel,
    onImportUris: (List<Uri>) -> Unit,
    onCopyVideo: (LibraryItemEntity) -> Unit,
    onShareVideo: (LibraryItemEntity) -> Unit,
    onCopyText: (LibraryItemEntity) -> Unit,
    onOpenItem: (LibraryItemEntity) -> Unit,
    onShareItem: (LibraryItemEntity) -> Unit,
    onOpenVault: () -> Unit,
    onOpenAva: () -> Unit,
    onOpenBin: () -> Unit,
    onOpenBackup: () -> Unit,
    onOpenStorage: () -> Unit,
    onOpenSharedStash: () -> Unit,
    onOpenPhoneCleanup: () -> Unit,
    onOpenAvaFollowUps: (String?) -> Unit,
    onOpenMobileCompanion: () -> Unit,
) {
    var showMoreActions by remember { mutableStateOf(false) }
    var showCreateFolder by remember { mutableStateOf(false) }
    var newFolderName by remember { mutableStateOf("") }
    var editingTagsItem by remember { mutableStateOf<LibraryItemEntity?>(null) }
    var editingTags by remember { mutableStateOf("") }
    var showBulkFolderMenu by remember { mutableStateOf(false) }
    val items by viewModel.items.collectAsStateWithLifecycle()
    val totalItems by viewModel.totalCount.collectAsStateWithLifecycle()
    val folders by viewModel.folders.collectAsStateWithLifecycle()
    val selectedFilter by viewModel.filter.collectAsState()
    val selectedModeFilter by viewModel.modeFilter.collectAsState()
    val selectedFolder by viewModel.folderFilter.collectAsStateWithLifecycle()
    val favoritesOnly by viewModel.favoriteFilter.collectAsStateWithLifecycle()
    val query by viewModel.query.collectAsState()
    val selectionMode by viewModel.selectionMode.collectAsStateWithLifecycle()
    val selectedItemIds by viewModel.selectedItemIds.collectAsStateWithLifecycle()
    val snackbarHostState = remember { SnackbarHostState() }
    val filePicker = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenMultipleDocuments(),
        onResult = { uris -> if (uris.isNotEmpty()) onImportUris(uris) },
    )

    LaunchedEffect(viewModel) {
        viewModel.events.collect { message -> snackbarHostState.showSnackbar(message) }
    }

    Scaffold(
        modifier = Modifier.fillMaxSize(),
        containerColor = MaterialTheme.colorScheme.background,
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { contentPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(contentPadding)
                .padding(horizontal = 20.dp),
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 22.dp, bottom = 18.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Stash",
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    Text(
                        text = "Your private library",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    TextButton(onClick = onOpenAva) { Text("Ask Ava") }
                    TextButton(onClick = onOpenVault) { Text("Vault") }
                    Box {
                        TextButton(onClick = { showMoreActions = true }) { Text("More") }
                        DropdownMenu(
                            expanded = showMoreActions,
                            onDismissRequest = { showMoreActions = false },
                        ) {
                            DropdownMenuItem(
                                text = { Text("Bin") },
                                onClick = { showMoreActions = false; onOpenBin() },
                            )
                            DropdownMenuItem(
                                text = { Text("Backup and restore") },
                                onClick = { showMoreActions = false; onOpenBackup() },
                            )
                            DropdownMenuItem(
                                text = { Text("Storage overview") },
                                onClick = { showMoreActions = false; onOpenStorage() },
                            )
                            DropdownMenuItem(
                                text = { Text("Shared Stash sync") },
                                onClick = { showMoreActions = false; onOpenSharedStash() },
                            )
                            DropdownMenuItem(
                                text = { Text("Ava phone cleanup") },
                                onClick = { showMoreActions = false; onOpenPhoneCleanup() },
                            )
                            DropdownMenuItem(
                                text = { Text("Ava Follow-ups") },
                                onClick = { showMoreActions = false; onOpenAvaFollowUps(null) },
                            )
                            DropdownMenuItem(
                                text = { Text("Connect desktop / Action Inbox") },
                                onClick = { showMoreActions = false; onOpenMobileCompanion() },
                            )
                        }
                    }
                    Button(
                        onClick = { filePicker.launch(arrayOf("*/*")) },
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.primary,
                            contentColor = MaterialTheme.colorScheme.onPrimary,
                        ),
                    ) {
                        Text("Add files", fontWeight = FontWeight.SemiBold)
                    }
                }
            }
            Text(
                text = "Only download videos you own or are authorized to download. DRM-protected videos aren't supported.",
                modifier = Modifier.padding(bottom = 10.dp),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            SearchField(
                value = query,
                onValueChange = viewModel::updateQuery,
                readOnly = selectionMode,
            )
            Spacer(Modifier.height(14.dp))
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                LibraryModeFilter.entries.forEach { filter ->
                    FilterChip(
                        selected = selectedModeFilter == filter,
                        onClick = { viewModel.selectModeFilter(filter) },
                        enabled = !selectionMode,
                        label = { Text(filter.label) },
                    )
                }
            }
            Spacer(Modifier.height(8.dp))
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                LibraryFilter.entries.forEach { filter ->
                    FilterChip(
                        selected = selectedFilter == filter,
                        onClick = { viewModel.selectFilter(filter) },
                        enabled = !selectionMode,
                        label = { Text(filter.label) },
                    )
                }
            }
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                FilterChip(
                    selected = selectedFolder == null,
                    onClick = { viewModel.selectFolder(null) },
                    enabled = !selectionMode,
                    label = { Text("All folders") },
                )
                FilterChip(
                    selected = selectedFolder == "",
                    onClick = { viewModel.selectFolder("") },
                    enabled = !selectionMode,
                    label = { Text("Unfiled") },
                )
                folders.forEach { folder ->
                    FilterChip(
                        selected = selectedFolder == folder.name,
                        onClick = { viewModel.selectFolder(folder.name) },
                        enabled = !selectionMode,
                        label = { Text(folder.name) },
                    )
                }
                FilterChip(
                    selected = favoritesOnly,
                    onClick = { viewModel.showFavoritesOnly(!favoritesOnly) },
                    enabled = !selectionMode,
                    label = { Text("★ Favorites") },
                )
                TextButton(onClick = { showCreateFolder = true }, enabled = !selectionMode) {
                    Text("New folder")
                }
            }

            Row(
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp, bottom = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(
                    text = if (selectionMode) {
                        "${selectedItemIds.size} selected · ${items.size} shown"
                    } else {
                        "${items.size} shown · ${totalItems.size} saved"
                    },
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                TextButton(
                    onClick = { viewModel.setSelectionMode(!selectionMode) },
                    enabled = items.isNotEmpty() || selectionMode,
                ) {
                    Text(if (selectionMode) "Done" else "Select")
                }
            }
            if (selectionMode) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End,
                ) {
                    TextButton(onClick = { viewModel.selectVisibleItems(items) }) {
                        Text("Select all shown")
                    }
                    TextButton(onClick = viewModel::clearSelectedItems) {
                        Text("Clear")
                    }
                }
            }

            if (items.isEmpty()) {
                EmptyLibrary(
                    modifier = Modifier.weight(1f),
                    hasAnyItems = totalItems.isNotEmpty(),
                    onAddFiles = { filePicker.launch(arrayOf("*/*")) },
                )
            } else {
                LazyColumn(
                    modifier = Modifier.weight(1f).fillMaxWidth(),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    items(items = items, key = LibraryItemEntity::id) { item ->
                        LibraryItemCard(
                            item = item,
                            selectionMode = selectionMode,
                            selected = item.id in selectedItemIds,
                            onToggleSelected = { viewModel.toggleSelectedItem(item.id) },
                            onMoveToBin = { viewModel.moveToBin(item.id) },
                            onCopyVideo = { onCopyVideo(item) },
                            onShareVideo = { onShareVideo(item) },
                            onCopyText = { onCopyText(item) },
                            onOpenItem = { onOpenItem(item) },
                            onShareItem = { onShareItem(item) },
                            folders = folders.map { it.name },
                            onToggleFavorite = { viewModel.toggleFavorite(item) },
                            onMoveToFolder = { folder -> viewModel.moveToFolder(listOf(item.id), folder) },
                            onEditTags = {
                                editingTagsItem = item
                                editingTags = runCatching {
                                    org.json.JSONArray(item.tagsJson).let { array ->
                                        (0 until array.length()).joinToString(", ") { array.optString(it) }
                                    }
                                }.getOrDefault("")
                            },
                            onOpenAvaFollowUps = { onOpenAvaFollowUps(item.id) },
                        )
                    }
                    item { Spacer(Modifier.height(20.dp)) }
                }
            }
            if (selectionMode && selectedItemIds.isNotEmpty()) {
                Box {
                    TextButton(
                        onClick = { showBulkFolderMenu = true },
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text("Move selected to folder")
                    }
                    DropdownMenu(
                        expanded = showBulkFolderMenu,
                        onDismissRequest = { showBulkFolderMenu = false },
                    ) {
                        DropdownMenuItem(
                            text = { Text("Unfiled") },
                            onClick = {
                                showBulkFolderMenu = false
                                viewModel.moveToFolder(selectedItemIds.toList(), null)
                            },
                        )
                        folders.forEach { folder ->
                            DropdownMenuItem(
                                text = { Text(folder.name) },
                                onClick = {
                                    showBulkFolderMenu = false
                                    viewModel.moveToFolder(selectedItemIds.toList(), folder.name)
                                },
                            )
                        }
                    }
                }
                Button(
                    onClick = viewModel::moveSelectedToBin,
                    modifier = Modifier.fillMaxWidth().padding(vertical = 10.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.primary,
                        contentColor = MaterialTheme.colorScheme.onPrimary,
                    ),
                ) {
                    val count = selectedItemIds.size
                    Text("Move $count selected ${if (count == 1) "item" else "items"} to Bin")
                }
            }
        }
    }

    if (showCreateFolder) {
        AlertDialog(
            onDismissRequest = { showCreateFolder = false },
            title = { Text("Create a folder") },
            text = {
                OutlinedTextField(
                    value = newFolderName,
                    onValueChange = { newFolderName = it },
                    singleLine = true,
                    label = { Text("Folder name") },
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    viewModel.createFolder(newFolderName)
                    newFolderName = ""
                    showCreateFolder = false
                }) { Text("Create") }
            },
            dismissButton = {
                TextButton(onClick = { showCreateFolder = false }) { Text("Cancel") }
            },
        )
    }
    editingTagsItem?.let { item ->
        AlertDialog(
            onDismissRequest = { editingTagsItem = null },
            title = { Text("Tags for ${item.title}") },
            text = {
                OutlinedTextField(
                    value = editingTags,
                    onValueChange = { editingTags = it },
                    label = { Text("Comma-separated tags") },
                    supportingText = { Text("Up to 12 tags, 24 characters each") },
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    viewModel.updateTags(item, editingTags)
                    editingTagsItem = null
                }) { Text("Save tags") }
            },
            dismissButton = {
                TextButton(onClick = { editingTagsItem = null }) { Text("Cancel") }
            },
        )
    }
}

@Composable
private fun SearchField(
    value: String,
    onValueChange: (String) -> Unit,
    readOnly: Boolean,
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = MaterialTheme.shapes.large,
        color = MaterialTheme.colorScheme.surface,
        contentColor = MaterialTheme.colorScheme.onSurface,
        tonalElevation = 1.dp,
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 15.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("⌕", color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.width(10.dp))
            BasicTextField(
                value = value,
                onValueChange = onValueChange,
                modifier = Modifier.weight(1f),
                singleLine = true,
                readOnly = readOnly,
                textStyle = MaterialTheme.typography.bodyLarge.copy(
                    color = MaterialTheme.colorScheme.onSurface,
                ),
                decorationBox = { innerTextField ->
                    if (value.isEmpty()) {
                        Text(
                            "Search saved copies, photos, and PDFs",
                            style = MaterialTheme.typography.bodyLarge,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    innerTextField()
                },
            )
        }
    }
}

@Composable
private fun LibraryItemCard(
    item: LibraryItemEntity,
    selectionMode: Boolean,
    selected: Boolean,
    onToggleSelected: () -> Unit,
    onMoveToBin: () -> Unit,
    onCopyVideo: () -> Unit,
    onShareVideo: () -> Unit,
    onCopyText: () -> Unit,
    onOpenItem: () -> Unit,
    onShareItem: () -> Unit,
    folders: List<String>,
    onToggleFavorite: () -> Unit,
    onMoveToFolder: (String?) -> Unit,
    onEditTags: () -> Unit,
    onOpenAvaFollowUps: () -> Unit,
) {
    var showFolderMenu by remember(item.id) { mutableStateOf(false) }
    var dateSuggestionCount by remember(item.id) { mutableIntStateOf(0) }
    LaunchedEffect(item.id, item.contentText, item.ocrText) {
        dateSuggestionCount = withContext(Dispatchers.Default) {
            AvaFollowUpDateDetector.detect(item).size
        }
    }
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .then(if (selectionMode) Modifier.clickable(onClick = onToggleSelected) else Modifier),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        shape = MaterialTheme.shapes.large,
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                if (selectionMode) {
                    Checkbox(checked = selected, onCheckedChange = { onToggleSelected() })
                    Spacer(Modifier.width(8.dp))
                }
                Text(
                    text = item.title,
                    modifier = Modifier.weight(1f),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                if (!selectionMode) {
                    TextButton(onClick = onToggleFavorite) {
                        Text(if (item.isFavorite) "★" else "☆")
                    }
                }
                Spacer(Modifier.width(10.dp))
                Text(
                    text = item.mode.lowercase().replaceFirstChar { it.uppercase() },
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.primary,
                )
            }
            Text(
                text = listOf(
                    item.category.lowercase().replaceFirstChar { it.uppercase() },
                    formatDate(item.savedAt),
                    item.mimeType,
                    formatSize(item.byteSize),
                )
                    .filter(String::isNotBlank)
                    .joinToString(" · "),
                modifier = Modifier.padding(top = 5.dp),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            val tags = runCatching {
                val array = org.json.JSONArray(item.tagsJson)
                (0 until array.length()).map { array.optString(it) }.filter(String::isNotBlank)
            }.getOrDefault(emptyList())
            Text(
                text = "Folder: ${item.folderName ?: "Unfiled"}${if (tags.isEmpty()) "" else " · ${tags.joinToString(", ")}"}",
                modifier = Modifier.padding(top = 4.dp),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            if (dateSuggestionCount > 0) {
                TextButton(
                    onClick = onOpenAvaFollowUps,
                    modifier = Modifier.padding(top = 2.dp),
                ) {
                    Text("Ava found $dateSuggestionCount possible ${if (dateSuggestionCount == 1) "date" else "dates"} · Review")
                }
            }
            item.contentText?.takeIf(String::isNotBlank)?.let { content ->
                Text(
                    text = content,
                    modifier = Modifier.padding(top = 10.dp),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 3,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            if (!selectionMode) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.End,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    if (item.category.equals("LINK", ignoreCase = true)) {
                        TextButton(onClick = onOpenItem) { Text("Open link") }
                    } else if (!item.relativePath.isNullOrBlank()) {
                        TextButton(onClick = onOpenItem) { Text("Open") }
                    }
                    Box {
                        TextButton(onClick = { showFolderMenu = true }) { Text("Folder") }
                        DropdownMenu(
                            expanded = showFolderMenu,
                            onDismissRequest = { showFolderMenu = false },
                        ) {
                            DropdownMenuItem(
                                text = { Text("Unfiled") },
                                onClick = { showFolderMenu = false; onMoveToFolder(null) },
                            )
                            folders.forEach { folder ->
                                DropdownMenuItem(
                                    text = { Text(folder) },
                                    onClick = { showFolderMenu = false; onMoveToFolder(folder) },
                                )
                            }
                        }
                    }
                    TextButton(onClick = onEditTags) { Text("Tags") }
                    if (item.contentText?.isNotBlank() == true) {
                        TextButton(onClick = onCopyText) {
                            Text(if (item.category.equals("LINK", ignoreCase = true)) "Copy link" else "Copy text")
                        }
                    }
                    if (!item.relativePath.isNullOrBlank() && !item.category.equals("VIDEO", ignoreCase = true)) {
                        TextButton(onClick = onShareItem) { Text("Share") }
                    }
                    if (item.category.equals("VIDEO", ignoreCase = true) && !item.relativePath.isNullOrBlank()) {
                        TextButton(onClick = onCopyVideo) { Text("Copy video") }
                    }
                    if (item.category.equals("VIDEO", ignoreCase = true) && !item.relativePath.isNullOrBlank()) {
                        TextButton(onClick = onShareVideo) { Text("Share video file") }
                    }
                    TextButton(onClick = onMoveToBin) { Text("Move to Bin") }
                }
            }
        }
    }
}

@Composable
private fun EmptyLibrary(
    modifier: Modifier = Modifier,
    hasAnyItems: Boolean,
    onAddFiles: () -> Unit,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(bottom = 48.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            text = if (hasAnyItems) "No matching copies" else "Your library is empty",
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.SemiBold,
        )
        Spacer(Modifier.height(8.dp))
        Text(
            text = if (hasAnyItems) {
                "Try another search or category."
            } else {
                "Share text, photos, audio, videos, or files to Stash."
            },
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (!hasAnyItems) {
            Spacer(Modifier.height(18.dp))
            Button(onClick = onAddFiles) { Text("Choose files") }
        }
    }
}

private fun formatDate(timeMillis: Long): String =
    DateFormat.getDateTimeInstance(DateFormat.MEDIUM, DateFormat.SHORT).format(Date(timeMillis))

private fun formatSize(size: Long): String = when {
    size <= 0L -> ""
    size < 1024L -> "$size B"
    size < 1024L * 1024L -> "${size / 1024L} KB"
    else -> "${"%.1f".format(size / (1024.0 * 1024.0))} MB"
}
