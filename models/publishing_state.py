# models/publishing_state.py
"""
Publishing State Machine Model
States: queued → processing → ready → posted / failed
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


class PublishingState(str, Enum):
    """Publishing state machine states"""

    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    POSTED = "posted"
    FAILED = "failed"


@dataclass
class PublishingEntry:
    """
    Publishing entry with state machine tracking.

    Fields:
        queue_id: Queue entry ID
        url: Product URL
        state: Current state (queued → processing → ready → posted/failed)
        message_id: Telegram message ID (if posted)
        chat_id: Telegram chat ID (channel/chat)
        text: Message text/caption
        scheduled_time: Scheduled publication time
        created_at: Entry creation timestamp
        updated_at: Last update timestamp
        error: Error message (if failed)
    """

    queue_id: int
    url: str
    state: PublishingState
    message_id: Optional[int] = None
    chat_id: Optional[int] = None
    text: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    error: Optional[str] = None

    def __post_init__(self):
        """Initialize timestamps if not set."""
        now = datetime.utcnow()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        data = asdict(self)
        # Convert enums and datetimes to strings
        data["state"] = self.state.value
        for key in ["scheduled_time", "created_at", "updated_at"]:
            if data.get(key):
                data[key] = (
                    data[key].isoformat()
                    if isinstance(data[key], datetime)
                    else data[key]
                )
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PublishingEntry":
        """Create from dictionary."""
        # Convert strings to enums and datetimes
        if isinstance(data.get("state"), str):
            data["state"] = PublishingState(data["state"])
        for key in ["scheduled_time", "created_at", "updated_at"]:
            if isinstance(data.get(key), str):
                try:
                    data[key] = datetime.fromisoformat(data[key])
                except (ValueError, TypeError):
                    data[key] = None
        return cls(**data)

    def can_transition_to(self, new_state: PublishingState) -> bool:
        """
        Check if transition to new state is valid.

        Valid transitions:
        - queued → processing
        - processing → ready
        - processing → failed
        - ready → posted
        - ready → failed
        """
        transitions = {
            PublishingState.QUEUED: [PublishingState.PROCESSING],
            PublishingState.PROCESSING: [PublishingState.READY, PublishingState.FAILED],
            PublishingState.READY: [PublishingState.POSTED, PublishingState.FAILED],
            PublishingState.POSTED: [],  # Terminal state
            PublishingState.FAILED: [],  # Terminal state
        }
        return new_state in transitions.get(self.state, [])

    def transition_to(
        self, new_state: PublishingState, error: Optional[str] = None
    ) -> bool:
        """
        Transition to new state if valid.

        Returns:
            True if transition successful, False otherwise
        """
        if not self.can_transition_to(new_state):
            logger.warning(
                f"Invalid state transition: {self.state.value} → {new_state.value} "
                f"for queue_id={self.queue_id}"
            )
            return False

        self.state = new_state
        self.updated_at = datetime.utcnow()
        if error:
            self.error = error

        logger.debug(
            f"State transition: queue_id={self.queue_id} "
            f"{self.state.value} → {new_state.value}"
        )
        return True
