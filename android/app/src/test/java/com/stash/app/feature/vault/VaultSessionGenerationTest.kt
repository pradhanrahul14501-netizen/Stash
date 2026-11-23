package com.stash.app.feature.vault

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class VaultSessionGenerationTest {
    @Test
    fun invalidatesOperationsCapturedBeforeLockOrNewSession() {
        val generation = VaultSessionGeneration()
        val pendingUnlock = generation.capture()

        generation.advance()

        assertFalse(generation.isCurrent(pendingUnlock))
        assertTrue(generation.isCurrent(generation.capture()))
    }
}
