package com.vocabcheck.app.data

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.withContext
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.io.File

class WordRepository(private val context: Context) {

    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    private val progressFile: File
        get() = File(context.filesDir, "progress.json")

    private val _words = MutableStateFlow<List<WordEntry>>(emptyList())
    val words: StateFlow<List<WordEntry>> = _words.asStateFlow()

    private val _loaded = MutableStateFlow(false)
    val loaded: StateFlow<Boolean> = _loaded.asStateFlow()

    suspend fun load() = withContext(Dispatchers.IO) {
        if (_loaded.value) return@withContext
        val restored = restoreProgress()
        _words.value = restored ?: loadBundled()
        _loaded.value = true
    }

    private fun loadBundled(): List<WordEntry> {
        val raw = context.assets.open("words_slim.json").bufferedReader().use { it.readText() }
        return json.decodeFromString<List<WordEntry>>(raw)
    }

    private fun restoreProgress(): List<WordEntry>? {
        if (!progressFile.exists()) return null
        return runCatching {
            json.decodeFromString<ProgressSnapshot>(progressFile.readText()).words
        }.getOrNull()
    }

    private fun persist() {
        val snapshot = ProgressSnapshot(_words.value)
        progressFile.writeText(json.encodeToString(snapshot))
    }

    fun markOk(id: Int) = updateWord(id) { it.copy(status = ReviewStatus.OK) }

    fun markNeedsEdit(id: Int) = updateWord(id) { it.copy(status = ReviewStatus.NEEDS_EDIT) }

    fun swapMainAndFirstAlso(id: Int) = updateWord(id) { word ->
        val firstAlso = word.also.firstOrNull() ?: return@updateWord word
        val remaining = word.also.drop(1).toMutableList()
        if (word.main.isNotBlank()) {
            remaining.add(0, word.main)
        }
        word.copy(main = firstAlso, also = remaining)
    }

    fun saveEdit(id: Int, main: String, also: List<String>, markOk: Boolean) = updateWord(id) { word ->
        word.copy(
            main = main.trim(),
            also = also.map { it.trim() }.filter { it.isNotEmpty() },
            status = if (markOk) ReviewStatus.OK else ReviewStatus.NEEDS_EDIT,
        )
    }

    fun resetAll() {
        _words.value = loadBundled()
        persist()
    }

    fun pendingWords(): List<WordEntry> =
        _words.value.filter { it.status == ReviewStatus.PENDING }

    fun needsEditWords(): List<WordEntry> =
        _words.value.filter { it.status == ReviewStatus.NEEDS_EDIT }

    fun okCount(): Int = _words.value.count { it.status == ReviewStatus.OK }

    fun totalCount(): Int = _words.value.size

    fun allOk(): Boolean =
        _words.value.isNotEmpty() && _words.value.all { it.status == ReviewStatus.OK }

    private val exportJson = Json {
        prettyPrint = true
        encodeDefaults = true
    }

    fun buildExportJson(): String {
        val payload = _words.value.map { word ->
            ExportWord(
                word = word.word,
                pos = word.pos,
                translations = ExportTranslations(
                    ru = ExportRu(
                        main = word.main,
                        also = word.also,
                    ),
                ),
            )
        }
        return exportJson.encodeToString(payload)
    }

    suspend fun writeExportFile(): File = withContext(Dispatchers.IO) {
        val dir = File(context.cacheDir, "exports").apply { mkdirs() }
        File(dir, "vocab_checked.json").apply {
            writeText(buildExportJson())
        }
    }

    private fun updateWord(id: Int, transform: (WordEntry) -> WordEntry) {
        _words.update { list ->
            list.map { if (it.id == id) transform(it) else it }
        }
        persist()
    }
}
