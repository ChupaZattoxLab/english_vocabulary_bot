package com.vocabcheck.app

import android.app.Application
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.vocabcheck.app.data.ReviewStatus
import com.vocabcheck.app.data.WordEntry
import com.vocabcheck.app.data.WordRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

data class UiState(
    val loaded: Boolean = false,
    val pending: List<WordEntry> = emptyList(),
    val needsEdit: List<WordEntry> = emptyList(),
    val okWords: List<WordEntry> = emptyList(),
    val currentPending: WordEntry? = null,
    val okCount: Int = 0,
    val totalCount: Int = 0,
    val allOk: Boolean = false,
    val selectedEditId: Int? = null,
    val canUndo: Boolean = false,
    val message: String? = null,
)

class MainViewModel(
    application: Application,
    private val repository: WordRepository = WordRepository(application),
) : AndroidViewModel(application) {

    private val selectedEditId = MutableStateFlow<Int?>(null)
    private val reviewCursorId = MutableStateFlow<Int?>(null)
    private val message = MutableStateFlow<String?>(null)
    private val canUndo = MutableStateFlow(false)
    private val undoStack = ArrayDeque<WordEntry>()

    val uiState: StateFlow<UiState> = combine(
        combine(
            repository.words,
            repository.loaded,
            selectedEditId,
            reviewCursorId,
        ) { words, loaded, editId, cursor ->
            ReviewSlice(words, loaded, editId, cursor)
        },
        canUndo,
        message,
    ) { slice, undo, msg ->
        val pending = slice.words.filter { it.status == ReviewStatus.PENDING }
        val okWords = slice.words.filter { it.status == ReviewStatus.OK }
        UiState(
            loaded = slice.loaded,
            pending = pending,
            needsEdit = slice.words.filter { it.status == ReviewStatus.NEEDS_EDIT },
            okWords = okWords,
            currentPending = resolveCurrentPending(pending, slice.cursor),
            okCount = okWords.size,
            totalCount = slice.words.size,
            allOk = slice.words.isNotEmpty() && slice.words.all { it.status == ReviewStatus.OK },
            selectedEditId = slice.editId,
            canUndo = undo,
            message = msg,
        )
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = UiState(),
    )

    init {
        viewModelScope.launch { repository.load() }
    }

    fun findWord(id: Int): WordEntry? = repository.findById(id)

    fun jumpToPending(id: Int) {
        val word = repository.findById(id) ?: return
        if (word.status != ReviewStatus.PENDING) return
        reviewCursorId.value = id
    }

    fun approve(id: Int) {
        pushUndo(id) ?: return
        advanceCursorAfter(id)
        repository.markOk(id)
    }

    fun reject(id: Int) {
        pushUndo(id) ?: return
        advanceCursorAfter(id)
        repository.markNeedsEdit(id)
    }

    fun swapOnCard(id: Int) {
        pushUndo(id) ?: return
        repository.swapMainAndFirstAlso(id)
    }

    fun selectForEdit(id: Int?) {
        selectedEditId.value = id
    }

    fun saveEdit(id: Int, main: String, also: List<String>) {
        if (main.isBlank()) {
            message.value = "Основной перевод обязателен"
            return
        }
        val current = repository.findById(id) ?: return
        val wasNeedsEdit = current.status == ReviewStatus.NEEDS_EDIT
        val nextId = if (wasNeedsEdit) {
            val queue = repository.needsEditWords()
            val idx = queue.indexOfFirst { it.id == id }
            queue.getOrNull(idx + 1)?.id
        } else {
            null
        }

        pushUndo(id) ?: return
        repository.saveEdit(id, main, also, markOk = true)

        selectedEditId.value = nextId
        message.value = when {
            nextId != null -> "Сохранено · следующее слово"
            wasNeedsEdit -> "Сохранено · правок больше нет"
            else -> "Сохранено"
        }
    }

    fun undo() {
        val previous = undoStack.removeLastOrNull() ?: return
        canUndo.value = undoStack.isNotEmpty()
        repository.restoreWord(previous)
        if (previous.status == ReviewStatus.PENDING) {
            reviewCursorId.value = previous.id
            selectedEditId.value = null
        } else if (previous.status == ReviewStatus.NEEDS_EDIT || previous.status == ReviewStatus.OK) {
            selectedEditId.value = previous.id
        }
        message.value = "Отменено: ${previous.word}"
    }

    fun resetProgress() {
        repository.resetAll()
        selectedEditId.value = null
        reviewCursorId.value = null
        undoStack.clear()
        canUndo.value = false
        message.value = "Прогресс сброшен"
    }

    fun clearMessage() {
        message.value = null
    }

    suspend fun exportFile(): File? {
        if (repository.totalCount() == 0) {
            message.value = "Нечего экспортировать"
            return null
        }
        val file = repository.writeExportFile()
        val ok = repository.okCount()
        val total = repository.totalCount()
        message.value = if (repository.allOk()) {
            "Экспорт готов: все $total слов OK"
        } else {
            "Экспорт готов: $ok/$total OK (прогресс неполный)"
        }
        return file
    }

    fun importFromUri(uri: Uri) {
        viewModelScope.launch {
            val result = runCatching {
                val raw = withContext(Dispatchers.IO) {
                    getApplication<Application>().contentResolver
                        .openInputStream(uri)
                        ?.bufferedReader()
                        ?.use { it.readText() }
                        ?: error("Не удалось прочитать файл")
                }
                repository.importExportJson(raw)
            }
            result.onSuccess { imported ->
                selectedEditId.value = null
                reviewCursorId.value = null
                undoStack.clear()
                canUndo.value = false
                message.value =
                    "Импорт: обновлено ${imported.updated} из ${imported.importedCount} · OK ${imported.okCount}"
            }.onFailure {
                message.value = "Ошибка импорта: ${it.message ?: "неверный JSON"}"
            }
        }
    }

    private fun advanceCursorAfter(id: Int) {
        val before = repository.pendingWords()
        val idx = before.indexOfFirst { it.id == id }
        val nextId = before.getOrNull(idx + 1)?.id
        reviewCursorId.value = nextId
    }

    private fun pushUndo(id: Int): WordEntry? {
        val previous = repository.findById(id) ?: return null
        undoStack.addLast(previous)
        while (undoStack.size > 50) {
            undoStack.removeFirst()
        }
        canUndo.value = true
        return previous
    }

    companion object {
        fun resolveCurrentPending(pending: List<WordEntry>, cursor: Int?): WordEntry? {
            if (pending.isEmpty()) return null
            if (cursor == null) return pending.first()
            val atCursor = pending.firstOrNull { it.id == cursor }
            if (atCursor != null) return atCursor
            return pending.firstOrNull { it.id > cursor } ?: pending.first()
        }

        fun factory(application: Application): ViewModelProvider.Factory =
            object : ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : ViewModel> create(modelClass: Class<T>): T {
                    return MainViewModel(application) as T
                }
            }
    }
}

private data class ReviewSlice(
    val words: List<WordEntry>,
    val loaded: Boolean,
    val editId: Int?,
    val cursor: Int?,
)
