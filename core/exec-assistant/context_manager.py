"""Context Manager for Exec-Assistant

Manages executive profile, preferences, priorities, relationships, and learned patterns.
This is the "brain" that learns your working style and makes it better over time.
"""

import logging
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime, timedelta

from .models import (
    ExecutiveContext,
    ContextType,
    ContextSource,
)

log = logging.getLogger(__name__)


class ContextManager:
    """
    Learns and maintains executive preferences, working style, strategic priorities,
    and decision frameworks.

    Example usage:
        cm = ContextManager(executive_id="user_uuid", db=supabase_client)

        # Set a preference
        cm.set_preference("working_hours", {"start": "09:00", "end": "18:00"})

        # Get full profile
        profile = cm.get_profile()

        # Learn from feedback
        cm.learn_from_feedback("consolidation_accepted", value=True, strength=0.8)
    """

    def __init__(self, executive_id: UUID, db=None):
        """
        Initialize context manager for an executive.

        Args:
            executive_id: UUID of the executive
            db: Supabase client (injected dependency)
        """
        self.executive_id = executive_id
        self.db = db
        self._cache: Dict[str, ExecutiveContext] = {}
        self._cache_timestamp = None

    def set_preference(
        self,
        key: str,
        value: Dict[str, Any],
        source: ContextSource = ContextSource.MANUAL,
    ) -> ExecutiveContext:
        """
        Set an executive preference.

        Common preferences:
        - "working_hours": {"start": "09:00", "end": "18:00", "timezone": "Australia/Brisbane"}
        - "meeting_preferences": {"max_per_day": 5, "preferred_slots": ["09:30", "14:00"]}
        - "communication_style": {"format": "bullet_points", "brevity": "concise"}

        Args:
            key: Preference key (e.g., "working_hours")
            value: Preference value (structured as dict)
            source: Whether this is manual or learned

        Returns:
            ExecutiveContext object
        """
        if self.db is None:
            log.warning("No database connection; cannot persist preference")
            return None

        context = {
            "context_type": ContextType.PREFERENCE.value,
            "key": key,
            "value": value,
            "source": source.value,
            "updated_at": datetime.now().isoformat(),
        }

        # Upsert to database
        try:
            result = self.db.table("exec_assistant_context").upsert(
                context,
                on_conflict="executive_id,context_type,key"
            ).execute()

            log.info(f"Set preference: {key}")
            self._invalidate_cache()
            return result
        except Exception as e:
            log.error(f"Failed to set preference {key}: {e}")
            return None

    def set_priority(
        self,
        priority_area: str,
        details: Dict[str, Any],
    ) -> ExecutiveContext:
        """
        Set a strategic priority area.

        Example:
            cm.set_priority("health_wellness", {
                "focus": "establish consistent exercise",
                "target": "3x weekly workouts",
                "timeframe": "Q3 2026"
            })

        Args:
            priority_area: Name of the priority (e.g., "health_wellness")
            details: Details about this priority

        Returns:
            ExecutiveContext object
        """
        return self.set_preference(
            f"priority_{priority_area}",
            {"area": priority_area, **details},
            source=ContextSource.MANUAL
        )

    def set_relationship_context(
        self,
        person_name: str,
        context: Dict[str, Any],
    ) -> ExecutiveContext:
        """
        Store context about a key relationship.

        Example:
            cm.set_relationship_context("Sarah Chen", {
                "role": "CFO",
                "communication_preference": "weekly summary",
                "key_topics": ["budget", "headcount"],
                "last_contact": "2026-08-05",
                "follow_up_needed": True
            })

        Args:
            person_name: Name of the person
            context: Relationship context details

        Returns:
            ExecutiveContext object
        """
        if self.db is None:
            return None

        full_context = {
            "context_type": ContextType.RELATIONSHIP.value,
            "key": person_name,
            "value": context,
            "source": ContextSource.MANUAL.value,
            "updated_at": datetime.now().isoformat(),
        }

        try:
            result = self.db.table("exec_assistant_context").upsert(
                full_context,
                on_conflict="executive_id,context_type,key"
            ).execute()

            log.info(f"Updated relationship context: {person_name}")
            self._invalidate_cache()
            return result
        except Exception as e:
            log.error(f"Failed to update relationship context for {person_name}: {e}")
            return None

    def set_framework(
        self,
        framework_name: str,
        rules: Dict[str, Any],
    ) -> ExecutiveContext:
        """
        Set a decision framework or SOP.

        Example:
            cm.set_framework("meeting_scheduling", {
                "rule": "All meetings must have clear objective",
                "exception": "1:1s with direct reports",
                "approver": "self"
            })

        Args:
            framework_name: Name of the framework
            rules: Framework rules and details

        Returns:
            ExecutiveContext object
        """
        if self.db is None:
            return None

        full_context = {
            "context_type": ContextType.FRAMEWORK.value,
            "key": framework_name,
            "value": rules,
            "source": ContextSource.MANUAL.value,
            "updated_at": datetime.now().isoformat(),
        }

        try:
            result = self.db.table("exec_assistant_context").upsert(
                full_context,
                on_conflict="executive_id,context_type,key"
            ).execute()

            log.info(f"Set framework: {framework_name}")
            self._invalidate_cache()
            return result
        except Exception as e:
            log.error(f"Failed to set framework {framework_name}: {e}")
            return None

    def learn_from_feedback(
        self,
        pattern_name: str,
        value: bool = True,
        strength: float = 0.7,
        description: str = None
    ) -> ExecutiveContext:
        """
        Learn a pattern from your feedback.

        Example:
            # You approved a meeting consolidation suggestion
            cm.learn_from_feedback(
                "consolidation_accepted",
                value=True,
                strength=0.9,
                description="Back-to-back meetings appreciated"
            )

        Args:
            pattern_name: Name of the pattern (e.g., "consolidation_accepted")
            value: Boolean - is this a positive pattern?
            strength: Confidence in this learning (0-1)
            description: Optional explanation

        Returns:
            ExecutiveContext object
        """
        if self.db is None:
            return None

        pattern_context = {
            "context_type": ContextType.PATTERN.value,
            "key": pattern_name,
            "value": {
                "learned": value,
                "description": description or pattern_name,
            },
            "source": ContextSource.LEARNED.value,
            "confidence": strength,
            "updated_at": datetime.now().isoformat(),
        }

        try:
            result = self.db.table("exec_assistant_context").upsert(
                pattern_context,
                on_conflict="executive_id,context_type,key"
            ).execute()

            log.info(f"Learned pattern: {pattern_name} (strength={strength})")
            self._invalidate_cache()
            return result
        except Exception as e:
            log.error(f"Failed to learn pattern {pattern_name}: {e}")
            return None

    def get_preference(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific preference.

        Args:
            key: Preference key

        Returns:
            Preference value or None if not found
        """
        if self.db is None:
            return None

        try:
            result = self.db.table("exec_assistant_context").select("value").where(
                "executive_id", "eq", str(self.executive_id)
            ).where(
                "context_type", "eq", ContextType.PREFERENCE.value
            ).where(
                "key", "eq", key
            ).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]["value"]
            return None
        except Exception as e:
            log.error(f"Failed to get preference {key}: {e}")
            return None

    def get_priorities(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all strategic priorities.

        Returns:
            Dict of all priority areas and their details
        """
        if self.db is None:
            return {}

        try:
            result = self.db.table("exec_assistant_context").select("key,value").where(
                "executive_id", "eq", str(self.executive_id)
            ).where(
                "context_type", "eq", ContextType.PRIORITY.value
            ).execute()

            priorities = {}
            for row in result.data:
                key = row["key"].replace("priority_", "")
                priorities[key] = row["value"]
            return priorities
        except Exception as e:
            log.error(f"Failed to get priorities: {e}")
            return {}

    def get_relationship_context(self, person_name: str) -> Optional[Dict[str, Any]]:
        """
        Get relationship context for a specific person.

        Args:
            person_name: Name of the person

        Returns:
            Relationship context or None
        """
        if self.db is None:
            return None

        try:
            result = self.db.table("exec_assistant_context").select("value").where(
                "executive_id", "eq", str(self.executive_id)
            ).where(
                "context_type", "eq", ContextType.RELATIONSHIP.value
            ).where(
                "key", "eq", person_name
            ).execute()

            if result.data and len(result.data) > 0:
                return result.data[0]["value"]
            return None
        except Exception as e:
            log.error(f"Failed to get relationship context for {person_name}: {e}")
            return None

    def get_profile(self) -> Dict[str, Any]:
        """
        Get complete executive profile (all contexts).

        Returns:
            Complete profile with preferences, priorities, relationships, frameworks
        """
        if self.db is None:
            return {
                "preferences": {},
                "priorities": {},
                "relationships": {},
                "frameworks": {},
                "patterns": {},
            }

        try:
            result = self.db.table("exec_assistant_context").select(
                "context_type,key,value"
            ).where(
                "executive_id", "eq", str(self.executive_id)
            ).execute()

            profile = {
                "preferences": {},
                "priorities": {},
                "relationships": {},
                "frameworks": {},
                "patterns": {},
            }

            for row in result.data:
                context_type = row["context_type"]
                key = row["key"]
                value = row["value"]

                if context_type == ContextType.PREFERENCE.value:
                    profile["preferences"][key] = value
                elif context_type == ContextType.PRIORITY.value:
                    priority_name = key.replace("priority_", "")
                    profile["priorities"][priority_name] = value
                elif context_type == ContextType.RELATIONSHIP.value:
                    profile["relationships"][key] = value
                elif context_type == ContextType.FRAMEWORK.value:
                    profile["frameworks"][key] = value
                elif context_type == ContextType.PATTERN.value:
                    profile["patterns"][key] = value

            return profile
        except Exception as e:
            log.error(f"Failed to get profile: {e}")
            return {}

    def _invalidate_cache(self) -> None:
        """Invalidate cached profile data after updates."""
        self._cache = {}
        self._cache_timestamp = None

    def suggest_profile_improvements(self) -> List[str]:
        """
        Suggest areas where the profile could be enhanced.

        Returns:
            List of suggestions for things to configure
        """
        profile = self.get_profile()
        suggestions = []

        if not profile.get("preferences", {}).get("working_hours"):
            suggestions.append("Set your working hours for better calendar optimization")

        if not profile.get("preferences", {}).get("meeting_preferences"):
            suggestions.append("Configure meeting preferences (max per day, preferred times)")

        if not profile.get("priorities"):
            suggestions.append("Define your strategic priorities for the quarter")

        if not profile.get("relationships"):
            suggestions.append("Add key relationships and their communication preferences")

        if not profile.get("frameworks"):
            suggestions.append("Document your decision frameworks and SOPs")

        return suggestions
