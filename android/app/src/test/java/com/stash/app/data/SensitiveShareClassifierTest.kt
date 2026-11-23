package com.stash.app.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class SensitiveShareClassifierTest {
    @Test
    fun classifiesExplicitSecretLabels() {
        assertEquals("Shared password", SensitiveShareClassifier.classify("Password: spring-123")?.title)
        assertEquals("Shared verification code", SensitiveShareClassifier.classify("Your OTP is 348921")?.title)
        assertEquals("Shared private key or token", SensitiveShareClassifier.classify("API key: sk-abcdefghijklmnopqrstuvwxyz")?.title)
    }

    @Test
    fun leavesOrdinaryTextAndBlankInputUnclassified() {
        assertNull(SensitiveShareClassifier.classify("Remember to pick up groceries"))
        assertNull(SensitiveShareClassifier.classify("  "))
    }
}
