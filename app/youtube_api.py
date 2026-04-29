"""YouTube Data API v3 client."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)
YOUTUBE_API_BASE_URL = "https://www.googleapis.com/youtube/v3"
YOUTUBE_DURATION_PATTERN = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


class YouTubeAPIError(RuntimeError):
    """Raised when the YouTube API returns an error."""

    def __init__(self, message: str, reason: str = "unknown") -> None:
        super().__init__(message)
        self.reason = reason

    @property
    def is_quota_error(self) -> bool:
        """Return whether the API error means daily quota is exhausted."""
        return self.reason in {"quotaExceeded", "dailyLimitExceeded"}


@dataclass(frozen=True)
class SearchVideo:
    """Video discovered via search.list."""

    video_id: str
    keyword: str


@dataclass(frozen=True)
class VideoDetails:
    """Normalized video details from videos.list."""

    video_id: str
    title: str
    channel_id: str
    channel_title: str
    published_at: datetime
    url: str
    description: str
    tags: str
    category_id: str
    duration: str
    duration_seconds: int
    view_count: int
    like_count: int
    comment_count: int


@dataclass(frozen=True)
class ChannelDetails:
    """Normalized channel details from channels.list."""

    channel_id: str
    subscriber_count: int | None
    hidden_subscriber_count: bool
    channel_view_count: int
    channel_video_count: int


class YouTubeClient:
    """Small wrapper around YouTube Data API v3."""

    def __init__(self, api_key: str, timeout_seconds: int = 30) -> None:
        if not api_key:
            raise ValueError("YOUTUBE_API_KEY is required")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()

    def search_videos(
        self,
        keyword: str,
        region_code: str,
        relevance_language: str,
        max_results: int,
    ) -> list[SearchVideo]:
        """Discover video IDs for a keyword using search.list."""
        params = {
            "part": "id",
            "type": "video",
            "q": keyword,
            "regionCode": region_code,
            "relevanceLanguage": relevance_language,
            "order": "viewCount",
            "maxResults": min(max_results, 50),
            "key": self.api_key,
        }
        data = self._get("search", params)
        videos: list[SearchVideo] = []
        for item in data.get("items", []):
            video_id = item.get("id", {}).get("videoId")
            if video_id:
                videos.append(SearchVideo(video_id=video_id, keyword=keyword))
        LOGGER.info("Discovered %s videos for keyword '%s'", len(videos), keyword)
        return videos

    def get_video_details(self, video_ids: list[str]) -> list[VideoDetails]:
        """Fetch video details in videos.list batches of up to 50 IDs."""
        details: list[VideoDetails] = []
        for index in range(0, len(video_ids), 50):
            batch = video_ids[index : index + 50]
            params = {
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(batch),
                "key": self.api_key,
            }
            data = self._get("videos", params)
            for item in data.get("items", []):
                details.append(self._parse_video_details(item))
            LOGGER.info("Fetched details for %s videos", len(batch))
        return details

    def get_channel_details(self, channel_ids: list[str]) -> dict[str, ChannelDetails]:
        """Fetch channel statistics in channels.list batches of up to 50 IDs."""
        details: dict[str, ChannelDetails] = {}
        unique_channel_ids = list(dict.fromkeys(channel_ids))
        for index in range(0, len(unique_channel_ids), 50):
            batch = unique_channel_ids[index : index + 50]
            params = {
                "part": "statistics",
                "id": ",".join(batch),
                "key": self.api_key,
            }
            data = self._get("channels", params)
            for item in data.get("items", []):
                channel = self._parse_channel_details(item)
                details[channel.channel_id] = channel
            LOGGER.info("Fetched channel details for %s channels", len(batch))
        return details

    def _get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{YOUTUBE_API_BASE_URL}/{endpoint}"
        try:
            response = self.session.get(url, params=params, timeout=self.timeout_seconds)
        except requests.RequestException as exc:
            raise YouTubeAPIError(f"YouTube API request failed: {exc}") from exc

        if response.status_code >= 400:
            self._raise_api_error(response)

        try:
            return response.json()
        except ValueError as exc:
            raise YouTubeAPIError("YouTube API returned invalid JSON") from exc

    @staticmethod
    def _raise_api_error(response: requests.Response) -> None:
        try:
            payload = response.json()
            error = payload.get("error", {})
            reason = "unknown"
            errors = error.get("errors") or []
            if errors:
                reason = errors[0].get("reason", reason)
            message = error.get("message", response.text)
        except ValueError:
            reason = "unknown"
            message = response.text

        if response.status_code in {403, 429} or reason in {"quotaExceeded", "dailyLimitExceeded"}:
            raise YouTubeAPIError(
                f"YouTube quota/API limit error ({reason}): {message}",
                reason=reason,
            )
        raise YouTubeAPIError(
            f"YouTube API error {response.status_code} ({reason}): {message}",
            reason=reason,
        )

    @staticmethod
    def _parse_video_details(item: dict[str, Any]) -> VideoDetails:
        snippet = item.get("snippet", {})
        statistics = item.get("statistics", {})
        content_details = item.get("contentDetails", {})
        video_id = item["id"]
        published_at = datetime.fromisoformat(snippet["publishedAt"].replace("Z", "+00:00"))
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)

        return VideoDetails(
            video_id=video_id,
            title=snippet.get("title", ""),
            channel_id=snippet.get("channelId", ""),
            channel_title=snippet.get("channelTitle", ""),
            published_at=published_at,
            url=f"https://www.youtube.com/watch?v={video_id}",
            description=snippet.get("description", ""),
            tags=", ".join(snippet.get("tags", [])),
            category_id=snippet.get("categoryId", ""),
            duration=content_details.get("duration", ""),
            duration_seconds=parse_iso8601_duration(content_details.get("duration", "")),
            view_count=int(statistics.get("viewCount", 0)),
            like_count=int(statistics.get("likeCount", 0)),
            comment_count=int(statistics.get("commentCount", 0)),
        )

    @staticmethod
    def _parse_channel_details(item: dict[str, Any]) -> ChannelDetails:
        statistics = item.get("statistics", {})
        hidden_subscriber_count = bool(statistics.get("hiddenSubscriberCount", False))
        subscriber_count = None if hidden_subscriber_count else int(statistics.get("subscriberCount", 0))
        return ChannelDetails(
            channel_id=item["id"],
            subscriber_count=subscriber_count,
            hidden_subscriber_count=hidden_subscriber_count,
            channel_view_count=int(statistics.get("viewCount", 0)),
            channel_video_count=int(statistics.get("videoCount", 0)),
        )


def parse_iso8601_duration(duration: str) -> int:
    """Parse a YouTube ISO 8601 duration string into seconds."""
    match = YOUTUBE_DURATION_PATTERN.match(duration or "")
    if not match:
        return 0

    parts = {key: int(value or 0) for key, value in match.groupdict().items()}
    return (
        parts["days"] * 86_400
        + parts["hours"] * 3_600
        + parts["minutes"] * 60
        + parts["seconds"]
    )
