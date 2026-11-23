package com.stash.app.data.mobilecompanion

import android.content.Context
import com.stash.app.data.LibraryRepository
import com.stash.app.data.ava.AvaFollowUpRepository
import com.stash.app.data.local.AvaFollowUpEntity
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

data class MobileActionItem(
    val path: String?,
    val destination: String?,
    val size: Long?,
)

data class MobileActionPreview(
    val operation: String,
    val message: String,
    val itemsTotal: Int,
    val itemsTruncated: Boolean,
    val items: List<MobileActionItem>,
)

data class MobileAction(val id: String, val preview: MobileActionPreview)
data class MobileActionResult(val status: String, val message: String)

class MobileCompanionRepository(
    context: Context,
    private val followUpRepository: AvaFollowUpRepository,
    private val libraryRepository: LibraryRepository,
) {
    private val sessions = MobileCompanionSessionStore(context)

    fun connection(): MobileCompanionConnection? = sessions.connection()

    suspend fun pair(address: String, code: String) = withContext(Dispatchers.IO) {
        val base = normalizeAddress(address)
        val result = request(base, "/mobile-companion/pair", "POST", null,
            JSONObject().put("code", code.trim().uppercase()).toString())
        val token = result.optString("token").takeIf(String::isNotBlank)
            ?: throw IOException("Desktop Stash did not finish pairing.")
        sessions.save(base, token)
    }

    suspend fun actions(): List<MobileAction> = withContext(Dispatchers.IO) {
        val connection = requireConnection()
        val response = request(connection.baseUrl, "/mobile-companion/actions", "GET", connection.token, null)
        val items = response.optJSONArray("actions") ?: JSONArray()
        (0 until items.length()).mapNotNull { index ->
            val item = items.optJSONObject(index) ?: return@mapNotNull null
            val preview = item.optJSONObject("preview") ?: JSONObject()
            val previewItems = preview.optJSONArray("items") ?: JSONArray()
            MobileAction(
                id = item.optString("id"),
                preview = MobileActionPreview(
                    operation = preview.optString("operation", "File action"),
                    message = preview.optString("message"),
                    itemsTotal = preview.optInt("items_total", previewItems.length()),
                    itemsTruncated = preview.optBoolean("items_truncated"),
                    items = (0 until previewItems.length()).mapNotNull { itemIndex ->
                        val detail = previewItems.optJSONObject(itemIndex) ?: return@mapNotNull null
                        MobileActionItem(
                            path = detail.optString("path").takeIf(String::isNotBlank),
                            destination = detail.optString("destination").takeIf(String::isNotBlank),
                            size = detail.optLong("size").takeIf { detail.has("size") && !detail.isNull("size") },
                        )
                    },
                ),
            )
        }
    }

    suspend fun decide(actionId: String, approved: Boolean) = withContext(Dispatchers.IO) {
        val connection = requireConnection()
        request(
            connection.baseUrl,
            "/mobile-companion/actions/${actionId.encodePathSegment()}/decision",
            "POST",
            connection.token,
            JSONObject().put("decision", if (approved) "approved" else "rejected").toString(),
        )
    }

    suspend fun awaitActionResult(actionId: String): MobileActionResult = withContext(Dispatchers.IO) {
        val connection = requireConnection()
        val deadline = System.currentTimeMillis() + 5 * 60 * 1000L
        while (System.currentTimeMillis() < deadline) {
            val response = request(
                connection.baseUrl,
                "/mobile-companion/actions/${actionId.encodePathSegment()}",
                "GET",
                connection.token,
                null,
            )
            val result = MobileActionResult(response.optString("status"), response.optString("message"))
            if (result.status in setOf("executed", "error", "rejected")) return@withContext result
            delay(1_000)
        }
        throw IOException("Desktop Stash is still working. Refresh the Action Inbox in a moment.")
    }

    suspend fun syncFollowUps(): Int = withContext(Dispatchers.IO) {
        val connection = requireConnection()
        val local = followUpRepository.allForSync()
        val outgoing = JSONArray().apply { local.forEach { put(it.toJson()) } }
        val response = request(
            connection.baseUrl,
            "/mobile-companion/follow-ups",
            "PUT",
            connection.token,
            JSONObject().put("follow_ups", outgoing).toString(),
        )
        val remote = response.optJSONArray("follow_ups") ?: JSONArray()
        val records = (0 until remote.length()).mapNotNull { index ->
            remote.optJSONObject(index)?.toEntity()
        }
        val itemIds = libraryRepository.allItemsForBackup().mapTo(mutableSetOf()) { it.id }
        followUpRepository.mergeRemote(records, itemIds)
        records.count { it.deletedAt == null }
    }

    suspend fun unpair() = withContext(Dispatchers.IO) {
        val connection = sessions.connection()
        if (connection != null) {
            runCatching {
                request(connection.baseUrl, "/mobile-companion/unpair", "POST", connection.token, "{}")
            }
        }
        sessions.clear()
    }

    private fun requireConnection(): MobileCompanionConnection = sessions.connection()
        ?: throw IOException("Connect Android Stash to desktop Stash first.")

    private fun request(
        base: String,
        path: String,
        method: String,
        token: String?,
        body: String?,
    ): JSONObject {
        val connection = (URL(base + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 6_000
            readTimeout = 12_000
            setRequestProperty("Accept", "application/json")
            token?.let { setRequestProperty("Authorization", "Bearer $it") }
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
            }
        }
        try {
            if (body != null) connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            val result = runCatching { JSONObject(text) }.getOrDefault(JSONObject())
            if (status !in 200..299) throw IOException(result.optString("error").ifBlank { "Desktop Stash returned HTTP $status." })
            return result
        } finally {
            connection.disconnect()
        }
    }

    private fun normalizeAddress(value: String): String {
        val uri = runCatching { URI(value.trim().trimEnd('/')) }
            .getOrElse { throw IllegalArgumentException("Enter the desktop address shown in Stash Settings.") }
        val host = uri.host.orEmpty()
        val octets = host.split('.')
        val isNumericIpv4 = octets.size == 4 && octets.all { part -> part.toIntOrNull()?.let { it in 0..255 } == true }
        val first = octets.firstOrNull()?.toIntOrNull()
        val second = octets.getOrNull(1)?.toIntOrNull()
        val privateAddress = isNumericIpv4 && (
            first == 10 || first == 192 && second == 168 || first == 172 && second != null && second in 16..31
        )
        require(
            uri.scheme.equals("http", true) && privateAddress && uri.port == 5052 &&
                uri.userInfo == null && uri.path in listOf("", "/") && uri.query == null && uri.fragment == null,
        ) { "Use the private Wi-Fi address and port shown in desktop Stash Settings." }
        return "http://$host:5052"
    }

    private fun AvaFollowUpEntity.toJson(): JSONObject = JSONObject()
        .put("id", id)
        .put("sourceItemId", sourceItemId)
        .put("sourceTitle", sourceTitle)
        .put("eventLabel", eventLabel)
        .put("eventAt", eventAt)
        .put("remindAt", remindAt)
        .put("createdAt", createdAt)
        .put("updatedAt", updatedAt)
        .put("deletedAt", deletedAt ?: JSONObject.NULL)
        .put("notifiedAt", notifiedAt ?: JSONObject.NULL)

    private fun JSONObject.toEntity(): AvaFollowUpEntity = AvaFollowUpEntity(
        id = getString("id"),
        sourceItemId = getString("sourceItemId"),
        sourceTitle = optString("sourceTitle"),
        eventLabel = optString("eventLabel"),
        sourceExcerpt = "",
        eventAt = optLong("eventAt"),
        remindAt = optLong("remindAt"),
        createdAt = optLong("createdAt"),
        notifiedAt = optNullableLong("notifiedAt"),
        updatedAt = optLong("updatedAt", optLong("createdAt")),
        deletedAt = optNullableLong("deletedAt"),
    )

    private fun JSONObject.optNullableLong(key: String): Long? =
        if (!has(key) || isNull(key)) null else optLong(key).takeIf { it > 0L }

    private fun String.encodePathSegment(): String = java.net.URLEncoder.encode(this, "UTF-8")
}
