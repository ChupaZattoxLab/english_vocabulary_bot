package com.vocabcheck.app.ui

import android.content.Intent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Undo
import androidx.compose.material.icons.filled.FileDownload
import androidx.compose.material.icons.filled.FileUpload
import androidx.compose.material.icons.filled.RestartAlt
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.ScrollableTabRow
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.vocabcheck.app.MainViewModel
import com.vocabcheck.app.data.ReviewStatus
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreen(viewModel: MainViewModel) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    var tabIndex by remember { mutableIntStateOf(0) }
    var showResetDialog by remember { mutableStateOf(false) }
    var showUndoDialog by remember { mutableStateOf(false) }
    var showExportDialog by remember { mutableStateOf(false) }
    var showImportDialog by remember { mutableStateOf(false) }
    var showPendingPicker by remember { mutableStateOf(false) }
    val snackbar = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current

    val importLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenDocument(),
    ) { uri ->
        if (uri != null) {
            runCatching {
                context.contentResolver.takePersistableUriPermission(
                    uri,
                    Intent.FLAG_GRANT_READ_URI_PERMISSION,
                )
            }
            viewModel.importFromUri(uri)
        }
    }

    fun shareExport() {
        scope.launch {
            val file = viewModel.exportFile() ?: return@launch
            val uri = FileProvider.getUriForFile(
                context,
                "${context.packageName}.fileprovider",
                file,
            )
            val share = Intent(Intent.ACTION_SEND).apply {
                type = "application/json"
                putExtra(Intent.EXTRA_STREAM, uri)
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }
            context.startActivity(
                Intent.createChooser(share, "Экспорт словаря"),
            )
        }
    }

    LaunchedEffect(state.message) {
        val msg = state.message ?: return@LaunchedEffect
        snackbar.showSnackbar(msg)
        viewModel.clearMessage()
    }

    val editingWord = state.selectedEditId?.let { viewModel.findWord(it) }

    if (editingWord != null) {
        val inNeedsEdit = editingWord.status == ReviewStatus.NEEDS_EDIT
        val list = if (inNeedsEdit) state.needsEdit else state.okWords
        val index = list.indexOfFirst { it.id == editingWord.id }.coerceAtLeast(0)
        EditWordScreen(
            word = editingWord,
            positionLabel = if (inNeedsEdit) {
                "Правка · слово ${index + 1} из ${list.size}"
            } else {
                "OK · повторная проверка"
            },
            canUndo = state.canUndo,
            onBack = { viewModel.selectForEdit(null) },
            onUndo = viewModel::undo,
            onSave = { id, main, also ->
                viewModel.saveEdit(id, main, also)
            },
            onSwap = viewModel::swapOnCard,
            snackbarHostState = snackbar,
        )
        return
    }

    if (showPendingPicker) {
        PendingPickerScreen(
            pending = state.pending,
            onBack = { showPendingPicker = false },
            onSelect = { id ->
                viewModel.jumpToPending(id)
                showPendingPicker = false
                tabIndex = 0
            },
        )
        return
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("Vocab Check", fontWeight = FontWeight.Bold)
                        Text(
                            text = "${state.okCount}/${state.totalCount} OK · ${state.needsEdit.size} правок",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                },
                actions = {
                    IconButton(
                        onClick = { showUndoDialog = true },
                        enabled = state.canUndo,
                    ) {
                        Icon(Icons.AutoMirrored.Filled.Undo, contentDescription = "Отменить")
                    }
                    IconButton(
                        onClick = { showImportDialog = true },
                        enabled = state.loaded,
                    ) {
                        Icon(Icons.Default.FileDownload, contentDescription = "Импорт")
                    }
                    IconButton(
                        onClick = { showExportDialog = true },
                        enabled = state.loaded && state.totalCount > 0,
                    ) {
                        Icon(Icons.Default.FileUpload, contentDescription = "Экспорт")
                    }
                    IconButton(onClick = { showResetDialog = true }) {
                        Icon(Icons.Default.RestartAlt, contentDescription = "Сброс")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background,
                ),
            )
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            ScrollableTabRow(
                selectedTabIndex = tabIndex,
                edgePadding = 12.dp,
            ) {
                Tab(
                    selected = tabIndex == 0,
                    onClick = { tabIndex = 0 },
                    text = { Text("Проверка (${state.pending.size})") },
                )
                Tab(
                    selected = tabIndex == 1,
                    onClick = { tabIndex = 1 },
                    text = { Text("Правки (${state.needsEdit.size})") },
                )
                Tab(
                    selected = tabIndex == 2,
                    onClick = { tabIndex = 2 },
                    text = { Text("OK (${state.okCount})") },
                )
            }

            if (!state.loaded) {
                Text(
                    text = "Загрузка словаря…",
                    modifier = Modifier.padding(24.dp),
                )
            } else when (tabIndex) {
                0 -> ReviewTab(
                    current = state.currentPending,
                    pendingCount = state.pending.size,
                    okCount = state.okCount,
                    totalCount = state.totalCount,
                    onApprove = viewModel::approve,
                    onReject = viewModel::reject,
                    onPickWord = { showPendingPicker = true },
                )
                1 -> EditListTab(
                    needsEdit = state.needsEdit,
                    onOpen = viewModel::selectForEdit,
                )
                else -> OkListTab(
                    okWords = state.okWords,
                    onOpen = viewModel::selectForEdit,
                )
            }
        }
    }

    if (showImportDialog) {
        AlertDialog(
            onDismissRequest = { showImportDialog = false },
            title = { Text("Импорт словаря") },
            text = {
                Text(
                    "Выбери JSON из экспорта (vocab_checked.json). " +
                        "Переводы и статусы совпавших слов будут обновлены поверх текущего прогресса.",
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        showImportDialog = false
                        importLauncher.launch(arrayOf("application/json", "text/*", "*/*"))
                    },
                ) { Text("Выбрать файл") }
            },
            dismissButton = {
                TextButton(onClick = { showImportDialog = false }) { Text("Отмена") }
            },
        )
    }

    if (showExportDialog) {
        val pending = state.pending.size
        val edits = state.needsEdit.size
        val exportHint = when {
            state.allOk -> "Все ${state.totalCount} слов проверены. Экспортировать словарь?"
            else -> "Проверено ${state.okCount}/${state.totalCount}. " +
                "Ещё не готово: $pending в очереди, $edits на правке. " +
                "Экспортировать текущий прогресс?"
        }
        AlertDialog(
            onDismissRequest = { showExportDialog = false },
            title = { Text("Экспорт словаря") },
            text = { Text(exportHint) },
            confirmButton = {
                TextButton(
                    onClick = {
                        showExportDialog = false
                        shareExport()
                    },
                ) { Text("Экспортировать") }
            },
            dismissButton = {
                TextButton(onClick = { showExportDialog = false }) { Text("Отмена") }
            },
        )
    }

    if (showUndoDialog) {
        AlertDialog(
            onDismissRequest = { showUndoDialog = false },
            title = { Text("Отменить последнее действие?") },
            text = { Text("Будет восстановлено предыдущее состояние слова.") },
            confirmButton = {
                TextButton(
                    onClick = {
                        viewModel.undo()
                        showUndoDialog = false
                    },
                ) { Text("Отменить") }
            },
            dismissButton = {
                TextButton(onClick = { showUndoDialog = false }) { Text("Нет") }
            },
        )
    }

    if (showResetDialog) {
        AlertDialog(
            onDismissRequest = { showResetDialog = false },
            title = { Text("Сбросить прогресс?") },
            text = { Text("Все статусы и правки будут очищены. Словарь загрузится заново.") },
            confirmButton = {
                TextButton(
                    onClick = {
                        viewModel.resetProgress()
                        showResetDialog = false
                        tabIndex = 0
                    },
                ) { Text("Сбросить") }
            },
            dismissButton = {
                TextButton(onClick = { showResetDialog = false }) { Text("Отмена") }
            },
        )
    }
}
