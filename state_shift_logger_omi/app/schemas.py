from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TranscriptSegment:
    text: str
    speaker: str | None = None
    speaker_id: int | None = None
    speaker_name: str | None = None
    is_user: bool | None = None
    start: float | None = None
    end: float | None = None


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    return None


def extract_segments(payload: Any) -> list[TranscriptSegment]:
    """Handle several Omi-like payload shapes.

    Supported:
    - [ { text, is_user, ... } ]
    - { segments: [ ... ] }
    - { transcript_segments: [ ... ] }
    - memory-trigger object with transcript_segments
    """
    raw_segments: list[Any]

    if isinstance(payload, list):
        raw_segments = payload
    elif isinstance(payload, dict):
        if isinstance(payload.get("segments"), list):
            raw_segments = payload["segments"]
        elif isinstance(payload.get("transcript_segments"), list):
            raw_segments = payload["transcript_segments"]
        else:
            text = (
                payload.get("text")
                or payload.get("transcript")
                or payload.get("overview")
                or payload.get("structured", {}).get("overview")
                or ""
            )
            raw_segments = [{"text": text, "is_user": True}] if text else []
    else:
        raw_segments = []

    segments: list[TranscriptSegment] = []
    for item in raw_segments:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue

        speaker_id = item.get("speakerId", item.get("speaker_id"))
        try:
            speaker_id = int(speaker_id) if speaker_id is not None else None
        except (ValueError, TypeError):
            speaker_id = None

        start = item.get("start", item.get("start_time"))
        end = item.get("end", item.get("end_time"))
        try:
            start = float(start) if start is not None else None
        except (ValueError, TypeError):
            start = None
        try:
            end = float(end) if end is not None else None
        except (ValueError, TypeError):
            end = None

        segments.append(
            TranscriptSegment(
                text=text,
                speaker=item.get("speaker"),
                speaker_id=speaker_id,
                speaker_name=item.get("speaker_name"),
                is_user=_bool_or_none(item.get("is_user")),
                start=start,
                end=end,
            )
        )

    return segments


def user_text_from_segments(segments: list[TranscriptSegment]) -> str:
    """Prefer user's segments when Omi provides is_user flags; otherwise use all text."""
    has_user_flags = any(seg.is_user is not None for seg in segments)
    if has_user_flags:
        selected = [seg.text for seg in segments if seg.is_user is True]
        if selected:
            return "\n".join(selected)
    return "\n".join(seg.text for seg in segments)
