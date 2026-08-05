package com.vocabcheck.app.data

import kotlinx.serialization.Serializable

enum class ReviewStatus {
    PENDING,
    OK,
    NEEDS_EDIT,
    DELETED,
}

@Serializable
data class SensePair(
    val definition: String = "",
    val example: String = "",
)

@Serializable
data class WordEntry(
    val id: Int,
    val word: String = "",
    val wordUs: String = "",
    val wordGb: String = "",
    val pos: String = "",
    val cefr: String = "",
    val definitionUrlOxford: String = "",
    val definitionUrlCambridge: String = "",
    val ipaUs: List<String> = emptyList(),
    val ipaGb: List<String> = emptyList(),
    val definition: String = "",
    val example: String = "",
    val extraSenses: List<SensePair> = emptyList(),
    val audioUs: List<String> = emptyList(),
    val audioGb: List<String> = emptyList(),
    val main: String = "",
    val also: List<String> = emptyList(),
    val status: ReviewStatus = ReviewStatus.PENDING,
) {
    fun headword(): String = wordUs.ifBlank { word.ifBlank { wordGb } }
}

@Serializable
data class ExportWord(
    val word: String,
    val wordUs: String = "",
    val wordGb: String = "",
    val pos: String = "",
    val cefr: String = "",
    val status: ReviewStatus = ReviewStatus.PENDING,
    val definitionUrlOxford: String = "",
    val definitionUrlCambridge: String = "",
    val ipaUs: List<String> = emptyList(),
    val ipaGb: List<String> = emptyList(),
    val definition: String = "",
    val example: String = "",
    val extraSenses: List<SensePair> = emptyList(),
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

data class ImportResult(
    val updated: Int,
    val importedCount: Int,
    val okCount: Int,
)

data class WordEditPayload(
    val main: String,
    val also: List<String>,
    val definition: String,
    val example: String,
    val extraSenses: List<SensePair>,
    val wordUs: String = "",
    val wordGb: String = "",
    val pos: String = "",
    val cefr: String = "",
    val ipaUs: List<String> = emptyList(),
    val ipaGb: List<String> = emptyList(),
)

object CardFieldOptions {
    val CEFR: List<String> = listOf("a1", "a2", "b1", "b2", "c1", "c2")

    /** One POS per card — no compound labels like "adjective , adverb". */
    val POS: List<String> = listOf(
        "adjective",
        "adverb",
        "auxiliary verb",
        "conjunction",
        "definite article",
        "determiner",
        "exclamation",
        "indefinite article",
        "infinitive marker",
        "linking verb",
        "modal verb",
        "noun",
        "number",
        "ordinal number",
        "preposition",
        "pronoun",
        "verb",
    )
}
