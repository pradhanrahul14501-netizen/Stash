package com.stash.app.data.video

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class SharedUrlValidatorTest {
    @Test
    fun extractsHttpsLinkAndDropsTrailingPunctuation() {
        assertEquals(
            "https://video.example/watch?id=42",
            SharedUrlValidator.extractHttpsUrl("Watch this: https://video.example/watch?id=42."),
        )
    }

    @Test
    fun rejectsInsecurePrivateAndCredentialBearingLinks() {
        assertNull(SharedUrlValidator.extractHttpsUrl("http://video.example/watch"))
        assertNull(SharedUrlValidator.extractHttpsUrl("https://localhost/watch"))
        assertNull(SharedUrlValidator.extractHttpsUrl("https://192.168.1.12/watch"))
        assertNull(SharedUrlValidator.extractHttpsUrl("https://user:pass@video.example/watch"))
    }

    @Test
    fun rejectsOverlongLinks() {
        assertNull(SharedUrlValidator.extractHttpsUrl("https://video.example/${"a".repeat(4_100)}"))
    }
}
