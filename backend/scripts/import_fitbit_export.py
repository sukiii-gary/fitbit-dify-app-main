from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import select

from app.db.session import SessionLocal, create_db_and_tables
from app.importers.fitabase_merged import FitabaseImportResult, load_fitabase_merged_export
from app.importers.fitbit_export import FitbitImportResult, load_fitbit_export
from app.models.raw_segment import RawSegment
from app.models.user import User
from app.schemas.user import UserCreateRequest
from app.services.user_service import create_user


def parse_args() -> argparse.Namespace:
    default_export_dir = ROOT_DIR.parent / "data" / "raw" / "fitbit-export"

    parser = argparse.ArgumentParser(
        description="Import Fitbit export files into hourly raw_segments for the local backend."
    )
    parser.add_argument(
        "--export-dir",
        type=Path,
        default=default_export_dir,
        help=f"Directory or zip file containing Fitbit export files (default: {default_export_dir})",
    )
    parser.add_argument("--external-user-id", help="Stable external user id for single-user Fitbit exports.")
    parser.add_argument(
        "--external-user-id-prefix",
        default="fitabase",
        help="User id prefix for multi-user Fitabase merged exports.",
    )
    parser.add_argument("--name", default=None, help="Optional display name for the user record.")
    parser.add_argument("--timezone", default="Asia/Shanghai", help="Timezone for naive Fitbit timestamps.")
    parser.add_argument("--source-type", default=None, help="source_type to store on imported segments.")
    parser.add_argument(
        "--steps-per-active-minute",
        type=float,
        default=50.0,
        help="Fallback divisor when active minutes must be inferred from hourly steps.",
    )
    parser.add_argument(
        "--calories-per-step",
        type=float,
        default=0.04,
        help="Fallback calories multiplier when calorie files are missing.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Parse files and print a summary without writing to DB.")
    parser.add_argument(
        "--print-first",
        type=int,
        default=3,
        help="How many generated segments to preview in the summary output.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    create_db_and_tables()
    mode = detect_export_mode(args.export_dir)
    source_type = args.source_type or ("fitabase_merged" if mode == "fitabase_merged" else "fitbit_export")

    if mode == "fitabase_merged":
        result = load_fitabase_merged_export(
            export_path=args.export_dir,
            timezone=args.timezone,
            steps_per_active_minute=args.steps_per_active_minute,
        )
        return run_fitabase_import(args=args, result=result, source_type=source_type)

    if not args.external_user_id:
        raise SystemExit("--external-user-id is required for single-user Fitbit exports.")

    result = load_fitbit_export(
        export_path=args.export_dir,
        timezone=args.timezone,
        steps_per_active_minute=args.steps_per_active_minute,
        default_calories_per_step=args.calories_per_step,
    )

    if not result.segments:
        print_summary(
            mode=mode,
            result=result,
            created_user_id=None,
            inserted=0,
            skipped_existing=0,
            dry_run=args.dry_run,
            preview_count=args.print_first,
        )
        print("No hourly segments were generated. Check that your export contains intraday timestamps.", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        existing_user = db.scalar(select(User).where(User.external_user_id == args.external_user_id))

        if args.dry_run:
            user_id = existing_user.id if existing_user else None
            inserted = 0
            skipped_existing = _count_existing_segments(
                db=db,
                user_id=user_id,
                source_type=source_type,
                result=result,
            )
        else:
            user = create_user(
                db=db,
                payload=UserCreateRequest(
                    external_user_id=args.external_user_id,
                    name=args.name,
                    timezone=args.timezone,
                ),
            )
            inserted, skipped_existing = _persist_segments(
                db=db,
                user_id=user.id,
                source_type=source_type,
                result=result,
            )
            user_id = user.id

    print_summary(
        mode=mode,
        result=result,
        created_user_id=user_id,
        inserted=inserted,
        skipped_existing=skipped_existing,
        dry_run=args.dry_run,
        preview_count=args.print_first,
    )
    return 0


def run_fitabase_import(*, args: argparse.Namespace, result: FitabaseImportResult, source_type: str) -> int:
    total_segments = sum(len(segments) for segments in result.user_segments.values())
    if total_segments == 0:
        print_fitabase_summary(
            result=result,
            inserted_users=0,
            inserted_segments=0,
            skipped_existing=0,
            dry_run=args.dry_run,
            preview_count=args.print_first,
            source_type=source_type,
            external_user_id_prefix=args.external_user_id_prefix,
        )
        print("No per-user hourly segments were generated from this Fitabase export.", file=sys.stderr)
        return 1

    inserted_users = 0
    inserted_segments = 0
    skipped_existing = 0

    with SessionLocal() as db:
        for source_user_id, segments in sorted(result.user_segments.items()):
            external_user_id = f"{args.external_user_id_prefix}_{source_user_id}"
            existing_user = db.scalar(select(User).where(User.external_user_id == external_user_id))

            if args.dry_run:
                user_id = existing_user.id if existing_user else None
                skipped_existing += _count_existing_segments_for_segments(
                    db=db,
                    user_id=user_id,
                    source_type=source_type,
                    segments=segments,
                )
                continue

            if existing_user:
                user = existing_user
            else:
                user = create_user(
                    db=db,
                    payload=UserCreateRequest(
                        external_user_id=external_user_id,
                        name=f"Fitabase {source_user_id}",
                        timezone=args.timezone,
                    ),
                )
                inserted_users += 1

            inserted, skipped = _persist_imported_segments(
                db=db,
                user_id=user.id,
                source_type=source_type,
                segments=segments,
            )
            inserted_segments += inserted
            skipped_existing += skipped

    print_fitabase_summary(
        result=result,
        inserted_users=inserted_users,
        inserted_segments=inserted_segments,
        skipped_existing=skipped_existing,
        dry_run=args.dry_run,
        preview_count=args.print_first,
        source_type=source_type,
        external_user_id_prefix=args.external_user_id_prefix,
    )
    return 0


def detect_export_mode(export_dir: Path) -> str:
    if export_dir.is_file() and export_dir.name.lower().endswith(".zip"):
        return "fitbit_export"

    merged_paths = list(export_dir.rglob("*_merged.csv"))
    if merged_paths:
        return "fitabase_merged"
    return "fitbit_export"


def _persist_segments(
    *,
    db,
    user_id: str,
    source_type: str,
    result: FitbitImportResult,
) -> tuple[int, int]:
    existing_keys = _load_existing_keys(db=db, user_id=user_id, source_type=source_type)
    inserted = 0
    skipped_existing = 0

    for segment in result.segments:
        key = _segment_identity(segment.segment_start, source_type)
        if key in existing_keys:
            skipped_existing += 1
            continue

        db.add(
            RawSegment(
                user_id=user_id,
                segment_start=segment.segment_start,
                segment_end=segment.segment_end,
                granularity="1h",
                source_type=source_type,
                raw_payload_json=segment.raw_payload,
            )
        )
        existing_keys.add(key)
        inserted += 1

    db.commit()
    return inserted, skipped_existing


def _persist_imported_segments(*, db, user_id: str, source_type: str, segments) -> tuple[int, int]:
    existing_keys = _load_existing_keys(db=db, user_id=user_id, source_type=source_type)
    inserted = 0
    skipped_existing = 0

    for segment in segments:
        key = _segment_identity(segment.segment_start, source_type)
        if key in existing_keys:
            skipped_existing += 1
            continue

        db.add(
            RawSegment(
                user_id=user_id,
                segment_start=segment.segment_start,
                segment_end=segment.segment_end,
                granularity="1h",
                source_type=source_type,
                raw_payload_json=segment.raw_payload,
            )
        )
        existing_keys.add(key)
        inserted += 1

    db.commit()
    return inserted, skipped_existing


def _count_existing_segments(*, db, user_id: str | None, source_type: str, result: FitbitImportResult) -> int:
    if not user_id:
        return 0
    existing_keys = _load_existing_keys(db=db, user_id=user_id, source_type=source_type)
    return sum(1 for segment in result.segments if _segment_identity(segment.segment_start, source_type) in existing_keys)


def _count_existing_segments_for_segments(*, db, user_id: str | None, source_type: str, segments) -> int:
    if not user_id:
        return 0
    existing_keys = _load_existing_keys(db=db, user_id=user_id, source_type=source_type)
    return sum(1 for segment in segments if _segment_identity(segment.segment_start, source_type) in existing_keys)


def _load_existing_keys(*, db, user_id: str, source_type: str) -> set[str]:
    rows = db.execute(
        select(RawSegment.segment_start)
        .where(RawSegment.user_id == user_id)
        .where(RawSegment.source_type == source_type)
        .where(RawSegment.granularity == "1h")
    ).all()
    return {_segment_identity(row[0], source_type) for row in rows}


def _segment_identity(segment_start, source_type: str) -> str:
    normalized = segment_start
    if getattr(normalized, "tzinfo", None) is not None:
        normalized = normalized.replace(tzinfo=None)
    normalized = normalized.replace(minute=0, second=0, microsecond=0)
    return f"{source_type}:{normalized.isoformat()}"


def print_summary(
    *,
    mode: str,
    result: FitbitImportResult,
    created_user_id: str | None,
    inserted: int,
    skipped_existing: int,
    dry_run: bool,
    preview_count: int,
) -> None:
    print(f"Mode:               {mode}")
    print(f"Discovered sources: {result.discovered_sources}")
    print(f"Processed sources:  {result.processed_sources}")
    print(f"Skipped sources:    {result.skipped_sources}")
    print(f"Generated segments: {len(result.segments)}")
    print(f"Dry run:            {dry_run}")
    if created_user_id:
        print(f"User id:            {created_user_id}")
    if not dry_run:
        print(f"Inserted segments:  {inserted}")
    print(f"Existing skipped:   {skipped_existing}")
    print(f"Metrics detected:   {json.dumps(result.metrics_detected, ensure_ascii=False)}")

    if result.segments:
        first = result.segments[0]
        last = result.segments[-1]
        print(f"Time range:         {first.segment_start.isoformat()} -> {last.segment_end.isoformat()}")
        print("Preview:")
        for segment in result.segments[: max(0, preview_count)]:
            print(
                json.dumps(
                    {
                        "segment_start": segment.segment_start.isoformat(),
                        "segment_end": segment.segment_end.isoformat(),
                        "raw_payload": segment.raw_payload,
                    },
                    ensure_ascii=False,
                )
            )

    if result.warnings:
        print("Warnings:")
        for warning in result.warnings[:20]:
            print(f"- {warning}")
        if len(result.warnings) > 20:
            print(f"- ... {len(result.warnings) - 20} more")


def print_fitabase_summary(
    *,
    result: FitabaseImportResult,
    inserted_users: int,
    inserted_segments: int,
    skipped_existing: int,
    dry_run: bool,
    preview_count: int,
    source_type: str,
    external_user_id_prefix: str,
) -> None:
    total_segments = sum(len(segments) for segments in result.user_segments.values())
    print("Mode:               fitabase_merged")
    print(f"Source type:        {source_type}")
    print(f"Discovered sources: {result.discovered_sources}")
    print(f"Processed sources:  {result.processed_sources}")
    print(f"Skipped sources:    {result.skipped_sources}")
    print(f"Detected users:     {len(result.user_segments)}")
    print(f"Generated segments: {total_segments}")
    print(f"Dry run:            {dry_run}")
    if not dry_run:
        print(f"Inserted users:     {inserted_users}")
        print(f"Inserted segments:  {inserted_segments}")
    print(f"Existing skipped:   {skipped_existing}")
    print(f"Metrics detected:   {json.dumps(result.metrics_detected, ensure_ascii=False)}")
    print("Preview users:")
    for source_user_id in sorted(result.user_segments)[: max(0, preview_count)]:
        segments = result.user_segments[source_user_id]
        first = segments[0]
        last = segments[-1]
        print(
            json.dumps(
                {
                    "source_user_id": source_user_id,
                    "external_user_id": f"{external_user_id_prefix}_{source_user_id}",
                    "segment_count": len(segments),
                    "time_range": [first.segment_start.isoformat(), last.segment_end.isoformat()],
                    "first_payload": first.raw_payload,
                },
                ensure_ascii=False,
            )
        )

    if result.warnings:
        print("Warnings:")
        for warning in result.warnings[:20]:
            print(f"- {warning}")
        if len(result.warnings) > 20:
            print(f"- ... {len(result.warnings) - 20} more")


if __name__ == "__main__":
    raise SystemExit(main())
