"""Opportunity ranking calculations."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd


def build_videos_dataframe(rows: list[object]) -> pd.DataFrame:
    """Convert database rows into an analysis-ready DataFrame."""
    records = [dict(row) for row in rows]
    if not records:
        return _empty_dataframe()

    dataframe = pd.DataFrame.from_records(records).copy()
    now = datetime.now(UTC)
    published_at = pd.to_datetime(dataframe["published_at"], utc=True, errors="coerce")
    age_seconds = (now - published_at).dt.total_seconds().clip(lower=0)

    days_since_publish = (age_seconds / 86_400).clip(lower=1).round(2)
    views_per_day = (dataframe["view_count"] / days_since_publish).round(2)
    interactions = dataframe["like_count"] + dataframe["comment_count"]
    engagement_rate = (interactions / dataframe["view_count"].replace(0, pd.NA)).fillna(0).round(6)
    subscriber_count = pd.to_numeric(dataframe.get("subscriber_count", 0), errors="coerce")
    view_subscriber_ratio = (
        dataframe["view_count"] / subscriber_count.replace(0, pd.NA)
    ).fillna(0).round(4)
    small_channel_boost = _calculate_small_channel_boost(subscriber_count, view_subscriber_ratio)

    dataframe = dataframe.assign(
        days_since_publish=days_since_publish,
        views_per_day=views_per_day,
        engagement_rate=engagement_rate,
        views_growth_24h=dataframe["views_growth_24h"].fillna(0).astype(int),
        subscriber_count=subscriber_count,
        view_subscriber_ratio=view_subscriber_ratio,
        small_channel_boost=small_channel_boost,
    )
    dataframe = dataframe.assign(opportunity_score=_calculate_opportunity_score(dataframe))
    return dataframe.sort_values("opportunity_score", ascending=False)


def _calculate_opportunity_score(dataframe: pd.DataFrame) -> pd.Series:
    views_per_day_score = _min_max(dataframe["views_per_day"])
    growth_score = _min_max(dataframe["views_growth_24h"])
    engagement_score = _min_max(dataframe["engagement_rate"])
    small_channel_score = _min_max(dataframe["small_channel_boost"])
    recency_score = (1 / dataframe["days_since_publish"].clip(lower=1)).clip(upper=1)

    score = (
        views_per_day_score * 0.35
        + growth_score * 0.20
        + small_channel_score * 0.25
        + engagement_score * 0.10
        + recency_score * 0.10
    ) * 100
    return score.round(2)


def _calculate_small_channel_boost(
    subscriber_count: pd.Series,
    view_subscriber_ratio: pd.Series,
) -> pd.Series:
    subscribers = pd.to_numeric(subscriber_count, errors="coerce").fillna(0)
    ratio = pd.to_numeric(view_subscriber_ratio, errors="coerce").fillna(0)

    channel_size_score = pd.Series(0.2, index=subscribers.index)
    channel_size_score = channel_size_score.mask(subscribers <= 250_000, 0.45)
    channel_size_score = channel_size_score.mask(subscribers <= 100_000, 0.65)
    channel_size_score = channel_size_score.mask(subscribers <= 50_000, 0.80)
    channel_size_score = channel_size_score.mask(subscribers <= 10_000, 1.00)
    channel_size_score = channel_size_score.mask(subscribers <= 0, 0.35)

    ratio_score = (ratio / 5).clip(lower=0, upper=1)
    return ((channel_size_score * 0.55) + (ratio_score * 0.45)).round(4)


def _min_max(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").fillna(0)
    minimum = numeric.min()
    maximum = numeric.max()
    if maximum == minimum:
        return pd.Series([0.0] * len(numeric), index=numeric.index)
    return (numeric - minimum) / (maximum - minimum)


def select_top_opportunities(dataframe: pd.DataFrame, limit: int = 50) -> pd.DataFrame:
    """Return the strongest ranked opportunities."""
    if dataframe.empty:
        return dataframe
    return dataframe.head(limit)


def _empty_dataframe() -> pd.DataFrame:
    columns = [
        "video_id",
        "title",
        "channel_title",
        "published_at",
        "url",
        "keywords",
        "view_count",
        "subscriber_count",
        "view_subscriber_ratio",
        "small_channel_boost",
        "like_count",
        "comment_count",
        "days_since_publish",
        "views_per_day",
        "views_growth_24h",
        "engagement_rate",
        "opportunity_score",
    ]
    return pd.DataFrame(columns=columns)
