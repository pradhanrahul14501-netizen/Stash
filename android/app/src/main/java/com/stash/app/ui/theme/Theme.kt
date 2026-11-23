package com.stash.app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

private val StashDarkColors = darkColorScheme(
    primary = StashLime,
    onPrimary = StashBackground,
    background = StashBackground,
    onBackground = StashText,
    surface = StashSurface,
    onSurface = StashText,
    onSurfaceVariant = StashMutedText,
)

@Composable
fun StashTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = StashDarkColors,
        content = content,
    )
}
