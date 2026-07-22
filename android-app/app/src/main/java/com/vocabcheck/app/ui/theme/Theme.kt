package com.vocabcheck.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val Green = Color(0xFF1B4D3E)
private val Sand = Color(0xFFF3EDE3)
private val Ink = Color(0xFF1A2421)
private val Coral = Color(0xFFC45C4A)
private val Mint = Color(0xFF2F7D6D)
private val CardColor = Color(0xFFFFFBF6)

private val LightColors = lightColorScheme(
    primary = Green,
    onPrimary = Color.White,
    secondary = Mint,
    onSecondary = Color.White,
    tertiary = Coral,
    background = Sand,
    onBackground = Ink,
    surface = CardColor,
    onSurface = Ink,
    error = Coral,
)

private val DarkColors = darkColorScheme(
    primary = Mint,
    onPrimary = Color.White,
    secondary = Green,
    tertiary = Coral,
    background = Color(0xFF121816),
    onBackground = Color(0xFFE8EFEA),
    surface = Color(0xFF1C2622),
    onSurface = Color(0xFFE8EFEA),
    error = Coral,
)

@Composable
fun VocabCheckTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        content = content,
    )
}
