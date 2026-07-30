#!/usr/bin/env python3
"""
MSN-0013C: Event-Driven Context Loading
Owner: Chief Engineer / Coder Agent
Date: 2026-06-08
Purpose: Listen for events (Slack messages, GitHub PRs, Notion updates) and surface relevant context
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Callable
from datetime import datetime
from abc import ABC, abstractmethod
import json


@dataclass
class Event:
    """Base event class."""
    source: str  # 'slack', 'github', 'notion'
    event_type: str  # 'message_posted', 'pr_opened', 'page_updated'
    event_id: str
    timestamp: datetime
    actor: str  # User/account that triggered event
    payload: dict  # Event-specific data


@dataclass
class ContextSurface:
    """Context surfaced by event."""
    event: Event
    relevant_documents: List[dict]  # [{'id': '...', 'relevance': 0.85}, ...]
    recommendations: List[str]
    action_items: List[str]
    summary: str


class EventListener(ABC):
    """Abstract base class for event listeners."""

    def __init__(self, name: str):
        self.name = name
        self.handlers: List[Callable] = []

    @abstractmethod
    def listen(self):
        """Start listening for events."""
        pass

    @abstractmethod
    def handle_event(self, event: Event) -> Optional[ContextSurface]:
        """Handle incoming event and surface context."""
        pass

    def register_handler(self, handler: Callable):
        """Register callback handler for events."""
        self.handlers.append(handler)

    def notify_handlers(self, event: Event, context: ContextSurface):
        """Notify all registered handlers."""
        for handler in self.handlers:
            try:
                handler(event, context)
            except Exception as e:
                print(f"❌ Handler error: {e}")


class SlackEventListener(EventListener):
    """Listen for Slack messages and surface context."""

    def __init__(self, semantic_retriever=None):
        super().__init__("SlackEventListener")
        self.retriever = semantic_retriever

    def listen(self):
        """Start listening for Slack events."""
        print(f"🎧 {self.name} started. Listening for Slack messages...")

    def handle_event(self, event: Event) -> Optional[ContextSurface]:
        """Handle Slack message and surface relevant context."""
        if event.source != "slack" or event.event_type != "message_posted":
            return None

        message_text = event.payload.get("text", "")
        print(f"\n📨 Slack message from {event.actor}: {message_text[:80]}...")

        # Use semantic retriever to find relevant docs
        if not self.retriever:
            return None

        # Mock retrieval (in production, uses real semantic search)
        relevant_docs = [
            {'id': 'adr_001', 'relevance': 0.92, 'title': 'Kubernetes Migration Decision'},
            {'id': 'dec_015', 'relevance': 0.87, 'title': 'Defer Kafka upgrade to Q4'}
        ]

        context = ContextSurface(
            event=event,
            relevant_documents=relevant_docs,
            recommendations=[
                "See ADR-001 for context on infrastructure decisions",
                "Note: Kafka upgrade deferred to Q4 per DEC-015"
            ],
            action_items=["Tag @Chief-Engineer for infrastructure questions"],
            summary=f"Relevant to infrastructure planning. 2 related decisions found."
        )

        return context


class GitHubEventListener(EventListener):
    """Listen for GitHub PR/issue events."""

    def __init__(self, semantic_retriever=None):
        super().__init__("GitHubEventListener")
        self.retriever = semantic_retriever

    def listen(self):
        """Start listening for GitHub events."""
        print(f"🎧 {self.name} started. Listening for GitHub PRs and issues...")

    def handle_event(self, event: Event) -> Optional[ContextSurface]:
        """Handle GitHub event and surface context."""
        if event.source != "github" or event.event_type not in ["pr_opened", "issue_opened"]:
            return None

        title = event.payload.get("title", "")
        print(f"\n📝 GitHub {event.event_type} by {event.actor}: {title[:80]}...")

        # Surface relevant context
        relevant_docs = [
            {'id': 'arch_design', 'relevance': 0.88, 'title': 'Architecture Design Guidelines'},
        ]

        context = ContextSurface(
            event=event,
            relevant_documents=relevant_docs,
            recommendations=[
                "Ensure code review includes architecture compliance check",
                "Link to related ADR-003 if introducing new services"
            ],
            action_items=["Assign reviewer from @architecture-team"],
            summary="Code change detected. Architecture guidelines recommended."
        )

        return context


class NotionEventListener(EventListener):
    """Listen for Notion page updates."""

    def __init__(self, semantic_retriever=None):
        super().__init__("NotionEventListener")
        self.retriever = semantic_retriever

    def listen(self):
        """Start listening for Notion events."""
        print(f"🎧 {self.name} started. Listening for Notion page updates...")

    def handle_event(self, event: Event) -> Optional[ContextSurface]:
        """Handle Notion event and surface context."""
        if event.source != "notion" or event.event_type != "page_updated":
            return None

        page_title = event.payload.get("page_title", "")
        print(f"\n📄 Notion page updated by {event.actor}: {page_title[:80]}...")

        # Surface relevant context
        context = ContextSurface(
            event=event,
            relevant_documents=[],
            recommendations=[
                "Check if this relates to any open decisions",
                "Update decision tracker if applicable"
            ],
            action_items=[],
            summary="Knowledge update detected. Cross-check with decision log."
        )

        return context


class EventDispatcher:
    """Coordinate multiple event listeners."""

    def __init__(self):
        self.listeners: List[EventListener] = []

    def register_listener(self, listener: EventListener):
        """Register event listener."""
        self.listeners.append(listener)
        listener.listen()

    def dispatch_event(self, event: Event) -> List[ContextSurface]:
        """Dispatch event to all listeners and collect context."""
        surfaces = []

        for listener in self.listeners:
            context = listener.handle_event(event)
            if context:
                surfaces.append(context)
                print(f"   ✅ {listener.name} surfaced {len(context.relevant_documents)} documents")

        return surfaces


if __name__ == "__main__":
    # Example usage
    dispatcher = EventDispatcher()
    dispatcher.register_listener(SlackEventListener())
    dispatcher.register_listener(GitHubEventListener())
    dispatcher.register_listener(NotionEventListener())

    # Simulate events
    slack_event = Event(
        source="slack",
        event_type="message_posted",
        event_id="evt_001",
        timestamp=datetime.now(),
        actor="captain-tjr",
        payload={"text": "Should we defer the Kafka migration?"}
    )

    surfaces = dispatcher.dispatch_event(slack_event)
    print(f"\n{'='*70}")
    print(f"Context surfaced for {len(surfaces)} listener(s)")
    for surface in surfaces:
        print(f"  - {len(surface.relevant_documents)} documents")
        for rec in surface.recommendations[:2]:
            print(f"    💡 {rec}")
