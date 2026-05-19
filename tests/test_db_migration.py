"""Tests for idempotent DB migration: display_name column on audio_clips."""

import os
import tempfile

import pytest


@pytest.mark.asyncio
async def test_display_name_column_created_on_fresh_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        from core.db import init_db

        conn = await init_db(db_path)
        async with conn.execute("PRAGMA table_info(audio_clips)") as cur:
            cols = [row[1] async for row in cur]
        assert "display_name" in cols
        await conn.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_display_name_migration_idempotent():
    """init_db() called twice must not fail."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        from core.db import init_db

        conn = await init_db(db_path)
        await conn.close()
        conn2 = await init_db(db_path)  # second call — must be idempotent
        async with conn2.execute("PRAGMA table_info(audio_clips)") as cur:
            cols = [row[1] async for row in cur]
        assert "display_name" in cols
        await conn2.close()
    finally:
        os.unlink(db_path)
