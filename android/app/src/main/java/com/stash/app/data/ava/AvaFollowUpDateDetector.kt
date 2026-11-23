package com.stash.app.data.ava

import com.stash.app.data.local.LibraryItemEntity
import java.text.SimpleDateFormat
import java.time.LocalDate
import java.time.ZoneId
import java.util.Date
import java.util.Locale
import java.util.regex.Pattern

data class AvaDateSuggestion(
    val sourceItemId: String,
    val sourceTitle: String,
    val eventLabel: String,
    val eventAt: Long,
    val matchedDate: String,
    val sourceExcerpt: String,
)

/** Finds explicit, future calendar dates in saved text and on-device OCR results. */
object AvaFollowUpDateDetector {
    private val isoDate = Pattern.compile("(?<!\\d)(20\\d{2})-(\\d{1,2})-(\\d{1,2})(?!\\d)")
    private val numericDate = Pattern.compile("(?<!\\d)(\\d{1,2})[./-](\\d{1,2})[./-](20\\d{2})(?!\\d)")
    private val monthFirst = Pattern.compile(
        "(?i)\\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\\.?\\s+(\\d{1,2})(?:st|nd|rd|th)?[,]?\\s+(20\\d{2})\\b",
    )
    private val dayFirst = Pattern.compile(
        "(?i)\\b(\\d{1,2})(?:st|nd|rd|th)?\\s+(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\\.?[,]?\\s+(20\\d{2})\\b",
    )
    private val monthNumbers = mapOf(
        "JAN" to 1, "FEB" to 2, "MAR" to 3, "APR" to 4, "MAY" to 5, "JUN" to 6,
        "JUL" to 7, "AUG" to 8, "SEP" to 9, "SEPT" to 9, "OCT" to 10, "NOV" to 11,
        "DEC" to 12,
    )

    fun detect(item: LibraryItemEntity, today: LocalDate = LocalDate.now()): List<AvaDateSuggestion> {
        val text = listOfNotNull(item.contentText, item.ocrText)
            .filter(String::isNotBlank)
            .joinToString("\n")
            .take(MAX_SOURCE_CHARACTERS)
        if (text.isBlank()) return emptyList()

        val found = mutableListOf<AvaDateSuggestion>()
        addMatches(text, isoDate, found) { matcher ->
            localDate(matcher.group(1).orEmpty().toInt(), matcher.group(2).orEmpty().toInt(), matcher.group(3).orEmpty().toInt())
        }
        addMatches(text, numericDate, found) { matcher ->
            val first = matcher.group(1).orEmpty().toInt()
            val second = matcher.group(2).orEmpty().toInt()
            val year = matcher.group(3).orEmpty().toInt()
            if (first <= 12 && second <= 12 && first != second) return@addMatches null
            val dayFirstOrder = when {
                first > 12 -> true
                second > 12 -> false
                else -> numericDateIsDayFirst()
            }
            val day = if (dayFirstOrder) first else second
            val month = if (dayFirstOrder) second else first
            localDate(year, month, day)
        }
        addMatches(text, monthFirst, found) { matcher ->
            localDate(matcher.group(3).orEmpty().toInt(), monthNumber(matcher.group(1).orEmpty()), matcher.group(2).orEmpty().toInt())
        }
        addMatches(text, dayFirst, found) { matcher ->
            localDate(matcher.group(3).orEmpty().toInt(), monthNumber(matcher.group(2).orEmpty()), matcher.group(1).orEmpty().toInt())
        }

        return found.asSequence()
            .filter { suggestion ->
                val date = Date(suggestion.eventAt).toInstant().atZone(ZoneId.systemDefault()).toLocalDate()
                !date.isBefore(today)
            }
            .distinctBy(AvaDateSuggestion::eventAt)
            .sortedBy(AvaDateSuggestion::eventAt)
            .take(MAX_SUGGESTIONS_PER_ITEM)
            .map { it.copy(sourceItemId = item.id, sourceTitle = item.title) }
            .toList()
    }

    private fun addMatches(
        text: String,
        pattern: Pattern,
        output: MutableList<AvaDateSuggestion>,
        parseDate: (java.util.regex.Matcher) -> LocalDate?,
    ) {
        val matcher = pattern.matcher(text)
        while (matcher.find()) {
            val date = runCatching { parseDate(matcher) }.getOrNull() ?: continue
            val eventAt = date.atStartOfDay(ZoneId.systemDefault()).toInstant().toEpochMilli()
            val start = (matcher.start() - EXCERPT_CONTEXT).coerceAtLeast(0)
            val end = (matcher.end() + EXCERPT_CONTEXT).coerceAtMost(text.length)
            val excerpt = text.substring(start, end).replace(Regex("\\s+"), " ").trim().take(MAX_EXCERPT_CHARACTERS)
            val nearbyText = text.substring(start, end)
            output += AvaDateSuggestion(
                sourceItemId = "",
                sourceTitle = "",
                eventLabel = labelFor(nearbyText),
                eventAt = eventAt,
                matchedDate = matcher.group(),
                sourceExcerpt = excerpt,
            )
        }
    }

    private fun localDate(year: Int, month: Int, day: Int): LocalDate? =
        runCatching { LocalDate.of(year, month, day) }.getOrNull()

    private fun monthNumber(month: String): Int {
        val normalized = month.trimEnd('.').uppercase(Locale.ROOT)
        return monthNumbers[normalized] ?: monthNumbers[normalized.take(3)] ?: 1
    }

    private fun numericDateIsDayFirst(): Boolean {
        val pattern = (java.text.DateFormat.getDateInstance(java.text.DateFormat.SHORT) as? SimpleDateFormat)
            ?.toPattern()
            .orEmpty()
        val dayIndex = pattern.indexOf('d').let { if (it < 0) Int.MAX_VALUE else it }
        val monthIndex = pattern.indexOf('M').let { if (it < 0) Int.MIN_VALUE else it }
        return dayIndex < monthIndex
    }

    private fun labelFor(text: String): String = when {
        RETURN_PATTERN.containsMatchIn(text) -> "Return or refund deadline"
        EXPIRY_PATTERN.containsMatchIn(text) -> "Expiry or renewal date"
        PAYMENT_PATTERN.containsMatchIn(text) -> "Payment due date"
        EVENT_PATTERN.containsMatchIn(text) -> "Event or appointment"
        else -> "Important date"
    }

    private val RETURN_PATTERN = Regex("(?i)\\b(return|refund|exchange|last day to return|return by)\\b")
    private val EXPIRY_PATTERN = Regex("(?i)\\b(expir(?:y|es|ation)|valid until|renew(?:al|s| by)?)\\b")
    private val PAYMENT_PATTERN = Regex("(?i)\\b(due|payment|pay by|bill)\\b")
    private val EVENT_PATTERN = Regex("(?i)\\b(flight|departure|boarding|check.?in|appointment|booking|reservation|conference|event)\\b")

    private const val MAX_SOURCE_CHARACTERS = 100_000
    private const val MAX_EXCERPT_CHARACTERS = 220
    private const val EXCERPT_CONTEXT = 72
    private const val MAX_SUGGESTIONS_PER_ITEM = 6
}
