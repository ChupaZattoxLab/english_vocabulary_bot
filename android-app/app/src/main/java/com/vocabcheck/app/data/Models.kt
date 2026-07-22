package com.vocabcheck.app.data

import kotlinx.serialization.Serializable

enum class ReviewStatus {
    PENDING,
    OK,
    NEEDS_EDIT,
}

@Serializable
data class WordEntry(
    val id: Int,
    val word: String,
    val pos: String = "",
    val main: String = "",
    val also: List<String> = emptyList(),
    val status: ReviewStatus = ReviewStatus.PENDING,
)

@Serializable
data class ExportWord(
    val word: String,
    val pos: String = "",
    val status: ReviewStatus = ReviewStatus.PENDING,
    val translations: ExportTranslations,
)

@Serializable
data class ExportTranslations(
    val ru: ExportRu,
)

@Serializable
data class ExportRu(
    val main: String,
    val also: List<String> = emptyList(),
)

@Serializable
data class ProgressSnapshot(
    val words: List<WordEntry>,
)
