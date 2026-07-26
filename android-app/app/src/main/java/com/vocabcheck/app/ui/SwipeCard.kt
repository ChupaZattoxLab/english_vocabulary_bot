package com.vocabcheck.app.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.OpenInNew
import androidx.compose.material.icons.filled.VolumeUp
import androidx.compose.material3.AssistChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.vocabcheck.app.audio.rememberPronunciationPlayer
import com.vocabcheck.app.data.WordEntry
import kotlin.math.roundToInt

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun WordCardContent(
    word: WordEntry,
    modifier: Modifier = Modifier,
) {
    val player = rememberPronunciationPlayer()
    val context = LocalContext.current

    Column(
        modifier = modifier
            .fillMaxWidth()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 18.dp, vertical = 20.dp),
        horizontalAlignment = Alignment.Start,
    ) {
        Text(
            text = word.headword(),
            style = MaterialTheme.typography.headlineLarge.copy(
                fontWeight = FontWeight.Bold,
                fontSize = 34.sp,
            ),
            modifier = Modifier.fillMaxWidth(),
            textAlign = TextAlign.Center,
        )

        val metaBits = buildList {
            if (word.pos.isNotBlank()) add(word.pos)
            if (word.cefr.isNotBlank()) add(word.cefr.uppercase())
        }
        if (metaBits.isNotEmpty()) {
            Spacer(Modifier.height(6.dp))
            Text(
                text = metaBits.joinToString(" · "),
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.55f),
                modifier = Modifier.fillMaxWidth(),
                textAlign = TextAlign.Center,
            )
        }

        if (word.wordUs.isNotBlank() && word.wordGb.isNotBlank() &&
            !word.wordUs.equals(word.wordGb, ignoreCase = true)
        ) {
            Spacer(Modifier.height(8.dp))
            Text(
                text = "US: ${word.wordUs} · GB: ${word.wordGb}",
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.fillMaxWidth(),
                textAlign = TextAlign.Center,
            )
        }

        CardBlock(title = "Перевод") {
            Text(
                text = word.main.ifBlank { "—" },
                style = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.SemiBold),
            )
            if (word.also.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                word.also.forEach { alt ->
                    Text(
                        text = "· $alt",
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.75f),
                        modifier = Modifier.padding(vertical = 1.dp),
                    )
                }
            }
        }

        CardBlock(title = "Произношение") {
            PronunciationRow(
                label = "US",
                ipa = word.ipaUs,
                audio = word.audioUs,
                onPlay = player::play,
            )
            Spacer(Modifier.height(10.dp))
            PronunciationRow(
                label = "GB",
                ipa = word.ipaGb,
                audio = word.audioGb,
                onPlay = player::play,
            )
        }

        CardBlock(title = "Definition / Example") {
            SenseBlock(definition = word.definition, example = word.example)
            word.extraSenses.forEachIndexed { index, sense ->
                Spacer(Modifier.height(12.dp))
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                Spacer(Modifier.height(12.dp))
                Text(
                    text = "Доп. ${index + 1}",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.primary,
                )
                Spacer(Modifier.height(6.dp))
                SenseBlock(definition = sense.definition, example = sense.example)
            }
        }

        if (word.definitionUrlOxford.isNotBlank() || word.definitionUrlCambridge.isNotBlank()) {
            CardBlock(title = "Словари") {
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    if (word.definitionUrlOxford.isNotBlank()) {
                        TextButton(
                            onClick = {
                                context.startActivity(
                                    Intent(Intent.ACTION_VIEW, Uri.parse(word.definitionUrlOxford)),
                                )
                            },
                        ) {
                            Icon(Icons.Default.OpenInNew, contentDescription = null)
                            Text(" Oxford")
                        }
                    }
                    if (word.definitionUrlCambridge.isNotBlank()) {
                        TextButton(
                            onClick = {
                                context.startActivity(
                                    Intent(Intent.ACTION_VIEW, Uri.parse(word.definitionUrlCambridge)),
                                )
                            },
                        ) {
                            Icon(Icons.Default.OpenInNew, contentDescription = null)
                            Text(" Cambridge")
                        }
                    }
                }
            }
        }

        Spacer(Modifier.height(8.dp))
    }
}

@Composable
private fun CardBlock(
    title: String,
    content: @Composable () -> Unit,
) {
    Spacer(Modifier.height(16.dp))
    HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.7f))
    Spacer(Modifier.height(12.dp))
    Text(
        text = title,
        style = MaterialTheme.typography.labelLarge,
        color = MaterialTheme.colorScheme.primary,
        fontWeight = FontWeight.SemiBold,
    )
    Spacer(Modifier.height(8.dp))
    content()
}

@Composable
private fun SenseBlock(
    definition: String,
    example: String,
) {
    Text(
        text = definition.ifBlank { "—" },
        style = MaterialTheme.typography.bodyLarge,
    )
    if (example.isNotBlank()) {
        Spacer(Modifier.height(6.dp))
        Text(
            text = example,
            style = MaterialTheme.typography.bodyMedium.copy(fontStyle = FontStyle.Italic),
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.75f),
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PronunciationRow(
    label: String,
    ipa: List<String>,
    audio: List<String>,
    onPlay: (String) -> Unit,
) {
    Column(modifier = Modifier.fillMaxWidth()) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.SemiBold,
        )
        if (ipa.isNotEmpty()) {
            Text(
                text = ipa.joinToString("  "),
                style = MaterialTheme.typography.bodyLarge,
            )
        } else {
            Text(
                text = "—",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.45f),
            )
        }
        if (audio.isNotEmpty()) {
            Spacer(Modifier.height(4.dp))
            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                audio.forEachIndexed { index, url ->
                    AssistChip(
                        onClick = { onPlay(url) },
                        label = {
                            Text(if (audio.size == 1) "Слушать" else "Слушать ${index + 1}")
                        },
                        leadingIcon = {
                            Icon(Icons.Default.VolumeUp, contentDescription = null)
                        },
                    )
                }
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
                .padding(horizontal = 12.dp)
                .heightIn(min = 420.dp, max = 560.dp)
                .offset { IntOffset(offsetX.roundToInt(), 0) }
                .rotate(rotation)
                .pointerInput(word.id) {
                    detectHorizontalDragGestures(
                        onDragEnd = {
                            when {
                                offsetX > threshold -> latestRight()
                                offsetX < -threshold -> latestLeft()
                                else -> offsetX = 0f
                            }
                        },
                        onDragCancel = { offsetX = 0f },
                        onHorizontalDrag = { change, dragAmount ->
                            change.consume()
                            offsetX += dragAmount
                        },
                    )
                },
            shape = RoundedCornerShape(24.dp),
            tonalElevation = 2.dp,
            shadowElevation = 8.dp,
            color = MaterialTheme.colorScheme.surface,
        ) {
            Box {
                WordCardContent(
                    word = word,
                    modifier = Modifier.fillMaxSize(),
                )

                SwipeBadge(
                    text = "OK",
                    color = Color(0xFF2F7D6D),
                    alpha = okAlpha,
                    modifier = Modifier
                        .align(Alignment.TopStart)
                        .padding(16.dp)
                        .graphicsLayer { rotationZ = -12f },
                )
                SwipeBadge(
                    text = "ПРАВКА",
                    color = Color(0xFFC45C4A),
                    alpha = editAlpha,
                    modifier = Modifier
                        .align(Alignment.TopEnd)
                        .padding(16.dp)
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
