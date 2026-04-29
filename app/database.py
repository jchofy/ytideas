"""SQLite persistence layer."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path

from app.youtube_api import VideoDetails


class Database:
    """SQLite database gateway."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        """Create a configured SQLite connection."""
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def initialize(self) -> None:
        """Create database tables and indexes."""
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS videos (
                    video_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    channel_title TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    url TEXT NOT NULL,
                    description TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    category_id TEXT NOT NULL,
                    duration TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    last_keyword TEXT NOT NULL,
                    view_count INTEGER NOT NULL DEFAULT 0,
                    like_count INTEGER NOT NULL DEFAULT 0,
                    comment_count INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS video_keywords (
                    video_id TEXT NOT NULL,
                    keyword TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    PRIMARY KEY (video_id, keyword),
                    FOREIGN KEY (video_id) REFERENCES videos(video_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS metric_snapshots (
                    snapshot_date TEXT NOT NULL,
                    video_id TEXT NOT NULL,
                    view_count INTEGER NOT NULL,
                    like_count INTEGER NOT NULL,
                    comment_count INTEGER NOT NULL,
                    views_growth_24h INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (snapshot_date, video_id),
                    FOREIGN KEY (video_id) REFERENCES videos(video_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_snapshots_video_date
                ON metric_snapshots(video_id, snapshot_date);
                """
            )

    def get_known_video_ids(self, video_ids: Iterable[str] | None = None) -> set[str]:
        """Return known IDs, optionally constrained to a candidate list."""
        with self.connect() as connection:
            if video_ids is None:
                rows = connection.execute("SELECT video_id FROM videos").fetchall()
            else:
                candidates = list(dict.fromkeys(video_ids))
                if not candidates:
                    return set()
                placeholders = ",".join("?" for _ in candidates)
                rows = connection.execute(
                    f"SELECT video_id FROM videos WHERE video_id IN ({placeholders})",
                    candidates,
                ).fetchall()
        return {row["video_id"] for row in rows}

    def upsert_videos(self, videos: list[VideoDetails], keyword_by_video_id: dict[str, str]) -> None:
        """Insert or update videos and keyword associations."""
        now = datetime.now(UTC).isoformat()
        with self.connect() as connection:
            for video in videos:
                keyword = keyword_by_video_id.get(video.video_id, "")
                connection.execute(
                    """
                    INSERT INTO videos (
                        video_id, title, channel_id, channel_title, published_at, url,
                        description, tags, category_id, duration, first_seen_at, last_seen_at,
                        last_keyword, view_count, like_count, comment_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(video_id) DO UPDATE SET
                        title = excluded.title,
                        channel_id = excluded.channel_id,
                        channel_title = excluded.channel_title,
                        published_at = excluded.published_at,
                        url = excluded.url,
                        description = excluded.description,
                        tags = excluded.tags,
                        category_id = excluded.category_id,
                        duration = excluded.duration,
                        last_seen_at = excluded.last_seen_at,
                        last_keyword = excluded.last_keyword,
                        view_count = excluded.view_count,
                        like_count = excluded.like_count,
                        comment_count = excluded.comment_count
                    """,
                    (
                        video.video_id,
                        video.title,
                        video.channel_id,
                        video.channel_title,
                        video.published_at.isoformat(),
                        video.url,
                        video.description,
                        video.tags,
                        video.category_id,
                        video.duration,
                        now,
                        now,
                        keyword,
                        video.view_count,
                        video.like_count,
                        video.comment_count,
                    ),
                )
                if keyword:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO video_keywords (video_id, keyword, first_seen_at)
                        VALUES (?, ?, ?)
                        """,
                        (video.video_id, keyword, now),
                    )

    def get_all_video_ids(self) -> list[str]:
        """Return all tracked video IDs."""
        with self.connect() as connection:
            rows = connection.execute("SELECT video_id FROM videos ORDER BY first_seen_at").fetchall()
        return [row["video_id"] for row in rows]

    def create_daily_snapshot(self, snapshot_day: date | None = None) -> None:
        """Create or update metric snapshots for the selected day."""
        day = snapshot_day or datetime.now(UTC).date()
        previous_day = day.fromordinal(day.toordinal() - 1).isoformat()
        now = datetime.now(UTC).isoformat()

        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT v.video_id, v.view_count, v.like_count, v.comment_count,
                       COALESCE(v.view_count - previous.view_count, 0) AS views_growth_24h
                FROM videos v
                LEFT JOIN metric_snapshots previous
                  ON previous.video_id = v.video_id AND previous.snapshot_date = ?
                """,
                (previous_day,),
            ).fetchall()
            connection.executemany(
                """
                INSERT INTO metric_snapshots (
                    snapshot_date, video_id, view_count, like_count, comment_count,
                    views_growth_24h, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(snapshot_date, video_id) DO UPDATE SET
                    view_count = excluded.view_count,
                    like_count = excluded.like_count,
                    comment_count = excluded.comment_count,
                    views_growth_24h = excluded.views_growth_24h,
                    created_at = excluded.created_at
                """,
                [
                    (
                        day.isoformat(),
                        row["video_id"],
                        row["view_count"],
                        row["like_count"],
                        row["comment_count"],
                        row["views_growth_24h"],
                        now,
                    )
                    for row in rows
                ],
            )

    def fetch_analysis_rows(self) -> list[sqlite3.Row]:
        """Fetch denormalized rows for analysis/export."""
        with self.connect() as connection:
            return connection.execute(
                """
                WITH latest_snapshot AS (
                    SELECT ms.*
                    FROM metric_snapshots ms
                    INNER JOIN (
                        SELECT video_id, MAX(snapshot_date) AS snapshot_date
                        FROM metric_snapshots
                        GROUP BY video_id
                    ) latest
                      ON latest.video_id = ms.video_id
                     AND latest.snapshot_date = ms.snapshot_date
                ), keyword_rollup AS (
                    SELECT video_id, GROUP_CONCAT(keyword, ', ') AS keywords
                    FROM video_keywords
                    GROUP BY video_id
                )
                SELECT v.*, COALESCE(k.keywords, v.last_keyword) AS keywords,
                       COALESCE(s.views_growth_24h, 0) AS views_growth_24h,
                       s.snapshot_date
                FROM videos v
                LEFT JOIN latest_snapshot s ON s.video_id = v.video_id
                LEFT JOIN keyword_rollup k ON k.video_id = v.video_id
                ORDER BY v.view_count DESC
                """
            ).fetchall()
