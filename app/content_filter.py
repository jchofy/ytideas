"""Editorial filtering for niche fit and feasibility."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.youtube_api import VideoDetails


@dataclass(frozen=True)
class ContentRules:
    """Content matching rules managed from config files."""

    include_terms: list[str]
    exclude_terms: list[str]
    require_include_match: bool = False


def get_editable_rules_paths(settings: Settings) -> tuple[Path, Path]:
    """Return persistent content-rule paths."""
    return settings.data_dir / "include_terms.txt", settings.data_dir / "exclude_terms.txt"


def ensure_editable_rules_files(settings: Settings) -> tuple[Path, Path]:
    """Create persistent content-rule files from default config if needed."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    include_path, exclude_path = get_editable_rules_paths(settings)
    _ensure_file(include_path, Path("config/include_terms.txt"))
    _ensure_file(exclude_path, Path("config/exclude_terms.txt"))
    return include_path, exclude_path


def load_content_rules(settings: Settings) -> ContentRules:
    """Load content rules from persistent files."""
    include_path, exclude_path = ensure_editable_rules_files(settings)
    return ContentRules(
        include_terms=read_terms(include_path),
        exclude_terms=read_terms(exclude_path),
        require_include_match=settings.require_include_match,
    )


def read_terms(path: Path) -> list[str]:
    """Read non-empty, non-comment terms from a file."""
    if not path.exists():
        return []

    terms: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        term = line.strip().lower()
        if term and not term.startswith("#"):
            terms.append(term)
    return terms


def classify_video(video: VideoDetails, rules: ContentRules) -> tuple[bool, str, float]:
    """Return whether a video should be kept, the reason, and editorial relevance score."""
    searchable_text = build_searchable_text(video)
    matched_excludes = [term for term in rules.exclude_terms if term_matches(term, searchable_text)]
    if matched_excludes:
        return False, f"blocked_terms={', '.join(matched_excludes[:5])}", 0.0

    matched_includes = [term for term in rules.include_terms if term_matches(term, searchable_text)]
    if rules.require_include_match and not matched_includes:
        return False, "no_include_term_match", 0.0

    if not rules.include_terms:
        return True, "no_include_terms_configured", 1.0

    relevance_score = min(1.0, len(matched_includes) / 3)
    return True, "matched_include_terms" if matched_includes else "neutral", relevance_score


def build_searchable_text(video: VideoDetails) -> str:
    """Build lowercased searchable text for rule matching."""
    return f"{video.title} {video.description} {video.tags} {video.channel_title}".lower()


def term_matches(term: str, searchable_text: str) -> bool:
    """Match a term as a full word/phrase when possible."""
    escaped_term = re.escape(term)
    if re.fullmatch(r"[\w\s]+", term):
        return re.search(rf"(?<!\w){escaped_term}(?!\w)", searchable_text) is not None
    return term in searchable_text


def _ensure_file(destination: Path, default_source: Path) -> None:
    if destination.exists():
        return
    if default_source.exists():
        destination.write_text(default_source.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        destination.write_text("", encoding="utf-8")
