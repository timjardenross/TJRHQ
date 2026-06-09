"""
MSN-0055B-1: Working Memory MVP

Operational context layer for storing transient mission-critical state.
Provides in-memory caching with Supabase as source of truth.

Features:
- Key-value storage with expiry support
- In-memory LRU cache with automatic refresh
- Context-aware retrieval (type + id)
- Safe fallback behavior for failures
- Minimal CRUD operations
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from functools import lru_cache
import threading
import time

try:
    from supabase import create_client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

log = logging.getLogger(__name__)


class WorkingMemoryCache:
    """In-memory LRU cache for working memory entries."""

    def __init__(self, max_size: int = 256, ttl_seconds: int = 3600):
        """
        Initialize cache.

        Args:
            max_size: Maximum number of entries in cache
            ttl_seconds: How long to keep entries before refresh from DB
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._timestamps: Dict[str, float] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get entry from cache if exists and not expired."""
        with self._lock:
            if key not in self._cache:
                return None

            # Check if cached entry is still fresh
            age = time.time() - self._timestamps[key]
            if age > self.ttl_seconds:
                del self._cache[key]
                del self._timestamps[key]
                return None

            return self._cache[key]

    def set(self, key: str, value: Dict[str, Any]) -> None:
        """Set entry in cache, evicting oldest if needed."""
        with self._lock:
            # Simple eviction: remove oldest entry if at capacity
            if len(self._cache) >= self.max_size and key not in self._cache:
                oldest_key = min(self._timestamps.keys(), key=lambda k: self._timestamps[k])
                del self._cache[oldest_key]
                del self._timestamps[oldest_key]

            self._cache[key] = value
            self._timestamps[key] = time.time()

    def delete(self, key: str) -> None:
        """Remove entry from cache."""
        with self._lock:
            self._cache.pop(key, None)
            self._timestamps.pop(key, None)

    def clear(self) -> None:
        """Clear entire cache."""
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()


class WorkingMemory:
    """
    Operational working memory service.

    Provides transient key-value storage with:
    - Automatic expiry
    - In-memory caching
    - Supabase persistence
    - Context awareness
    """

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
        cache_size: int = 256,
        cache_ttl: int = 3600,
    ):
        """
        Initialize working memory.

        Args:
            supabase_url: Supabase project URL (defaults to env var)
            supabase_key: Supabase service role key (defaults to env var)
            cache_size: Max entries in in-memory cache
            cache_ttl: Seconds before cache entries refresh from DB
        """
        self.supabase_url = supabase_url or os.getenv("SUPABASE_URL")
        self.supabase_key = supabase_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        self.client = None
        self._initialize_supabase()

        self.cache = WorkingMemoryCache(max_size=cache_size, ttl_seconds=cache_ttl)
        self._lock = threading.Lock()

    def _initialize_supabase(self) -> None:
        """Initialize Supabase client if credentials available."""
        if not SUPABASE_AVAILABLE:
            log.warning("[working-memory] Supabase not available, using memory-only mode")
            return

        if not self.supabase_url or not self.supabase_key:
            log.warning("[working-memory] Supabase credentials not configured")
            return

        try:
            self.client = create_client(self.supabase_url, self.supabase_key)
            log.info("[working-memory] Supabase client initialized")
        except Exception as e:
            log.error("[working-memory] Failed to initialize Supabase: %s", e)

    def set(
        self,
        key: str,
        value: Any,
        context_type: Optional[str] = None,
        context_id: Optional[str] = None,
        priority: int = 0,
        expires_in_seconds: Optional[int] = None,
    ) -> bool:
        """
        Store a value in working memory.

        Args:
            key: Unique identifier
            value: Value to store (will be JSON-serialized if not string)
            context_type: Optional type (e.g., "mission", "decision")
            context_id: Optional ID within context
            priority: Priority level (higher = keep longer on eviction)
            expires_in_seconds: Auto-expiry time (None = no expiry)

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            try:
                # Serialize value if needed
                if isinstance(value, str):
                    value_str = value
                else:
                    value_str = json.dumps(value)

                # Calculate expiry
                expires_at = None
                if expires_in_seconds:
                    expires_at = (datetime.utcnow() + timedelta(seconds=expires_in_seconds)).isoformat()

                # Store in database
                if self.client:
                    try:
                        self.client.table("working_memory").upsert({
                            "key": key,
                            "value": value_str,
                            "context_type": context_type,
                            "context_id": context_id,
                            "priority": priority,
                            "expires_at": expires_at,
                            "updated_at": datetime.utcnow().isoformat(),
                        }).execute()
                        log.debug("[working-memory] Stored key=%s context=%s", key, context_type)
                    except Exception as e:
                        log.warning("[working-memory] Failed to store in DB: %s", e)
                        # Continue to cache anyway (graceful degradation)

                # Store in cache
                self.cache.set(key, {
                    "key": key,
                    "value": value_str,
                    "context_type": context_type,
                    "context_id": context_id,
                    "priority": priority,
                    "expires_at": expires_at,
                })

                return True

            except Exception as e:
                log.error("[working-memory] Error storing key=%s: %s", key, e)
                return False

    def get(self, key: str, parse_json: bool = False) -> Optional[Any]:
        """
        Retrieve value from working memory.

        Args:
            key: Key to retrieve
            parse_json: If True, parse value as JSON

        Returns:
            Value if found and not expired, None otherwise
        """
        with self._lock:
            try:
                # Try cache first
                cached = self.cache.get(key)
                if cached:
                    value = cached["value"]
                    if parse_json:
                        return json.loads(value)
                    return value

                # Fall back to database
                if not self.client:
                    log.debug("[working-memory] No cache hit and no DB client: key=%s", key)
                    return None

                try:
                    result = self.client.table("working_memory").select("*").eq("key", key).execute()

                    if not result.data:
                        log.debug("[working-memory] Key not found: %s", key)
                        return None

                    entry = result.data[0]

                    # Check expiry
                    if entry.get("expires_at"):
                        expires_at = datetime.fromisoformat(entry["expires_at"].replace("Z", "+00:00"))
                        if datetime.utcnow() > expires_at:
                            log.debug("[working-memory] Key expired: %s", key)
                            # Delete expired entry
                            try:
                                self.client.table("working_memory").delete().eq("key", key).execute()
                            except:
                                pass
                            return None

                    # Update access metadata
                    try:
                        self.client.table("working_memory").update({
                            "access_count": (entry.get("access_count") or 0) + 1,
                            "last_accessed_at": datetime.utcnow().isoformat(),
                        }).eq("key", key).execute()
                    except:
                        pass  # Non-critical

                    # Cache the result
                    self.cache.set(key, entry)

                    # Return value
                    value = entry["value"]
                    if parse_json:
                        return json.loads(value)
                    return value

                except Exception as e:
                    log.warning("[working-memory] DB retrieval error: %s", e)
                    return None

            except Exception as e:
                log.error("[working-memory] Error retrieving key=%s: %s", key, e)
                return None

    def delete(self, key: str) -> bool:
        """
        Delete a working memory entry.

        Args:
            key: Key to delete

        Returns:
            True if deleted, False otherwise
        """
        with self._lock:
            try:
                # Delete from cache
                self.cache.delete(key)

                # Delete from database
                if self.client:
                    try:
                        self.client.table("working_memory").delete().eq("key", key).execute()
                        log.debug("[working-memory] Deleted key=%s", key)
                    except Exception as e:
                        log.warning("[working-memory] Failed to delete from DB: %s", e)

                return True

            except Exception as e:
                log.error("[working-memory] Error deleting key=%s: %s", key, e)
                return False

    def get_by_context(
        self,
        context_type: str,
        context_id: str,
    ) -> Dict[str, Any]:
        """
        Retrieve all entries for a context (type + id).

        Args:
            context_type: Type (e.g., "mission")
            context_id: ID within type

        Returns:
            Dict mapping keys to values
        """
        with self._lock:
            try:
                if not self.client:
                    log.debug("[working-memory] No DB client for context retrieval")
                    return {}

                try:
                    result = self.client.table("working_memory").select("*").eq(
                        "context_type", context_type
                    ).eq("context_id", context_id).execute()

                    entries = {}
                    for entry in result.data:
                        # Check expiry
                        if entry.get("expires_at"):
                            expires_at = datetime.fromisoformat(entry["expires_at"].replace("Z", "+00:00"))
                            if datetime.utcnow() > expires_at:
                                continue

                        entries[entry["key"]] = entry["value"]

                    log.debug("[working-memory] Retrieved %d entries for context=%s:%s",
                             len(entries), context_type, context_id)
                    return entries

                except Exception as e:
                    log.warning("[working-memory] Context retrieval error: %s", e)
                    return {}

            except Exception as e:
                log.error("[working-memory] Error retrieving context: %s", e)
                return {}

    def cleanup_expired(self) -> int:
        """
        Delete all expired entries from database.

        Returns:
            Number of entries deleted
        """
        with self._lock:
            try:
                if not self.client:
                    log.debug("[working-memory] No DB client for cleanup")
                    return 0

                try:
                    result = self.client.table("working_memory").delete().lt(
                        "expires_at", datetime.utcnow().isoformat()
                    ).not_.is_("expires_at", "null").execute()

                    count = len(result.data) if result.data else 0
                    log.info("[working-memory] Cleaned up %d expired entries", count)
                    return count

                except Exception as e:
                    log.warning("[working-memory] Cleanup error: %s", e)
                    return 0

            except Exception as e:
                log.error("[working-memory] Error during cleanup: %s", e)
                return 0

    def clear_cache(self) -> None:
        """Clear in-memory cache only (DB persists)."""
        self.cache.clear()
        log.debug("[working-memory] Cache cleared")


# Global singleton instance
_working_memory: Optional[WorkingMemory] = None


def get_working_memory() -> WorkingMemory:
    """Get or create global working memory instance."""
    global _working_memory
    if _working_memory is None:
        _working_memory = WorkingMemory()
    return _working_memory


def init_working_memory(
    supabase_url: Optional[str] = None,
    supabase_key: Optional[str] = None,
) -> WorkingMemory:
    """
    Initialize global working memory instance.

    Args:
        supabase_url: Override Supabase URL
        supabase_key: Override Supabase key

    Returns:
        WorkingMemory instance
    """
    global _working_memory
    _working_memory = WorkingMemory(supabase_url=supabase_url, supabase_key=supabase_key)
    return _working_memory
