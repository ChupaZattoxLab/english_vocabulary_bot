package com.vocabcheck.app.audio

import android.media.AudioAttributes
import android.media.MediaPlayer
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember

class PronunciationPlayer {
    private var player: MediaPlayer? = null

    fun play(url: String) {
        if (url.isBlank()) return
        stop()
        runCatching {
            player = MediaPlayer().apply {
                setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build(),
                )
                setDataSource(url)
                setOnPreparedListener { start() }
                setOnCompletionListener { stop() }
                setOnErrorListener { _, _, _ ->
                    stop()
                    true
                }
                prepareAsync()
            }
        }.onFailure {
            stop()
        }
    }

    fun stop() {
        runCatching {
            player?.reset()
            player?.release()
        }
        player = null
    }
}

@Composable
fun rememberPronunciationPlayer(): PronunciationPlayer {
    val player = remember { PronunciationPlayer() }
    DisposableEffect(player) {
        onDispose { player.stop() }
    }
    return player
}
