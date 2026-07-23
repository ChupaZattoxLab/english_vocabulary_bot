package com.vocabcheck.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Undo
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.SwapVert
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.vocabcheck.app.data.WordEntry

@Composable
fun ReviewTab(
    current: WordEntry?,
    pendingCount: Int,
    okCount: Int,
    totalCount: Int,
    onApprove: (Int) -> Unit,
    onReject: (Int) -> Unit,
    onPickWord: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 8.dp),
    ) {
        Text(
            text = "Проверено: $okCount / $totalCount",
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.SemiBold,
        )
        Text(
            text = "В очереди: $pendingCount",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.65f),
        )
        Spacer(Modifier.height(8.dp))
        OutlinedButton(
            onClick = onPickWord,
            enabled = pendingCount > 0,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Выбрать слово из непроверенных")
        }
        Spacer(Modifier.height(12.dp))

        if (current == null) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 48.dp, horizontal = 24.dp),
                verticalArrangement = Arrangement.Center,
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text(
                    text = if (totalCount > 0 && okCount == totalCount) {
                        "Все слова проверены"
                    } else {
                        "Очередь пуста"
                    },
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold,
                )
                Spacer(Modifier.height(8.dp))
                Text(
                    text = "Если есть слова на правку — открой вкладку «Правки».",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.7f),
                )
            }
        } else {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(400.dp),
            ) {
                SwipeableWordCard(
                    word = current,
                    onSwipeLeft = { onReject(current.id) },
                    onSwipeRight = { onApprove(current.id) },
                )
            }

            Spacer(Modifier.height(28.dp))

            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterHorizontally),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                FilledTonalButton(
                    onClick = { onReject(current.id) },
                    contentPadding = PaddingValues(horizontal = 14.dp, vertical = 6.dp),
                ) {
                    Icon(
                        Icons.Default.Close,
                        contentDescription = null,
                        modifier = Modifier.height(16.dp),
                    )
                    Spacer(Modifier.width(4.dp))
                    Text("Правка", style = MaterialTheme.typography.labelLarge)
                }
                Button(
                    onClick = { onApprove(current.id) },
                    contentPadding = PaddingValues(horizontal = 14.dp, vertical = 6.dp),
                ) {
                    Icon(
                        Icons.Default.Check,
                        contentDescription = null,
                        modifier = Modifier.height(16.dp),
                    )
                    Spacer(Modifier.width(4.dp))
                    Text("OK", style = MaterialTheme.typography.labelLarge)
                }
            }

            Spacer(Modifier.height(20.dp))

            Text(
                text = "Вправо — OK · Влево — на правку",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.55f),
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 8.dp)
                    .padding(bottom = 24.dp),
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PendingPickerScreen(
    pending: List<WordEntry>,
    onBack: () -> Unit,
    onSelect: (Int) -> Unit,
) {
    var query by remember { mutableStateOf("") }
    val filtered = remember(pending, query) {
        val q = query.trim()
        if (q.isEmpty()) {
            pending
        } else {
            pending.filter { word ->
                word.word.contains(q, ignoreCase = true) ||
                    word.main.contains(q, ignoreCase = true) ||
                    word.also.any { it.contains(q, ignoreCase = true) }
            }
        }
    }

    BackHandler { onBack() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("Непроверенные", fontWeight = FontWeight.Bold)
                        Text(
                            text = "Выбери слово — проверка продолжится с него",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Назад")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background,
                ),
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 8.dp),
                label = { Text("Поиск") },
                singleLine = true,
                shape = RoundedCornerShape(14.dp),
            )

            if (filtered.isEmpty()) {
                Text(
                    text = if (pending.isEmpty()) "Нет непроверенных слов" else "Ничего не найдено",
                    modifier = Modifier.padding(24.dp),
                    color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.65f),
                )
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    item {
                        Text(
                            text = "Найдено: ${filtered.size}",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold,
                            modifier = Modifier.padding(horizontal = 4.dp, vertical = 4.dp),
                        )
                    }
                    items(filtered, key = { it.id }) { word ->
                        Card(
                            colors = CardDefaults.cardColors(
                                containerColor = MaterialTheme.colorScheme.surface,
                            ),
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable { onSelect(word.id) },
                        ) {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(horizontal = 14.dp, vertical = 14.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Column(modifier = Modifier.weight(1f)) {
                                    Text(word.word, fontWeight = FontWeight.SemiBold)
                                    if (word.main.isNotBlank()) {
                                        Text(
                                            text = word.main,
                                            maxLines = 1,
                                            overflow = TextOverflow.Ellipsis,
                                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                                            style = MaterialTheme.typography.bodyMedium,
                                        )
                                    }
                                }
                                Icon(
                                    Icons.Default.ChevronRight,
                                    contentDescription = "Выбрать",
                                    tint = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.45f),
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun EditListTab(
    needsEdit: List<WordEntry>,
    onOpen: (Int) -> Unit,
) {
    if (needsEdit.isEmpty()) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(24.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = "Нет слов на правку",
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.height(8.dp))
            Text(
                text = "Свайпни влево на вкладке «Проверка», если перевод не подходит.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.7f),
            )
        }
        return
    }

    WordList(
        words = needsEdit,
        header = "К правке: ${needsEdit.size}",
        onOpen = onOpen,
    )
}

@Composable
fun OkListTab(
    okWords: List<WordEntry>,
    onOpen: (Int) -> Unit,
) {
    var query by remember { mutableStateOf("") }
    val filtered = remember(okWords, query) {
        val q = query.trim()
        if (q.isEmpty()) {
            okWords
        } else {
            okWords.filter { word ->
                word.word.contains(q, ignoreCase = true) ||
                    word.main.contains(q, ignoreCase = true) ||
                    word.also.any { it.contains(q, ignoreCase = true) }
            }
        }
    }

    Column(modifier = Modifier.fillMaxSize()) {
        OutlinedTextField(
            value = query,
            onValueChange = { query = it },
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 8.dp),
            label = { Text("Поиск по слову или переводу") },
            singleLine = true,
            shape = RoundedCornerShape(14.dp),
        )

        if (okWords.isEmpty()) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(24.dp),
                verticalArrangement = Arrangement.Center,
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text(
                    text = "Пока нет OK-слов",
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold,
                )
                Spacer(Modifier.height(8.dp))
                Text(
                    text = "Свайпни вправо на проверке или сохрани правку.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.7f),
                )
            }
        } else if (filtered.isEmpty()) {
            Text(
                text = "Ничего не найдено",
                modifier = Modifier.padding(24.dp),
                color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.65f),
            )
        } else {
            WordList(
                words = filtered,
                header = if (query.isBlank()) {
                    "OK: ${okWords.size}"
                } else {
                    "Найдено: ${filtered.size} из ${okWords.size}"
                },
                onOpen = onOpen,
            )
        }
    }
}

@Composable
private fun WordList(
    words: List<WordEntry>,
    header: String,
    onOpen: (Int) -> Unit,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        item {
            Text(
                text = header,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.padding(horizontal = 4.dp, vertical = 4.dp),
            )
            Spacer(Modifier.height(4.dp))
        }
        items(words, key = { it.id }) { word ->
            Card(
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surface,
                ),
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { onOpen(word.id) },
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 14.dp, vertical = 14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(word.word, fontWeight = FontWeight.SemiBold)
                        if (word.main.isNotBlank()) {
                            Text(
                                text = word.main,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                                style = MaterialTheme.typography.bodyMedium,
                            )
                        }
                    }
                    Icon(
                        Icons.Default.ChevronRight,
                        contentDescription = "Открыть",
                        tint = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.45f),
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EditWordScreen(
    word: WordEntry,
    positionLabel: String,
    canUndo: Boolean,
    onBack: () -> Unit,
    onUndo: () -> Unit,
    onSave: (id: Int, main: String, also: List<String>) -> Unit,
    onSwap: (Int) -> Unit,
    snackbarHostState: SnackbarHostState,
) {
    var showUndoDialog by remember { mutableStateOf(false) }

    BackHandler { onBack() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("Правка: ${word.word}", fontWeight = FontWeight.Bold)
                        Text(
                            text = positionLabel,
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Назад")
                    }
                },
                actions = {
                    IconButton(
                        onClick = { showUndoDialog = true },
                        enabled = canUndo,
                    ) {
                        Icon(Icons.AutoMirrored.Filled.Undo, contentDescription = "Отменить")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background,
                ),
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { padding ->
        EditForm(
            word = word,
            onSave = onSave,
            onSwap = onSwap,
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
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
                        showUndoDialog = false
                        onUndo()
                    },
                ) { Text("Отменить") }
            },
            dismissButton = {
                TextButton(onClick = { showUndoDialog = false }) { Text("Нет") }
            },
        )
    }
}

@Composable
private fun EditForm(
    word: WordEntry,
    onSave: (id: Int, main: String, also: List<String>) -> Unit,
    onSwap: (Int) -> Unit,
    modifier: Modifier = Modifier,
) {
    var main by remember(word.id) { mutableStateOf(word.main) }
    val alsoFields = remember(word.id) {
        mutableStateListOf<String>().apply {
            addAll(word.also.ifEmpty { listOf("") })
        }
    }

    Column(
        modifier = modifier
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 8.dp),
    ) {
        Text(
            text = word.word,
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
        )
        if (word.pos.isNotBlank()) {
            Text(
                text = word.pos,
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.55f),
            )
        }
        Spacer(Modifier.height(16.dp))

        OutlinedTextField(
            value = main,
            onValueChange = { main = it },
            label = { Text("Основной перевод") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
            shape = RoundedCornerShape(14.dp),
        )

        Spacer(Modifier.height(12.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("Дополнительные переводы", fontWeight = FontWeight.SemiBold)
            IconButton(onClick = { alsoFields.add("") }) {
                Icon(Icons.Default.Add, contentDescription = "Добавить поле")
            }
        }

        alsoFields.forEachIndexed { index, value ->
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.fillMaxWidth(),
            ) {
                OutlinedTextField(
                    value = value,
                    onValueChange = { alsoFields[index] = it },
                    label = { Text("Доп. ${index + 1}") },
                    singleLine = true,
                    modifier = Modifier.weight(1f),
                    shape = RoundedCornerShape(14.dp),
                )
                IconButton(
                    onClick = {
                        if (alsoFields.size == 1) {
                            alsoFields[0] = ""
                        } else {
                            alsoFields.removeAt(index)
                        }
                    },
                ) {
                    Icon(Icons.Default.Delete, contentDescription = "Удалить")
                }
            }
            Spacer(Modifier.height(8.dp))
        }

        Spacer(Modifier.height(8.dp))
        OutlinedButton(
            onClick = {
                val updatedMain = alsoFields.firstOrNull { it.isNotBlank() } ?: return@OutlinedButton
                val rest = alsoFields.filter { it.isNotBlank() }.drop(1).toMutableList()
                if (main.isNotBlank()) rest.add(0, main)
                main = updatedMain
                alsoFields.clear()
                alsoFields.addAll(rest.ifEmpty { listOf("") })
                onSwap(word.id)
            },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Icon(Icons.Default.SwapVert, contentDescription = null)
            Spacer(Modifier.width(8.dp))
            Text("Поменять основной и первый доп.")
        }

        Spacer(Modifier.height(12.dp))
        Button(
            onClick = {
                onSave(
                    word.id,
                    main,
                    alsoFields.filter { it.isNotBlank() },
                )
            },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Icon(Icons.Default.Check, contentDescription = null)
            Spacer(Modifier.width(8.dp))
            Text("Сохранить как OK")
        }
        Spacer(Modifier.height(32.dp))
    }
}
