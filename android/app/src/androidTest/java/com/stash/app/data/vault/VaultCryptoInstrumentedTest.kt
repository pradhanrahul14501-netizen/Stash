package com.stash.app.data.vault

import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class VaultCryptoInstrumentedTest {
    @Test
    fun deviceBoundVaultKeyAndEncryptedEntryRoundTrip() {
        val crypto = VaultCrypto()
        val password = "Correct horse battery"
        val envelope = crypto.createEnvelope(password)
        try {
            val unlockedKey = crypto.unlock(envelope.encoded, password)
            try {
                assertArrayEquals(envelope.dataKey, unlockedKey)
                val original = VaultSecret("entry-1", 100L, "Email", "user", "secret", "notes")
                val encrypted = crypto.encryptSecret(unlockedKey, original)
                assertEquals(original, crypto.decryptSecret(unlockedKey, encrypted))
            } finally {
                unlockedKey.fill(0)
            }
            assertThrows(VaultPasswordException::class.java) {
                crypto.unlock(envelope.encoded, "A different password")
            }
        } finally {
            envelope.dataKey.fill(0)
        }
    }
}
