package com.vocabcheck.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vocabcheck.app.data.WordEntry
import kotlin.math.roundToInt

@Composable
fun WordCardContent(
    word: WordEntry,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 24.dp, vertical = 28.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            text = word.word,
            style = MaterialTheme.typography.headlineLarge.copy(
                fontWeight = FontWeight.Bold,
                fontSize = 40.sp,
            ),
            textAlign = TextAlign.Center,
            color = MaterialTheme.colorScheme.onSurface,
        )
        Spacer(Modifier.height(28.dp))
        Text(
            text = word.main.ifBlank { "—" },
            style = MaterialTheme.typography.headlineSmall.copy(fontWeight = FontWeight.SemiBold),
            textAlign = TextAlign.Center,
        )
        if (word.also.isNotEmpty()) {
            Spacer(Modifier.height(20.dp))
            word.also.forEach { alt ->
                Text(
                    text = alt,
                    style = MaterialTheme.typography.titleMedium,
                    textAlign = TextAlign.Center,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.75f),
                    modifier = Modifier.padding(vertical = 2.dp),
                )
            }
        }
    }
}

@Composable
fun SwipeableWordCard(
    word: WordEntry,
    onSwipeLeft: () -> Unit,
    onSwipeRight: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val density = LocalDensity.current
    val screenWidthPx = with(density) {
        LocalConfiguration.current.screenWidthDp.dp.toPx()
    }
    val threshold = screenWidthPx * 0.28f

    var offsetX by remember(word.id) { mutableFloatStateOf(0f) }
    var offsetY by remember(word.id) { mutableFloatStateOf(0f) }
    val latestLeft by rememberUpdatedState(onSwipeLeft)
    val latestRight by rememberUpdatedState(onSwipeRight)

    val rotation = (offsetX / screenWidthPx) * 12f
    val okAlpha = (offsetX / threshold).coerceIn(0f, 1f)
    val editAlpha = (-offsetX / threshold).coerceIn(0f, 1f)

    Box(
        modifier = modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        Surface(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp)
                .offset { IntOffset(offsetX.roundToInt(), offsetY.roundToInt()) }
                .rotate(rotation)
                .pointerInput(word.id) {
                    detectDragGestures(
                        onDragEnd = {
                            when {
                                offsetX > threshold -> latestRight()
                                offsetX < -threshold -> latestLeft()
                                else -> {
                                    offsetX = 0f
                                    offsetY = 0f
                                }
                            }
                        },
                        onDragCancel = {
                            offsetX = 0f
                            offsetY = 0f
                        },
                        onDrag = { change, dragAmount ->
                            change.consume()
                            offsetX += dragAmount.x
                            offsetY += dragAmount.y * 0.25f
                        },
                    )
                },
            shape = RoundedCornerShape(28.dp),
            tonalElevation = 2.dp,
            shadowElevation = 8.dp,
            color = MaterialTheme.colorScheme.surface,
        ) {
            Box {
                WordCardContent(
                    word = word,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(420.dp),
                )

                SwipeBadge(
                    text = "OK",
                    color = Color(0xFF2F7D6D),
                    alpha = okAlpha,
                    modifier = Modifier
                        .align(Alignment.TopStart)
                        .padding(20.dp)
                        .graphicsLayer { rotationZ = -12f },
                )
                SwipeBadge(
                    text = "ПРАВКА",
                    color = Color(0xFFC45C4A),
                    alpha = editAlpha,
                    modifier = Modifier
                        .align(Alignment.TopEnd)
                        .padding(20.dp)
                        .graphicsLayer { rotationZ = 12f },
                )
            }
        }
    }
}

@Composable
private fun SwipeBadge(
    text: String,
    color: Color,
    alpha: Float,
    modifier: Modifier = Modifier,
) {
    if (alpha <= 0.01f) return
    Text(
        text = text,
        color = color.copy(alpha = alpha),
        fontWeight = FontWeight.Bold,
        fontSize = 22.sp,
        modifier = modifier
            .border(2.dp, color.copy(alpha = alpha), RoundedCornerShape(8.dp))
            .background(Color.Transparent)
            .padding(horizontal = 12.dp, vertical = 6.dp),
    )
}
