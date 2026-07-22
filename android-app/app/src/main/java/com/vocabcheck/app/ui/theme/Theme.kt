package com.vocabcheck.app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val Green = Color(0xFF1B4D3E)
private val Sand = Color(0xFFF7F2EA)
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
    surfaceVariant = Color(0xFFEDE6DA),
    onSurfaceVariant = Color(0xFF4A5550),
    error = Coral,
)

@Composable
fun VocabCheckTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = LightColors,
        content = content,
    )
}
