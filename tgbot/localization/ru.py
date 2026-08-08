"""Russian UI strings shown to users and admins in Telegram."""

from __future__ import annotations


class user:
    settings_title = "<b>Ваши настройки</b>"
    levels_none = "не выбраны"
    delivery_active = "активна"
    delivery_paused = "приостановлена"
    settings_levels = "Уровни: {levels}"
    settings_pronunciation = "Произношение: {pronunciation}"
    settings_delivery = "Рассылка: {state}"
    settings_schedule = "Время: {schedule}"

    welcome_back = "С возвращением!\n\n{settings}"
    welcome_new = (
        "Привет! Я буду присылать {cards_per_day} новые английские карточки в день.\n\n"
        "Сначала выберите один или несколько уровней CEFR:"
    )
    settings_pick_levels = "\n\nВыберите уровни. Можно отметить несколько:"
    pick_levels = "Выберите один или несколько уровней CEFR:"
    need_start = "Сначала отправьте /start"
    need_one_level = "Выберите хотя бы один уровень"
    pick_pronunciation_next = "Теперь выберите произношение для карточек:"
    pick_pronunciation = "Какое произношение использовать?"
    need_level_first = "Сначала выберите хотя бы один уровень"
    onboarding_done = (
        "Настройка завершена!\n\n{settings}\n\nДля проверки можно запросить /card."
    )
    settings_saved = "Настройки сохранены"

    paused = "Рассылка приостановлена. Команда для продолжения: /resume"
    need_onboarding = "Сначала завершите настройку через /start."
    resumed = "Рассылка снова активна."
    no_cards_left = (
        "Для выбранных уровней больше нет новых карточек с загруженным "
        "аудио. Карточки не повторяются."
    )
    card_send_failed = "Не удалось отправить карточку, попробуйте позже."
    resume_hint = "Чтобы снова получать по расписанию - /resume"

    help = (
        "<b>Команды</b>\n"
        "/start - регистрация\n"
        "/settings - все настройки\n"
        "/levels - уровни CEFR\n"
        "/pronunciation - US или GB\n"
        "/card - получить карточку сейчас\n"
        "/pause - приостановить рассылку\n"
        "/resume - продолжить рассылку\n"
        "/help - эта справка"
    )


class keyboard:
    continue_button = "Продолжить"
    pronunciation_us = "🇺🇸 American (US)"
    pronunciation_gb = "🇬🇧 British (GB)"
    pronunciation_both = "🇺🇸 + 🇬🇧 Оба варианта"
    level_selected_prefix = "✅ "

    admin_users = "👥 Пользователи"
    admin_test_card = "🧪 Тест-карта"
    admin_refresh = "🔄 Обновить"
    admin_back = "⬅️ Назад"

    unknown_category = "неизвестно"
    dash = "-"


class commands:
    start = "Начать работу"
    card = "Получить новую карточку"
    settings = "Настройки"
    levels = "Выбрать уровни CEFR"
    pronunciation = "Выбрать произношение"
    pause = "Приостановить рассылку"
    resume = "Продолжить рассылку"
    help = "Помощь"

    admin = "Открыть админ-панель"
    users = "Статистика пользователей"
    user = "Пользователь по Telegram ID"
    word = "Карточка слова"
    send_test = "Тестовая карточка"
    reload_templates = "Перезагрузить шаблоны"


class labels:
    pronunciation_short = {
        "us": "US",
        "gb": "GB",
        "both": "US + GB",
    }
    pronunciation_short_unknown = "не выбрано"

    pronunciation_admin = {
        "us": "American English",
        "gb": "British English",
        "both": "American + British English",
    }
    pronunciation_admin_unknown = "не выбран"

    dialect_flags = {
        "US": "🇺🇸",
        "GB": "🇬🇧",
        "BOTH": "🇺🇸 + 🇬🇧",
    }
    dialect_captions = {
        "US": "🇺🇸 US",
        "GB": "🇬🇧 GB",
    }

    card_heading_definition = "Definition"
    card_heading_example = "Example"
    card_heading_translation = "Translation"


class admin:
    no_access = "Нет доступа."
    delivery_blocked = "бот заблокирован"
    delivery_paused = "приостановлена"
    delivery_active = "включена"
    none = "нет"
    placeholder = "-"
    never_delivered = "ещё не было"

    overview = (
        "<b>🛠 Vocabulary Bot - Admin Panel</b>\n\n"
        "👥 Пользователей: {total_users}\n"
        "📨 Получают карточки: {active_users}\n"
        "📚 Готовых карточек: {ready_entries}\n\n"
    )
    users_panel = (
        "<b>👥 Пользователи</b>\n\n"
        "Всего: {total_users}\n"
        "Получают карточки: {active_users}\n"
        "Пауза: {paused_users}\n"
        "Заблокировали бота: {blocked_users}\n\n"
        "<b>Новые</b>\n"
        "Сегодня: {new_today}\n"
        "За {week_days} дней: {new_week}\n"
        "За {month_days} дней: {new_month}\n\n"
        "<b>По уровням</b>\n{levels}\n\n"
        "<b>По произношению</b>\n{dialects}"
    )

    user_usage = "Использование: <code>/user TELEGRAM_ID</code>"
    user_not_found = "Пользователь не найден."
    user_detail = (
        "<b>👤 User {telegram_user_id}</b>\n\n"
        "Username: {username}\n"
        "Зарегистрирован: {registered}\n"
        "Уровни: {levels}\n"
        "Произношение: {pronunciation}\n"
        "Карточек в день: {cards_per_day}\n"
        "Время отправки: {send_times}\n"
        "Часовой пояс: {timezone}\n"
        "Рассылка: {delivery_state}\n\n"
        "Отправлено карточек: {delivered_cards}\n"
        "Последняя отправка: {last_delivery}\n"
    )

    word_usage = "Использование: <code>/word WORD</code>"
    word_not_found = "Слово не найдено."
    word_pick_category = "У слова <b>{word}</b> несколько частей речи. Выберите нужную:"
    word_no_both_audio = "Для этого слова нет одновременно US и GB аудио."
    word_entry_no_both_audio = (
        "Для выбранной части речи нет одновременно US и GB аудио."
    )
    no_test_cards = "Нет карточек с готовым аудио для тестовой отправки."
    no_preview_cards = "Нет карточек с готовым аудио для предпросмотра."
    sending_card = "Отправляю карточку…"
    sending_test_card = "Отправляю тестовую карточку…"

    template_error = "Ошибка шаблона: <code>{error}</code>"
    templates_reloaded = "Оба шаблона карточек проверены и перезагружены."
    panel_unavailable = "Сообщение панели недоступно."
    bad_choice = "Некорректный выбор."
    already_up_to_date = "Данные уже актуальны."
    panel_update_failed = "Не удалось обновить раздел."
    panel_error = "Ошибка admin panel: <code>{error}</code>"


def pronunciation_short(value: str | None) -> str:
    return labels.pronunciation_short.get(
        value or "",
        labels.pronunciation_short_unknown,
    )


def pronunciation_admin(value: str | None) -> str:
    return labels.pronunciation_admin.get(
        value or "",
        labels.pronunciation_admin_unknown,
    )


def dialect_flag(dialect: str) -> str:
    return labels.dialect_flags.get(dialect.upper(), "")


def dialect_caption(dialect: str) -> str:
    normalized = dialect.upper()
    return labels.dialect_captions.get(normalized, normalized)


def user_settings_lines(
    *,
    levels: str,
    pronunciation: str,
    delivery_state: str,
    schedule: str,
) -> str:
    return "\n".join(
        (
            user.settings_title,
            user.settings_levels.format(levels=levels),
            user.settings_pronunciation.format(pronunciation=pronunciation),
            user.settings_delivery.format(state=delivery_state),
            user.settings_schedule.format(schedule=schedule),
        )
    )
