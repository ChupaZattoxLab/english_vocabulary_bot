"""Normalize translations for student-facing bot cards.

Goal: one clear primary RU gloss + up to 2 short alternatives.
Strip dictionary noise (meta labels, broken Mueller spacing, 50+ senses).

Result shape:
  "translations": { "ru": { "main": "изучать", "also": ["учиться", "заниматься"] } }

Usage:
  python scripts/clean_translations_student.py
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lexicon_promote import promote_by_lexicon  # noqa: E402
OUT = ROOT / "data" / "oald"
JSON_PATH = OUT / "words.json"
CSV_PATH = OUT / "words.csv"
META_PATH = OUT / "meta.json"

SCHEMA = [
    "word_us",
    "word_gb",
    "lexical_category",
    "cefr",
    "definition_url_oxford",
    "definition_url_cambridge",
    "ipa_us",
    "ipa_gb",
    "definition",
    "example",
    "audio_source_us",
    "audio_source_gb",
    "translations",
]

# Hard overrides when auto-clean cannot recover a sensible student gloss
CURATED: dict[tuple[str, str], dict[str, list[str] | str]] = {
    ("a", "indefinite article"): {"main": "неопределённый артикль", "also": ["один", "некий"]},
    ("an", "indefinite article"): {"main": "неопределённый артикль", "also": []},
    ("the", "definite article"): {"main": "определённый артикль", "also": []},
    ("app", "noun"): {"main": "приложение", "also": ["программа"]},
    ("ability", "noun"): {"main": "способность", "also": ["умение", "ловкость"]},
    ("blog", "noun"): {"main": "блог", "also": ["сетевой дневник"]},
    ("ah", "exclamation"): {"main": "ах", "also": ["о"]},
    ("email", "noun"): {"main": "электронная почта", "also": ["письмо"]},
    ("email", "verb"): {"main": "написать на почту", "also": ["отправить письмо"]},
    ("website", "noun"): {"main": "сайт", "also": ["вебсайт"]},
    ("smartphone", "noun"): {"main": "смартфон", "also": []},
    ("firefighter", "noun"): {"main": "пожарный", "also": []},
    ("tourism", "noun"): {"main": "туризм", "also": []},
    ("browser", "noun"): {"main": "браузер", "also": []},
    ("yeah", "exclamation"): {"main": "да", "also": ["ага"]},
    ("AIDS", "noun"): {"main": "СПИД", "also": []},
    ("CD", "noun"): {"main": "компакт-диск", "also": []},
    ("DVD", "noun"): {"main": "видеодиск", "also": ["диск"]},
    ("TV", "noun"): {"main": "телевизор", "also": ["ТВ"]},
    ("arms", "noun"): {"main": "оружие", "also": ["вооружение"]},
    ("everyone", "pronoun"): {"main": "все", "also": ["каждый"]},
    ("cannot", "verb"): {"main": "не мочь", "also": ["нельзя"]},
    ("database", "noun"): {"main": "база данных", "also": []},
    ("broadband", "noun"): {"main": "широкополосный интернет", "also": []},
    ("bathroom", "noun"): {"main": "ванная", "also": ["туалет"]},
    ("bike", "noun"): {"main": "велосипед", "also": ["мотоцикл"]},
    ("seal", "noun"): {"main": "печать", "also": ["тюлень", "пломба"]},
    ("seal", "verb"): {"main": "запечатать", "also": ["пломбировать"]},
    ("archive", "noun"): {"main": "архив", "also": []},
    ("auto", "noun"): {"main": "автомобиль", "also": ["авто"]},
    ("basketball", "noun"): {"main": "баскетбол", "also": []},
    ("better", "noun"): {"main": "лучшие", "also": ["преимущество"]},
    ("broadly", "adverb"): {"main": "в целом", "also": ["широко"]},
    ("contempt", "noun"): {"main": "презрение", "also": []},
    ("counselling", "noun"): {"main": "консультирование", "also": ["психологическая помощь"]},
    ("eighteen", "number"): {"main": "восемнадцать", "also": []},
    ("electronics", "noun"): {"main": "электроника", "also": []},
    ("firearm", "noun"): {"main": "огнестрельное оружие", "also": []},
    ("fridge", "noun"): {"main": "холодильник", "also": []},
    ("fundraising", "noun"): {"main": "сбор средств", "also": []},
    ("gaming", "noun"): {"main": "игры", "also": ["видеоигры"]},
    ("gym", "noun"): {"main": "спортзал", "also": ["тренажёрный зал"]},
    ("healthcare", "noun"): {"main": "здравоохранение", "also": ["медобслуживание"]},
    ("hey", "exclamation"): {"main": "эй", "also": ["привет"]},
    ("him", "pronoun"): {"main": "его", "also": ["ему"]},
    ("infrastructure", "noun"): {"main": "инфраструктура", "also": []},
    ("lab", "noun"): {"main": "лаборатория", "also": []},
    ("lifestyle", "noun"): {"main": "образ жизни", "also": []},
    ("lobby", "verb"): {"main": "лоббировать", "also": ["добиваться"]},
    ("mathematics", "noun"): {"main": "математика", "also": []},
    ("maths", "noun"): {"main": "математика", "also": []},
    ("me", "pronoun"): {"main": "меня", "also": ["мне"]},
    ("meanwhile", "adverb"): {"main": "тем временем", "also": ["между тем"]},
    ("memo", "noun"): {"main": "записка", "also": ["служебная записка"]},
    ("next", "noun"): {"main": "следующий", "also": []},
    ("organizational", "adjective"): {"main": "организационный", "also": []},
    ("physics", "noun"): {"main": "физика", "also": []},
    ("rugby", "noun"): {"main": "регби", "also": []},
    ("ski", "adjective"): {"main": "лыжный", "also": []},
    ("ski", "noun"): {"main": "лыжа", "also": []},
    ("ski", "verb"): {"main": "кататься на лыжах", "also": []},
    ("slowly", "adverb"): {"main": "медленно", "also": []},
    ("someone", "pronoun"): {"main": "кто-то", "also": ["кто-нибудь"]},
    ("suspect", "noun"): {"main": "подозреваемый", "also": []},
    ("teens", "noun"): {"main": "подростки", "also": ["юность"]},
    ("thanks", "exclamation"): {"main": "спасибо", "also": []},
    ("thanks", "noun"): {"main": "благодарность", "also": ["спасибо"]},
    ("this", "adverb"): {"main": "так", "also": ["настолько"]},
    ("this", "determiner , pronoun"): {"main": "этот", "also": ["это"]},
    ("upgrade", "noun"): {"main": "обновление", "also": ["улучшение"]},
    ("upgrade", "verb"): {"main": "обновить", "also": ["улучшить"]},
    ("laptop", "noun"): {"main": "ноутбук", "also": []},
    ("supermarket", "noun"): {"main": "супермаркет", "also": []},
    ("camera", "noun"): {"main": "камера", "also": ["фотоаппарат"]},
    ("photograph", "noun"): {"main": "фотография", "also": ["снимок"]},
    ("desk", "noun"): {"main": "письменный стол", "also": ["стол"]},
    ("vehicle", "noun"): {"main": "транспорт", "also": ["машина"]},
    ("broadcast", "noun"): {"main": "трансляция", "also": ["вещание"]},
    ("broadcast", "verb"): {"main": "транслировать", "also": ["передавать"]},
    ("apologize", "verb"): {"main": "извиняться", "also": ["просить прощения"]},
    ("certificate", "noun"): {"main": "сертификат", "also": ["свидетельство"]},
    ("allegation", "noun"): {"main": "обвинение", "also": ["утверждение"]},
    ("discount", "noun"): {"main": "скидка", "also": []},
    ("discount", "verb"): {"main": "снижать цену", "also": ["делать скидку"]},
    ("pledge", "noun"): {"main": "обещание", "also": ["залог"]},
    ("pledge", "verb"): {"main": "обещать", "also": ["закладывать"]},
    ("power", "verb"): {"main": "питать", "also": ["давать энергию"]},
    ("sue", "verb"): {"main": "подавать в суд", "also": ["судиться"]},
    ("tour", "verb"): {"main": "путешествовать", "also": ["ездить"]},
    ("download", "verb"): {"main": "скачивать", "also": ["загружать"]},
    ("download", "noun"): {"main": "загрузка", "also": ["скачивание"]},
    ("disc", "noun"): {"main": "диск", "also": []},
    ("disk", "noun"): {"main": "диск", "also": []},
    ("habit", "noun"): {"main": "привычка", "also": ["обычай"]},
    ("used to", "modal verb"): {"main": "раньше", "also": ["бывало"]},
    ("wire", "noun"): {"main": "провод", "also": ["проволока"]},
    ("tape", "noun"): {"main": "лента", "also": ["скотч"]},
    ("bet", "verb"): {"main": "ставить", "also": ["держать пари"]},
    ("bet", "noun"): {"main": "ставка", "also": ["пари"]},
    ("radio", "noun"): {"main": "радио", "also": []},
    ("hardware", "noun"): {"main": "оборудование", "also": ["аппаратная часть"]},
    ("mortgage", "verb"): {"main": "брать ипотеку", "also": ["закладывать"]},
    ("cheer", "noun"): {"main": "ура", "also": ["крик"]},
    ("composition", "noun"): {"main": "сочинение", "also": ["композиция", "состав"]},
    ("deprive", "verb"): {"main": "лишать", "also": ["отбирать"]},
    ("agenda", "noun"): {"main": "повестка", "also": ["план"]},
    ("chamber", "noun"): {"main": "палата", "also": ["камера"]},
    ("base", "verb"): {"main": "основывать", "also": ["базировать"]},
    ("fill", "verb"): {"main": "наполнять", "also": ["заполнять"]},
    ("found", "verb"): {"main": "основывать", "also": ["учреждать"]},
    ("prompt", "verb"): {"main": "побуждать", "also": ["подсказывать"]},
    ("suggest", "verb"): {"main": "предлагать", "also": ["советовать"]},
    ("suck", "verb"): {"main": "сосать", "also": ["втягивать"]},
    ("phone", "noun"): {"main": "телефон", "also": ["трубка"]},
    ("phone", "verb"): {"main": "звонить", "also": []},
    ("mostly", "adverb"): {"main": "в основном", "also": ["обычно"]},
    ("usually", "adverb"): {"main": "обычно", "also": []},
    ("commonly", "adverb"): {"main": "обычно", "also": ["часто"]},
    ("face", "verb"): {"main": "сталкиваться", "also": ["смотреть в лицо"]},
    ("us", "pronoun"): {"main": "нас", "also": ["нам"]},
    ("whatsoever", "adverb"): {"main": "совсем", "also": ["вообще"]},
    ("whom", "pronoun"): {"main": "кого", "also": ["кому"]},
    ("worse", "adjective"): {"main": "хуже", "also": ["худший"]},
    ("worst", "adjective"): {"main": "худший", "also": ["хуже всего"]},
    ("bye", "exclamation"): {"main": "пока", "also": ["до свидания"]},
    ("could", "modal verb"): {"main": "мог", "also": ["можно было"]},
    ("encouragement", "noun"): {"main": "поддержка", "also": ["ободрение"]},
    ("exit", "verb"): {"main": "выйти", "also": ["покинуть"]},
    ("firework", "noun"): {"main": "фейерверк", "also": ["салют"]},
    ("hers", "pronoun"): {"main": "её", "also": []},
    ("hi", "exclamation"): {"main": "привет", "also": []},
    ("how", "adverb"): {"main": "как", "also": []},
    ("I", "pronoun"): {"main": "я", "also": []},
    ("if", "conjunction"): {"main": "если", "also": []},
    ("investor", "noun"): {"main": "инвестор", "also": ["вкладчик"]},
    ("latest", "adjective"): {"main": "последний", "also": ["новейший"]},
    ("latest", "noun"): {"main": "последние новости", "also": ["новинка"]},
    ("lesser", "adjective"): {"main": "меньший", "also": ["менее значительный"]},
    ("lost", "adjective"): {"main": "потерянный", "also": ["заблудившийся"]},
    ("mine", "pronoun"): {"main": "мой", "also": ["моё"]},
    ("neither", "adverb"): {"main": "тоже не", "also": ["ни"]},
    ("neither", "determiner , pronoun"): {"main": "ни один", "also": ["никто"]},
    ("oh", "exclamation"): {"main": "о", "also": ["ох"]},
    ("OK", "adjective , adverb"): {"main": "нормально", "also": ["хорошо"]},
    ("OK", "exclamation"): {"main": "хорошо", "also": ["ладно"]},
    ("online", "adjective"): {"main": "онлайн", "also": ["сетевой"]},
    ("online", "adverb"): {"main": "онлайн", "also": ["в интернете"]},
    ("our", "determiner"): {"main": "наш", "also": ["наша"]},
    ("ours", "pronoun"): {"main": "наш", "also": ["наше"]},
    ("severely", "adverb"): {"main": "серьёзно", "also": ["жестоко"]},
    ("strictly", "adverb"): {"main": "строго", "also": []},
    ("teenage", "adjective"): {"main": "подростковый", "also": []},
    ("theirs", "pronoun"): {"main": "их", "also": []},
    ("they", "pronoun"): {"main": "они", "also": []},
    ("trauma", "noun"): {"main": "травма", "also": ["потрясение"]},
    ("upon", "preposition"): {"main": "на", "also": ["по"]},
    ("violation", "noun"): {"main": "нарушение", "also": []},
    ("what", "pronoun , determiner"): {"main": "что", "also": ["какой"]},
    ("which", "pronoun , determiner"): {"main": "который", "also": ["какой"]},
    ("workout", "noun"): {"main": "тренировка", "also": []},
    ("worst", "adverb"): {"main": "хуже всего", "also": []},
    ("yours", "pronoun"): {"main": "ваш", "also": ["твой"]},
    # sense / ranking fixes (main must be the student-primary gloss)
    ("begin", "verb"): {"main": "начинать", "also": ["начинаться"]},
    ("spring", "noun"): {"main": "весна", "also": ["пружина", "источник"]},
    ("shoot", "noun"): {"main": "росток", "also": ["побег", "съёмка"]},
    ("spam", "noun"): {"main": "спам", "also": []},
    ("media", "noun"): {"main": "СМИ", "also": ["пресса", "медиа"]},
    ("mobile", "noun"): {"main": "мобильный телефон", "also": ["мобильник"]},
    ("brand", "noun"): {"main": "бренд", "also": ["марка"]},
    ("brand", "verb"): {"main": "клеймить", "also": ["ставить марку"]},
    ("about", "adverb"): {"main": "примерно", "also": ["около", "кругом"]},
    ("animation", "noun"): {"main": "анимация", "also": ["мультипликация"]},
    ("August", "noun"): {"main": "август", "also": []},
    ("endorse", "verb"): {"main": "поддерживать", "also": ["одобрять"]},
    ("endorsement", "noun"): {"main": "поддержка", "also": ["одобрение"]},
    ("beneficiary", "noun"): {"main": "получатель", "also": ["бенефициар"]},
    ("hazard", "noun"): {"main": "опасность", "also": ["риск"]},
    ("turnout", "noun"): {"main": "явка", "also": ["посещаемость"]},
    ("inspire", "verb"): {"main": "вдохновлять", "also": ["воодушевлять"]},
    ("mortgage", "noun"): {"main": "ипотека", "also": ["залог"]},
    ("absorb", "verb"): {"main": "поглощать", "also": ["впитывать"]},
    ("chance", "noun"): {"main": "шанс", "also": ["возможность", "случай"]},
    ("access", "verb"): {"main": "получить доступ", "also": ["открыть"]},
    ("city", "noun"): {"main": "город", "also": []},
    ("venue", "noun"): {"main": "площадка", "also": ["место"]},
    ("seeker", "noun"): {"main": "искатель", "also": []},
    ("suspect", "noun"): {"main": "подозреваемый", "also": []},
    ("accountability", "noun"): {"main": "ответственность", "also": ["подотчётность"]},
    ("accuracy", "noun"): {"main": "точность", "also": ["правильность"]},
    ("aluminium", "noun"): {"main": "алюминий", "also": []},
    ("authority", "noun"): {"main": "власть", "also": ["авторитет"]},
    ("availability", "noun"): {"main": "доступность", "also": ["наличие"]},
    ("awareness", "noun"): {"main": "осведомлённость", "also": ["осознание"]},
    ("born", "verb"): {"main": "родиться", "also": []},
    ("capability", "noun"): {"main": "способность", "also": ["возможность"]},
    ("caution", "noun"): {"main": "осторожность", "also": ["предосторожность"]},
    ("combat", "noun"): {"main": "бой", "also": ["сражение"]},
    ("commercial", "noun"): {"main": "реклама", "also": ["ролик"]},
    ("compliance", "noun"): {"main": "соблюдение", "also": ["соответствие"]},
    ("conscience", "noun"): {"main": "совесть", "also": []},
    ("courtesy", "noun"): {"main": "вежливость", "also": ["учтивость"]},
    ("credibility", "noun"): {"main": "достоверность", "also": ["авторитет"]},
    ("daughter", "noun"): {"main": "дочь", "also": []},
    ("desktop", "noun"): {"main": "рабочий стол", "also": ["десктоп"]},
    ("disability", "noun"): {"main": "инвалидность", "also": ["ограничение"]},
    ("diversity", "noun"): {"main": "разнообразие", "also": []},
    ("duration", "noun"): {"main": "продолжительность", "also": ["длительность"]},
    ("dynamic", "noun"): {"main": "динамика", "also": []},
    ("effectiveness", "noun"): {"main": "эффективность", "also": []},
    ("efficiency", "noun"): {"main": "эффективность", "also": ["производительность"]},
    ("ethic", "noun"): {"main": "этика", "also": ["нравственность"]},
    ("euro", "noun"): {"main": "евро", "also": []},
    ("flexibility", "noun"): {"main": "гибкость", "also": []},
    ("fossil", "noun"): {"main": "ископаемое", "also": []},
    ("gravity", "noun"): {"main": "гравитация", "also": ["тяжесть"]},
    ("hate", "noun"): {"main": "ненависть", "also": []},
    ("hatred", "noun"): {"main": "ненависть", "also": []},
    ("ice cream", "noun"): {"main": "мороженое", "also": []},
    ("identity", "noun"): {"main": "личность", "also": ["идентичность"]},
    ("inability", "noun"): {"main": "неспособность", "also": []},
    ("injustice", "noun"): {"main": "несправедливость", "also": []},
    ("jury", "noun"): {"main": "суд присяжных", "also": ["присяжные"]},
    ("latter", "noun"): {"main": "последний", "also": ["второй"]},
    ("literacy", "noun"): {"main": "грамотность", "also": []},
    ("little", "determiner , pronoun"): {"main": "мало", "also": ["немного"]},
    ("live", "adverb"): {"main": "в прямом эфире", "also": ["живьём"]},
    ("live", "verb"): {"main": "жить", "also": ["проживать"]},
    # homograph: main must match THIS OALD definition (not another sense)
    ("arm", "verb"): {"main": "вооружать", "also": ["снабжать оружием"]},
    ("bank", "noun"): {"main": "банк", "also": ["берег"]},
    ("bat", "noun"): {"main": "бита", "also": ["летучая мышь"]},
    ("bat", "verb"): {"main": "бить битой", "also": ["отбивать"]},
    ("bow", "noun"): {"main": "поклон", "also": ["лук"]},
    ("bow", "verb"): {"main": "кланяться", "also": ["наклоняться"]},
    ("can", "noun"): {"main": "банка", "also": ["консервная банка"]},
    ("close", "adjective"): {"main": "близкий", "also": ["тесный"]},
    ("close", "verb"): {"main": "закрывать", "also": ["закрываться"]},
    ("lead", "noun"): {"main": "лидерство", "also": ["первое место", "свинец"]},
    ("lead", "verb"): {"main": "вести", "also": ["лидировать"]},
    ("plant", "noun"): {"main": "растение", "also": ["завод"]},
    ("present", "verb"): {"main": "представлять", "also": ["дарить"]},
    ("present", "adjective"): {"main": "текущий", "also": ["присутствующий"]},
    ("wind", "verb"): {"main": "извиваться", "also": ["виться", "наматывать"]},
    ("match", "noun"): {"main": "матч", "also": ["спичка"]},
    ("fan", "noun"): {"main": "фанат", "also": ["вентилятор", "веер"]},
    ("yard", "noun"): {"main": "двор", "also": ["ярд"]},
    ("flat", "noun"): {"main": "квартира", "also": []},
    ("content", "noun"): {"main": "содержание", "also": ["содержимое"]},
    ("sink", "verb"): {"main": "тонуть", "also": ["опускаться"]},
    ("park", "verb"): {"main": "парковать", "also": ["ставить"]},
    ("train", "verb"): {"main": "тренировать", "also": ["обучать"]},
    ("watch", "verb"): {"main": "смотреть", "also": ["наблюдать"]},
    ("object", "noun"): {"main": "предмет", "also": ["объект"]},
    # more homograph / wrong-sense fixes
    ("chip", "noun"): {"main": "чипсы", "also": ["щепка"]},
    ("club", "noun"): {"main": "клуб", "also": ["дубинка"]},
    ("draft", "noun"): {"main": "черновик", "also": ["набросок"]},
    ("draft", "verb"): {"main": "составлять черновик", "also": ["набрасывать"]},
    ("file", "noun"): {"main": "папка", "also": ["файл"]},
    ("file", "verb"): {"main": "подшивать", "also": ["регистрировать"]},
    ("fine", "adjective"): {"main": "хороший", "also": ["в порядке"]},
    ("fine", "noun"): {"main": "штраф", "also": ["пеня"]},
    ("fine", "verb"): {"main": "штрафовать", "also": []},
    ("hide", "verb"): {"main": "прятать", "also": ["скрывать"]},
    ("interest", "noun"): {"main": "интерес", "also": ["процент"]},
    ("jam", "noun"): {"main": "варенье", "also": ["джем", "пробка"]},
    ("letter", "noun"): {"main": "письмо", "also": ["буква"]},
    ("nail", "noun"): {"main": "ноготь", "also": ["гвоздь"]},
    ("net", "noun"): {"main": "сеть", "also": ["сетка"]},
    ("note", "verb"): {"main": "замечать", "also": ["отмечать"]},
    ("organ", "noun"): {"main": "орган", "also": []},
    ("party", "noun"): {"main": "вечеринка", "also": ["партия"]},
    ("patient", "adjective"): {"main": "терпеливый", "also": []},
    ("patient", "noun"): {"main": "пациент", "also": ["больной"]},
    ("ring", "noun"): {"main": "кольцо", "also": ["круг"]},
    ("ring", "verb"): {"main": "окружать", "also": ["звонить"]},
    ("sentence", "noun"): {"main": "предложение", "also": ["приговор"]},
    ("sentence", "verb"): {"main": "приговаривать", "also": ["осуждать"]},
    ("space", "noun"): {"main": "космос", "also": ["пространство"]},
    ("staff", "noun"): {"main": "персонал", "also": ["штаб"]},
    ("state", "adjective"): {"main": "государственный", "also": []},
    ("state", "noun"): {"main": "государство", "also": ["штат", "состояние"]},
    ("stick", "verb"): {"main": "приклеивать", "also": ["втыкать"]},
    ("table", "noun"): {"main": "стол", "also": ["таблица"]},
    ("wave", "noun"): {"main": "волна", "also": []},
    ("wave", "verb"): {"main": "махать", "also": ["размахивать"]},
    ("well", "noun"): {"main": "колодец", "also": []},
    ("well", "exclamation"): {"main": "ну", "also": ["что ж"]},
    ("well", "adjective"): {"main": "здоровый", "also": ["хороший"]},
    ("date", "verb"): {"main": "датировать", "also": ["ходить на свидание"]},
    ("mean", "verb"): {"main": "означать", "also": ["иметь в виду"]},
    ("grave", "noun"): {"main": "могила", "also": []},

    ("long-term", "adverb"): {"main": "в долгосрочной перспективе", "also": ["надолго"]},
    ("loyalty", "noun"): {"main": "лояльность", "also": ["верность"]},
    ("lung", "noun"): {"main": "лёгкое", "also": []},
    ("more", "determiner , pronoun"): {"main": "больше", "also": ["ещё"]},
    ("mosque", "noun"): {"main": "мечеть", "also": []},
    ("nearby", "adverb"): {"main": "рядом", "also": ["поблизости"]},
    ("opposite", "noun"): {"main": "противоположность", "also": []},
    ("past", "noun"): {"main": "прошлое", "also": []},
    ("plastic", "noun"): {"main": "пластик", "also": ["пластмасса"]},
    ("popularity", "noun"): {"main": "популярность", "also": []},
    ("possibility", "noun"): {"main": "возможность", "also": ["вероятность"]},
    ("precision", "noun"): {"main": "точность", "also": []},
    ("pregnancy", "noun"): {"main": "беременность", "also": []},
    ("probability", "noun"): {"main": "вероятность", "also": []},
    ("publishing", "noun"): {"main": "издательское дело", "also": ["публикация"]},
    ("rapidly", "adverb"): {"main": "быстро", "also": ["стремительно"]},
    ("rear", "adjective"): {"main": "задний", "also": []},
    ("relevance", "noun"): {"main": "актуальность", "also": ["уместность"]},
    ("reliability", "noun"): {"main": "надёжность", "also": []},
    ("safety", "noun"): {"main": "безопасность", "also": []},
    ("saint", "noun"): {"main": "святой", "also": []},
    ("same", "adverb"): {"main": "так же", "also": ["одинаково"]},
    ("same", "pronoun"): {"main": "то же самое", "also": []},
    ("scenario", "noun"): {"main": "сценарий", "also": []},
    ("security", "noun"): {"main": "безопасность", "also": ["охрана"]},
    ("sensitivity", "noun"): {"main": "чувствительность", "also": []},
    ("slow", "verb"): {"main": "замедлять", "also": ["замедляться"]},
    ("smoking", "noun"): {"main": "курение", "also": []},
    ("solidarity", "noun"): {"main": "солидарность", "also": []},
    ("stability", "noun"): {"main": "стабильность", "also": ["устойчивость"]},
    ("statistic", "noun"): {"main": "статистика", "also": ["показатель"]},
    ("surface", "noun"): {"main": "поверхность", "also": []},
    ("theology", "noun"): {"main": "теология", "also": ["богословие"]},
    ("update", "noun"): {"main": "обновление", "also": []},
    ("upset", "adjective"): {"main": "расстроенный", "also": ["огорчённый"]},
    ("validity", "noun"): {"main": "действительность", "also": ["валидность"]},
    ("vulnerability", "noun"): {"main": "уязвимость", "also": []},
    ("willingness", "noun"): {"main": "готовность", "also": []},
    ("worse", "noun"): {"main": "худшее", "also": []},
    ("worst", "noun"): {"main": "худшее", "also": []},
    ("telephone", "noun"): {"main": "телефон", "also": []},
    ("telephone", "verb"): {"main": "звонить", "also": ["звонить по телефону"]},
    # catastrophic sense fixes (main must match OALD primary definition)
    ("dollar", "noun"): {"main": "доллар", "also": []},
    ("tent", "noun"): {"main": "палатка", "also": []},
    ("palm", "noun"): {"main": "пальма", "also": ["ладонь"]},
    ("toe", "noun"): {"main": "палец ноги", "also": []},
    ("ban", "noun"): {"main": "запрет", "also": []},
    ("bounce", "verb"): {"main": "отскакивать", "also": ["подпрыгивать"]},
    ("feature", "verb"): {"main": "показывать", "also": ["включать"]},
    ("square", "noun"): {"main": "квадрат", "also": ["площадь"]},
    ("star", "verb"): {"main": "играть главную роль", "also": ["сниматься"]},
    ("spot", "verb"): {"main": "замечать", "also": ["пятнать"]},
    ("simulate", "verb"): {"main": "моделировать", "also": ["симулировать"]},
    ("satisfaction", "noun"): {"main": "удовлетворение", "also": []},
    ("wool", "noun"): {"main": "шерсть", "also": []},
    ("instrumental", "adjective"): {"main": "инструментальный", "also": ["важный"]},
    ("aspire", "verb"): {"main": "стремиться", "also": []},
    ("thumb", "noun"): {"main": "большой палец", "also": []},
    ("environment", "noun"): {"main": "окружающая среда", "also": ["окружение"]},
    ("exchange", "noun"): {"main": "обмен", "also": []},
    ("serious", "adjective"): {"main": "серьёзный", "also": ["важный"]},
    ("bitter", "adjective"): {"main": "горький", "also": ["резкий"]},
    ("unemployed", "adjective"): {"main": "безработный", "also": []},
    ("badly", "adverb"): {"main": "плохо", "also": ["сильно"]},
    ("happy", "adjective"): {"main": "счастливый", "also": ["довольный"]},
    ("choose", "verb"): {"main": "выбирать", "also": ["решать"]},
    ("contribute", "verb"): {"main": "вносить вклад", "also": ["жертвовать"]},
    ("audio", "adjective"): {"main": "аудио", "also": ["звуковой"]},
    ("tonne", "noun"): {"main": "тонна", "also": []},
    ("breakthrough", "noun"): {"main": "прорыв", "also": ["открытие"]},
    ("academic", "adjective"): {"main": "академический", "also": ["учебный"]},
    ("best", "noun"): {"main": "лучшее", "also": []},
    ("solid", "noun"): {"main": "твёрдое тело", "also": []},
    ("emergence", "noun"): {"main": "появление", "also": []},
    ("outlet", "noun"): {"main": "магазин", "also": ["выход"]},
    ("chat", "noun"): {"main": "болтовня", "also": ["беседа"]},
    ("official", "adjective"): {"main": "официальный", "also": ["служебный"]},
    ("reliable", "adjective"): {"main": "надёжный", "also": []},
    ("opposed", "adjective"): {"main": "противоположный", "also": ["против"]},
    ("opposition", "noun"): {"main": "оппозиция", "also": ["сопротивление"]},
    ("sponsorship", "noun"): {"main": "спонсорство", "also": []},
    ("routine", "noun"): {"main": "рутина", "also": ["распорядок"]},
    ("routine", "adjective"): {"main": "обычный", "also": ["рутинный"]},
    ("agree", "verb"): {"main": "соглашаться", "also": ["договариваться"]},
    ("filter", "verb"): {"main": "фильтровать", "also": []},
    ("exaggerate", "verb"): {"main": "преувеличивать", "also": []},
    ("reluctant", "adjective"): {"main": "неохотный", "also": ["не желающий"]},
    ("resist", "verb"): {"main": "сопротивляться", "also": ["противостоять"]},
    ("oppose", "verb"): {"main": "противостоять", "also": ["сопротивляться"]},
    ("penny", "noun"): {"main": "пенни", "also": ["монета"]},
    ("terms", "noun"): {"main": "условия", "also": []},
    ("succeed", "verb"): {"main": "добиться успеха", "also": ["преуспеть"]},
    ("switch", "verb"): {"main": "переключать", "also": ["менять"]},
    ("tip", "verb"): {"main": "давать чаевые", "also": ["наклонять"]},
    ("log", "verb"): {"main": "записывать", "also": ["вести журнал"]},
    ("coach", "verb"): {"main": "тренировать", "also": ["наставлять"]},
    ("local", "noun"): {"main": "местный житель", "also": []},
    ("premise", "noun"): {"main": "предпосылка", "also": ["посылка"]},
    ("asset", "noun"): {"main": "актив", "also": ["достоинство"]},
    ("sake", "noun"): {"main": "ради", "also": []},
    ("low", "noun"): {"main": "низкий уровень", "also": ["минимум"]},
    ("we", "pronoun"): {"main": "мы", "also": []},
    ("about", "preposition"): {"main": "о", "also": ["об", "про"]},
    ("after", "preposition"): {"main": "после", "also": ["за"]},
    ("at", "preposition"): {"main": "в", "also": ["у", "на"]},
    ("by", "preposition"): {"main": "у", "also": ["к", "посредством"]},
    ("from", "preposition"): {"main": "из", "also": ["от"]},
    ("of", "preposition"): {"main": "из", "also": ["от"]},
    ("on", "preposition"): {"main": "на", "also": ["по"]},
    ("over", "preposition"): {"main": "над", "also": ["через", "более"]},
    ("over", "adverb"): {"main": "через", "also": ["свыше"]},
    ("through", "preposition"): {"main": "через", "also": ["сквозь"]},
    ("to", "preposition"): {"main": "к", "also": ["в", "на"]},
    ("to", "infinitive marker"): {"main": "чтобы", "also": []},
    ("under", "preposition"): {"main": "под", "also": []},
    ("up", "adverb"): {"main": "вверх", "also": ["наверх"]},
    ("with", "preposition"): {"main": "с", "also": []},
    ("and", "conjunction"): {"main": "и", "also": ["а"]},
    ("internet", "noun"): {"main": "интернет", "also": []},
    ("footage", "noun"): {"main": "кадры", "also": ["съёмка"]},
    ("damaging", "adjective"): {"main": "вредный", "also": ["разрушительный"]},
    ("adjust", "verb"): {"main": "настраивать", "also": ["регулировать"]},
    ("arrange", "verb"): {"main": "организовать", "also": ["устроить"]},
    ("arrangement", "noun"): {"main": "договорённость", "also": ["расположение"]},
    ("order", "verb"): {"main": "заказывать", "also": ["приказывать"]},
    ("book", "verb"): {"main": "бронировать", "also": ["заказывать"]},
    ("alert", "verb"): {"main": "предупреждать", "also": ["оповещать"]},
    ("align", "verb"): {"main": "выравнивать", "also": ["выстраивать"]},
    ("campaign", "verb"): {"main": "вести кампанию", "also": []},
    ("living", "noun"): {"main": "средства к жизни", "also": ["жизнь"]},
    ("unique", "adjective"): {"main": "уникальный", "also": ["единственный"]},
    ("upstairs", "adjective"): {"main": "наверху", "also": []},
    ("privatization", "noun"): {"main": "приватизация", "also": []},
    ("shopping", "noun"): {"main": "покупки", "also": ["шопинг"]},
    ("technology", "noun"): {"main": "технология", "also": ["техника"]},
    ("current", "adjective"): {"main": "текущий", "also": ["нынешний"]},
    ("abortion", "noun"): {"main": "аборт", "also": ["выкидыш"]},
    ("replace", "verb"): {"main": "заменять", "also": ["заменить"]},
    ("vote", "verb"): {"main": "голосовать", "also": []},
    ("launch", "noun"): {"main": "запуск", "also": ["старт"]},
    ("into", "preposition"): {"main": "в", "also": ["внутрь"]},
    ("towards", "preposition"): {"main": "к", "also": ["по направлению к"]},
    ("fish", "verb"): {"main": "ловить рыбу", "also": ["удить"]},
    ("grandparent", "noun"): {"main": "дед или бабушка", "also": ["бабушка", "дедушка"]},
    ("funding", "noun"): {"main": "финансирование", "also": ["средства"]},
    ("dismissal", "noun"): {"main": "увольнение", "also": ["отставка"]},
    ("escalate", "verb"): {"main": "обостряться", "also": ["нарастать"]},
    ("fortunately", "adverb"): {"main": "к счастью", "also": ["удачно"]},
    ("unfortunately", "adverb"): {"main": "к сожалению", "also": []},
    ("it", "pronoun"): {"main": "это", "also": ["оно"]},
    ("expand", "verb"): {"main": "расширять", "also": ["увеличивать"]},
    ("land", "verb"): {"main": "приземляться", "also": ["высаживаться"]},
    ("pause", "verb"): {"main": "делать паузу", "also": ["останавливаться"]},
    ("very", "adverb"): {"main": "очень", "also": []},
    ("off", "preposition"): {"main": "с", "also": ["от"]},
    ("philosopher", "noun"): {"main": "философ", "also": []},
    ("race", "verb"): {"main": "мчаться", "also": ["состязаться"]},
    ("racing", "noun"): {"main": "гонки", "also": ["скачки"]},
    ("range", "verb"): {"main": "варьироваться", "also": ["располагать"]},
    ("soak", "verb"): {"main": "замачивать", "also": ["пропитывать"]},
    ("unveil", "verb"): {"main": "открывать", "also": ["представить"]},
    ("north", "adjective"): {"main": "северный", "also": []},
    ("setting", "noun"): {"main": "обстановка", "also": ["декорации"]},
    ("rehabilitation", "noun"): {"main": "реабилитация", "also": ["восстановление"]},
    ("suspect", "verb"): {"main": "подозревать", "also": ["сомневаться"]},
    ("thoughtful", "adjective"): {"main": "задумчивый", "also": ["внимательный"]},
    # Full QA pass — catastrophic / wrong-sense / artifacts (2026-07)
    ("bass", "noun"): {"main": "бас", "also": ["бас-гитара"]},
    ("administrator", "noun"): {"main": "администратор", "also": ["управляющий"]},
    ("advance", "adjective"): {"main": "предварительный", "also": ["авансовый"]},
    ("advance", "noun"): {"main": "прогресс", "also": ["аванс", "продвижение"]},
    ("advance", "verb"): {"main": "продвигаться", "also": ["развиваться"]},
    ("against", "preposition"): {"main": "против", "also": ["вопреки"]},
    ("appetite", "noun"): {"main": "аппетит", "also": []},
    ("architecture", "noun"): {"main": "архитектура", "also": []},
    ("artificial", "adjective"): {"main": "искусственный", "also": []},
    ("automatic", "adjective"): {"main": "автоматический", "also": []},
    ("aggressive", "adjective"): {"main": "агрессивный", "also": ["напористый"]},
    ("adventure", "noun"): {"main": "приключение", "also": []},
    ("advise", "verb"): {"main": "советовать", "also": ["консультировать"]},
    ("afford", "verb"): {"main": "позволить себе", "also": []},
    ("adapt", "verb"): {"main": "приспосабливаться", "also": ["адаптироваться"]},
    ("accumulate", "verb"): {"main": "накапливать", "also": []},
    ("accommodate", "verb"): {"main": "размещать", "also": ["предоставлять жильё"]},
    ("advantage", "noun"): {"main": "преимущество", "also": ["выгода"]},
    ("adverse", "adjective"): {"main": "неблагоприятный", "also": ["вредный"]},
    ("agricultural", "adjective"): {"main": "сельскохозяйственный", "also": []},
    ("aged", "adjective"): {"main": "пожилой", "also": ["преклонных лет"]},
    ("alarm", "noun"): {"main": "сигнал тревоги", "also": ["тревога"]},
    ("alarm", "verb"): {"main": "тревожить", "also": ["пугать"]},
    ("alignment", "noun"): {"main": "выравнивание", "also": ["согласование"]},
    ("appeal", "verb"): {"main": "обращаться", "also": ["привлекать", "апеллировать"]},
    ("articulate", "verb"): {"main": "формулировать", "also": ["чётко выражать"]},
    ("authorize", "verb"): {"main": "уполномочивать", "also": ["разрешать"]},
    ("attribute", "verb"): {"main": "приписывать", "also": []},
    ("assassination", "noun"): {"main": "убийство", "also": ["покушение"]},
    ("asylum", "noun"): {"main": "убежище", "also": ["приют"]},
    ("ballot", "noun"): {"main": "голосование", "also": ["бюллетень"]},
    ("actual", "adjective"): {"main": "фактический", "also": ["реальный"]},
    ("adjustment", "noun"): {"main": "регулировка", "also": ["корректировка"]},
    ("adoption", "noun"): {"main": "усыновление", "also": ["принятие"]},
    ("exist", "verb"): {"main": "существовать", "also": []},
    ("feature", "verb"): {"main": "включать", "also": ["показывать"]},
    ("fire", "verb"): {"main": "стрелять", "also": ["увольнять"]},
    ("glass", "noun"): {"main": "стекло", "also": ["стакан"]},
    ("forget", "verb"): {"main": "забывать", "also": []},
    ("intend", "verb"): {"main": "намереваться", "also": ["предназначать"]},
    ("deposit", "verb"): {"main": "вносить вклад", "also": ["депонировать"]},
    ("dive", "noun"): {"main": "ныряние", "also": ["прыжок"]},
    ("dive", "verb"): {"main": "нырять", "also": []},
    ("tide", "noun"): {"main": "прилив", "also": ["отлив", "течение"]},
    ("toilet", "noun"): {"main": "туалет", "also": []},
    ("proceeding", "noun"): {"main": "судебное разбирательство", "also": ["дело"]},
    ("regard", "verb"): {"main": "считать", "also": ["рассматривать"]},
    ("regard", "noun"): {"main": "уважение", "also": ["внимание"]},
    ("punk", "noun"): {"main": "панк", "also": ["панк-рок"]},
    ("viewer", "noun"): {"main": "зритель", "also": []},
    ("speaker", "noun"): {"main": "оратор", "also": ["спикер"]},
    ("neighbour", "noun"): {"main": "сосед", "also": ["соседка"]},
    ("maximize", "verb"): {"main": "максимизировать", "also": ["увеличивать"]},
    ("philosophy", "noun"): {"main": "философия", "also": []},
    ("connection", "noun"): {"main": "связь", "also": ["соединение"]},
    ("donation", "noun"): {"main": "пожертвование", "also": ["дар"]},
    ("repeat", "verb"): {"main": "повторять", "also": []},
    ("spotlight", "noun"): {"main": "прожектор", "also": ["внимание"]},
    ("one", "number , determiner"): {"main": "один", "also": []},
    ("organize", "verb"): {"main": "организовывать", "also": ["устраивать"]},
    ("slavery", "noun"): {"main": "рабство", "also": []},
    ("edit", "verb"): {"main": "редактировать", "also": []},
    ("hell", "noun"): {"main": "ад", "also": []},
    ("iron", "verb"): {"main": "гладить", "also": ["утюжить"]},
    ("warehouse", "noun"): {"main": "склад", "also": []},
    ("architect", "noun"): {"main": "архитектор", "also": []},
    ("accountant", "noun"): {"main": "бухгалтер", "also": []},
    ("accounting", "noun"): {"main": "бухучёт", "also": ["учёт"]},
    ("architect", "noun"): {"main": "архитектор", "also": []},
    ("background", "noun"): {"main": "происхождение", "also": ["биография", "фон"]},
    ("career", "noun"): {"main": "карьера", "also": []},
    ("chase", "noun"): {"main": "погоня", "also": ["преследование"]},
    ("civilian", "noun"): {"main": "мирный житель", "also": ["гражданское лицо"]},
    ("civilian", "adjective"): {"main": "гражданский", "also": ["штатский"]},
    ("shooting", "noun"): {"main": "стрельба", "also": ["перестрелка"]},
    ("monkey", "noun"): {"main": "обезьяна", "also": []},
    ("mineral", "noun"): {"main": "минерал", "also": ["полезное ископаемое"]},
    ("migration", "noun"): {"main": "миграция", "also": ["перелёт"]},
    ("master", "verb"): {"main": "осваивать", "also": ["овладевать"]},
    ("major", "adjective"): {"main": "главный", "also": ["крупный"]},
    ("news", "noun"): {"main": "новости", "also": ["известие"]},
    ("occasionally", "adverb"): {"main": "иногда", "also": ["изредка"]},
    ("operator", "noun"): {"main": "оператор", "also": ["механик"]},
    ("overwhelm", "verb"): {"main": "ошеломлять", "also": ["переполнять"]},
    ("pill", "noun"): {"main": "таблетка", "also": []},
    ("permanent", "adjective"): {"main": "постоянный", "also": []},
    ("mysterious", "adjective"): {"main": "таинственный", "also": ["загадочный"]},
    ("noble", "adjective"): {"main": "благородный", "also": []},
    ("nationwide", "adjective , adverb"): {"main": "общенациональный", "also": ["по всей стране"]},
    ("mount", "verb"): {"main": "организовывать", "also": ["начать"]},
    ("produce", "verb"): {"main": "производить", "also": ["выпускать"]},
    ("resident", "noun"): {"main": "житель", "also": ["резидент"]},
    ("physical", "adjective"): {"main": "физический", "also": ["телесный"]},
    ("perceive", "verb"): {"main": "воспринимать", "also": ["понимать"]},
    ("persistent", "adjective"): {"main": "настойчивый", "also": ["стойкий"]},
    ("care", "verb"): {"main": "заботиться", "also": ["волноваться"]},
    ("cast", "verb"): {"main": "бросать", "also": ["направлять"]},
    ("cattle", "noun"): {"main": "скот", "also": []},
    ("acceptable", "adjective"): {"main": "приемлемый", "also": ["допустимый"]},
    ("address", "verb"): {"main": "заниматься", "also": ["решать", "адресовать"]},
    ("satisfy", "verb"): {"main": "удовлетворять", "also": []},
    ("saving", "noun"): {"main": "экономия", "also": ["сбережения"]},
    ("scream", "verb"): {"main": "кричать", "also": ["визжать"]},
    ("self", "noun"): {"main": "личность", "also": ["я"]},
    ("tactical", "adjective"): {"main": "тактический", "also": []},
    ("tail", "noun"): {"main": "хвост", "also": []},
    ("term", "noun"): {"main": "термин", "also": ["срок"]},
    ("territory", "noun"): {"main": "территория", "also": []},
    ("tin", "noun"): {"main": "банка", "also": ["олово"]},
    ("theatrical", "adjective"): {"main": "театральный", "also": []},
    ("sadly", "adverb"): {"main": "грустно", "also": ["к сожалению"]},
    ("sacrifice", "noun"): {"main": "жертва", "also": ["жертвоприношение"]},
    ("abundance", "noun"): {"main": "изобилие", "also": ["избыток"]},
    ("cow", "noun"): {"main": "корова", "also": []},
    ("knee", "noun"): {"main": "колено", "also": []},
    ("brain", "noun"): {"main": "мозг", "also": []},
    ("chicken", "noun"): {"main": "курица", "also": ["цыплёнок"]},
    ("counter", "verb"): {"main": "противостоять", "also": ["возражать"]},
    ("craft", "verb"): {"main": "мастерить", "also": ["изготовлять"]},
    ("dislike", "verb"): {"main": "не любить", "also": ["испытывать неприязнь"]},
    ("locate", "verb"): {"main": "находить", "also": ["определять местоположение"]},
    ("structure", "verb"): {"main": "структурировать", "also": ["организовывать"]},
    ("greet", "verb"): {"main": "приветствовать", "also": []},
    ("grey", "adjective"): {"main": "серый", "also": ["седой"]},
    ("grey", "noun"): {"main": "серый цвет", "also": []},
    ("defeat", "noun"): {"main": "поражение", "also": []},
    ("defeat", "verb"): {"main": "побеждать", "also": ["наносить поражение"]},
    ("up", "preposition"): {"main": "вверх по", "also": ["по"]},
    ("unusual", "adjective"): {"main": "необычный", "also": ["странный"]},
    ("whereas", "conjunction"): {"main": "тогда как", "also": ["в то время как"]},
    ("ghost", "noun"): {"main": "привидение", "also": ["дух"]},
    ("update", "verb"): {"main": "обновлять", "also": ["модернизировать"]},
    ("deem", "verb"): {"main": "считать", "also": ["полагать"]},
    # ok-tier sense / student fixes
    ("appropriately", "adverb"): {"main": "уместно", "also": ["соответственно"]},
    ("behalf", "noun"): {"main": "от имени", "also": []},
    ("anyway", "adverb"): {"main": "в любом случае", "also": []},
    ("bush", "noun"): {"main": "куст", "also": ["кустарник"]},
    ("alien", "noun"): {"main": "иностранец", "also": ["чужестранец"]},
    ("alliance", "noun"): {"main": "союз", "also": ["альянс"]},
    ("camp", "verb"): {"main": "жить в палатке", "also": []},
    ("chat", "verb"): {"main": "болтать", "also": []},
    ("cheer", "verb"): {"main": "болеть", "also": ["подбадривать"]},
    ("confidence", "noun"): {"main": "уверенность", "also": ["доверие"]},
    ("cooperative", "adjective"): {"main": "совместный", "also": ["сотрудничающий"]},
    ("coordinate", "verb"): {"main": "координировать", "also": ["согласовывать"]},
    ("demonstration", "noun"): {"main": "демонстрация", "also": ["митинг"]},
    ("dependence", "noun"): {"main": "зависимость", "also": []},
    ("downstairs", "adjective"): {"main": "внизу", "also": []},
    ("downtown", "adjective"): {"main": "центральный", "also": ["деловой"]},
    ("dramatically", "adverb"): {"main": "резко", "also": ["значительно"]},
    ("elsewhere", "adverb"): {"main": "в другом месте", "also": []},
    ("emergency", "noun"): {"main": "чрезвычайная ситуация", "also": []},
    ("express", "verb"): {"main": "выражать", "also": []},
    ("facility", "noun"): {"main": "объект", "also": ["удобства"]},
    ("fluid", "noun"): {"main": "жидкость", "also": []},
    ("frustrating", "adjective"): {"main": "раздражающий", "also": []},
    ("generic", "adjective"): {"main": "общий", "also": ["типовой"]},
    ("gentleman", "noun"): {"main": "джентльмен", "also": ["господин"]},
    ("graduate", "verb"): {"main": "окончить университет", "also": []},
    ("grandparent", "noun"): {"main": "бабушка или дедушка", "also": []},
    ("independence", "noun"): {"main": "независимость", "also": []},
    ("indoor", "adjective"): {"main": "комнатный", "also": ["внутренний"]},
    ("indulge", "verb"): {"main": "баловать себя", "also": ["позволять себе"]},
    ("judgement", "noun"): {"main": "суждение", "also": ["оценка"]},
    ("legislature", "noun"): {"main": "законодательный орган", "also": []},
    ("likelihood", "noun"): {"main": "вероятность", "also": []},
    ("line-up", "noun"): {"main": "состав", "also": []},
    ("market", "verb"): {"main": "продвигать", "also": ["рекламировать"]},
    ("matching", "adjective"): {"main": "парный", "also": ["подходящий"]},
    ("ministry", "noun"): {"main": "министерство", "also": []},
    ("necessity", "noun"): {"main": "необходимость", "also": []},
    ("nomination", "noun"): {"main": "выдвижение", "also": ["номинация"]},
    ("non-profit", "adjective"): {"main": "некоммерческий", "also": []},
    ("outdoor", "adjective"): {"main": "уличный", "also": ["на открытом воздухе"]},
    ("practitioner", "noun"): {"main": "практик", "also": ["специалист"]},
    ("protocol", "noun"): {"main": "протокол", "also": ["этикет"]},
    ("recycle", "verb"): {"main": "перерабатывать", "also": []},
    ("rental", "noun"): {"main": "аренда", "also": ["арендная плата"]},
    ("riot", "noun"): {"main": "бунт", "also": ["беспорядки"]},
    ("sack", "verb"): {"main": "увольнять", "also": []},
    ("sexuality", "noun"): {"main": "сексуальность", "also": []},
    ("shaped", "adjective"): {"main": "имеющий форму", "also": []},
    ("sibling", "noun"): {"main": "брат или сестра", "also": []},
    ("straightforward", "adjective"): {"main": "простой", "also": ["понятный"]},
    ("transfer", "verb"): {"main": "переводить", "also": ["переносить"]},
    ("underlying", "adjective"): {"main": "лежащий в основе", "also": ["скрытый"]},
    ("undertake", "verb"): {"main": "брать на себя", "also": ["предпринимать"]},
    ("venture", "noun"): {"main": "предприятие", "also": ["рискованное начинание"]},
    ("wow", "exclamation"): {"main": "вау", "also": ["ого"]},
    ("written", "adjective"): {"main": "письменный", "also": []},
    ("beneficiary", "noun"): {"main": "получатель", "also": []},
    ("private", "adjective"): {"main": "личный", "also": ["частный"]},
    ("orchestra", "noun"): {"main": "оркестр", "also": []},
}

# Same word+POS, different OALD senses (definition decides). Checked before CURATED.
SENSE_BY_DEF: list[tuple[str, str, str, dict[str, list[str] | str]]] = [
    (
        "lie",
        "verb",
        r"flat position|not standing or sitting",
        {"main": "лежать", "also": ["ложиться"]},
    ),
    (
        "lie",
        "verb",
        r"not true|knowing that it is not true",
        {"main": "лгать", "also": ["обманывать"]},
    ),
    (
        "march",
        "noun",
        r"month of the year|February and April",
        {"main": "март", "also": []},
    ),
    (
        "march",
        "noun",
        r"organized walk|protest|demonstrate",
        {"main": "марш", "also": ["демонстрация"]},
    ),
]

# High-precision: if OALD definition matches cue and also has preferred gloss
# while main does not → promote also→main (sense alignment).
DEF_PROMOTE: list[tuple[re.Pattern[str], re.Pattern[str]]] = [
    (re.compile(r"set of rooms for living|apartment|one floor of a building", re.I), re.compile(r"квартир", re.I)),
    (re.compile(r"road vehicle with an engine and four wheels", re.I), re.compile(r"машин|автомоб|легков", re.I)),
    (re.compile(r"continuous pain in the head", re.I), re.compile(r"головн.*боль|боль.*голов", re.I)),
    (re.compile(r"^sleeping\b|\bsleeping$", re.I), re.compile(r"спящ|уснув", re.I)),
    (re.compile(r"hard material that the trunk and branches of a tree", re.I), re.compile(r"дерев|древес", re.I)),
    (re.compile(r"pale in colour", re.I), re.compile(r"бледн|светл", re.I)),
    (re.compile(r"colour of earth or coffee", re.I), re.compile(r"коричнев", re.I)),
    (re.compile(r"very darkest colour, like night or coal", re.I), re.compile(r"чёрн|черн", re.I)),
    (re.compile(r"very young child or animal", re.I), re.compile(r"ребён|ребен|малыш|младен", re.I)),
    (re.compile(r"work that is given by teachers for students to do at home", re.I), re.compile(r"домашн|уроки|задан", re.I)),
    (re.compile(r"money that you earn for the work that you do", re.I), re.compile(r"заработ|зарплат|заработан|доход", re.I)),
    (re.compile(r"drinks such as beer, wine", re.I), re.compile(r"алкогол|спиртн", re.I)),
    (re.compile(r"meat that comes from a cow", re.I), re.compile(r"говядин", re.I)),
    (re.compile(r"hit somebody/something with your foot", re.I), re.compile(r"ног|пина|удар", re.I)),
    (re.compile(r"prepare food by heating", re.I), re.compile(r"готов|вари|жар|печь|кулинар", re.I)),
    (re.compile(r"take and use something that belongs to somebody else, and return", re.I), re.compile(r"заим|одалжива|брать на время", re.I)),
    (re.compile(r"say things; to speak in order to give information", re.I), re.compile(r"^говорить$|разговор|бесед", re.I)),
    (re.compile(r"ask somebody questions about something, especially officially", re.I), re.compile(r"спрашив|вопрос", re.I)),
    (re.compile(r"stretch out your finger.*towards", re.I), re.compile(r"пальц|указ|показ", re.I)),
    (re.compile(r"near in space or time", re.I), re.compile(r"близк|близко|рядом", re.I)),
    (re.compile(r"length of time that something lasts", re.I), re.compile(r"период|продолжительн|срок|время", re.I)),
    (re.compile(r"small bag made of very thin rubber that becomes larger", re.I), re.compile(r"шар|воздушн", re.I)),
    (re.compile(r"curve or turn, especially in a road or river", re.I), re.compile(r"изгиб|поворот", re.I)),
    (re.compile(r"show your approval.*clapping your hands", re.I), re.compile(r"аплод|рукоплеск|хлопа", re.I)),
    (re.compile(r"encourage somebody or give them help; to give financial support", re.I), re.compile(r"поддерж", re.I)),
    (re.compile(r"take willingly something that is offered", re.I), re.compile(r"принима", re.I)),
    (re.compile(r"^(?:a )?friend\b", re.I), re.compile(r"друг|приятел|товарищ", re.I)),
    (re.compile(r"statement saying that you strongly believe something to be true", re.I), re.compile(r"утвержден|заявлен", re.I)),
    (re.compile(r"connected with education, especially studying in schools", re.I), re.compile(r"учебн|академическ|образоват", re.I)),
    (re.compile(r"explosion or a powerful movement of air", re.I), re.compile(r"взрыв|поток|струя|воздух", re.I)),
    (re.compile(r"the length of time that something lasts or is able to continue", re.I), re.compile(r"продолжительн", re.I)),
]

JUNK_START = re.compile(
    r"^(?:"
    r"напр|в выражениях|сокр|сущ\.?|гл\.?|прил\.?|нареч\.?|мест\.?|числ\.?|"
    r"межд\.?|частица|I+|II+|III+|•|=|\(|обыкн|преим|разг\.?|проф\.?|"
    r"амер\.?|брит\.?|книж|юр\.?|ком\.?|спорт\.?|муз\.?|информ"
    r")\b",
    re.I,
)
JUNK_CONTAINS = re.compile(
    r"(?:т\.?\s*п\.|т\.?\s*д\.|Syn\s*:|см\.|от\s+[A-Za-z]|сокр\.?\s+от|"
    r"источник:|на Gufo|предложить)",
    re.I,
)


def fix_muller_spacing(s: str) -> str:
    """Join broken 'зак а з' / 'оформл е ние' Mueller artefacts.

    Do NOT collapse real one-letter prepositions (в, к, с, у, о, и, а).
    """
    tokens = s.split()
    if len(tokens) < 3:
        return s
    # Only repair when many isolated letters look like OCR/Mueller letter-spacing
    singles = [
        t
        for t in tokens
        if len(t) == 1
        and re.fullmatch(r"[А-Яа-яЁё]", t)
        and t.lower() not in {"в", "к", "с", "у", "о", "и", "а", "я"}
    ]
    if len(singles) >= max(2, len(tokens) // 3):
        return re.sub(r"(?<=[А-Яа-яЁё])\s+(?=[А-Яа-яЁё])", "", s)
    # collapse only non-preposition single letters between words
    return re.sub(
        r"(?<=[А-Яа-яЁё])\s([бгдежзлмнпрстфхцчшщъыьэю])\s(?=[А-Яа-яЁё])",
        r"\1",
        s,
        flags=re.I,
    )


# Stuck Mueller tokens → spaced Russian
UNGLUE_EXACT = {
    "техническиеиприкладные": "технические и прикладные",
    "формироватьиукомплектовывать": "формировать и укомплектовывать",
    "приводитьвпорядок": "приводить в порядок",
    "приведениевпорядок": "приведение в порядок",
    "привестивсостояние": "привести в состояние",
    "выстраиватьвлинию": "выстраивать в линию",
    "выстраиватьвряд": "выстраивать в ряд",
    "заноситьвкнигу": "заносить в книгу",
    "заноситьвсписок": "заносить в список",
    "вноситьвсписок": "вносить в список",
    "участвоватьвпоходе": "участвовать в походе",
    "участвоватьвскачках": "участвовать в скачках",
    "ехатьвкарете": "ехать в карете",
    "перевозитьвкарете": "перевозить в карете",
    "относящийсякконгрессу": "относящийся к конгрессу",
    "относящийсякделу": "относящийся к делу",
    "относящийсяктрагедии": "относящийся к трагедии",
    "относящийсякзападу": "относящийся к западу",
    "относящийсякдействию": "относящийся к действию",
    "относящийсякучреждению": "относящийся к учреждению",
    "относящийсякэволюционизму": "относящийся к эволюционизму",
    "относящийсякокружающей": "относящийся к окружающей",
    "относящийсякборьбе": "относящийся к борьбе",
    "неотносящийсякделу": "не относящийся к делу",
    "имеющийсявраспоряжении": "имеющийся в распоряжении",
    "отпечатыватьсявпамяти": "отпечатываться в памяти",
    "бытьвсостоянии": "быть в состоянии",
    "входитьвподробности": "входить в подробности",
    "готовитькпечати": "готовить к печати",
    "получатьсяврезультате": "получаться в результате",
    "происходитьврезультате": "происходить в результате",
    "вводитьвупотребление": "вводить в употребление",
    "находящийсявобращении": "находящийся в обращении",
    "находящийсявверхнем": "находящийся в верхнем",
    "находящийсявопределённых": "находящийся в определённых",
    "помещатьвцентре": "помещать в центре",
    "расположенныйвцентре": "расположенный в центре",
    "проживающийвданной": "проживающий в данной",
    "привестиксознанию": "привести к сознанию",
    "освещениевпечати": "освещение в печати",
    "занятиявлаборатории": "занятия в лаборатории",
    "пускатьвобращение": "пускать в обращение",
    "приводитьвчувство": "приводить в чувство",
    "приведениевсоответствие": "приведение в соответствие",
    "средстваксуществованию": "средства к существованию",
    "всемирнаякомпьютернаясеть": "всемирная компьютерная сеть",
    "портативныйкомпьютер": "портативный компьютер",
    "поломкамеханизма": "поломка механизма",
    "единственныйвсвоём": "единственный в своём",
    "передачавчастную": "передача в частную",
    "магазинасцелью": "магазина с целью",
    "фильмавфутах": "фильма в футах",
    "столкновениескаким": "столкновение с каким",
    "слитносчислительным": "слитно с числительным",
    "документовиотчётности": "документов и отчётности",
    "операцийвэвм": "операций в эвм",
    "возвращатьвоборот": "возвращать в оборот",
    "лежащийвоснове": "лежащий в основе",
    "расположенныйвнижнем": "расположенный в нижнем",
    "расположенныйвделовой": "расположенный в деловой",
    "где-нибудьвдругом": "где-нибудь в другом",
    "куда-нибудьвдругое": "куда-нибудь в другое",
    "происходящийвпомещении": "происходящий в помещении",
    "объединениеводно": "объединение в одно",
    "кончатьуниверситетсучёной": "кончать университет с учёной",
    "информационныйбюллетень": "информационный бюллетень",
    "рекламныйпроспект": "рекламный проспект",
    "ссыпатьвмешок": "ссыпать в мешок",
}

UNGLUE_RE = [
    (re.compile(r"([а-яё]{4,})и(костюм\w*|прикладн\w*|укомплект\w*|отчётн\w*)", re.I), r"\1 и \2"),
    (re.compile(r"(относящийся|не\s*относящийся)к([а-яё]+)", re.I), r"\1 к \2"),
    (re.compile(
        r"(приводить|приведение|привести|выстраивать|заносить|вносить|"
        r"участвовать|ехать|перевозить|помещать|входить|получаться|"
        r"происходить|вводить|находящийся|имеющийся|отпечатываться|"
        r"быть|готовить|пускать|лежащий|расположенный|проживающий|"
        r"возвращать|объединение|увеличивать|приставать|обращённый|"
        r"находиться|состязаться|состязание|располагать|восстановление|"
        r"погружаться|погружённый|сомневаться|предстать|натаскивать)"
        r"(в|к|с|во|ко)([а-яё]{3,})",
        re.I,
    ), r"\1 \2 \3"),
    (re.compile(r"(всемирная)(компьютерная)(сеть)", re.I), r"\1 \2 \3"),
    (re.compile(r"(портативный)(компьютер)", re.I), r"\1 \2"),
    (re.compile(r"(средства)(к)(существованию)", re.I), r"\1 \2 \3"),
    (re.compile(r"(единственный)(в)(своём)", re.I), r"\1 \2 \3"),
    (re.compile(r"(передача)(в)(частную)", re.I), r"\1 \2 \3"),
    (re.compile(r"(поломка)(механизма)", re.I), r"\1 \2"),
    (re.compile(r"ксчастью", re.I), "к счастью"),
    (re.compile(r"ксожалению", re.I), "к сожалению"),
    (re.compile(r"кнесчастью", re.I), "к несчастью"),
    (re.compile(r"декорацииикостюмы", re.I), "декорации и костюмы"),
    (re.compile(r"увеличиватьвобъёме", re.I), "увеличивать в объёме"),
    (re.compile(r"приставатькберегу", re.I), "приставать к берегу"),
    (re.compile(r"обращённыйксеверу", re.I), "обращённый к северу"),
    (re.compile(r"состязатьсявскорости", re.I), "состязаться в скорости"),
    (re.compile(r"состязаниевскорости", re.I), "состязание в скорости"),
    (re.compile(r"располагатьвпорядке", re.I), "располагать в порядке"),
    (re.compile(r"восстановлениевправах", re.I), "восстановление в правах"),
    (re.compile(r"погружатьсявжидкость", re.I), "погружаться в жидкость"),
    (re.compile(r"погружённыйвразмышления", re.I), "погружённый в размышления"),
    (re.compile(r"сомневатьсявистинности", re.I), "сомневаться в истинности"),
    (re.compile(r"предстатьвистинном", re.I), "предстать в истинном"),
    (re.compile(r"смотретьвлицо", re.I), "смотреть в лицо"),
    (re.compile(r"подаватьвсуд", re.I), "подавать в суд"),
    (re.compile(r"звукозаписьивоспроизведение", re.I), "звукозапись и воспроизведение"),
    (re.compile(r"крупноедостижение", re.I), "крупное достижение"),
    (re.compile(r"связанныйсисполнением", re.I), "связанный с исполнением"),
    (re.compile(r"рушитьсястреском", re.I), "рушиться с треском"),
]

STILL_GLUED = re.compile(
    r"(?:"
    r"[а-яё]{4,}и(?:прикладн|научн|техн|социальн|укомплект|отчётн|костюм)|"
    r"(?:приводить|приведение|привести|выстраивать|заносить|вносить|"
    r"участвовать|ехать|перевозить|относящийся|имеющийся|отпечатываться|"
    r"быть|входить|готовить|получаться|происходить|вводить|находящийся|"
    r"помещать|расположенный|пускать|лежащий|проживающий|возвращать|"
    r"объединение|увеличивать|приставать|обращённый|находиться|"
    r"состязаться|состязание|располагать|восстановление|погружаться|"
    r"погружённый|сомневаться|предстать)(?:в|к|с|во|ко)[а-яё]{3,}|"
    r"всемирнаякомп|портативныйкомп|средстваксуществ|"
    r"фильмав|столкновениес|слитнос|магазинас|освещениев|"
    r"поломкамехан|документовиот|информационныйбюлл|"
    r"ксчасть|ксожал|кнесчаст|вкачестведополн|частовсочетани|"
    r"удалениесповерх|человексфилософ|философскимподход"
    r")",
    re.I,
)

META_GLOSS = re.compile(
    r"указывает на|соединительный союз|противительный союз|"
    r"в пространственном значении|во временном значении|"
    r"передаётся приставк",
    re.I,
)
WEAK_PRIMARY = re.compile(
    r"^(?:головня|мычание|воодушевление|величественный|индоссамент|"
    r"дисконтировать|внушать|заклад|всасывать|универсам|лэптоп|"
    r"апгрейд|гейминг|конторка|патефонная пластинка|сатисфакция|"
    r"анафема|руно|мена|дурно|домогаться|уславливаться|хвастать|"
    r"пачкать|тампон|ходячий|незанятый|средством|лапа|крона|клетка|"
    r"противиться|порука|заведённый порядок|животного|головешка)$",
    re.I,
)

# Demote these mains when also contains a preferred modern alternative
DEMOTE_WHEN_ALSO: list[tuple[re.Pattern[str], re.Pattern[str]]] = [
    (re.compile(r"^удачный$", re.I), re.compile(r"счастлив|успешн|удачлив|благоприятн", re.I)),
    (re.compile(r"^окружение$", re.I), re.compile(r"сред[аые]|обстановк", re.I)),
    (re.compile(r"^служебный$", re.I), re.compile(r"официальн", re.I)),
    (re.compile(r"^учебный$", re.I), re.compile(r"академическ", re.I)),
    (re.compile(r"^решать$", re.I), re.compile(r"^выбирать$", re.I)),
    (re.compile(r"^важный$", re.I), re.compile(r"серьёзн|значительн|веск", re.I)),
    (re.compile(r"^пачкать$", re.I), re.compile(r"замеча", re.I)),
    (re.compile(r"^рисовать$", re.I), re.compile(r"описыв|изображ|показ", re.I)),
    (re.compile(r"^прыжок$", re.I), re.compile(r"^весна$", re.I)),
    (re.compile(r"^охота$", re.I), re.compile(r"росток|побег|съёмк", re.I)),
    (re.compile(r"^собрание$", re.I), re.compile(r"явк|посещаем", re.I)),
    (re.compile(r"^шанс$", re.I), re.compile(r"опасност|риск", re.I)),
    (re.compile(r"^случай$", re.I), re.compile(r"шанс|возможност", re.I)),
    (re.compile(r"^заклад$", re.I), re.compile(r"ипотек|залог", re.I)),
    (re.compile(r"^мена$", re.I), re.compile(r"^обмен", re.I)),
    (re.compile(r"^дурно$", re.I), re.compile(r"^плохо$", re.I)),
    (re.compile(r"^незанятый$", re.I), re.compile(r"безработн", re.I)),
    (re.compile(r"^тело$", re.I), re.compile(r"твёрд", re.I)),
    (re.compile(r"^выход$", re.I), re.compile(r"появлен", re.I)),
    (re.compile(r"^противиться$", re.I), re.compile(r"сопротивля|препятств", re.I)),
    (re.compile(r"^излишне подчёркивать$", re.I), re.compile(r"преувелич", re.I)),
    (re.compile(r"^сопротивляющийся$", re.I), re.compile(r"неохотн", re.I)),
]

BOOKISH_MAIN = re.compile(r"(?:ование|ирование|ствование|ификация)$", re.I)

# Archaic / bookish Mueller gloss → modern student gloss (exact phrase)
MODERN_EXACT = {
    "заклад": "залог",
    "универсам": "супермаркет",
    "лэптоп": "ноутбук",
    "апгрейд": "обновление",
    "гейминг": "видеоигры",
    "дисконт": "скидка",
    "учёт векселей": "",
    "патефонная пластинка": "диск",
    "фотографический аппарат": "фотоаппарат",
    "фотографический снимок": "фотография",
    "киноаппарат": "камера",
    "перевозочное средство": "транспорт",
    "радиовещание": "вещание",
    "конторка": "письменный стол",
    "обыкновение": "привычка",
    "обыкновенно": "обычно",
    "обыкновенный": "обычный",
    "необыкновенный": "необычный",
    "необыкновенное явление": "явление",
    "фона": "телефон",
    "подаватьвсуд": "подавать в суд",
    "всасывать": "впитывать",
    "внушать": "подсказывать",
    "битья об заклад": "пари",
    "биться об заклад": "держать пари",
    "приносить официальные извинения": "извиняться",
    "голословное утверждение": "обвинение",
    "письменное удостоверение": "свидетельство",
    "преследовать судебным порядком": "подавать в суд",
    "снабжать силовым двигателем": "питать",
    "совершать путешествие": "путешествовать",
    "имел обыкновение": "бывало",
    "отбирать бенефицию": "",
    "отрешать от должности": "увольнять",
    "последовательность операций в эвм": "",
    "контора адвоката": "кабинет",
    "телеграф": "провод",
    "телеграфная лента": "лента",
    "раскалённое железо": "",
    "головешка": "",
    "передаточная надпись": "",
    "индоссамент": "поддержка",
    "дисконтировать": "снижать цену",
    "сатисфакция": "удовлетворение",
    "анафема": "запрет",
    "домогаться": "стремиться",
    "дурно": "плохо",
    "мена": "обмен",
    "руно": "шерсть",
}

DATED_FRAGMENT = re.compile(
    r"(?:эвм|патефон|граммофон|бенефиц|вексел|индосс|"
    r"раскалённое железо|телеграфн)",
    re.I,
)


def modernize_gloss(s: str) -> str | None:
    """Rewrite dated dictionary glosses; return None to drop."""
    key = s.strip().lower()
    if key in MODERN_EXACT:
        out = MODERN_EXACT[key]
        return out or None
    if DATED_FRAGMENT.search(s):
        return None
    return s


def looks_glued(s: str) -> bool:
    """Detect residual Mueller space-less compounds."""
    if STILL_GLUED.search(s):
        return True
    for tok in re.findall(r"[А-Яа-яЁё]+", s):
        if len(tok) >= 28:
            return True
        if len(tok) >= 16 and re.search(
            r"(?:в|к|с|во|ко)(?:объём|берег|север|поверхн|нерешит|скорост|"
            r"порядок|правах|жидкост|истинн|размышлен|сочетани|дополнен|"
            r"философ|счаст|сожал)",
            tok,
            re.I,
        ):
            return True
    return False


def unglue_muller(s: str) -> str:
    """Insert missing spaces in Mueller glued compounds."""
    out = []
    for tok in re.split(r"(\s+)", s):
        if not tok or tok.isspace():
            out.append(tok)
            continue
        key = tok.lower()
        if key in UNGLUE_EXACT:
            # preserve original casing roughly: use fixed lowercase form
            out.append(UNGLUE_EXACT[key])
            continue
        fixed = tok
        for rx, repl in UNGLUE_RE:
            fixed = rx.sub(repl, fixed)
        out.append(fixed)
    s2 = "".join(out)
    s2 = re.sub(r"\s+", " ", s2).strip()
    return s2


# After cleaning, gloss may contain only Cyrillic letters + light punctuation
RU_ONLY = re.compile(r"^[А-Яа-яЁё]+(?:[\s\-–—/,:;«»\"'()]+[А-Яа-яЁё]+)*\.?$")


def strip_non_russian(s: str) -> str:
    """Remove IPA, English words/letters; keep Cyrillic phrase core."""
    s = re.sub(r"\[[^\]]*\]", " ", s)
    s = re.sub(r"^=\s*", "", s)
    s = re.sub(r"\b[A-Za-z][A-Za-z0-9'./\-]*\b", " ", s)
    s = re.sub(r"[A-Za-z]+", " ", s)
    s = re.sub(r"[↗↑↓ˈˌːəɛɪʊɔɑɒʌθðʃʒŋɾɫɹ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" ;,.—–-:=*•")
    return s


def dedupe_words(s: str) -> str:
    """Collapse repeated tokens/phrases: 'Подросток подросток', 'тонна тонна'."""
    words = s.split()
    if not words:
        return s
    # repeated half-phrase: A B A B
    if len(words) >= 4 and len(words) % 2 == 0:
        half = len(words) // 2
        if [w.casefold() for w in words[:half]] == [
            w.casefold() for w in words[half:]
        ]:
            words = words[:half]
    out: list[str] = []
    for w in words:
        if out and out[-1].casefold() == w.casefold():
            if out[-1] != out[-1].lower() and w == w.lower():
                out[-1] = w
            continue
        out.append(w)
    return " ".join(out)


# Substantivized adjectives that are valid noun glosses
NOUN_OK_ADJ_FORM = {
    "учёный",
    "взрослый",
    "больной",
    "знакомый",
    "рабочий",
    "управляющий",
    "обвиняемый",
    "подсудимый",
    "служащий",
    "заведующий",
    "учащийся",
    "следующий",
    "прочий",
    "первый",
    "второй",
    "третий",
    "пожарный",
    "военнослужащий",
    "безработный",
    "подозреваемый",
    "управляемый",
    "святой",
    "последний",
    "ископаемое",
    "худшее",
}


def looks_like_ru_verb(gloss: str) -> bool:
    w = gloss.strip().lower().split()[-1]
    # abstract nouns / short nouns that look like infinitives
    if re.search(r"(?:ость|есть|исть)$", w):
        return False
    if w.endswith("сть") and w not in {"есть"}:  # шерсть, радость…; есть=to eat
        return False
    if w in {
        "дочь",
        "ночь",
        "речь",
        "ложь",
        "вещь",
        "мечеть",
        "печать",
        "кровать",
        "благодать",
        "мать",
        "нить",
        "сеть",
        "плеть",
        "путь",
        "зять",
        "нефть",
        "четверть",
        "смерть",
        "часть",
        "власть",
        "страсть",
        "кость",
        "гость",
        "ноготь",
        "локоть",
        "коготь",
    }:
        return False
    if re.search(r"[чшщ]еть$", w):  # мечеть
        return False
    return bool(re.search(r"(?:ть|ти|чь|ться|тись|чься)$", w))


def looks_like_ru_adj(gloss: str) -> bool:
    """True for clear adjective forms (not deverbal nouns on -ение/-ость)."""
    w = gloss.strip().lower().split()[-1]
    if w in NOUN_OK_ADJ_FORM:
        return False
    if w in {
        "алюминий",
        "магний",
        "кальций",
        "калий",
        "натрий",
        "гелий",
        "литий",
        "мороженое",
    }:
        return False
    # abstract / deverbal nouns
    if re.search(
        r"(?:ение|ание|яние|тие|ствие|ость|есть|исть|изм|ция|сия|ство|"
        r"тель|ник|щик|чик|арь|ец)$",
        w,
    ):
        return False
    # relational adjective endings
    return bool(
        re.search(
            r"(?:ный|ной|ная|ное|ные|"
            r"шний|тний|дний|жний|енний|янний|ешний|"
            r"ский|ская|ское|ские|цкий|цкая|"
            r"овый|евый|ичный|альный|ивный|ческий|онный|"
            r"атый|истый|ящий|ущий|енный|ённый|анный|янный)$",
            w,
        )
    )


def looks_like_ru_adv(gloss: str) -> bool:
    w = gloss.strip().lower().split()[-1]
    if looks_like_ru_verb(w) or looks_like_ru_adj(w):
        # -о/-е adverbs from adj: быстро, хорошо — adj check may true for some
        if re.search(r"(?:о|е|ски|ьи)$", w) and not re.search(
            r"(?:ный|ский|ая|ое|ые|ие|ый|ий|ой)$", w
        ):
            return True
        if re.search(r"(?:о|е)$", w) and len(w) >= 4:
            return True
    return bool(re.search(r"(?:о|е|ски)$", w)) and not looks_like_ru_verb(w)


def gloss_fits_pos(gloss: str, pos: str) -> bool:
    """Keep glosses whose Russian form matches the English POS."""
    if not gloss or not pos:
        return True
    p = pos.lower().strip()
    words = gloss.split()
    # multi-word: usually phrases OK (говорить по телефону, база данных)
    if len(words) >= 2:
        if "noun" in p:
            # need at least one noun-like token (not pure adj/verb/adv)
            def nounish(tok: str) -> bool:
                t = tok.lower()
                if t in NOUN_OK_ADJ_FORM:
                    return True
                if looks_like_ru_verb(t) or looks_like_ru_adj(t):
                    return False
                if re.fullmatch(r"(?:очень|чисто|весьма|наиболее|менее|более)", t):
                    return False
                return True

            return any(nounish(w) for w in words)
        return True

    if p.startswith("verb") or "modal verb" in p:
        if looks_like_ru_adj(gloss) and not looks_like_ru_verb(gloss):
            return False
        return True

    if p.startswith("adjective"):
        if looks_like_ru_verb(gloss):
            return False
        return True

    if p.startswith("adverb"):
        if looks_like_ru_verb(gloss):
            return False
        if looks_like_ru_adj(gloss) and not re.search(r"(?:о|е|ски)$", gloss.lower()):
            return False
        return True

    # nouns / numbers / exclamations / articles / pronouns / determiners / prepositions…
    if "noun" in p:
        if looks_like_ru_verb(gloss):
            return False
        if looks_like_ru_adj(gloss):
            return False
        return True

    return True


def filter_by_pos(glosses: list[str], pos: str) -> list[str]:
    return [g for g in glosses if gloss_fits_pos(g, pos)]


def clean_one(raw: str) -> str | None:
    s = (raw or "").strip()
    s = s.strip(" ;,.—–-\"'«»•*")
    s = fix_muller_spacing(s)
    s = unglue_muller(s)
    s = re.sub(r"\s+", " ", s).strip(" ;,.—–-")
    s = re.sub(r"\s+\([^)]*$", "", s).strip()
    s = re.sub(r"\s*\([^)]*\)\s*", " ", s).strip()
    s = strip_non_russian(s)
    s = unglue_muller(s)
    s = re.sub(r"\s+", " ", s).strip(" ;,.—–-:")
    s = dedupe_words(s)
    modern = modernize_gloss(s)
    if modern is None:
        return None
    s = dedupe_words(modern)
    if not s or len(s) < 2 or len(s) > 48:
        return None
    if JUNK_START.search(s) or JUNK_CONTAINS.search(s):
        return None
    if looks_glued(s):
        return None
    if META_GLOSS.search(s):
        return None
    if s.lower() in {
        "тот",
        "эта",
        "этот",
        "это",
        "то",
        "он",
        "она",
        "они",
        "мы",
        "вы",
        "я",
        "и",
        "а",
        "но",
    }:
        return None
    if not RU_ONLY.match(s):
        return None
    if len(s.split()) > 5 and len(s) > 36:
        return None
    if s.endswith("-") or s.endswith("("):
        return None
    return s


def gloss_rank(s: str) -> tuple:
    """Lower tuple = better student primary gloss."""
    words = s.split()
    n = len(words)
    chars = len(s)
    glued = 1 if looks_glued(s) else 0
    meta = 1 if META_GLOSS.search(s) else 0
    weak = 0
    if WEAK_PRIMARY.match(s):
        weak += 3
    if BOOKISH_MAIN.search(s):
        weak += 1
    # prefer 1–2 words, short natural
    length_pen = 0
    if n == 1 and 3 <= chars <= 16:
        length_pen = 0
    elif n <= 2 and chars <= 24:
        length_pen = 1
    elif n == 3 and chars <= 32:
        length_pen = 2
    else:
        length_pen = 4
    if chars > 28:
        length_pen += 1
    return (glued, meta, weak, length_pen, n, chars, s.lower())


def promote_better_also(main: str, also: list[str]) -> tuple[str, list[str]]:
    """If also has a clearly better student gloss, make it main.

    Fixes Mueller's habit of putting archaic/rare sense first.
    """
    if not main or not also:
        return main, also

    # Explicit demote pairs (удачный → счастливый, etc.)
    for dem_re, pref_re in DEMOTE_WHEN_ALSO:
        if dem_re.match(main):
            for alt in also:
                if pref_re.search(alt):
                    rest = [main] + [x for x in also if x.casefold() != alt.casefold()]
                    return alt, rest[:2]

    best = min(also, key=gloss_rank)
    mr, br = gloss_rank(main), gloss_rank(best)
    # Promote only on strict improvement in weak/meta/glued or big length win
    weak_better = br[2] < mr[2]
    form_better = (br[0], br[1]) < (mr[0], mr[1])
    much_shorter = mr[3] >= 2 and br[3] <= 1 and br[2] <= mr[2]
    if form_better or weak_better or much_shorter:
        if br < mr:
            rest = [main] + [x for x in also if x.casefold() != best.casefold()]
            return best, rest[:2]
    return main, also


def promote_by_definition(
    main: str, also: list[str], definition: str
) -> tuple[str, list[str]]:
    """Promote also→main when also matches OALD definition sense and main does not."""
    if not main or not also or not definition:
        return main, also
    for def_re, ru_re in DEF_PROMOTE:
        if not def_re.search(definition):
            continue
        if ru_re.search(main):
            return main, also
        for alt in also:
            if ru_re.search(alt):
                rest = [main] + [x for x in also if x.casefold() != alt.casefold()]
                return alt, rest[:2]
        return main, also
    return main, also


def pick_student(
    glosses: list[str], *, prefer_first: bool = False, pos: str = ""
) -> tuple[str, list[str]]:
    """Pick main + up to 2 also.

    prefer_first=True keeps the first surviving gloss as main unless an
    alternative is clearly better for a student (modern / shorter / not weak).
    """
    cleaned: list[str] = []
    for g in glosses:
        c = clean_one(g)
        if c and c.lower() not in {x.lower() for x in cleaned}:
            cleaned.append(c)
    cleaned = filter_by_pos(cleaned, pos)
    if not cleaned:
        return "", []

    if prefer_first:
        main = cleaned[0]
        also = cleaned[1:3]
        return promote_better_also(main, also)

    cleaned.sort(key=gloss_rank)
    return cleaned[0], cleaned[1:3]


def write_outputs(rows: list[dict]) -> None:
    with CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SCHEMA, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            row = {k: r.get(k) for k in SCHEMA}
            for lk in (
                "ipa_us",
                "ipa_gb",
                "audio_source_us",
                "audio_source_gb",
                "translations",
            ):
                row[lk] = json.dumps(row.get(lk), ensure_ascii=False)
            w.writerow(row)
    clean = [{k: r.get(k) for k in SCHEMA} for r in rows]
    JSON_PATH.write_text(
        json.dumps(clean, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    rows = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    with_main = 0
    emptied = 0
    curated_n = 0
    promoted_n = 0
    def_promoted_n = 0
    lex_promoted_n = 0

    for r in rows:
        pos = (r.get("lexical_category") or "").strip()
        word = (r.get("word_gb") or "").strip()
        definition = r.get("definition") or ""
        key = (word, pos)
        key_l = (key[0].lower(), key[1].lower())

        curated = None
        for w, p, d_re, v in SENSE_BY_DEF:
            if w.lower() != key_l[0]:
                continue
            pos_tokens = {
                t.strip() for t in re.split(r"[\s,]+", key_l[1]) if t.strip()
            }
            cur_tokens = {
                t.strip() for t in re.split(r"[\s,]+", p.lower()) if t.strip()
            }
            if not (cur_tokens & pos_tokens):
                continue
            if re.search(d_re, definition, re.I):
                curated = v
                break

        if curated is None:
            curated = CURATED.get(key) or CURATED.get(key_l)
        # Fuzzy POS: whole-token match only (avoid "verb" ⊂ "adverb", "noun" ⊂ "pronoun")
        if curated is None:
            pos_tokens = {t.strip() for t in re.split(r"[\s,]+", key[1].lower()) if t.strip()}
            for (w, p), v in CURATED.items():
                if w.lower() != key[0].lower() or not p:
                    continue
                cur_tokens = {t.strip() for t in re.split(r"[\s,]+", p.lower()) if t.strip()}
                if cur_tokens & pos_tokens:
                    curated = v
                    break

        used_curated = False
        if curated:
            raw_cur = [str(curated["main"])] + [
                str(x) for x in (curated.get("also") or [])
            ]
            cleaned_cur: list[str] = []
            for g in raw_cur:
                c = clean_one(g)
                if not c:
                    c = strip_non_russian(g)
                    c = unglue_muller(c)
                    c = dedupe_words(re.sub(r"\s+", " ", c).strip())
                    if not c or re.search(r"[A-Za-z]", c) or not RU_ONLY.match(c):
                        c = None
                if (
                    c
                    and gloss_fits_pos(c, pos)
                    and c.lower() not in {x.lower() for x in cleaned_cur}
                ):
                    cleaned_cur.append(c)
            # preserve curated order: first entry is the intended main
            main = cleaned_cur[0] if cleaned_cur else ""
            also = cleaned_cur[1:3]
            curated_n += 1
            used_curated = True
        else:
            raw = (r.get("translations") or {}).get("ru") or []
            if isinstance(raw, dict):
                # already cleaned shape — re-rank so best sense is main
                raw = [raw.get("main", "")] + list(raw.get("also") or [])
            main, also = pick_student(
                [str(x) for x in raw if x], prefer_first=True, pos=pos
            )

        # final guard: no Latin letters; POS match
        def ru_ok(s: str) -> bool:
            return (
                bool(s)
                and not re.search(r"[A-Za-z]", s)
                and bool(RU_ONLY.match(s))
                and gloss_fits_pos(s, pos)
            )

        if main and not ru_ok(main):
            # try promote from also
            also = [x for x in also if ru_ok(x)]
            main = also[0] if also else ""
            also = also[1:3]
        else:
            also = [x for x in also if ru_ok(x) and x.lower() != (main or "").lower()][:2]

        # Prefer modern/common sense from also over archaic Mueller-first main.
        # Never re-rank curated glosses (promote prefers shorter forms and
        # would undo sense fixes like «в прямом эфире» → «живьём»).
        if not used_curated:
            before = main
            main, also = promote_better_also(main, also)
            also = [
                x for x in also if ru_ok(x) and x.lower() != (main or "").lower()
            ][:2]
            if main and before and main.casefold() != before.casefold():
                promoted_n += 1

            # Align main with OALD definition when also carries the matching sense
            before = main
            main, also = promote_by_definition(main, also, definition)
            also = [
                x for x in also if ru_ok(x) and x.lower() != (main or "").lower()
            ][:2]
            if main and before and main.casefold() != before.casefold():
                def_promoted_n += 1

            # Headword lexicon: also→main when also matches primary sense of EN word
            before = main
            main, also = promote_by_lexicon(word, main or "", also, definition)
            also = [
                x for x in also if ru_ok(x) and x.lower() != (main or "").lower()
            ][:2]
            if main and before and main.casefold() != before.casefold():
                lex_promoted_n += 1

        if main:
            r["translations"] = {"ru": {"main": main, "also": also}}
            with_main += 1
        else:
            r["translations"] = {"ru": {"main": "", "also": []}}
            emptied += 1

    write_outputs(rows)

    meta = {}
    if META_PATH.exists():
        meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    meta["schema"] = SCHEMA
    meta["translations"] = {
        "shape": {"ru": {"main": "string", "also": ["string", "..."]}},
        "policy": (
            "student-friendly: 1 primary + ≤2 alternatives; Cyrillic-only; "
            "POS-matched; promote modern also over archaic main; "
            "promote also→main when also matches OALD definition sense; "
            "promote also→main when also matches English headword primary sense"
        ),
        "with_main": with_main,
        "empty_main": emptied,
        "curated": curated_n,
        "promoted_also_to_main": promoted_n,
        "promoted_by_definition": def_promoted_n,
        "promoted_by_lexicon": lex_promoted_n,
        "coverage_pct": round(100 * with_main / max(len(rows), 1), 1),
    }
    if "counts" in meta:
        meta["counts"]["with_translations_ru"] = with_main
        meta["counts"]["entries"] = len(rows)
    META_PATH.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(
        f"entries={len(rows)} with_main={with_main} "
        f"empty={emptied} curated={curated_n} promoted={promoted_n} "
        f"def_promoted={def_promoted_n} lex_promoted={lex_promoted_n} "
        f"({meta['translations']['coverage_pct']}%)"
    )
    for w in ("a", "study", "abandon", "blog", "app", "ability", "run", "browser"):
        for r in rows:
            if r["word_gb"].lower() == w:
                print(f"  {r['word_gb']:12} {r['lexical_category']:20} -> {r['translations']}")
                break


if __name__ == "__main__":
    main()
