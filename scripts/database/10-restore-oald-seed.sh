#!/bin/sh
set -eu

parts_directory=/database-seed
dump_path=/tmp/english_vocabulary_oald_seed.dump
expected_sha256=253e5244a3dbcc81a002eb3f07a7644106a46ee13faa2b31768bf51d96f3cde0

set -- "$parts_directory"/english_vocabulary_oald_seed_2026-08-01.dump.part-*
if [ ! -e "$1" ]; then
    echo "OALD seed parts are missing; skipping automatic restore"
    exit 0
fi

echo "Reassembling the OALD PostgreSQL seed dump"
cat "$@" > "$dump_path"
echo "$expected_sha256  $dump_path" | sha256sum -c -

echo "Restoring OALD entries and audio into $POSTGRES_DB"
pg_restore \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --no-owner \
    --no-privileges \
    --exit-on-error \
    "$dump_path"

rm -f "$dump_path"
echo "OALD seed restore completed"
