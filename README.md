# American English vocabulary dataset builder

The dataset builder joins two sources into one CSV. A separate importer can
store that CSV in PostgreSQL and safely add or refresh words later.

| Output column | Source |
|---|---|
| `word` | CEFR-J + English Wiktionary entry |
| `cefr` | CEFR-J Vocabulary Profile 1.5 |
| `part_of_speech` | CEFR-J, confirmed against Wiktionary |
| `definition` | first suitable Wiktionary sense from Kaikki/Wiktextract |
| `example` | example attached to the chosen Wiktionary sense |
| `phonetic` | Wiktionary IPA; US/General American is preferred |
| `audio_url` | Wiktionary/Wikimedia Commons; US audio is preferred |
| `source_url` | corresponding Wiktionary page for provenance |

`CEFR` is the correct spelling (not `CERF`). CEFR-J may contain finer labels
such as `A1.1`; the script normalizes them to `A1`, `A2`, `B1`, etc.

## Sources and licensing

- CEFR levels: [CEFR-J Vocabulary Profile 1.5](https://github.com/openlanguageprofiles/olp-en-cefrj).
  It is free for research and commercial use when cited; copyright belongs to
  Tono Laboratory at Tokyo University of Foreign Studies.
- Dictionary data: [Kaikki English Wiktionary extraction](https://kaikki.org/dictionary/English/).
  It is machine-readable data extracted with Wiktextract from Wiktionary.
- Audio files are hosted on Wikimedia Commons. Individual files can have their
  own license and attribution requirements, so keep the source URL/filename.

Do not copy definitions and examples from Cambridge, Oxford, or
Merriam-Webster in bulk unless their license explicitly permits your use.

## Build a small CSV

The CSV builder requires Python 3.10+ and no third-party packages.

```powershell
python scripts\build_dataset.py `
  --dictionary source\kaikki\simple-extract.jsonl `
  --cefr auto `
  --levels A1 A2 B1 B2 `
  --pos noun verb adjective adverb `
  --limit 100 `
  --require-example `
  --require-us-audio `
  --output data\american_vocab_100_us.csv
```

`--limit 100` limits output rows. Because one row represents a
`word + part_of_speech` pair, it does not guarantee 100 distinct spellings.

## Run on your Kaikki/Wiktextract dump

You already have the right kind of JSONL if one line looks like the object you
showed, with `word`, `lang_code`, `pos`, `senses`, and `sounds` fields.

```bash
python scripts/build_dataset.py \
  --dictionary /path/to/kaikki.org-dictionary-English.jsonl.gz \
  --cefr auto \
  --words starter_words.txt \
  --limit 50 \
  --require-example \
  --output data/american_vocab_50.csv
```

With `--cefr auto`, the small CEFR-J CSV is downloaded once and cached under
`data/cache/`. The dictionary dump may be either plain `.jsonl` or compressed
`.jsonl.gz`; it is read line by line and never loaded fully into RAM.

Add `--require-us-audio` if every output row must have audio specifically tagged
as US/General American. Without it, the script still prefers American audio but
keeps good rows whose audio is missing or not tagged.

## Scaling up

For a larger dataset, provide a larger word list or omit `--words` entirely:

```bash
python scripts/build_dataset.py \
  --dictionary /path/to/english.jsonl.gz \
  --cefr auto \
  --levels A1 A2 B1 B2 \
  --pos noun verb adjective adverb \
  --limit 5000 \
  --output data/american_vocab_5000.csv
```

The algorithm keeps only the CEFR index, requested words, and best matching
rows in memory. Its memory use therefore depends on the target vocabulary, not
on the multi-gigabyte dictionary dump. Each run still scans the dump once. The
PostgreSQL importer below avoids rebuilding the database when a later CSV adds
or improves words.

## Import a CSV into PostgreSQL

The included Docker Compose service runs PostgreSQL 16 locally. Its default
credentials are intended for local development only:

```text
database: english_vocabulary
user: vocab_app
password: vocab_dev_password
host: 127.0.0.1
port: 5432
```

Install the Python driver and start PostgreSQL from PowerShell:

```powershell
python -m pip install -r requirements.txt
docker compose up -d
```

You can validate the complete CSV without connecting to PostgreSQL:

```powershell
python scripts\import_postgres.py `
  --csv data\american_vocab_100_us.csv `
  --dry-run
```

Import it after the container healthcheck becomes healthy:

```powershell
python scripts\import_postgres.py `
  --csv data\american_vocab_100_us.csv `
  --database-url "postgresql://vocab_app:vocab_dev_password@localhost:5432/english_vocabulary"
```

Instead of putting the URL on the command line, set it once for the current
PowerShell session:

```powershell
$env:DATABASE_URL = "postgresql://vocab_app:vocab_dev_password@localhost:5432/english_vocabulary"
python scripts\import_postgres.py --csv data\american_vocab_100_us.csv
```

The importer creates `vocabulary_entries` and its indexes automatically. One
row is uniquely identified by `(word, part_of_speech)`. Running the importer
again with another CSV inserts new pairs and updates existing pairs. Empty
optional fields in a later CSV never erase an existing example, phonetic value,
or audio URL.

The input is read in batches of 1,000 rows by default. Change this without
loading the full CSV into memory by passing, for example, `--batch-size 5000`.
The whole import is one transaction: a malformed row or database error rolls
back all changes from that run.

## Store the audio files in PostgreSQL

The CSV importer keeps `audio_url` as provenance. A separate downloader fetches
the referenced file and stores it in the same `vocabulary_entries` row as
PostgreSQL `BYTEA` data:

```powershell
python scripts\download_audio.py `
  --database-url "postgresql://vocab_app:vocab_dev_password@localhost:5432/english_vocabulary"
```

For a small test, process only five candidate rows:

```powershell
python scripts\download_audio.py `
  --database-url "postgresql://vocab_app:vocab_dev_password@localhost:5432/english_vocabulary" `
  --limit 5
```

The downloader stores:

- `audio_data`: the file bytes;
- `audio_content_type`: MIME type such as `audio/ogg`;
- `audio_filename`: original filename when it can be determined;
- `audio_size_bytes`: downloaded byte count;
- `audio_sha256`: checksum for integrity and deduplication work later;
- `audio_file_source_url`: the exact URL used for the stored bytes;
- `audio_downloaded_at`: download timestamp.

By default, only missing files and rows whose `audio_url` changed are
processed. Use `--force` to download current files again. Downloads larger than
10 MB are rejected; change the limit with `--max-audio-bytes`. A failed URL is
reported and the downloader continues with the next word; add `--fail-fast` to
stop immediately. Requests are spaced two seconds apart, and temporary HTTP
errors are retried with exponential backoff. If Wikimedia continues returning
HTTP 429, the run stops to respect the rate limit; run the same command later
and it will resume with the still-missing files. Adjust the pacing with
`--request-delay`, `--retries`, and `--retry-backoff`.

Both PostgreSQL scripts write timestamped progress logs to the terminal at
`INFO` level by default. A normal audio run shows each word before download and
the stored filename, size, and MIME type afterward. Use `DEBUG` to also see
request URLs, schema checks, and pacing delays:

```powershell
python scripts\download_audio.py `
  --database-url "postgresql://vocab_app:vocab_dev_password@localhost:5432/english_vocabulary" `
  --log-level DEBUG
```

The CSV importer logs schema initialization and every completed database
batch. Reduce output for automation with `--log-level WARNING` or
`--log-level ERROR`. Database connection URLs and passwords are never written
to logs.

Check stored files from `psql` without printing the binary content itself:

```sql
SELECT word,
       part_of_speech,
       audio_filename,
       audio_content_type,
       octet_length(audio_data) AS stored_bytes,
       audio_downloaded_at
FROM vocabulary_entries
WHERE audio_data IS NOT NULL
ORDER BY word
LIMIT 20;
```

The original `audio_url` and Wiktionary `source_url` remain in the database.
Storing a Commons file does not remove its individual license and attribution
requirements. `BYTEA` is suitable for short pronunciation clips; if the audio
collection grows to many gigabytes, move the bytes to object storage while
keeping the metadata and object key in PostgreSQL.

The Compose volume preserves the database when the container is stopped:

```powershell
docker compose stop
docker compose start
```

## Data quality choices

- One row represents one `word + part_of_speech` pair. `book` as a noun and
  `book` as a verb can therefore have separate rows and CEFR levels.
- The earliest non-obsolete dictionary sense is preferred, with a bonus for a
  usable example.
- US/General American IPA and audio are preferred over untagged or UK variants.
- A blank `example`, `phonetic`, or `audio_url` means the source did not provide
  a suitable value. Use the strict flags to exclude incomplete rows.
- CEFR can vary by meaning. This first version assigns CEFR to `word + POS`;
  sense-level CEFR is a possible later schema upgrade.

## Tests

```bash
python -m unittest discover -s tests -v
```

The PostgreSQL integration test is skipped unless `TEST_DATABASE_URL` points
to a test database. With the included container:

```powershell
$env:TEST_DATABASE_URL = "postgresql://vocab_app:vocab_dev_password@localhost:5432/english_vocabulary"
python -m unittest discover -s tests -v
```

The integration test uses unique temporary words and removes only those rows
when it finishes.

## Import cached Oxford translations into PostgreSQL

`scripts/build_database/import_oxford_cache.py` reads every cached response under
`source/oxford_api/translations_en_ru`, combines Oxford homographs that share a
result ID and lexical category, and upserts the result into
`oxford_lexical_entries`.

Inspect the complete cache without changing PostgreSQL:

```powershell
python scripts\build_database\import_oxford_cache.py --dry-run
```

Import it into the local Compose database:

```powershell
python scripts\build_database\import_oxford_cache.py `
  --database-url "postgresql://vocab_app:vocab_dev_password@localhost:5432/english_vocabulary"
```

The table stores separate US and GB spellings plus PostgreSQL arrays for IPA,
audio source URLs, and all Russian translations. Definitions and examples are
joined from `data/enriched/words.json` by word, part of speech, and phonetic
value. Ambiguous definitions remain empty and are reported in the terminal.

Running the same command again is safe. Existing rows use the stable key
`oxford:<result_id>:<lexical_category>`, unchanged rows are not rewritten, and
new cache files add new rows. The importer never truncates the table and does
not delete rows when a cache file disappears.

Useful options:

```text
--source-dir PATH    alternative Oxford cache directory
--words-json PATH    alternative definition source
--limit-files N      process only the first N JSON files
--batch-size N       PostgreSQL rows per batch
--strict             stop on malformed JSON instead of skipping it
--log-level LEVEL    DEBUG, INFO, WARNING, or ERROR
```

Example query:

```sql
SELECT word_us,
       word_gb,
       lexical_category,
       ipa_us,
       ipa_gb,
       translations
FROM oxford_lexical_entries
WHERE word_us = 'analyze';
```

Search for a Russian translation inside the array:

```sql
SELECT word_us, word_gb, lexical_category, translations
FROM oxford_lexical_entries
WHERE 'алюминий' = ANY(translations);
```

## Import the OALD dataset and store its audio in PostgreSQL

`scripts/build_database/import_oald_postgres.py` validates
`data/oald/words.json`, creates a
separate `english_vocabulary_oald` database when it is missing, and upserts all
OALD entries. It does not modify `english_vocabulary` or its existing tables.

Start PostgreSQL and validate the complete JSON without changing the database:

```powershell
docker compose up -d
python scripts\build_database\import_oald_postgres.py --dry-run --strict
```

Create and populate the OALD database:

```powershell
python scripts\build_database\import_oald_postgres.py `
  --json data\oald\words.json `
  --database-url "postgresql://vocab_app:vocab_dev_password@localhost:5432/english_vocabulary_oald"
```

The Compose `vocab_app` role can create the local database. On a managed
PostgreSQL server, pass a separate administrator connection when the application
role does not have `CREATEDB`:

```powershell
python scripts\build_database\import_oald_postgres.py `
  --json data\oald\words.json `
  --database-url $env:OALD_DATABASE_URL `
  --admin-database-url $env:OALD_ADMIN_DATABASE_URL
```

The import is transactional and safe to repeat. `definition_url_oxford` is the
source identity, so the two `lie` verb entries remain separate. Reimporting
updates source fields and audio links, adds new entries, and keeps already
downloaded audio bytes. The current file produces 5,906 entries, 12,259 audio
references, and 10,393 unique audio URLs.

The database contains:

- `oald_entries`: words, CEFR, definitions, examples, IPA arrays, source URL
  arrays, and Russian translations as `JSONB`;
- `oald_audio_files`: one row and one `BYTEA` payload per unique audio URL;
- `oald_audio_variants`: prepared Telegram voice copies in OGG Opus format;
- `oald_entry_audio_sources`: ordered US/GB links between entries and files.

Set the connection once for the current PowerShell session:

```powershell
$env:OALD_DATABASE_URL = "postgresql://vocab_app:vocab_dev_password@localhost:5432/english_vocabulary_oald"
```

Download and store both US and GB pronunciation files:

```powershell
python scripts\build_database\download_oald_audio.py `
  --database-url $env:OALD_DATABASE_URL `
  --dialects us gb
```

Test only five unique URLs first:

```powershell
python scripts\build_database\download_oald_audio.py `
  --database-url $env:OALD_DATABASE_URL `
  --dialects us gb `
  --limit 5
```

The downloader stores every original file and immediately prepares a mono OGG
Opus copy for Telegram voice messages. On the first run after this feature was
added, already downloaded originals are converted locally without another HTTP
request. Every result is committed independently, so rerunning the same command
continues from the remaining URLs. Identical URLs are downloaded and converted
only once. `--force` refreshes the original and rebuilds its voice copy. The
default 0.5-second delay applies only between real HTTP requests, not local
conversions. HTTP 429 stops the run immediately; rerun it later to continue.

Check download progress without printing binary data:

```sql
SELECT download_status,
       count(*) AS files,
       pg_size_pretty(sum(coalesce(size_bytes, 0))::bigint) AS stored_size
FROM oald_audio_files
GROUP BY download_status
ORDER BY download_status;
```

Check Telegram voice preparation progress:

```sql
SELECT conversion_status,
       count(*) AS files,
       pg_size_pretty(sum(coalesce(size_bytes, 0))::bigint) AS stored_size
FROM oald_audio_variants
WHERE variant_type = 'telegram_voice_opus'
GROUP BY conversion_status
ORDER BY conversion_status;
```

Retrieve American audio bytes for a bot:

```sql
SELECT e.word_us,
       e.lexical_category,
       e.ipa_us,
       voice.content_type,
       voice.filename,
       voice.audio_data
FROM oald_entries AS e
JOIN oald_entry_audio_sources AS links
  ON links.entry_id = e.id
JOIN oald_audio_files AS f
  ON f.source_url = links.source_url
JOIN oald_audio_variants AS voice
  ON voice.source_url = f.source_url
 AND voice.variant_type = 'telegram_voice_opus'
 AND voice.conversion_status = 'prepared'
 AND voice.source_sha256 = f.sha256
WHERE lower(e.word_us) = lower('color')
  AND links.dialect = 'us'
  AND voice.audio_data IS NOT NULL
ORDER BY links.source_position;
```

In Python, `psycopg` returns `audio_data` as a bytes-like value suitable for a
Telegram voice response. Keep the source URL and review OALD's terms before
redistributing the downloaded files; the dataset does not contain license
metadata.

OALD integration tests are enabled only for an explicitly selected test
database:

```powershell
$env:TEST_OALD_DATABASE_URL = "postgresql://vocab_app:vocab_dev_password@localhost:5432/english_vocabulary_oald"
python -m unittest discover -s tests -p "test_*oald*.py" -v
```

## Telegram vocabulary bot

The `vocabulary_bot` package sends every active user three unseen cards per day.
Users select one or more CEFR levels and US, GB, or both pronunciations during
onboarding. PostgreSQL stores user settings, scheduled runs, Telegram file IDs,
and a permanent no-repeat history.

### Start from the bundled PostgreSQL seed

The repository contains a compressed PostgreSQL seed split into two GitHub-safe
files under
`data/backups/english_vocabulary_oald_seed_2026-08-01.dump.parts/`. On the first
start of a fresh Docker volume, Compose automatically reassembles and verifies
the dump, then restores all 5,906 OALD entries, original audio, and prepared OGG
Opus voice variants. No `words.json` import or audio download is required.

The published seed intentionally contains no `bot_users`, delivery history,
scheduler history, or Telegram `file_id` cache data. A cloned bot therefore
starts with an empty and private user history.

```powershell
git clone <repository-url>
cd english_vocabulary_bot
Copy-Item .env.example .env

# Put TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_IDS into .env, then:
docker compose up -d
docker compose logs -f postgres
```

Wait for `OALD seed restore completed`, press `Ctrl+C` to leave the log view,
then start the application:

```powershell
python -m pip install -r requirements.txt
python -m vocabulary_bot
```

The automatic restore runs only when PostgreSQL initializes an empty Docker
volume. It never overwrites an existing database volume. The unsplit local
`*.dump` file is ignored by Git because it exceeds GitHub's 100 MB per-file
limit; the two tracked parts are 75 MB and about 65 MB.

Install the dependencies and copy the environment template:

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Create a bot with `@BotFather`, then edit `.env`:

```text
TELEGRAM_BOT_TOKEN=123456:replace_with_the_real_token
TELEGRAM_ADMIN_IDS=
OALD_DATABASE_URL=postgresql://vocab_app:vocab_dev_password@localhost:5432/english_vocabulary_oald
BOT_TIMEZONE=Europe/Moscow
BOT_SEND_TIMES=09:00,14:00,20:00
BOT_CARD_TEMPLATE_PATH=config/card_template.html
BOT_CARD_TEMPLATE_BOTH_PATH=config/card_template_both.html
```

Start the bot with long polling:

```powershell
python -m vocabulary_bot
```

Send `/start` to the bot. To find your numeric Telegram ID for admin access,
query the newly registered user:

```sql
SELECT telegram_user_id, username, first_name
FROM bot_users
ORDER BY created_at;
```

Put that number into `TELEGRAM_ADMIN_IDS` and restart the bot. Several admins
are comma-separated. Every administrator command checks this list; other users
receive `Нет доступа.`. The main `/admin` dashboard summarizes active, paused,
and blocked users, today's scheduled delivery, send-ready content, and persisted
technical errors. It is an inline panel: section buttons edit the existing
message instead of sending a new statistics message. `Back` returns to the
overview and `Refresh` queries PostgreSQL again. Test-card and preview buttons
necessarily send separate card text and voice messages, while leaving the panel
in place.

The panel contains Overview, Users, Deliveries, Content, Audio, Errors,
Test card, and System sections. Parameterized and potentially destructive
operations remain explicit commands so that an accidental button press cannot
disable content or start a real retry batch.

Administrator commands:

```text
/admin                         operational dashboard
/users                         users, registrations, levels, dialects
/user TELEGRAM_ID              one user's settings and delivery history
/delivery [today|7d]           scheduler and delivery statistics
/delivery_failed               recent failed deliveries
/content                       content completeness and send readiness
/missing_fields                missing IPA/definition/example/translation
/missing_audio                 entries without prepared Telegram voice audio
/word WORD                     find all matching lexical entries
/word_id ID                    inspect one lexical entry
/preview_word ID [us|gb|both]  send the real card only to the administrator
/send_test                     send a random real card only to the administrator
/errors                        persisted delivery and scheduler errors for 24h
/health                        PostgreSQL, scheduler, and Telegram API checks
/disable_word ID               exclude an entry from future selection
/enable_word ID                return an entry to future selection
/retry_failed                  show how many deliveries can be retried
/retry_failed confirm          retry up to 50 failed deliveries
/reload_templates              validate and reload both card templates
```

On startup the bot adds non-destructive schema fields needed by this dashboard.
Existing rows are preserved. A user is counted as blocked only after Telegram
returns a forbidden/blocking error to this version of the bot; older inactive
rows cannot be classified retroactively and are treated as paused. Delivery and
scheduler failures are persisted, but ordinary log lines outside those flows are
not a complete application-error monitoring system.

User commands:

```text
/start           register and configure the bot
/settings        show and change all settings
/levels          select one or more CEFR levels
/pronunciation   select US, GB, or both audio variants
/card            request one unseen card immediately
/pause           pause scheduled delivery
/resume          resume scheduled delivery
/help            show help
```

Single-dialect messages use `config/card_template.html`; the US+GB option uses
`config/card_template_both.html`. The bot reloads both files after they change,
without needing a restart. Available placeholders:

```text
{word}
{word_upper}
{word_us}
{word_us_upper}
{word_gb}
{word_gb_upper}
{lexical_category}
{cefr}
{definition}
{ipa}
{ipa_us}
{ipa_gb}
{example}
{translation}
{dialect}
{dialect_flag}
```

The `_upper` fields contain uppercase spelling. `{dialect_flag}` renders the US
flag, GB flag, or both flags. A template must contain at least one word field
and either `{ipa}` or both `{ipa_us}` and `{ipa_gb}`.

When `both` is selected, a card is eligible only if prepared US and GB voice
files both exist. Card text is sent as its own message, followed by separate
`🇺🇸 US` and `🇬🇧 GB` voice messages. Single-dialect cards follow the same layout
with one labeled voice message. Each Telegram `file_id` is cached independently.

All values are HTML-escaped before formatting. The templates themselves may use
Telegram-supported HTML tags.

The scheduler uses `BOT_TIMEZONE` and exactly three unique `BOT_SEND_TIMES`.
`BOT_SCHEDULE_GRACE_MINUTES` controls how long a missed slot may be recovered
after a restart. Database constraints guarantee at most one card per user and
slot, and `(telegram_user_id, entry_id)` guarantees that a word entry is never
sent to the same user twice.

Only cards whose selected US/GB audio has a prepared OGG Opus voice copy are
eligible. Download and prepare the remaining pronunciation files before
inviting users:

```powershell
python scripts\build_database\download_oald_audio.py `
  --database-url "postgresql://vocab_app:vocab_dev_password@localhost:5432/english_vocabulary_oald" `
  --dialects us gb
```

OALD originals are preserved unchanged. The downloader converts each source to
OGG Opus once, and the bot sends that copy with `sendVoice`, so Telegram shows
its native voice-message player and waveform. Telegram `file_id` values are
cached after the first upload, avoiding repeated BYTEA uploads for other users.

Run bot unit tests:

```powershell
python -m unittest discover -s tests -p "test_bot_core.py" -v
```

Run the PostgreSQL no-repeat and scheduler integration tests:

```powershell
$env:TEST_OALD_DATABASE_URL = "postgresql://vocab_app:vocab_dev_password@localhost:5432/english_vocabulary_oald"
python -m unittest discover -s tests -p "test_bot_database.py" -v
```
