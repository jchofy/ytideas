"""Keyword batching and rotation to protect YouTube API quota."""

from __future__ import annotations

from pathlib import Path


def select_keyword_batch(
    keywords: list[str],
    batch_size: int,
    cursor_path: Path,
) -> list[str]:
    """Select a rotating keyword batch and advance the cursor."""
    if not keywords:
        return []

    effective_batch_size = max(1, min(batch_size, len(keywords)))
    cursor = _read_cursor(cursor_path) % len(keywords)
    selected_keywords = [
        keywords[(cursor + offset) % len(keywords)]
        for offset in range(effective_batch_size)
    ]
    next_cursor = (cursor + effective_batch_size) % len(keywords)
    cursor_path.parent.mkdir(parents=True, exist_ok=True)
    cursor_path.write_text(str(next_cursor), encoding="utf-8")
    return selected_keywords


def _read_cursor(cursor_path: Path) -> int:
    if not cursor_path.exists():
        return 0
    try:
        return int(cursor_path.read_text(encoding="utf-8").strip() or "0")
    except ValueError:
        return 0
