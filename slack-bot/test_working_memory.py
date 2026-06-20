"""
Tests for MSN-0055B-1: Working Memory MVP
"""

import pytest
import json
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from lib.working_memory import (
    WorkingMemory,
    WorkingMemoryCache,
    get_working_memory,
    init_working_memory,
)


class TestWorkingMemoryCache:
    """Tests for in-memory cache layer."""

    def test_cache_basic_operations(self):
        """Test set/get/delete on cache."""
        cache = WorkingMemoryCache(max_size=10, ttl_seconds=60)

        # Set
        cache.set("key1", {"value": "data1"})
        assert cache.get("key1") == {"value": "data1"}

        # Delete
        cache.delete("key1")
        assert cache.get("key1") is None

    def test_cache_expiry(self):
        """Test cache TTL expiry."""
        cache = WorkingMemoryCache(max_size=10, ttl_seconds=1)

        cache.set("key1", {"value": "data1"})
        assert cache.get("key1") is not None

        # Wait for expiry
        time.sleep(1.1)
        assert cache.get("key1") is None

    def test_cache_max_size(self):
        """Test cache eviction on max size."""
        cache = WorkingMemoryCache(max_size=3, ttl_seconds=3600)

        # Fill to capacity
        cache.set("key1", {"value": "data1"})
        time.sleep(0.01)
        cache.set("key2", {"value": "data2"})
        time.sleep(0.01)
        cache.set("key3", {"value": "data3"})

        # Should evict oldest (key1)
        cache.set("key4", {"value": "data4"})
        assert cache.get("key1") is None
        assert cache.get("key2") is not None
        assert cache.get("key3") is not None
        assert cache.get("key4") is not None


class TestWorkingMemory:
    """Tests for working memory service."""

    @pytest.fixture
    def memory(self):
        """Create working memory instance without Supabase.

        WorkingMemory falls back to env vars when url/key are None, so we must
        patch the env vars to empty strings to guarantee memory-only mode.
        """
        with patch.dict("os.environ", {"SUPABASE_URL": "", "SUPABASE_SERVICE_ROLE_KEY": ""}):
            wm = WorkingMemory(
                supabase_url="",
                supabase_key="",
                cache_size=10,
                cache_ttl=3600,
            )
        return wm

    def test_set_and_get_string(self, memory):
        """Test storing and retrieving string values."""
        assert memory.set("key1", "value1")
        assert memory.get("key1") == "value1"

    def test_set_and_get_json(self, memory):
        """Test storing and retrieving JSON values."""
        data = {"mission": "MSN-0055B-1", "status": "active"}
        assert memory.set("config", data)
        retrieved = memory.get("config", parse_json=True)
        assert retrieved == data

    def test_delete(self, memory):
        """Test deletion."""
        memory.set("key1", "value1")
        assert memory.get("key1") == "value1"
        assert memory.delete("key1")
        assert memory.get("key1") is None

    def test_expiry(self):
        """Test automatic expiry via cache TTL (no DB required).

        expires_at metadata is only enforced on DB fetch; without a DB client,
        expiry must be tested via the in-memory cache TTL instead.
        """
        with patch.dict("os.environ", {"SUPABASE_URL": "", "SUPABASE_SERVICE_ROLE_KEY": ""}):
            short_ttl_memory = WorkingMemory(supabase_url="", supabase_key="", cache_size=10, cache_ttl=1)
        short_ttl_memory.set("key1", "value1")
        assert short_ttl_memory.get("key1") == "value1"

        time.sleep(1.1)
        assert short_ttl_memory.get("key1") is None

    def test_context_aware_storage(self, memory):
        """Test context type and ID storage."""
        memory.set(
            "mission_state",
            "active",
            context_type="mission",
            context_id="MSN-0055B-1",
        )
        assert memory.get("mission_state") == "active"

    def test_priority_storage(self, memory):
        """Test priority parameter."""
        assert memory.set("key1", "value1", priority=5)
        # Priority doesn't affect retrieval, just storage
        assert memory.get("key1") == "value1"

    def test_get_nonexistent_key(self, memory):
        """Test retrieving non-existent key returns None."""
        assert memory.get("nonexistent") is None

    def test_get_by_context_no_db(self, memory):
        """Test get_by_context without Supabase."""
        # Without Supabase, should return empty dict
        result = memory.get_by_context("mission", "MSN-0055B-1")
        assert result == {}

    def test_cleanup_expired_no_db(self, memory):
        """Test cleanup without Supabase."""
        # Without Supabase, should return 0
        count = memory.cleanup_expired()
        assert count == 0

    def test_clear_cache(self, memory):
        """Test clearing cache."""
        memory.set("key1", "value1")
        memory.set("key2", "value2")
        memory.clear_cache()
        # Both should now be None (from in-memory cache perspective)
        assert memory.cache.get("key1") is None
        assert memory.cache.get("key2") is None


class TestWorkingMemoryWithSupabase:
    """Tests with mocked Supabase client."""

    @pytest.fixture
    def mock_supabase(self):
        """Create mocked Supabase client."""
        mock = MagicMock()
        return mock

    @pytest.fixture
    def memory_with_db(self, mock_supabase):
        """Create working memory with mocked Supabase."""
        with patch("lib.working_memory.create_client") as mock_create:
            mock_create.return_value = mock_supabase
            memory = WorkingMemory(
                supabase_url="https://test.supabase.co",
                supabase_key="test-key",
            )
            memory.client = mock_supabase
            return memory

    def test_set_to_database(self, memory_with_db, mock_supabase):
        """Test storing to database."""
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table
        mock_table.upsert.return_value.execute.return_value = None

        assert memory_with_db.set("key1", "value1")

        # Verify Supabase was called
        mock_supabase.table.assert_called_with("working_memory")
        mock_table.upsert.assert_called_once()
        mock_table.upsert.return_value.execute.assert_called_once()

    def test_get_from_database(self, memory_with_db, mock_supabase):
        """Test retrieving from database."""
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table

        # Mock response
        mock_result = MagicMock()
        mock_result.data = [{
            "key": "key1",
            "value": "value1",
            "expires_at": None,
            "access_count": 0,
        }]
        mock_table.select.return_value.eq.return_value.execute.return_value = mock_result
        mock_table.update.return_value.eq.return_value.execute.return_value = None

        # First call should hit database
        result = memory_with_db.get("key1")
        assert result == "value1"

        # Verify Supabase was called
        mock_supabase.table.assert_called()

    def test_expiry_in_database(self, memory_with_db, mock_supabase):
        """Test that expired entries are not returned from database."""
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table

        # Mock expired response
        past_time = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        mock_result = MagicMock()
        mock_result.data = [{
            "key": "expired",
            "value": "old_value",
            "expires_at": past_time,
            "access_count": 0,
        }]
        mock_table.select.return_value.eq.return_value.execute.return_value = mock_result
        mock_table.delete.return_value.eq.return_value.execute.return_value = None

        # Should return None for expired entry
        result = memory_with_db.get("expired")
        assert result is None

    def test_get_by_context_from_database(self, memory_with_db, mock_supabase):
        """Test get_by_context with database."""
        mock_table = MagicMock()
        mock_supabase.table.return_value = mock_table

        # Mock response
        mock_result = MagicMock()
        mock_result.data = [
            {"key": "key1", "value": "value1", "expires_at": None},
            {"key": "key2", "value": "value2", "expires_at": None},
        ]
        mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_result

        result = memory_with_db.get_by_context("mission", "MSN-0055B-1")

        assert len(result) == 2
        assert result["key1"] == "value1"
        assert result["key2"] == "value2"


class TestGlobalSingleton:
    """Tests for global singleton pattern."""

    def test_get_working_memory_singleton(self):
        """Test get_working_memory returns same instance."""
        mem1 = get_working_memory()
        mem2 = get_working_memory()
        assert mem1 is mem2

    def test_init_working_memory_replaces_singleton(self):
        """Test init_working_memory replaces global instance."""
        # Reset global
        import lib.working_memory
        lib.working_memory._working_memory = None

        mem1 = init_working_memory()
        mem2 = init_working_memory()

        # Should be different instances (both created fresh)
        assert mem1 is not mem2


class TestIntegration:
    """Integration tests."""

    def test_cache_and_memory_consistency(self):
        """Test cache and memory stay consistent."""
        memory = WorkingMemory(supabase_url=None, supabase_key=None)

        # Store value
        memory.set("key1", "value1", expires_in_seconds=3600)

        # First get (from cache)
        result1 = memory.get("key1")
        assert result1 == "value1"

        # Second get (from cache)
        result2 = memory.get("key1")
        assert result2 == "value1"

    def test_json_serialization(self):
        """Test JSON serialization works correctly."""
        memory = WorkingMemory(supabase_url=None, supabase_key=None)

        complex_data = {
            "mission": {
                "id": "MSN-0055B-1",
                "status": "active",
                "tasks": ["task1", "task2"],
            }
        }

        memory.set("complex", complex_data)
        retrieved = memory.get("complex", parse_json=True)

        assert retrieved == complex_data
        assert retrieved["mission"]["id"] == "MSN-0055B-1"

    def test_multiple_keys_isolation(self):
        """Test multiple keys don't interfere."""
        memory = WorkingMemory(supabase_url=None, supabase_key=None)

        memory.set("key1", "value1")
        memory.set("key2", "value2")
        memory.set("key3", "value3")

        assert memory.get("key1") == "value1"
        assert memory.get("key2") == "value2"
        assert memory.get("key3") == "value3"

        memory.delete("key2")

        assert memory.get("key1") == "value1"
        assert memory.get("key2") is None
        assert memory.get("key3") == "value3"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
