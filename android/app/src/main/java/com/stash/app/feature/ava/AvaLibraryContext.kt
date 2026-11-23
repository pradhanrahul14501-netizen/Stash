package com.stash.app.feature.ava

import com.stash.app.data.local.LibraryItemEntity
import java.text.DateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

internal object AvaLibraryContext {
    private val stopWords = setOf(
        "about", "after", "and", "are", "can", "copy", "copied", "did", "find", "for",
        "from", "have", "how", "into", "item", "items", "latest", "many", "me", "my",
        "please", "recent", "saved", "show", "stash", "that", "the", "there", "this",
        "total", "what", "when", "where", "which", "with", "you", "your",
    )

    fun exactCountAnswer(question: String, items: List<LibraryItemEntity>): String? {
        val normalized = question.lowercase(Locale.ROOT)
        val countQuestion = listOf("how many", "count", "total", "number of")
            .any(normalized::contains)
        if (!countQuestion) return null

        val category = requestedCategory(normalized)
        val dateWindow = requestedDateWindow(normalized)
        val matching = items.filter { item ->
            (category == null || item.category.equals(category, ignoreCase = true)) &&
                (dateWindow == null || dateWindow(item.savedAt))
        }
        val kind = category?.lowercase(Locale.ROOT) ?: "items"
        val period = when {
            normalized.contains("today") -> " saved today"
            normalized.contains("yesterday") -> " saved yesterday"
            else -> " saved in Stash"
        }
        return "You have ${matching.size} $kind$period."
    }

    fun createPrompt(question: String, items: List<LibraryItemEntity>): String {
        val normalized = question.lowercase(Locale.ROOT)
        val category = requestedCategory(normalized)
        val dateWindow = requestedDateWindow(normalized)
        val candidates = items.asSequence()
            .filter { category == null || it.category.equals(category, ignoreCase = true) }
            .filter { dateWindow == null || dateWindow(it.savedAt) }
            .sortedWith(
                compareByDescending<LibraryItemEntity> { relevance(question, it) }
                    .thenByDescending(LibraryItemEntity::savedAt),
            )
            .take(MAX_CONTEXT_ITEMS)
            .toList()

        val context = if (candidates.isEmpty()) {
            "No matching saved items were found in Stash."
        } else {
            candidates.joinToString("\n") { item ->
                val date = DateFormat.getDateTimeInstance(
                    DateFormat.MEDIUM,
                    DateFormat.SHORT,
                ).format(Date(item.savedAt))
                val text = listOfNotNull(item.contentText, item.ocrText)
                    .filter(String::isNotBlank)
                    .joinToString(" ")
                    .takeIf(String::isNotBlank)
                    ?.take(MAX_TEXT_PREVIEW)
                    ?.let { "\n  Saved text: $it" }
                    .orEmpty()
                val folder = item.folderName?.let { " | folder: $it" }.orEmpty()
                val tags = runCatching {
                    val array = org.json.JSONArray(item.tagsJson)
                    (0 until array.length()).map { array.optString(it) }.filter(String::isNotBlank)
                }.getOrDefault(emptyList()).takeIf { it.isNotEmpty() }
                    ?.joinToString(", ", prefix = " | tags: ").orEmpty()
                val favorite = if (item.isFavorite) " | favorite" else ""
                "- ${item.title} | ${item.category.lowercase(Locale.ROOT)} | $date$folder$tags$favorite$text"
            }
        }

        return """
            Current Stash library context (metadata, saved text, and indexed OCR snippets):
            $context

            User question: $question
        """.trimIndent()
    }

    private fun relevance(question: String, item: LibraryItemEntity): Int {
        val queryWords = WORD_PATTERN.findAll(question.lowercase(Locale.ROOT))
            .map { it.value }
            .filter { it !in stopWords }
            .toSet()
        if (queryWords.isEmpty()) return 0

        val title = item.title.lowercase(Locale.ROOT)
        val searchableText = listOf(item.contentText.orEmpty(), item.mimeType, item.category)
            .joinToString(" ")
            .lowercase(Locale.ROOT)
        return queryWords.sumOf { word ->
            (if (word in title) 4 else 0) + (if (word in searchableText) 2 else 0)
        }
    }

    private fun requestedCategory(question: String): String? = when {
        listOf("video", "videos", "reel", "reels", "movie").any(question::contains) -> "VIDEO"
        listOf("audio", "song", "songs", "music").any(question::contains) -> "AUDIO"
        listOf("image", "images", "photo", "photos", "picture", "pictures", "png")
            .any(question::contains) -> "IMAGE"
        listOf("link", "links", "url", "urls", "website").any(question::contains) -> "LINK"
        listOf("text", "texts", "note", "notes").any(question::contains) -> "TEXT"
        listOf("file", "files", "document", "documents").any(question::contains) -> "FILE"
        else -> null
    }

    private fun requestedDateWindow(question: String): ((Long) -> Boolean)? {
        val todayStart = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, 0)
            set(Calendar.MINUTE, 0)
            set(Calendar.SECOND, 0)
            set(Calendar.MILLISECOND, 0)
        }
        return when {
            question.contains("today") -> {
                val start = todayStart.timeInMillis
                val end = start + DAY_MILLIS
                { savedAt: Long -> savedAt >= start && savedAt < end }
            }
            question.contains("yesterday") -> {
                val end = todayStart.timeInMillis
                val start = end - DAY_MILLIS
                { savedAt: Long -> savedAt >= start && savedAt < end }
            }
            else -> null
        }
    }

    private const val MAX_CONTEXT_ITEMS = 6
    private const val MAX_TEXT_PREVIEW = 600
    private const val DAY_MILLIS = 24L * 60L * 60L * 1000L
    private val WORD_PATTERN = Regex("[\\p{L}\\p{N}]{2,}")
}
