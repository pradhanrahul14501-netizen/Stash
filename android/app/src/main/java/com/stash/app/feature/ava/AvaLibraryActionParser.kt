package com.stash.app.feature.ava

import com.stash.app.data.local.LibraryItemEntity
import java.util.Locale

enum class AvaLibraryActionKind { CREATE_FOLDER, MOVE_FOLDER, MOVE_TO_BIN, RESTORE, TAG, FAVORITE }

data class AvaLibraryAction(
    val kind: AvaLibraryActionKind,
    val description: String,
    val itemIds: List<String> = emptyList(),
    val beforeItems: List<LibraryItemEntity> = emptyList(),
    val folderName: String? = null,
    val tagValue: String? = null,
    val favoriteValue: Boolean? = null,
)

sealed interface AvaLibraryRoute {
    data object Chat : AvaLibraryRoute
    data object Audit : AvaLibraryRoute
    data class Summarize(val item: LibraryItemEntity) : AvaLibraryRoute
    data class Clarify(val message: String) : AvaLibraryRoute
    data class Preview(val action: AvaLibraryAction) : AvaLibraryRoute
}

internal object AvaLibraryActionParser {
    fun parse(
        command: String,
        items: List<LibraryItemEntity>,
        binItems: List<LibraryItemEntity>,
        folderNames: List<String>,
    ): AvaLibraryRoute {
        val text = command.trim().trimEnd('.', '!', '?')
        if (Regex("(?i)\\b(check|scan|audit)\\b.*\\b(storage|library|files|health)\\b").containsMatchIn(text)) {
            return AvaLibraryRoute.Audit
        }

        match("(?i)^(?:create|make|add)\\s+(?:a\\s+)?folder(?:\\s+(?:named|called))?\\s+(.+)$", text)?.let { rawName ->
            val name = clean(rawName)
            if (name.isBlank()) return AvaLibraryRoute.Clarify("Tell me the folder name. Nothing has changed.")
            if (folderNames.any { it.equals(name, ignoreCase = true) }) {
                return AvaLibraryRoute.Clarify("The folder “$name” already exists. Nothing was changed.")
            }
            return AvaLibraryRoute.Preview(
                AvaLibraryAction(
                    kind = AvaLibraryActionKind.CREATE_FOLDER,
                    folderName = name,
                    description = "Create the Stash folder “$name”.",
                ),
            )
        }

        match("(?i)^(?:summarize|summarise|summary of)\\s+(.+)$", text)?.let { reference ->
            return resolve(reference, items)?.let { AvaLibraryRoute.Summarize(it) }
                ?: AvaLibraryRoute.Clarify("I couldn’t identify one saved item to summarize. Nothing was changed.")
        }

        match("(?i)^(?:restore|bring back)\\s+(.+?)\\s+from\\s+(?:the\\s+)?bin$", text)?.let { reference ->
            return resolve(reference, binItems)?.let { item ->
                AvaLibraryRoute.Preview(
                    AvaLibraryAction(
                        kind = AvaLibraryActionKind.RESTORE,
                        description = "Restore “${item.title}” from Bin.",
                        itemIds = listOf(item.id),
                    ),
                )
            } ?: AvaLibraryRoute.Clarify("I couldn’t find that item in Bin. Nothing was changed.")
        }

        matchGroups("(?i)^(?:move|put)\\s+(.+?)\\s+(?:to|into)\\s+(?:the\\s+)?folder\\s+(.+)$", text)?.let { groups ->
            val itemName = clean(groups[0])
            val folderName = clean(groups[1])
            val item = resolve(itemName, items)
                ?: return AvaLibraryRoute.Clarify("I couldn’t identify one saved item to move. Nothing was changed.")
            val folder = folderNames.firstOrNull { it.equals(folderName, ignoreCase = true) }
                ?: return AvaLibraryRoute.Clarify("I couldn’t find the folder “$folderName”. Create it first; nothing was changed.")
            return AvaLibraryRoute.Preview(
                AvaLibraryAction(
                    kind = AvaLibraryActionKind.MOVE_FOLDER,
                    description = "Move “${item.title}” to “$folder”.",
                    itemIds = listOf(item.id),
                    beforeItems = listOf(item),
                    folderName = folder,
                ),
            )
        }

        matchGroups("(?i)^tag\\s+(.+?)\\s+(?:as|with)\\s+(.+)$", text)?.let { groups ->
            val item = resolve(clean(groups[0]), items)
                ?: return AvaLibraryRoute.Clarify("I couldn’t identify one saved item to tag. Nothing was changed.")
            val tag = clean(groups[1]).take(24)
            if (tag.isBlank()) return AvaLibraryRoute.Clarify("Tell me the tag name. Nothing has changed.")
            return AvaLibraryRoute.Preview(
                AvaLibraryAction(
                    kind = AvaLibraryActionKind.TAG,
                    description = "Add the tag “$tag” to “${item.title}”.",
                    itemIds = listOf(item.id),
                    beforeItems = listOf(item),
                    tagValue = tag,
                ),
            )
        }

        match("(?i)^(?:favorite|star)\\s+(.+)$", text)?.let { reference ->
            val item = resolve(clean(reference), items)
                ?: return AvaLibraryRoute.Clarify("I couldn’t identify one saved item to favorite. Nothing was changed.")
            return AvaLibraryRoute.Preview(
                AvaLibraryAction(
                    kind = AvaLibraryActionKind.FAVORITE,
                    description = if (item.isFavorite) "Remove “${item.title}” from Favorites."
                    else "Add “${item.title}” to Favorites.",
                    itemIds = listOf(item.id),
                    beforeItems = listOf(item),
                    favoriteValue = !item.isFavorite,
                ),
            )
        }

        match("(?i)^(?:unfavorite|unstar)\\s+(.+)$", text)?.let { reference ->
            val item = resolve(clean(reference), items)
                ?: return AvaLibraryRoute.Clarify("I couldn’t identify one saved item. Nothing was changed.")
            return AvaLibraryRoute.Preview(
                AvaLibraryAction(
                    kind = AvaLibraryActionKind.FAVORITE,
                    description = "Remove “${item.title}” from Favorites.",
                    itemIds = listOf(item.id),
                    beforeItems = listOf(item),
                    favoriteValue = false,
                ),
            )
        }

        val deleteReference = match("(?i)^(?:delete|remove|trash|move)\\s+(.+?)(?:\\s+(?:to|into)\\s+(?:the\\s+)?bin)?$", text)
        if (deleteReference != null && !deleteReference.contains(Regex("(?i)^(all|everything|my files|all files)$"))) {
            val item = resolve(clean(deleteReference), items)
                ?: return AvaLibraryRoute.Clarify("I couldn’t identify one saved item to move to Bin. Nothing was changed.")
            return AvaLibraryRoute.Preview(
                AvaLibraryAction(
                    kind = AvaLibraryActionKind.MOVE_TO_BIN,
                    description = "Move “${item.title}” to Bin. It can be restored later.",
                    itemIds = listOf(item.id),
                    beforeItems = listOf(item),
                ),
            )
        }

        return AvaLibraryRoute.Chat
    }

    private fun resolve(reference: String, candidates: List<LibraryItemEntity>): LibraryItemEntity? {
        val wanted = clean(reference).lowercase(Locale.ROOT)
        if (wanted.isBlank()) return null
        val matches = candidates.filter { item ->
            val title = item.title.trim().lowercase(Locale.ROOT)
            val titleWithoutExtension = title.substringBeforeLast('.', title)
            wanted == title || wanted == titleWithoutExtension
        }
        return matches.singleOrNull()
    }

    private fun match(pattern: String, text: String): String? =
        Regex(pattern).matchEntire(text)?.groupValues?.drop(1)?.firstOrNull()

    private fun matchGroups(pattern: String, text: String): List<String>? =
        Regex(pattern).matchEntire(text)?.groupValues?.drop(1)

    private fun clean(value: String): String =
        value.trim().trim('"', '\'', '`').trimEnd('.', '!', '?')
}
