from __future__ import annotations

import pytest

from bot.storage.db import init_db


@pytest.fixture
def db_path(tmp_path) -> str:
    path = str(tmp_path / "test.db")
    init_db(path)
    return path
