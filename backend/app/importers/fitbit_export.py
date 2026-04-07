from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from zipfile import ZipFile

from zoneinfo import ZoneInfo

SUPPORTED_SOURCE_SUFFIXES = {".json", ".csv", ".zip"}
POINT_DATETIME_KEYS = (
    "datetime",
    "date_time",
    "timestamp",
    "dateTime",
    "timestamp_utc",
    "date_time_utc",
)
POINT_DATE_KEYS = ("date", "date_only", "dateTime", "date_of_sleep")
POINT_TIME_KEYS = ("time", "clock_time", "minute")
SLEEP_START_KEYS = ("start_time", "start", "startTime", "start_datetime")
SLEEP_END_KEYS = ("end_time", "end", "endTime", "end_datetime")
VALUE_KEYS_BY_METRIC = {
    "steps": ("steps", "step", "value", "count", "total_steps"),
    "calories": ("calories", "calorie", "value", "kcal"),
    "heart_rate": ("heart_rate", "heartrate", "bpm", "value"),
    "active_minutes": ("active_minutes", "minutes_active", "value"),
    "sedentary_minutes": ("sedentary_minutes", "minutes_sedentary", "value"),
}


@dataclass(slots=True)
class ImportedSegment:
    segment_start: datetime
    segment_end: datetime
    raw_payload: dict[str, Any]


@dataclass(slots=True)
class FitbitImportResult:
    segments: list[ImportedSegment]
    discovered_sources: int
    processed_sources: int
    skipped_sources: int
    metrics_detected: dict[str, int]
    warnings: list[str]


@dataclass(slots=True)
class _HourlyBucket:
    steps: float = 0.0
    calories: float = 0.0
    heart_rate_series: list[float] = field(default_factory=list)
    sleep_minutes: float = 0.0
    active_minutes: float = 0.0
    sedentary_minutes: float = 0.0
    minute_steps_seen: int = 0
    explicit_active_minutes: bool = False
    explicit_sedentary_minutes: bool = False


def load_fitbit_export(
    export_path: str | Path,
    timezone: str,
    *,
    steps_per_active_minute: float = 50.0,
    default_calories_per_step: float = 0.04,
) -> FitbitImportResult:
    parser = _FitbitExportParser(
        timezone=timezone,
        steps_per_active_minute=steps_per_active_minute,
        default_calories_per_step=default_calories_per_step,
    )
    return parser.parse(Path(export_path))


class _FitbitExportParser:
    def __init__(
        self,
        *,
        timezone: str,
        steps_per_active_minute: float,
        default_calories_per_step: float,
    ) -> None:
        self.timezone = timezone
        self.zone = ZoneInfo(timezone)
        self.steps_per_active_minute = max(1.0, steps_per_active_minute)
        self.default_calories_per_step = max(0.0, default_calories_per_step)
        self._buckets: dict[datetime, _HourlyBucket] = defaultdict(_HourlyBucket)
        self._warnings: list[str] = []
        self._metrics_detected: Counter[str] = Counter()
        self._discovered_sources = 0
        self._processed_sources = 0
        self._skipped_sources = 0

    def parse(self, export_path: Path) -> FitbitImportResult:
        if not export_path.exists():
            raise FileNotFoundError(f"Fitbit export path not found: {export_path}")

        for source_name, suffix, text in self._iter_sources(export_path):
            self._discovered_sources += 1
            try:
                metrics = self._parse_source(source_name=source_name, suffix=suffix, text=text)
            except Exception as exc:  # pragma: no cover
                self._warnings.append(f"{source_name}: failed to parse ({exc})")
                self._skipped_sources += 1
                continue

            if metrics:
                self._processed_sources += 1
                for metric in metrics:
                    self._metrics_detected[metric] += 1
            else:
                self._skipped_sources += 1

        segments = self._build_segments()
        return FitbitImportResult(
            segments=segments,
            discovered_sources=self._discovered_sources,
            processed_sources=self._processed_sources,
            skipped_sources=self._skipped_sources,
            metrics_detected=dict(sorted(self._metrics_detected.items())),
            warnings=self._warnings,
        )

    def _iter_sources(self, export_path: Path) -> Iterable[tuple[str, str, str]]:
        paths: list[Path]
        if export_path.is_file():
            paths = [export_path]
        else:
            paths = sorted(path for path in export_path.rglob("*") if path.is_file())

        for path in paths:
            suffix = path.suffix.lower()
            if suffix not in SUPPORTED_SOURCE_SUFFIXES:
                continue

            if suffix == ".zip":
                with ZipFile(path) as archive:
                    for info in archive.infolist():
                        if info.is_dir():
                            continue
                        member_suffix = PurePosixPath(info.filename).suffix.lower()
                        if member_suffix not in {".json", ".csv"}:
                            continue
                        with archive.open(info) as file_obj:
                            text = file_obj.read().decode("utf-8-sig", errors="replace")
                        yield f"{path}!{info.filename}", member_suffix, text
                continue

            text = path.read_text(encoding="utf-8-sig", errors="replace")
            yield str(path), suffix, text

    def _parse_source(self, *, source_name: str, suffix: str, text: str) -> set[str]:
        if suffix == ".json":
            return self._parse_json_source(source_name, text)
        if suffix == ".csv":
            return self._parse_csv_source(source_name, text)
        return set()

    def _parse_json_source(self, source_name: str, text: str) -> set[str]:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            self._warnings.append(f"{source_name}: invalid JSON ({exc.msg})")
            return set()

        if isinstance(data, dict):
            return self._parse_json_object(source_name, data)
        if isinstance(data, list):
            return self._parse_json_rows(source_name, data)
        self._warnings.append(f"{source_name}: unsupported JSON root type {type(data).__name__}")
        return set()

    def _parse_json_object(self, source_name: str, data: dict[str, Any]) -> set[str]:
        metrics: set[str] = set()

        for key, value in data.items():
            metric = self._metric_from_intraday_key(key)
            if not metric:
                continue

            summary_key = key.replace("-intraday", "")
            reference_date = self._extract_reference_date(data.get(summary_key), source_name)
            if self._parse_intraday_payload(metric=metric, payload=value, reference_date=reference_date):
                metrics.add(metric)

        if "sleep" in data and isinstance(data["sleep"], list):
            if self._parse_sleep_entries(data["sleep"]):
                metrics.add("sleep")

        if self._looks_like_sleep_entry(data):
            if self._parse_sleep_entry(data):
                metrics.add("sleep")

        if not metrics and self._looks_like_record(data):
            metrics.update(self._parse_json_rows(source_name, [data]))

        return metrics

    def _parse_json_rows(self, source_name: str, rows: list[Any]) -> set[str]:
        dict_rows = [row for row in rows if isinstance(row, dict)]
        if not dict_rows:
            return set()

        if any(self._looks_like_sleep_entry(row) for row in dict_rows):
            return {"sleep"} if self._parse_sleep_entries(dict_rows) else set()

        metric = self._detect_metric(source_name, dict_rows[0].keys())
        if not metric:
            return set()

        return {metric} if self._parse_point_rows(metric=metric, source_name=source_name, rows=dict_rows) else set()

    def _parse_csv_source(self, source_name: str, text: str) -> set[str]:
        reader = csv.DictReader(text.splitlines())
        rows = [row for row in reader if row]
        if not rows or not reader.fieldnames:
            return set()

        if any(self._looks_like_sleep_entry(row) for row in rows):
            return {"sleep"} if self._parse_sleep_entries(rows) else set()

        metric = self._detect_metric(source_name, reader.fieldnames)
        if not metric:
            return set()

        return {metric} if self._parse_point_rows(metric=metric, source_name=source_name, rows=rows) else set()

    def _parse_intraday_payload(
        self,
        *,
        metric: str,
        payload: Any,
        reference_date: date | None,
    ) -> bool:
        if not isinstance(payload, dict):
            return False
        dataset = payload.get("dataset")
        if not isinstance(dataset, list):
            return False

        parsed_any = False
        for item in dataset:
            if not isinstance(item, dict):
                continue
            timestamp = self._extract_intraday_timestamp(item=item, reference_date=reference_date)
            value = self._extract_numeric_value(item, metric)
            if not timestamp or value is None:
                continue
            parsed_any = True
            self._add_metric_point(metric=metric, timestamp=timestamp, value=value, minute_resolution=True)
        return parsed_any

    def _parse_point_rows(self, *, metric: str, source_name: str, rows: list[dict[str, Any]]) -> bool:
        parsed_any = False
        warned_daily_only = False

        for row in rows:
            timestamp, has_clock = self._extract_point_timestamp(row=row, source_name=source_name)
            if not timestamp:
                continue
            if not has_clock:
                if not warned_daily_only:
                    self._warnings.append(
                        f"{source_name}: skipped daily-only {metric} rows because hourly import needs timestamps"
                    )
                    warned_daily_only = True
                continue

            value = self._extract_numeric_value(row, metric)
            if value is None:
                continue

            minute_resolution = self._looks_like_minute_resolution(row)
            self._add_metric_point(metric=metric, timestamp=timestamp, value=value, minute_resolution=minute_resolution)
            parsed_any = True

        return parsed_any

    def _parse_sleep_entries(self, rows: list[dict[str, Any]]) -> bool:
        parsed_any = False
        for row in rows:
            parsed_any = self._parse_sleep_entry(row) or parsed_any
        return parsed_any

    def _parse_sleep_entry(self, entry: dict[str, Any]) -> bool:
        levels = entry.get("levels")
        if isinstance(levels, dict) and self._parse_sleep_levels(levels):
            return True

        start = self._extract_datetime_from_keys(entry, SLEEP_START_KEYS)
        end = self._extract_datetime_from_keys(entry, SLEEP_END_KEYS)
        minutes_asleep = self._extract_numeric_value(entry, "sleep")

        if not start and isinstance(entry.get("dateOfSleep"), str):
            date_value = self._parse_datetime_text(entry["dateOfSleep"])
            time_value = entry.get("startTime") or entry.get("start_time")
            if date_value and time_value:
                start = self._combine_date_and_time(date_value.date(), str(time_value))

        if not start:
            return False

        if not end:
            duration_minutes = minutes_asleep
            if duration_minutes is None:
                duration_minutes = self._coerce_number(entry.get("timeInBed"))
            if duration_minutes is None:
                return False
            end = start + timedelta(minutes=duration_minutes)

        return self._add_sleep_interval(start=start, end=end, minutes_asleep=minutes_asleep)

    def _parse_sleep_levels(self, levels: dict[str, Any]) -> bool:
        parsed_any = False
        for key in ("data", "shortData"):
            events = levels.get(key)
            if not isinstance(events, list):
                continue
            for event in events:
                if not isinstance(event, dict):
                    continue
                level = str(event.get("level", "")).lower()
                if level == "wake":
                    continue
                start = self._parse_datetime_text(event.get("dateTime"))
                seconds = self._coerce_number(event.get("seconds"))
                if not start or seconds is None or seconds <= 0:
                    continue
                end = start + timedelta(seconds=seconds)
                parsed_any = self._add_sleep_interval(start=start, end=end) or parsed_any
        return parsed_any

    def _add_metric_point(
        self,
        *,
        metric: str,
        timestamp: datetime,
        value: float,
        minute_resolution: bool,
    ) -> None:
        bucket = self._buckets[self._bucket_start(timestamp)]

        if metric == "steps":
            bucket.steps += value
            if minute_resolution:
                bucket.minute_steps_seen += 1
                if value > 0:
                    bucket.active_minutes += 1
                else:
                    bucket.sedentary_minutes += 1
            return

        if metric == "calories":
            bucket.calories += value
            return

        if metric == "heart_rate":
            if value > 0:
                bucket.heart_rate_series.append(round(value, 4))
            return

        if metric == "active_minutes":
            bucket.active_minutes += value
            bucket.explicit_active_minutes = True
            return

        if metric == "sedentary_minutes":
            bucket.sedentary_minutes += value
            bucket.explicit_sedentary_minutes = True

    def _add_sleep_interval(
        self,
        *,
        start: datetime,
        end: datetime,
        minutes_asleep: float | None = None,
    ) -> bool:
        localized_start = self._ensure_timezone(start)
        localized_end = self._ensure_timezone(end)
        if localized_end <= localized_start:
            return False

        effective_end = localized_end
        if minutes_asleep is not None:
            minutes_asleep = max(0.0, minutes_asleep)
            effective_end = min(localized_end, localized_start + timedelta(minutes=minutes_asleep))
        if effective_end <= localized_start:
            return False

        current = localized_start
        while current < effective_end:
            bucket_start = self._bucket_start(current)
            next_bucket = bucket_start + timedelta(hours=1)
            overlap_end = min(effective_end, next_bucket)
            minutes = (overlap_end - current).total_seconds() / 60
            self._buckets[bucket_start].sleep_minutes += minutes
            current = overlap_end
        return True

    def _build_segments(self) -> list[ImportedSegment]:
        segments: list[ImportedSegment] = []

        for segment_start in sorted(self._buckets):
            bucket = self._buckets[segment_start]
            if not self._bucket_has_signal(bucket):
                continue

            sleep_minutes = round(min(bucket.sleep_minutes, 60.0), 4)
            active_minutes = bucket.active_minutes
            sedentary_minutes = bucket.sedentary_minutes

            if not bucket.explicit_active_minutes and bucket.minute_steps_seen == 0:
                inferred_active = round(min(max(0.0, 60.0 - sleep_minutes), bucket.steps / self.steps_per_active_minute), 4)
                active_minutes = max(active_minutes, inferred_active)

            if bucket.minute_steps_seen > 0 and not bucket.explicit_sedentary_minutes:
                sedentary_minutes = max(0.0, sedentary_minutes - sleep_minutes)

            if not bucket.explicit_sedentary_minutes:
                sedentary_floor = max(0.0, 60.0 - sleep_minutes - active_minutes)
                sedentary_minutes = max(sedentary_minutes, sedentary_floor)

            calories = bucket.calories
            if calories == 0 and bucket.steps > 0 and self.default_calories_per_step:
                calories = round(bucket.steps * self.default_calories_per_step, 4)

            raw_payload = {
                "steps": round(bucket.steps, 4),
                "calories": round(calories, 4),
                "heart_rate_series": [round(value, 4) for value in bucket.heart_rate_series],
                "sleep_minutes": round(sleep_minutes, 4),
                "sedentary_minutes": round(min(sedentary_minutes, 60.0), 4),
                "active_minutes": round(min(active_minutes, 60.0), 4),
            }

            segments.append(
                ImportedSegment(
                    segment_start=segment_start,
                    segment_end=segment_start + timedelta(hours=1),
                    raw_payload=raw_payload,
                )
            )

        return segments

    def _bucket_has_signal(self, bucket: _HourlyBucket) -> bool:
        return any(
            (
                bucket.steps,
                bucket.calories,
                bucket.sleep_minutes,
                bucket.active_minutes,
                bucket.sedentary_minutes,
                bucket.heart_rate_series,
            )
        )

    def _bucket_start(self, timestamp: datetime) -> datetime:
        localized = self._ensure_timezone(timestamp)
        return localized.replace(minute=0, second=0, microsecond=0)

    def _ensure_timezone(self, timestamp: datetime) -> datetime:
        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=self.zone)
        return timestamp.astimezone(self.zone)

    def _metric_from_intraday_key(self, value: str) -> str | None:
        token = _normalize_token(value)
        if token == "activities_heart_intraday":
            return "heart_rate"
        if token == "activities_steps_intraday":
            return "steps"
        if token == "activities_calories_intraday":
            return "calories"
        return None

    def _detect_metric(self, source_name: str, fieldnames: Iterable[str]) -> str | None:
        token = _normalize_token(source_name)
        tokens = set(token.split("_"))
        fields = {_normalize_token(fieldname) for fieldname in fieldnames}

        if "sedentary" in token or "sedentary_minutes" in fields:
            return "sedentary_minutes"
        if "active" in tokens and "sleep" not in tokens:
            return "active_minutes"
        if {"active_minutes", "minutes_active"} & fields:
            return "active_minutes"
        if "heart" in tokens or "heartrate" in token or {"bpm", "heart_rate", "heartrate"} & fields:
            return "heart_rate"
        if "calorie" in token or "calories" in tokens or {"calories", "calorie", "kcal"} & fields:
            return "calories"
        if "step" in token or "steps" in tokens or {"steps", "step", "total_steps"} & fields:
            return "steps"
        if "sleep" in tokens or self._looks_like_sleep_fields(fields):
            return "sleep"
        return None

    def _looks_like_sleep_fields(self, fields: Iterable[str]) -> bool:
        field_set = set(fields)
        return bool(
            {"minutes_asleep", "minutesasleep", "time_in_bed", "timeinbed", "start_time", "end_time"} & field_set
        )

    def _looks_like_record(self, data: dict[str, Any]) -> bool:
        return any(key in data for key in ("dateTime", "value", "time", "timestamp"))

    def _looks_like_sleep_entry(self, data: dict[str, Any]) -> bool:
        fields = {_normalize_token(key) for key in data}
        if "levels" in data or "sleep" in data:
            return True
        normalized_start_keys = {_normalize_token(key) for key in SLEEP_START_KEYS}
        return bool(
            {"minutes_asleep", "minutesasleep", "timeinbed", "time_in_bed"} & fields
            or (normalized_start_keys & fields)
        )

    def _extract_reference_date(self, value: Any, source_name: str) -> date | None:
        if isinstance(value, list):
            for item in value:
                if not isinstance(item, dict):
                    continue
                timestamp = self._parse_datetime_text(item.get("dateTime"))
                if timestamp:
                    return timestamp.date()
        if isinstance(value, dict):
            timestamp = self._parse_datetime_text(value.get("dateTime"))
            if timestamp:
                return timestamp.date()
        return _infer_date_from_name(source_name)

    def _extract_intraday_timestamp(self, *, item: dict[str, Any], reference_date: date | None) -> datetime | None:
        if "dateTime" in item:
            return self._parse_datetime_text(item.get("dateTime"), default_date=reference_date)

        time_text = item.get("time") or item.get("minute")
        if time_text and reference_date:
            return self._combine_date_and_time(reference_date, str(time_text))

        return None

    def _extract_point_timestamp(self, *, row: dict[str, Any], source_name: str) -> tuple[datetime | None, bool]:
        normalized = {_normalize_token(key): value for key, value in row.items()}
        source_date = _infer_date_from_name(source_name)

        datetime_value = _first_present(normalized, POINT_DATETIME_KEYS)
        if datetime_value:
            parsed = self._parse_datetime_text(datetime_value, default_date=source_date)
            if parsed:
                if _has_clock_component(str(datetime_value)):
                    return parsed, True
                time_value = _first_present(normalized, POINT_TIME_KEYS)
                if time_value:
                    return self._combine_date_and_time(parsed.date(), str(time_value)), True
                return parsed, False

        date_value = _first_present(normalized, POINT_DATE_KEYS)
        time_value = _first_present(normalized, POINT_TIME_KEYS)
        if date_value and time_value:
            date_parsed = self._parse_datetime_text(date_value)
            if date_parsed:
                return self._combine_date_and_time(date_parsed.date(), str(time_value)), True

        if time_value and source_date:
            return self._combine_date_and_time(source_date, str(time_value)), True

        return None, False

    def _extract_datetime_from_keys(self, data: dict[str, Any], keys: Iterable[str]) -> datetime | None:
        normalized = {_normalize_token(key): value for key, value in data.items()}
        value = _first_present(normalized, keys)
        return self._parse_datetime_text(value)

    def _extract_numeric_value(self, data: dict[str, Any], metric: str) -> float | None:
        normalized = {_normalize_token(key): value for key, value in data.items()}

        if metric == "sleep":
            for key in ("minutes_asleep", "minutesasleep", "time_in_bed", "timeinbed", "value"):
                if key in normalized:
                    number = self._coerce_number(normalized[key])
                    if number is not None:
                        return number
            return None

        ignored_keys = {
            _normalize_token(key)
            for key in POINT_DATETIME_KEYS + POINT_DATE_KEYS + POINT_TIME_KEYS + SLEEP_START_KEYS + SLEEP_END_KEYS
        }
        for key in VALUE_KEYS_BY_METRIC.get(metric, ()):
            if key in normalized:
                number = self._coerce_number(normalized[key])
                if number is not None:
                    return number

        for key, value in normalized.items():
            if key in ignored_keys:
                continue
            number = self._coerce_number(value)
            if number is not None:
                return number
        return None

    def _combine_date_and_time(self, date_value: date, time_value: str) -> datetime:
        parsed_time = _parse_time_text(time_value)
        return datetime.combine(date_value, parsed_time).replace(tzinfo=self.zone)

    def _parse_datetime_text(self, value: Any, default_date: date | None = None) -> datetime | None:
        if value is None or value == "":
            return None

        if isinstance(value, datetime):
            return self._ensure_timezone(value)

        if isinstance(value, (int, float)):
            timestamp = float(value)
            if timestamp > 10_000_000_000:
                timestamp /= 1000
            return datetime.fromtimestamp(timestamp, tz=self.zone)

        text = str(value).strip()
        if not text:
            return None

        if default_date and _looks_like_time_only(text):
            return self._combine_date_and_time(default_date, text)

        iso_candidate = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(iso_candidate)
        except ValueError:
            parsed = None

        if parsed is not None:
            return self._ensure_timezone(parsed)

        formats = (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%Y %H:%M",
            "%m/%d/%y %H:%M:%S",
            "%m/%d/%y %H:%M",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%m/%d/%Y",
            "%m/%d/%y",
            "%d/%m/%Y",
        )
        for fmt in formats:
            try:
                parsed = datetime.strptime(text, fmt)
            except ValueError:
                continue
            return self._ensure_timezone(parsed)

        return None

    def _coerce_number(self, value: Any) -> float | None:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, dict):
            for key in ("bpm", "value", "count", "steps", "calories", "minutes"):
                if key in value:
                    return self._coerce_number(value[key])
            return None

        text = str(value).strip()
        if not text:
            return None
        text = text.replace(",", "")
        try:
            return float(text)
        except ValueError:
            return None

    def _looks_like_minute_resolution(self, row: dict[str, Any]) -> bool:
        timestamp = row.get("dateTime") or row.get("datetime") or row.get("timestamp")
        if timestamp and _has_clock_component(str(timestamp)):
            return True
        time_value = row.get("time") or row.get("minute")
        return bool(time_value)


def _normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _first_present(mapping: dict[str, Any], keys: Iterable[str]) -> Any | None:
    for key in keys:
        normalized = _normalize_token(key)
        if normalized in mapping and mapping[normalized] not in (None, ""):
            return mapping[normalized]
    return None


def _has_clock_component(value: str) -> bool:
    return ":" in value or "T" in value.upper()


def _looks_like_time_only(value: str) -> bool:
    stripped = value.strip()
    if not stripped or "-" in stripped or "/" in stripped:
        return False
    return ":" in stripped


def _parse_time_text(value: str) -> time:
    stripped = value.strip()
    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p"):
        try:
            return datetime.strptime(stripped, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Unsupported time format: {value}")


def _infer_date_from_name(source_name: str) -> date | None:
    match = re.search(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})", source_name)
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    return date(year, month, day)
