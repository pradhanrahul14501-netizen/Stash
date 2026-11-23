package com.stash.app.data.shared

import android.content.Context
import com.stash.app.data.LibraryRepository
import com.stash.app.data.local.LibraryItemEntity
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

data class SharedSyncResult(val uploaded: Int, val downloaded: Int, val updated: Int)

data class SharedSyncPreview(val savedItems: Int, val fileCount: Int, val fileBytes: Long)

data class SharedServerStatus(
    val sharedMode: Boolean,
    val cloudReady: Boolean,
    val registrationOpen: Boolean,
)

/** Explicit account connection and two-way library sync with Shared Stash. */
class SharedStashRepository(
    context: Context,
    private val libraryRepository: LibraryRepository,
) {
    private val appContext = context.applicationContext
    private val sessions = SharedStashSessionStore(appContext)

    fun serverUrl(): String = sessions.serverUrl()
    fun identity(): String = sessions.identity()
    fun isConnected(): Boolean = sessions.sessionCookie() != null

    suspend fun previewSync(): SharedSyncPreview {
        val items = libraryRepository.observeItems().first()
        val files = items.mapNotNull(libraryRepository::fileFor)
        return SharedSyncPreview(items.size, files.size, files.sumOf { it.length() })
    }

    suspend fun serverStatus(serverUrl: String): SharedServerStatus = withContext(Dispatchers.IO) {
        val base = normalizeBaseUrl(serverUrl)
        val result = request(base, "/api/shared/status", "GET")
        val json = JSONObject(result.body)
        SharedServerStatus(
            sharedMode = json.optBoolean("sharedMode"),
            cloudReady = json.optBoolean("cloudReady"),
            registrationOpen = json.optBoolean("registrationOpen"),
        )
    }

    suspend fun signIn(serverUrl: String, email: String, password: String): String = withContext(Dispatchers.IO) {
        val base = normalizeBaseUrl(serverUrl)
        sessions.clearSession()
        sessions.saveServerUrl(base)
        val status = JSONObject(request(base, "/api/shared/status", "GET").body)
        if (!status.optBoolean("sharedMode")) {
            throw IOException("Shared Stash is not enabled at this address.")
        }
        val config = status.optJSONObject("firebaseConfig")
            ?: throw IOException("This Shared Stash server has not configured email sign-in.")
        val apiKey = config.optString("apiKey").takeIf(String::isNotBlank)
            ?: throw IOException("The server did not provide its sign-in configuration.")
        val firebaseBody = JSONObject()
            .put("email", email.trim())
            .put("password", password)
            .put("returnSecureToken", true)
            .toString()
        val firebaseResult = request(
            "https://identitytoolkit.googleapis.com",
            "/v1/accounts:signInWithPassword?key=$apiKey",
            "POST",
            firebaseBody.toByteArray(Charsets.UTF_8),
        )
        val idToken = JSONObject(firebaseResult.body).optString("idToken")
            .takeIf(String::isNotBlank)
            ?: throw IOException("Firebase did not return a sign-in token.")

        val login = request(
            base,
            "/api/shared/firebase-login",
            "POST",
            JSONObject().put("id_token", idToken).toString().toByteArray(Charsets.UTF_8),
            captureCookie = true,
            sameOrigin = true,
        )
        val cookie = login.sessionCookie ?: throw IOException("Shared Stash did not create a signed-in session.")
        val identity = email.trim().lowercase()
        sessions.saveSession(base, identity, cookie)
        identity
    }

    suspend fun signOut() = withContext(Dispatchers.IO) {
        val base = sessions.serverUrl()
        val cookie = sessions.sessionCookie()
        if (base.isNotBlank() && cookie != null) {
            runCatching {
                request(
                    normalizeBaseUrl(base),
                    "/api/shared/logout",
                    "POST",
                    "{}".toByteArray(Charsets.UTF_8),
                    cookie = cookie,
                    sameOrigin = true,
                )
            }
        }
        sessions.clearSession()
    }

    suspend fun syncNow(): SharedSyncResult = withContext(Dispatchers.IO) {
        val base = normalizeBaseUrl(sessions.serverUrl())
        val cookie = sessions.sessionCookie() ?: throw IOException("Connect your Shared Stash account first.")
        val firstRemote = getRemoteItems(base, cookie)
        val remoteById = firstRemote.associateBy { it.optLong("id") }
        val remoteByClientKey = firstRemote.filter { it.optString("client_key").isNotBlank() }
            .associateBy { it.optString("client_key") }
        val localItems = libraryRepository.allItemsForBackup()
        var uploaded = 0
        var updated = 0

        localItems.filter { it.deletedAt == null }.forEach { item ->
            val remote = item.sharedItemId?.let(remoteById::get) ?: remoteByClientKey[item.id]
            if (remote != null) {
                val remoteId = remote.optLong("id")
                libraryRepository.setSharedItemId(item.id, remoteId)
                pushItem(base, cookie, item, remoteId)
                updated += 1
            } else {
                if (item.sharedItemId != null) libraryRepository.setSharedItemId(item.id, null)
                val pushed = pushItem(base, cookie, item, null)
                val itemJson = pushed.optJSONObject("item")
                    ?: throw IOException("Shared Stash did not confirm the uploaded item.")
                libraryRepository.setSharedItemId(item.id, itemJson.optLong("id"))
                uploaded += 1
            }
        }

        val remoteItems = getRemoteItems(base, cookie)
        val bySharedId = localItems.filter { it.sharedItemId != null }.associateBy { it.sharedItemId }
        val byLocalId = localItems.associateBy(LibraryItemEntity::id)
        var downloaded = 0
        remoteItems.forEach { remote ->
            val remoteId = remote.optLong("id")
            if (remoteId <= 0L) return@forEach
            val clientKey = remote.optString("client_key").takeIf(String::isNotBlank)
            val local = bySharedId[remoteId] ?: clientKey?.let(byLocalId::get)
            val tags = remote.optJSONArray("tags").toStringList()
            val folderName = remote.optString("folder_name").takeIf(String::isNotBlank)
            if (local != null) {
                libraryRepository.updateFromShared(
                    local.id,
                    remoteId,
                    folderName,
                    tags,
                    remote.optBoolean("favorite"),
                )
                return@forEach
            }
            val type = remote.optString("type").ifBlank { "file" }
            val mimeType = remote.optString("mime_type").ifBlank { "application/octet-stream" }
            val relativePath = if (remote.optString("url").startsWith("/api/shared/media/")) {
                "/api/shared/media/$remoteId"
            } else null
            if (relativePath != null) {
                openMedia(base, relativePath, cookie).use { media ->
                    libraryRepository.importFromShared(
                        clientKey, remoteId, remote.optString("title"), type.toCategory(), mimeType,
                        remote.optString("content"), remote.optLong("saved_at"), folderName, tags,
                        remote.optBoolean("favorite"), media,
                    )
                }
            } else {
                libraryRepository.importFromShared(
                    clientKey, remoteId, remote.optString("title"), type.toCategory(), mimeType,
                    remote.optString("content"), remote.optLong("saved_at"), folderName, tags,
                    remote.optBoolean("favorite"), null,
                )
            }
            downloaded += 1
        }
        SharedSyncResult(uploaded, downloaded, updated)
    }

    private suspend fun getRemoteItems(base: String, cookie: String): List<JSONObject> = withContext(Dispatchers.IO) {
        val array = JSONArray(request(base, "/api/shared/native-sync", "GET", cookie = cookie).body)
        (0 until array.length()).mapNotNull(array::optJSONObject)
    }

    private suspend fun pushItem(base: String, cookie: String, item: LibraryItemEntity, remoteId: Long?): JSONObject =
        withContext(Dispatchers.IO) {
            val values = linkedMapOf(
                "client_key" to item.id,
                "remote_id" to (remoteId?.toString() ?: ""),
                "item_type" to item.category.toSharedType(),
                "title" to item.title,
                "mime_type" to item.mimeType,
                "content" to (item.contentText ?: ""),
                "source_url" to if (item.category.equals("LINK", true)) item.contentText.orEmpty() else "",
                "folder_name" to item.folderName.orEmpty(),
                "tags" to item.tagsJson,
                "favorite" to item.isFavorite.toString(),
                "saved_at" to item.savedAt.toString(),
            )
            val file = libraryRepository.fileFor(item)
            val body = if (file == null || remoteId != null) {
                JSONObject().apply {
                    values.forEach { (key, value) ->
                        if (key == "tags") put(key, runCatching { JSONArray(value) }.getOrDefault(JSONArray()))
                        else if (key == "remote_id" && value.isNotBlank()) put(key, value.toLong())
                        else if (key == "favorite") put(key, value.toBoolean())
                        else if (value.isNotBlank() || key in setOf("content", "folder_name", "source_url")) put(key, value)
                    }
                }.toString().toByteArray(Charsets.UTF_8)
            } else {
                val boundary = "StashSync-${UUID.randomUUID()}"
                val prefix = multipartPrefix(boundary, values, file.name, item.mimeType)
                val suffix = "\r\n--$boundary--\r\n".toByteArray(Charsets.UTF_8)
                val total = prefix.size.toLong() + file.length() + suffix.size
                val response = requestStream(base, "/api/shared/native-sync", cookie, boundary, total) { output ->
                    output.write(prefix)
                    file.inputStream().use { it.copyTo(output, 64 * 1024) }
                    output.write(suffix)
                }
                return@withContext JSONObject(response)
            }
            JSONObject(request(base, "/api/shared/native-sync", "POST", body, cookie = cookie, sameOrigin = true).body)
        }

    private fun multipartPrefix(
        boundary: String,
        values: Map<String, String>,
        filename: String,
        mimeType: String,
    ): ByteArray = buildString {
        values.forEach { (name, value) ->
            append("--$boundary\r\n")
            append("Content-Disposition: form-data; name=\"$name\"\r\n\r\n")
            append(value)
            append("\r\n")
        }
        append("--$boundary\r\n")
        append("Content-Disposition: form-data; name=\"file\"; filename=\"${filename.replace('"', '_')}\"\r\n")
        append("Content-Type: ${mimeType.ifBlank { "application/octet-stream" }}\r\n\r\n")
    }.toByteArray(Charsets.UTF_8)

    private fun requestStream(
        base: String,
        path: String,
        cookie: String,
        boundary: String,
        totalBytes: Long,
        writeBody: (java.io.OutputStream) -> Unit,
    ): String {
        val url = URL(base + path)
        val connection = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            instanceFollowRedirects = false
            connectTimeout = CONNECT_TIMEOUT_MS
            readTimeout = READ_TIMEOUT_MS
            doOutput = true
            setFixedLengthStreamingMode(totalBytes)
            setRequestProperty("Content-Type", "multipart/form-data; boundary=$boundary")
            setRequestProperty("Cookie", cookie)
            setRequestProperty("Origin", origin(url))
        }
        try {
            connection.outputStream.use(writeBody)
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val response = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (status !in 200..299) throw IOException(errorMessage(response, status))
            return response
        } finally {
            connection.disconnect()
        }
    }

    private fun openMedia(base: String, path: String, cookie: String): java.io.InputStream {
        val mediaUrl = URL(base + path)
        val connection = (mediaUrl.openConnection() as HttpURLConnection).apply {
            instanceFollowRedirects = false
            connectTimeout = CONNECT_TIMEOUT_MS
            readTimeout = READ_TIMEOUT_MS
            setRequestProperty("Cookie", cookie)
        }
        val status = connection.responseCode
        if (status in 300..399) {
            val location = connection.getHeaderField("Location")
            connection.disconnect()
            val target = location?.let { URL(mediaUrl, it) }
                ?: throw IOException("Shared Stash returned an invalid file link.")
            if (target.protocol != "https" || target.userInfo != null) {
                throw IOException("Shared Stash returned an unsafe file link.")
            }
            val redirected = (target.openConnection() as HttpURLConnection).apply {
                instanceFollowRedirects = true
                connectTimeout = CONNECT_TIMEOUT_MS
                readTimeout = READ_TIMEOUT_MS
            }
            val redirectedStatus = redirected.responseCode
            if (redirectedStatus !in 200..299) {
                val message = redirected.errorStream?.bufferedReader()?.use { it.readText() }.orEmpty()
                redirected.disconnect()
                throw IOException(errorMessage(message, redirectedStatus))
            }
            return managedStream(redirected)
        }
        if (status !in 200..299) {
            val message = connection.errorStream?.bufferedReader()?.use { it.readText() }.orEmpty()
            connection.disconnect()
            throw IOException(errorMessage(message, status))
        }
        return managedStream(connection)
    }

    private fun managedStream(connection: HttpURLConnection): java.io.InputStream =
        connection.inputStream.buffered().let { stream ->
            object : java.io.FilterInputStream(stream) {
                override fun close() {
                    try { super.close() } finally { connection.disconnect() }
                }
            }
        }

    private fun request(
        base: String,
        path: String,
        method: String,
        body: ByteArray? = null,
        cookie: String? = sessions.sessionCookie(),
        captureCookie: Boolean = false,
        sameOrigin: Boolean = false,
    ): HttpResult {
        val url = URL(base + path)
        val connection = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = method
            instanceFollowRedirects = false
            connectTimeout = CONNECT_TIMEOUT_MS
            readTimeout = READ_TIMEOUT_MS
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
            }
            if (cookie != null) setRequestProperty("Cookie", cookie)
            if (sameOrigin) setRequestProperty("Origin", origin(url))
        }
        try {
            if (body != null) connection.outputStream.use { it.write(body) }
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (status !in 200..299) throw IOException(errorMessage(text, status))
            val cookieHeader = if (captureCookie) {
                connection.getHeaderField("Set-Cookie")?.substringBefore(';')
            } else null
            return HttpResult(text, cookieHeader)
        } finally {
            connection.disconnect()
        }
    }

    private fun normalizeBaseUrl(value: String): String {
        val trimmed = value.trim().trimEnd('/')
        val url = runCatching { URL(trimmed) }.getOrElse {
            throw IllegalArgumentException("Enter the Shared Stash HTTPS address.")
        }
        if (url.protocol != "https" || url.host.isBlank() || url.userInfo != null ||
            url.path.isNotBlank() && url.path != "/" || url.query != null || url.ref != null
        ) {
            throw IllegalArgumentException("Use the Shared Stash site address beginning with https://")
        }
        return trimmed
    }

    private fun origin(url: URL): String = "${url.protocol}://${url.authority}"

    private fun errorMessage(body: String, status: Int): String = runCatching {
        JSONObject(body).optString("error").takeIf(String::isNotBlank)
    }.getOrNull() ?: "Shared Stash request failed (HTTP $status)."

    private fun JSONArray?.toStringList(): List<String> {
        val array = this ?: return emptyList()
        return (0 until array.length()).mapNotNull { array.optString(it).takeIf(String::isNotBlank) }.take(12)
    }

    private fun String.toCategory(): String = when (lowercase()) {
        "text" -> "TEXT"
        "link" -> "LINK"
        "image" -> "IMAGE"
        "audio" -> "AUDIO"
        "video" -> "VIDEO"
        else -> "FILE"
    }

    private fun String.toSharedType(): String = when (uppercase()) {
        "TEXT" -> "text"
        "LINK" -> "link"
        "IMAGE" -> "image"
        "AUDIO" -> "audio"
        "VIDEO" -> "video"
        else -> "file"
    }

    private data class HttpResult(val body: String, val sessionCookie: String?)

    private companion object {
        const val CONNECT_TIMEOUT_MS = 15_000
        const val READ_TIMEOUT_MS = 120_000
    }
}
