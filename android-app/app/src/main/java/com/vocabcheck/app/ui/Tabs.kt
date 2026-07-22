package com.vocabcheck.app.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.SwapVert
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
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
    pending: List<WordEntry>,
    okCount: Int,
    totalCount: Int,
    onApprove: (Int) -> Unit,
    onReject: (Int) -> Unit,
    onSwap: (Int) -> Unit,
) {
    val current = pending.firstOrNull()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 16.dp, vertical = 8.dp),
    ) {
        Text(
            text = "Проверено: $okCount / $totalCount",
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.SemiBold,
        )
        Text(
            text = "В очереди: ${pending.size}",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.65f),
        )
        Spacer(Modifier.height(12.dp))

        if (current == null) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(24.dp),
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
            BoxWithCard(
                word = current,
                onApprove = { onApprove(current.id) },
                onReject = { onReject(current.id) },
            )
            Spacer(Modifier.height(8.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                FilledTonalButton(onClick = { onReject(current.id) }) {
                    Icon(Icons.Default.Close, contentDescription = null)
                    Spacer(Modifier.width(6.dp))
                    Text("Правка")
                }
                OutlinedButton(onClick = { onSwap(current.id) }) {
                    Icon(Icons.Default.SwapVert, contentDescription = null)
                    Spacer(Modifier.width(6.dp))
                    Text("Swap")
                }
                Button(onClick = { onApprove(current.id) }) {
                    Icon(Icons.Default.Check, contentDescription = null)
                    Spacer(Modifier.width(6.dp))
                    Text("OK")
                }
            }
            Spacer(Modifier.height(8.dp))
            Text(
                text = "Вправо — OK · Влево — на правку · Swap — поменять main ↔ 1-й доп.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.55f),
                modifier = Modifier.padding(horizontal = 8.dp),
            )
        }
    }
}

@Composable
private fun BoxWithCard(
    word: WordEntry,
    onApprove: () -> Unit,
    onReject: () -> Unit,
) {
    androidx.compose.foundation.layout.Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(440.dp),
    ) {
        SwipeableWordCard(
            word = word,
            onSwipeLeft = onReject,
            onSwipeRight = onApprove,
        )
    }
}

@Composable
fun EditTab(
    needsEdit: List<WordEntry>,
    selectedId: Int?,
    onSelect: (Int?) -> Unit,
    onSave: (id: Int, main: String, also: List<String>) -> Unit,
    onSwap: (Int) -> Unit,
) {
    val selected = needsEdit.firstOrNull { it.id == selectedId } ?: needsEdit.firstOrNull()

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

    if (selected == null) return

    LaunchedEffect(selected.id) {
        if (selectedId != selected.id) onSelect(selected.id)
    }

    Column(modifier = Modifier.fillMaxSize()) {
        LazyColumn(
            modifier = Modifier
                .fillMaxWidth()
                .height(140.dp),
            contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(needsEdit, key = { it.id }) { word ->
                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = if (word.id == selected.id) {
                            MaterialTheme.colorScheme.primary.copy(alpha = 0.12f)
                        } else {
                            MaterialTheme.colorScheme.surface
                        },
                    ),
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onSelect(word.id) },
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 14.dp, vertical = 10.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Text(word.word, fontWeight = FontWeight.SemiBold)
                        Text(
                            text = word.main,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                            modifier = Modifier.padding(start = 12.dp),
                        )
                    }
                }
            }
        }

        EditForm(
            word = selected,
            onSave = onSave,
            onSwap = onSwap,
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth(),
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
                onSwap(word.id)
                val updatedMain = alsoFields.firstOrNull { it.isNotBlank() } ?: return@OutlinedButton
                val rest = alsoFields.filter { it.isNotBlank() }.drop(1).toMutableList()
                if (main.isNotBlank()) rest.add(0, main)
                main = updatedMain
                alsoFields.clear()
                alsoFields.addAll(rest.ifEmpty { listOf("") })
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
        Spacer(Modifier.height(24.dp))
    }
}
