"""Application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    youtube_api_key: str
    data_dir: Path
    database_path: Path
    keywords_path: Path
    region_code: str = "US"
    relevance_language: str = "en"
    max_results_per_keyword: int = 25
    min_days_since_publish: int = 1
    min_video_duration_seconds: int = 181
    require_include_match: bool = True
    default_keywords_path: Path = Path("config/keywords.txt")


def get_settings() -> Settings:
    """Build application settings from environment variables."""
    data_dir = Path(os.getenv("DATA_DIR", "/app/data")).expanduser().resolve()
    default_keywords_path = Path("config/keywords.txt")
    persistent_keywords_path = data_dir / "keywords.txt"
    keywords_path = Path(
        os.getenv(
            "KEYWORDS_PATH",
            str(persistent_keywords_path if persistent_keywords_path.exists() else default_keywords_path),
        )
    ).expanduser()
    api_key = os.getenv("YOUTUBE_API_KEY", "").strip()

    return Settings(
        youtube_api_key=api_key,
        data_dir=data_dir,
        database_path=data_dir / "youtube_trends.db",
        keywords_path=keywords_path,
        region_code=os.getenv("YOUTUBE_REGION_CODE", "US"),
        relevance_language=os.getenv("YOUTUBE_RELEVANCE_LANGUAGE", "en"),
        max_results_per_keyword=int(os.getenv("MAX_RESULTS_PER_KEYWORD", "25")),
        min_days_since_publish=int(os.getenv("MIN_DAYS_SINCE_PUBLISH", "1")),
        min_video_duration_seconds=int(os.getenv("MIN_VIDEO_DURATION_SECONDS", "181")),
        require_include_match=os.getenv("REQUIRE_INCLUDE_MATCH", "true").lower() in {"1", "true", "yes"},
        default_keywords_path=default_keywords_path,
    )


def read_keywords(path: Path) -> list[str]:
    """Read non-empty, non-comment keywords from a text file."""
    if not path.exists():
        raise FileNotFoundError(f"Keywords file not found: {path}")

    keywords: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        keyword = line.strip()
        if keyword and not keyword.startswith("#"):
            keywords.append(keyword)

    if not keywords:
        raise ValueError(f"No keywords found in {path}")
    return keywords


def get_editable_keywords_path(settings: Settings) -> Path:
    """Return the persistent keywords path used by the dashboard."""
    return settings.data_dir / "keywords.txt"


def ensure_editable_keywords_file(settings: Settings) -> Path:
    """Create a persistent editable keywords file from the default config if needed."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    editable_path = get_editable_keywords_path(settings)
    if editable_path.exists():
        return editable_path

    if settings.keywords_path.exists():
        editable_path.write_text(settings.keywords_path.read_text(encoding="utf-8"), encoding="utf-8")
    elif settings.default_keywords_path.exists():
        editable_path.write_text(settings.default_keywords_path.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        editable_path.write_text("", encoding="utf-8")
    return editable_path
