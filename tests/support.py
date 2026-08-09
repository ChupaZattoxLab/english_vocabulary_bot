import os
import unittest

TEST_OALD_DATABASE_URL = os.environ.get("TEST_OALD_DATABASE_URL", "")

requires_oald_database = unittest.skipUnless(
    TEST_OALD_DATABASE_URL,
    "TEST_OALD_DATABASE_URL is not set",
)
