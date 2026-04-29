"""CSV export and terminal reports."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

EXPORT_COLUMNS = [
    "opportunity_score",
    "title",
    "channel_title",
    "url",
    "keywords",
    "published_at",
    "duration_seconds",
    "days_since_publish",
    "subscriber_count",
    "view_subscriber_ratio",
    "small_channel_boost",
    "view_count",
    "views_per_day",
    "views_growth_24h",
    "like_count",
    "comment_count",
    "engagement_rate",
]


def export_csvs(dataframe: pd.DataFrame, data_dir: Path, top_limit: int = 50) -> tuple[Path, Path]:
    """Export all videos and top opportunities to CSV."""
    data_dir.mkdir(parents=True, exist_ok=True)
    all_videos_path = data_dir / "all_videos.csv"
    top_opportunities_path = data_dir / "top_opportunities.csv"

    export_frame = _select_existing_columns(dataframe, EXPORT_COLUMNS)
    export_frame.to_csv(all_videos_path, index=False)
    export_frame.head(top_limit).to_csv(top_opportunities_path, index=False)
    return top_opportunities_path, all_videos_path


def print_report(dataframe: pd.DataFrame, limit: int = 10) -> None:
    """Print a compact ranking report to stdout."""
    if dataframe.empty:
        print("No videos tracked yet. Run `python -m app run` first.")
        return

    report_columns = [
        "opportunity_score",
        "title",
        "channel_title",
        "subscriber_count",
        "view_count",
        "view_subscriber_ratio",
        "small_channel_boost",
        "views_per_day",
        "views_growth_24h",
        "engagement_rate",
        "url",
    ]
    report = _select_existing_columns(dataframe.head(limit), report_columns)
    print(report.to_string(index=False, max_colwidth=60))


def _select_existing_columns(dataframe: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    existing_columns = [column for column in columns if column in dataframe.columns]
    return dataframe.loc[:, existing_columns].copy()
