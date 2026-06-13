"""
Slack Integration for Number One Review Gate (Phase 1.2)
Handles Slack message parsing, interactive actions, and workflow triggers.
Uses non-blocking error handling (failures don't block mission state changes).
Includes canonical ID resolution for consistent mission identification (P2b).

DEPRECATED DUPLICATE / TRANSITIONAL:
Retain only while Slack review flows still depend on this adapter. New work
should prefer the canonical Number One integration path.
"""

import json
import asyncio
from typing import Dict, Any, Optional, Callable
from datetime import datetime
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from core.dashboard.canonical_id_resolver import CanonicalIDResolver


class SlackNumberOneHandler:
    """
    Manages Slack integration for Number One review workflows.

    Handles:
    - Closure submission notifications
    - Approval/rejection via Slack buttons
    - Checklist validation display
    - Non-blocking Slack failures
    """

    def __init__(
        self,
        slack_token: str,
        slack_signing_secret: str,
        app_token: str,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None
    ):
        """
        Initialize Slack handler.

        Args:
            slack_token: Bot token for Slack API
            slack_signing_secret: Signing secret for request verification
            app_token: Socket Mode app token for real-time events
            supabase_url: Supabase project URL (for canonical ID resolution)
            supabase_key: Supabase API key (for canonical ID resolution)
        """
        self.app = App(token=slack_token, signing_secret=slack_signing_secret)
        self.app_token = app_token
        self.handler = None

        # Initialize canonical ID resolver if Supabase credentials provided
        self.id_resolver = None
        if supabase_url and supabase_key:
            self.id_resolver = CanonicalIDResolver(supabase_url, supabase_key)

        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register all Slack event and action handlers."""

        # Handle closure approval button
        self.app.action("approve_closure")(self._handle_approve_action)

        # Handle closure rejection button
        self.app.action("reject_closure")(self._handle_reject_action)

        # Handle checklist checkbox interactions
        self.app.action("toggle_checklist")(self._handle_checklist_action)

        # Handle modal submission (rejection reason)
        self.app.view("rejection_reason_modal")(self._handle_rejection_modal)

    async def _handle_approve_action(self, ack: Callable, body: Dict[str, Any]) -> None:
        """
        Handle approval button click in Slack.

        Expected payload:
        {
            'actions': [{'value': 'mission_id'}],
            'user': {'username': 'reviewer'}
        }
        """
        ack()

        try:
            mission_id = body.get('actions', [{}])[0].get('value')
            reviewer = body.get('user', {}).get('username', 'unknown')

            # Emit approval event (non-blocking)
            await self._emit_approval_event(mission_id, reviewer)

        except Exception as e:
            # Non-blocking: Log but don't raise
            print(f"[WARN] Failed to process approval action: {e}")

    async def _handle_reject_action(self, ack: Callable, body: Dict[str, Any]) -> None:
        """
        Handle rejection button click in Slack.
        Opens modal for rejection reason input.

        Expected payload:
        {
            'actions': [{'value': 'mission_id'}],
            'user': {'username': 'reviewer'},
            'trigger_id': 'slack_trigger_id'
        }
        """
        ack()

        try:
            mission_id = body.get('actions', [{}])[0].get('value')
            trigger_id = body.get('trigger_id')

            # Open modal for rejection reason
            self.app.client.views_open(
                trigger_id=trigger_id,
                view={
                    'type': 'modal',
                    'callback_id': 'rejection_reason_modal',
                    'title': {'type': 'plain_text', 'text': 'Rejection Reason'},
                    'blocks': [
                        {
                            'type': 'section',
                            'text': {'type': 'mrkdwn', 'text': f'*Mission:* {mission_id}'},
                        },
                        {
                            'type': 'input',
                            'block_id': 'reason_block',
                            'label': {'type': 'plain_text', 'text': 'Rejection Reason'},
                            'element': {
                                'type': 'plain_text_input',
                                'action_id': 'reason_input',
                                'multiline': True,
                                'placeholder': {'type': 'plain_text', 'text': 'Describe what failed...'}
                            }
                        },
                        {
                            'type': 'input',
                            'block_id': 'defects_block',
                            'label': {'type': 'plain_text', 'text': 'Failed Checks'},
                            'element': {
                                'type': 'plain_text_input',
                                'action_id': 'defects_input',
                                'multiline': True,
                                'placeholder': {'type': 'plain_text', 'text': 'List failed checklist items (one per line)...'}
                            }
                        }
                    ],
                    'private_metadata': mission_id,
                    'submit': {'type': 'plain_text', 'text': 'Reject'}
                }
            )

        except Exception as e:
            # Non-blocking: Log but don't raise
            print(f"[WARN] Failed to process rejection action: {e}")

    async def _handle_rejection_modal(self, ack: Callable, body: Dict[str, Any]) -> None:
        """
        Handle rejection reason modal submission.

        Expected payload:
        {
            'view': {
                'private_metadata': 'mission_id',
                'state': {
                    'values': {
                        'reason_block': {'reason_input': {'value': 'reason text'}},
                        'defects_block': {'defects_input': {'value': 'defect list'}}
                    }
                }
            },
            'user': {'username': 'reviewer'}
        }
        """
        ack()

        try:
            view = body.get('view', {})
            mission_id = view.get('private_metadata')
            reviewer = body.get('user', {}).get('username', 'unknown')

            values = view.get('state', {}).get('values', {})
            reason = values.get('reason_block', {}).get('reason_input', {}).get('value', '')
            defects_text = values.get('defects_block', {}).get('defects_input', {}).get('value', '')

            # Parse defects (one per line)
            failed_checks = [line.strip() for line in defects_text.split('\n') if line.strip()]

            # Emit rejection event (non-blocking)
            await self._emit_rejection_event(mission_id, reviewer, reason, failed_checks)

        except Exception as e:
            # Non-blocking: Log but don't raise
            print(f"[WARN] Failed to process rejection modal: {e}")

    async def _handle_checklist_action(self, ack: Callable, body: Dict[str, Any]) -> None:
        """
        Handle checklist item toggle (not fully implemented in Phase 1.2 MVP).
        Phase 1.2 uses basic checklist validation server-side.
        """
        ack()
        # Checklist validation handled server-side by NumberOneReviewGate.validate_checklist()

    def _resolve_mission_id(self, mission_id: str) -> str:
        """
        Resolve mission ID to canonical format for Slack messages.
        Uses CanonicalIDResolver to normalize M-05 → MSN-0005, etc.

        Args:
            mission_id: Either legacy or canonical ID

        Returns:
            Canonical ID, or original if resolver unavailable
        """
        if self.id_resolver:
            try:
                return self.id_resolver.get_canonical_id(mission_id)
            except Exception as e:
                print(f"[WARN] Failed to resolve canonical ID for {mission_id}: {e}")
        return mission_id

    async def _emit_approval_event(self, mission_id: str, reviewer: str) -> None:
        """
        Emit approval event for downstream handlers.
        Non-blocking: failures logged but not raised.
        """
        try:
            event = {
                'type': 'number_one_approval',
                'mission_id': mission_id,
                'reviewed_by': reviewer,
                'timestamp': datetime.utcnow().isoformat()
            }
            # TODO: Emit to event bus / webhook
            print(f"[INFO] Approval event: {event}")
        except Exception as e:
            print(f"[WARN] Failed to emit approval event: {e}")

    async def _emit_rejection_event(
        self,
        mission_id: str,
        reviewer: str,
        reason: str,
        failed_checks: list
    ) -> None:
        """
        Emit rejection event for downstream handlers.
        Non-blocking: failures logged but not raised.
        """
        try:
            event = {
                'type': 'number_one_rejection',
                'mission_id': mission_id,
                'reviewed_by': reviewer,
                'rejection_reason': reason,
                'failed_checks': failed_checks,
                'timestamp': datetime.utcnow().isoformat()
            }
            # TODO: Emit to event bus / webhook
            print(f"[INFO] Rejection event: {event}")
        except Exception as e:
            print(f"[WARN] Failed to emit rejection event: {e}")

    def send_submission_notification(
        self,
        mission_id: str,
        submitted_by: str,
        expected_behaviour: str,
        validation_result: str,
        evidence_count: int,
        review_due_at: str
    ) -> bool:
        """
        Send submission notification to Slack.
        Non-blocking: returns True/False rather than raising.
        Uses canonical ID (MSN-XXXX) in notification.

        Returns:
            True if sent successfully, False if failed
        """
        try:
            # Resolve to canonical ID for consistent messaging
            canonical_id = self._resolve_mission_id(mission_id)

            blocks = [
                {
                    'type': 'header',
                    'text': {'type': 'plain_text', 'text': ':memo: Closure Review Waiting'}
                },
                {
                    'type': 'section',
                    'fields': [
                        {'type': 'mrkdwn', 'text': f'*Mission:*\n{canonical_id}'},
                        {'type': 'mrkdwn', 'text': f'*Submitted by:*\n{submitted_by}'},
                        {'type': 'mrkdwn', 'text': f'*Validation Result:*\n{validation_result}'},
                        {'type': 'mrkdwn', 'text': f'*Evidence Links:*\n{evidence_count}'},
                    ]
                },
                {
                    'type': 'section',
                    'text': {'type': 'mrkdwn', 'text': f'*Expected Behaviour:*\n{expected_behaviour}'}
                },
                {
                    'type': 'divider'
                },
                {
                    'type': 'section',
                    'text': {'type': 'mrkdwn', 'text': f':hourglass: Review due: {review_due_at}'}
                },
                {
                    'type': 'actions',
                    'elements': [
                        {
                            'type': 'button',
                            'text': {'type': 'plain_text', 'text': 'Review & Approve'},
                            'value': mission_id,
                            'action_id': 'approve_closure',
                            'style': 'primary'
                        },
                        {
                            'type': 'button',
                            'text': {'type': 'plain_text', 'text': 'Reject'},
                            'value': mission_id,
                            'action_id': 'reject_closure',
                            'style': 'danger'
                        }
                    ]
                }
            ]

            self.app.client.chat_postMessage(
                channel='#number-one-reviews',
                blocks=blocks,
                text=f'Closure review for {canonical_id}'
            )
            return True

        except Exception as e:
            print(f"[WARN] Failed to send Slack notification: {e}")
            return False

    def send_approval_notification(
        self,
        mission_id: str,
        reviewed_by: str,
        notes: str
    ) -> bool:
        """
        Send approval notification to XO.
        Non-blocking: returns True/False rather than raising.

        Returns:
            True if sent successfully, False if failed
        """
        try:
            blocks = [
                {
                    'type': 'header',
                    'text': {'type': 'plain_text', 'text': ':white_check_mark: Closure Approved'}
                },
                {
                    'type': 'section',
                    'fields': [
                        {'type': 'mrkdwn', 'text': f'*Mission:*\n{mission_id}'},
                        {'type': 'mrkdwn', 'text': f'*Approved by:*\n{reviewed_by}'},
                    ]
                },
                {
                    'type': 'section',
                    'text': {'type': 'mrkdwn', 'text': f'*Notes:*\n{notes}'}
                },
                {
                    'type': 'section',
                    'text': {'type': 'mrkdwn', 'text': ':point_right: Ready for XO final approval'}
                }
            ]

            self.app.client.chat_postMessage(
                channel='#xo-approvals',
                blocks=blocks,
                text=f'Closure approved for {mission_id}'
            )
            return True

        except Exception as e:
            print(f"[WARN] Failed to send Slack notification: {e}")
            return False

    def send_rejection_notification(
        self,
        mission_id: str,
        reviewed_by: str,
        rejection_reason: str,
        failed_checks: list
    ) -> bool:
        """
        Send rejection notification to builder.
        Non-blocking: returns True/False rather than raising.

        Returns:
            True if sent successfully, False if failed
        """
        try:
            failed_items = '\n'.join([f'• {item}' for item in failed_checks])

            blocks = [
                {
                    'type': 'header',
                    'text': {'type': 'plain_text', 'text': ':x: Closure Rejected'}
                },
                {
                    'type': 'section',
                    'fields': [
                        {'type': 'mrkdwn', 'text': f'*Mission:*\n{mission_id}'},
                        {'type': 'mrkdwn', 'text': f'*Rejected by:*\n{reviewed_by}'},
                    ]
                },
                {
                    'type': 'section',
                    'text': {'type': 'mrkdwn', 'text': f'*Failed Checks:*\n{failed_items}'}
                },
                {
                    'type': 'section',
                    'text': {'type': 'mrkdwn', 'text': f'*Reason:*\n{rejection_reason}'}
                },
                {
                    'type': 'section',
                    'text': {'type': 'mrkdwn', 'text': ':point_right: Fix defects, re-test, and resubmit closure'}
                }
            ]

            self.app.client.chat_postMessage(
                channel='#mission-closures',
                blocks=blocks,
                text=f'Closure rejected for {mission_id}'
            )
            return True

        except Exception as e:
            print(f"[WARN] Failed to send Slack notification: {e}")
            return False

    def start(self) -> None:
        """Start Slack Socket Mode handler (blocking)."""
        if not self.handler:
            self.handler = SocketModeHandler(self.app, self.app_token)
        self.handler.start()

    def stop(self) -> None:
        """Stop Slack Socket Mode handler."""
        if self.handler:
            self.handler.close()
