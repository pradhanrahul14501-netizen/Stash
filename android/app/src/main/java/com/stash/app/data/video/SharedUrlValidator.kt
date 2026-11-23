package com.stash.app.data.video

import java.net.URI

object SharedUrlValidator {
    fun extractHttpsUrl(sharedText: String): String? {
        val candidate = URL_PATTERN.find(sharedText)?.value
            ?.trimEnd('.', ',', ';', ':', '!', '?', ')', ']', '}')
            ?.takeIf { it.length <= MAX_URL_LENGTH }
            ?: return null
        val parsed = runCatching { URI(candidate) }.getOrNull() ?: return null
        val host = parsed.host?.lowercase() ?: return null
        if (!parsed.scheme.equals("https", ignoreCase = true) || parsed.userInfo != null) return null
        if (isLocalHost(host)) return null
        return parsed.toASCIIString()
    }

    private fun isLocalHost(host: String): Boolean {
        if (host == "localhost" || host.endsWith(".localhost") || host.endsWith(".local")) return true
        val address = host.removePrefix("[").removeSuffix("]")
        val lowerAddress = address.lowercase()
        if (':' in address) {
            if (lowerAddress == "::" || lowerAddress == "::1" ||
                lowerAddress.startsWith("fc") || lowerAddress.startsWith("fd") ||
                lowerAddress.startsWith("fe8") || lowerAddress.startsWith("fe9") ||
                lowerAddress.startsWith("fea") || lowerAddress.startsWith("feb")
            ) return true
            return false
        }
        val octets = address.split('.').mapNotNull(String::toIntOrNull)
        if (octets.size != 4 || octets.any { it !in 0..255 }) return address.matches(NUMERIC_HOST_PATTERN)
        return octets[0] == 10 ||
            octets[0] == 127 ||
            (octets[0] == 169 && octets[1] == 254) ||
            (octets[0] == 172 && octets[1] in 16..31) ||
            (octets[0] == 192 && octets[1] == 168) ||
            octets[0] == 0
    }

    private const val MAX_URL_LENGTH = 4_096
    private val URL_PATTERN = Regex("https://[^\\s<>\\\"']+", RegexOption.IGNORE_CASE)
    private val NUMERIC_HOST_PATTERN = Regex("[0-9.]+")
}
