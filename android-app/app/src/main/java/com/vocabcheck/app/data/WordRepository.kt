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
        val bundled = loadBundled()
        val restored = restoreProgress()
        _words.value = if (restored != null) mergeProgress(bundled, restored) else bundled
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

    private fun mergeProgress(bundled: List<WordEntry>, saved: List<WordEntry>): List<WordEntry> {
        val savedById = saved.associateBy { it.id }
        return bundled.map { base ->
            val s = savedById[base.id] ?: return@map base
            base.copy(
                main = s.main,
                also = s.also,
                status = s.status,
                definition = s.definition.ifBlank { base.definition },
                example = s.example.ifBlank { base.example },
                extraSenses = s.extraSenses,
            )
        }
    }

    private fun persist() {
        val snapshot = ProgressSnapshot(_words.value)
        progressFile.writeText(json.encodeToString(snapshot))
    }

    fun markOk(id: Int) = updateWord(id) { it.copy(status = ReviewStatus.OK) }

    fun markNeedsEdit(id: Int) = updateWord(id) { it.copy(status = ReviewStatus.NEEDS_EDIT) }

    fun findById(id: Int): WordEntry? = _words.value.firstOrNull { it.id == id }

    fun restoreWord(word: WordEntry) = updateWord(word.id) { word }

    fun swapMainAndFirstAlso(id: Int) = updateWord(id) { word ->
        val firstAlso = word.also.firstOrNull() ?: return@updateWord word
        val remaining = word.also.drop(1).toMutableList()
        if (word.main.isNotBlank()) {
            remaining.add(0, word.main)
        }
        word.copy(main = firstAlso, also = remaining)
    }

    fun saveEdit(id: Int, payload: WordEditPayload, markOk: Boolean) = updateWord(id) { word ->
        word.copy(
            main = payload.main.trim(),
            also = payload.also.map { it.trim() }.filter { it.isNotEmpty() },
            definition = payload.definition.trim(),
            example = payload.example.trim(),
            extraSenses = payload.extraSenses
                .map { SensePair(it.definition.trim(), it.example.trim()) }
                .filter { it.definition.isNotEmpty() || it.example.isNotEmpty() },
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
                word = word.headword(),
                wordUs = word.wordUs.ifBlank { word.word },
                wordGb = word.wordGb.ifBlank { word.word },
                pos = word.pos,
                cefr = word.cefr,
                status = word.status,
                definitionUrlOxford = word.definitionUrlOxford,
                definitionUrlCambridge = word.definitionUrlCambridge,
                ipaUs = word.ipaUs,
                ipaGb = word.ipaGb,
                definition = word.definition,
                example = word.example,
                extraSenses = word.extraSenses,
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

    /**
     * Snapshot in app files (same JSON shape as export).
     * Skips if this milestone file already exists.
     */
    suspend fun writeAutoBackupIfNeeded(okMilestone: Int): File? = withContext(Dispatchers.IO) {
        if (okMilestone < 100 || okMilestone % 100 != 0) return@withContext null
        val dir = File(context.filesDir, "auto_backups").apply { mkdirs() }
        val file = File(dir, "vocab_backup_${okMilestone}ok.json")
        if (file.exists()) return@withContext null
        file.writeText(buildExportJson())
        // Keep only the latest few milestones to limit disk use
        dir.listFiles()
            ?.filter { it.name.startsWith("vocab_backup_") && it.name.endsWith("ok.json") }
            ?.sortedByDescending { it.lastModified() }
            ?.drop(5)
            ?.forEach { it.delete() }
        file
    }

    suspend fun importExportJson(raw: String): ImportResult = withContext(Dispatchers.IO) {
        val imported = json.decodeFromString<List<ExportWord>>(raw)
        val byWordPos = LinkedHashMap<Pair<String, String>, ExportWord>()
        val byWord = LinkedHashMap<String, MutableList<ExportWord>>()
        for (item in imported) {
            val wordKey = item.word.trim().lowercase()
            val posKey = item.pos.trim().lowercase()
            byWordPos[wordKey to posKey] = item
            byWord.getOrPut(wordKey) { mutableListOf() }.add(item)
        }

        var updated = 0
        _words.update { list ->
            list.map { word ->
                val wordKey = word.headword().trim().lowercase()
                val posKey = word.pos.trim().lowercase()
                val match = byWordPos[wordKey to posKey]
                    ?: byWord[wordKey]?.singleOrNull()
                    ?: byWord[wordKey]?.firstOrNull { it.pos.isBlank() || word.pos.isBlank() }
                if (match == null) {
                    word
                } else {
                    updated++
                    word.copy(
                        main = match.translations.ru.main,
                        also = match.translations.ru.also,
                        status = match.status,
                        definition = match.definition.ifBlank { word.definition },
                        example = match.example.ifBlank { word.example },
                        extraSenses = match.extraSenses.ifEmpty { word.extraSenses },
                    )
                }
            }
        }
        persist()
        ImportResult(
            updated = updated,
            importedCount = imported.size,
            okCount = _words.value.count { it.status == ReviewStatus.OK },
        )
    }

    private fun updateWord(id: Int, transform: (WordEntry) -> WordEntry) {
        _words.update { list ->
            list.map { if (it.id == id) transform(it) else it }
        }
        persist()
    }
}
