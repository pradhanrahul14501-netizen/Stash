package com.stash.app.feature.vault

internal class VaultSessionGeneration {
    private var value = 0L

    fun capture(): Long = value

    fun isCurrent(captured: Long): Boolean = captured == value

    fun advance(): Long {
        value += 1
        return value
    }
}
