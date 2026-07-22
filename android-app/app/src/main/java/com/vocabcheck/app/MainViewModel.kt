package com.vocabcheck.app

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.vocabcheck.app.data.ReviewStatus
import com.vocabcheck.app.data.WordEntry
import com.vocabcheck.app.data.WordRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import java.io.File

data class UiState(
    val loaded: Boolean = false,
    val pending: List<WordEntry> = emptyList(),
    val needsEdit: List<WordEntry> = emptyList(),
    val okCount: Int = 0,
    val totalCount: Int = 0,
    val allOk: Boolean = false,
    val selectedEditId: Int? = null,
    val message: String? = null,
)

class MainViewModel(
    application: Application,
    private val repository: WordRepository = WordRepository(application),
) : AndroidViewModel(application) {

    private val selectedEditId = MutableStateFlow<Int?>(null)
    private val message = MutableStateFlow<String?>(null)

    val uiState: StateFlow<UiState> = combine(
        repository.words,
        repository.loaded,
        selectedEditId,
        message,
    ) { words, loaded, editId, msg ->
        UiState(
            loaded = loaded,
            pending = words.filter { it.status == ReviewStatus.PENDING },
            needsEdit = words.filter { it.status == ReviewStatus.NEEDS_EDIT },
            okCount = words.count { it.status == ReviewStatus.OK },
            totalCount = words.size,
            allOk = words.isNotEmpty() && words.all { it.status == ReviewStatus.OK },
            selectedEditId = editId,
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

    fun approve(id: Int) = repository.markOk(id)

    fun reject(id: Int) {
        repository.markNeedsEdit(id)
        selectedEditId.value = id
    }

    fun swapOnCard(id: Int) = repository.swapMainAndFirstAlso(id)

    fun selectForEdit(id: Int?) {
        selectedEditId.value = id
    }

    fun saveEdit(id: Int, main: String, also: List<String>) {
        if (main.isBlank()) {
            message.value = "Основной перевод обязателен"
            return
        }
        repository.saveEdit(id, main, also, markOk = true)
        selectedEditId.value = null
        message.value = "Сохранено"
    }

    fun resetProgress() {
        repository.resetAll()
        selectedEditId.value = null
        message.value = "Прогресс сброшен"
    }

    fun clearMessage() {
        message.value = null
    }

    suspend fun exportFile(): File? {
        if (!repository.allOk()) {
            message.value = "Экспорт доступен, когда все слова со статусом OK"
            return null
        }
        return repository.writeExportFile()
    }

    companion object {
        fun factory(application: Application): ViewModelProvider.Factory =
            object : ViewModelProvider.Factory {
                @Suppress("UNCHECKED_CAST")
                override fun <T : ViewModel> create(modelClass: Class<T>): T {
                    return MainViewModel(application) as T
                }
            }
    }
}
