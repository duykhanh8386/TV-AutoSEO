"""Post-scan session validation for reloaded channels."""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from src.module.base import validate_channel_session_token
from src.task_runtime import TaskStopped


@dataclass(frozen=True)
class ChannelSessionValidation:
    channel_id: str
    channel_name: str
    successful: bool
    error_type: str = ""


def validate_reloaded_channel_session(
    channel_id: str, channel_name: str = ""
) -> ChannelSessionValidation:
    """Validate a reloaded channel's real session token."""
    clean_channel_id = str(channel_id or "").strip()
    clean_channel_name = str(channel_name or "").strip()
    try:
        validate_channel_session_token(clean_channel_id)
    except TaskStopped:
        raise
    except Exception as exc:
        logger.error(
            "Channel session validation failed after reload: "
            "channel={} name={!r} error_type={}",
            clean_channel_id,
            clean_channel_name,
            type(exc).__name__,
        )
        return ChannelSessionValidation(
            channel_id=clean_channel_id,
            channel_name=clean_channel_name,
            successful=False,
            error_type=type(exc).__name__,
        )
    return ChannelSessionValidation(
        channel_id=clean_channel_id,
        channel_name=clean_channel_name,
        successful=True,
    )
