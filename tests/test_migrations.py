import os
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import psycopg
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from vocabulary_bot.schema import MANAGED_TABLES, metadata, oald_entries


TEST_DATABASE_URL = os.environ.get("TEST_OALD_DATABASE_URL", "")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(
    TEST_DATABASE_URL,
    "TEST_OALD_DATABASE_URL is not set",
)
class AlembicIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_name = f"vocab_alembic_{uuid.uuid4().hex}"
        parameters = conninfo_to_dict(TEST_DATABASE_URL)
        admin_parameters = dict(parameters)
        admin_parameters["dbname"] = "postgres"
        self.admin_conninfo = make_conninfo(**admin_parameters)
        with psycopg.connect(self.admin_conninfo, autocommit=True) as connection:
            connection.execute(
                sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(self.database_name)
                )
            )

        url = sa.engine.make_url(TEST_DATABASE_URL)
        self.database_url = url.set(database=self.database_name).render_as_string(
            hide_password=False
        )
        self.sqlalchemy_url = self.database_url.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1,
        )

    def tearDown(self) -> None:
        with psycopg.connect(self.admin_conninfo, autocommit=True) as connection:
            connection.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s
                  AND pid <> pg_backend_pid()
                """,
                (self.database_name,),
            )
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(
                    sql.Identifier(self.database_name)
                )
            )

    def upgrade_head(self) -> None:
        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        with patch.dict(
            os.environ,
            {"OALD_DATABASE_URL": self.database_url},
        ):
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
                        definition_url_oxford=(
                            "https://example.test/migration-test"
                        ),
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
            self.assertEqual(version, "6ba0adddda2c")
        finally:
            engine.dispose()

    def test_upgrade_rejects_partial_legacy_schema(self) -> None:
        engine = sa.create_engine(self.sqlalchemy_url)
        try:
            with engine.begin() as connection:
                connection.execute(
                    sa.text(
                        "CREATE TABLE oald_entries "
                        "(id BIGINT PRIMARY KEY)"
                    )
                )

            with self.assertRaisesRegex(
                RuntimeError,
                "Partially initialized managed schema",
            ):
                self.upgrade_head()
        finally:
            engine.dispose()
