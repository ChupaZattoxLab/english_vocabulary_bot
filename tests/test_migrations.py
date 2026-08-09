import os
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy.engine import make_url

from tests.support import TEST_OALD_DATABASE_URL, requires_oald_database
from tgbot.db.sync import sync_connection
from tgbot.db.tables import MANAGED_TABLES, metadata, oald_entries

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@requires_oald_database
class AlembicIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_name = f"vocab_alembic_{uuid.uuid4().hex}"
        base_url = make_url(TEST_OALD_DATABASE_URL)
        self.admin_url = base_url.set(database="postgres").render_as_string(
            hide_password=False
        )
        self.db_url = base_url.set(database=self.db_name).render_as_string(
            hide_password=False
        )
        self.sqlalchemy_url = self.db_url

        with sync_connection(self.admin_url, autocommit=True) as connection:
            raw = connection.connection.driver_connection
            assert raw is not None
            with raw.cursor() as cursor:
                cursor.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(self.db_name))
                )

    def tearDown(self) -> None:
        with sync_connection(self.admin_url, autocommit=True) as connection:
            raw = connection.connection.driver_connection
            assert raw is not None
            with raw.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = %s
                      AND pid <> pg_backend_pid()
                    """,
                    (self.db_name,),
                )
                cursor.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {}").format(
                        sql.Identifier(self.db_name)
                    )
                )

    def upgrade_head(self) -> None:
        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        with patch.dict(
            os.environ,
            {"OALD_DATABASE_URL": self.db_url},
        ):
            import tgbot.secrets as app_secrets

            app_secrets.secrets = app_secrets.Secrets.load()
            command.upgrade(config, "head")

    def test_upgrade_creates_schema_from_scratch(self) -> None:
        self.upgrade_head()

        engine = sa.create_engine(self.sqlalchemy_url)
        try:
            inspector = sa.inspect(engine)
            self.assertEqual(
                set(inspector.get_table_names()),
                set(MANAGED_TABLES) | {"alembic_version"},
            )
            self.assertNotIn(
                "bot_users_telegram_user_id_seq",
                inspector.get_sequence_names(),
            )
        finally:
            engine.dispose()

    def test_upgrade_adopts_complete_legacy_schema_without_data_loss(
        self,
    ) -> None:
        engine = sa.create_engine(self.sqlalchemy_url)
        try:
            metadata.create_all(engine)
            with engine.begin() as connection:
                connection.execute(
                    oald_entries.insert().values(
                        word_us="migration-test",
                        word_gb="migration-test",
                        lexical_category="noun",
                        cefr="a1",
                        definition_url_oxford=("https://example.test/migration-test"),
                        definition="A migration test entry.",
                        example="This row must survive migration.",
                    )
                )

            self.upgrade_head()

            with engine.connect() as connection:
                count = connection.scalar(
                    sa.select(sa.func.count()).select_from(oald_entries)
                )
                version = connection.scalar(
                    sa.text("SELECT version_num FROM alembic_version")
                )
            self.assertEqual(count, 1)
            self.assertEqual(version, "d8e9f0a1b2c3")
        finally:
            engine.dispose()

    def test_upgrade_rejects_partial_legacy_schema(self) -> None:
        engine = sa.create_engine(self.sqlalchemy_url)
        try:
            with engine.begin() as connection:
                connection.execute(
                    sa.text("CREATE TABLE oald_entries (id BIGINT PRIMARY KEY)")
                )

            with self.assertRaisesRegex(
                RuntimeError,
                "Partially initialized managed schema",
            ):
                self.upgrade_head()
        finally:
            engine.dispose()
