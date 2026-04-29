"""Command line interface for youtube-trend-radar."""

from __future__ import annotations

import argparse
import logging
from collections import OrderedDict

from app.analysis import build_videos_dataframe
from app.config import Settings, get_settings, read_keywords
from app.content_filter import ContentRules, classify_video, load_content_rules
from app.database import Database
from app.exporter import export_csvs, print_report
from app.keyword_rotation import select_keyword_batch
from app.logger import configure_logging
from app.youtube_api import VideoDetails, YouTubeAPIError, YouTubeClient

LOGGER = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(prog="youtube-trend-radar")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("run", help="Fetch YouTube data, snapshot metrics, and export rankings")
    subparsers.add_parser("export", help="Regenerate CSV files from the SQLite database")
    subparsers.add_parser("report", help="Print top opportunities from the SQLite database")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    args = parser.parse_args()

    configure_logging(args.log_level)
    settings = get_settings()
    database = Database(settings.database_path)
    database.initialize()

    if args.command == "run":
        run_pipeline(settings=settings, database=database)
    elif args.command == "export":
        export_current_data(settings=settings, database=database)
    elif args.command == "report":
        report_current_data(database=database)


def run_pipeline(settings: Settings, database: Database) -> None:
    """Run the complete data collection and ranking pipeline."""
    all_keywords = read_keywords(settings.keywords_path)
    keywords = select_keyword_batch(
        all_keywords,
        batch_size=settings.keyword_batch_size,
        cursor_path=settings.data_dir / "keyword_cursor.txt",
    )
    content_rules = load_content_rules(settings)
    client = YouTubeClient(settings.youtube_api_key)
    LOGGER.info(
        "Using %s/%s keywords this run: %s",
        len(keywords),
        len(all_keywords),
        ", ".join(keywords),
    )

    discovered_video_keywords: OrderedDict[str, str] = OrderedDict()
    quota_exhausted = False
    for keyword in keywords:
        try:
            search_results = client.search_videos(
                keyword=keyword,
                region_code=settings.region_code,
                relevance_language=settings.relevance_language,
                max_results=settings.max_results_per_keyword,
            )
        except YouTubeAPIError as exc:
            if exc.is_quota_error:
                quota_exhausted = True
                LOGGER.error("YouTube quota exhausted while searching keyword '%s'. Stopping searches.", keyword)
                break
            LOGGER.exception("Skipping keyword after YouTube API error: %s", keyword)
            continue

        for result in search_results:
            discovered_video_keywords.setdefault(result.video_id, result.keyword)

    discovered_ids = list(discovered_video_keywords.keys())
    known_discovered_ids = database.get_known_video_ids(discovered_ids)
    new_video_ids = [video_id for video_id in discovered_ids if video_id not in known_discovered_ids]
    tracked_video_ids = database.get_all_video_ids()
    ids_to_update = list(dict.fromkeys(new_video_ids + tracked_video_ids))

    LOGGER.info(
        "Discovered %s IDs (%s new). Updating %s tracked/new videos.",
        len(discovered_ids),
        len(new_video_ids),
        len(ids_to_update),
    )

    if ids_to_update:
        try:
            details = client.get_video_details(ids_to_update)
        except YouTubeAPIError as exc:
            if exc.is_quota_error:
                quota_exhausted = True
                LOGGER.error("YouTube quota exhausted while updating video metrics.")
            else:
                LOGGER.exception("Could not update video metrics after YouTube API error")
        else:
            allowed_details, excluded_video_ids = filter_allowed_videos(
                details,
                min_duration_seconds=settings.min_video_duration_seconds,
                content_rules=content_rules,
            )
            try:
                channel_details = client.get_channel_details(
                    [video.channel_id for video in allowed_details if video.channel_id]
                )
            except YouTubeAPIError as exc:
                channel_details = {}
                if exc.is_quota_error:
                    quota_exhausted = True
                    LOGGER.error("YouTube quota exhausted while updating channel metrics.")
                else:
                    LOGGER.exception("Could not update channel metrics after YouTube API error")
            deleted_count = database.delete_videos(excluded_video_ids)
            if excluded_video_ids:
                LOGGER.info(
                    "Excluded %s short-form/editorially filtered videos (%s deleted from DB).",
                    len(excluded_video_ids),
                    deleted_count,
                )
            database.upsert_videos(allowed_details, discovered_video_keywords, channel_details)
    else:
        LOGGER.info("No videos to update")

    if quota_exhausted:
        LOGGER.warning(
            "YouTube quota is exhausted. Existing data will still be snapshotted/exported; "
            "new API calls should resume after the daily quota reset."
        )

    database.create_daily_snapshot()
    export_current_data(settings=settings, database=database)


def export_current_data(settings: Settings, database: Database) -> None:
    """Export current database contents to CSV files."""
    dataframe = build_videos_dataframe(
        database.fetch_analysis_rows(min_duration_seconds=settings.min_video_duration_seconds)
    )
    top_path, all_path = export_csvs(dataframe, settings.data_dir)
    LOGGER.info("Exported top opportunities: %s", top_path)
    LOGGER.info("Exported all videos: %s", all_path)


def report_current_data(database: Database) -> None:
    """Print current top opportunities."""
    settings = get_settings()
    dataframe = build_videos_dataframe(
        database.fetch_analysis_rows(min_duration_seconds=settings.min_video_duration_seconds)
    )
    print_report(dataframe)


def filter_allowed_videos(
    videos: list[VideoDetails],
    min_duration_seconds: int,
    content_rules: ContentRules | None = None,
) -> tuple[list[VideoDetails], list[str]]:
    """Split long-form videos from probable Shorts."""
    allowed: list[VideoDetails] = []
    excluded_video_ids: list[str] = []

    for video in videos:
        text = f"{video.title} {video.description} {video.tags}".lower()
        has_shorts_marker = "#shorts" in text
        too_short = video.duration_seconds < min_duration_seconds
        if too_short or has_shorts_marker:
            excluded_video_ids.append(video.video_id)
            continue
        if content_rules is not None:
            is_allowed, reason, _relevance_score = classify_video(video, content_rules)
            if not is_allowed:
                LOGGER.info("Excluded video %s by editorial rules: %s", video.video_id, reason)
                excluded_video_ids.append(video.video_id)
                continue
        allowed.append(video)

    return allowed, excluded_video_ids


if __name__ == "__main__":
    main()
