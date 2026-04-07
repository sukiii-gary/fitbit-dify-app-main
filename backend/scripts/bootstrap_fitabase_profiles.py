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
from app.models.raw_segment import RawSegment
from app.models.user import User
from app.services.profile_bootstrap_service import build_fitabase_profile_seed
from app.services.user_service import get_profile_or_404


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Populate profile/goals/baseline values for fitabase_* users.")
    parser.add_argument("--external-user-id", help="Only update one fitabase user.")
    parser.add_argument("--force", action="store_true", help="Overwrite non-empty profiles.")
    parser.add_argument("--dry-run", action="store_true", help="Preview generated profile seeds without writing to DB.")
    parser.add_argument("--print-first", type=int, default=3, help="How many generated profiles to preview.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    create_db_and_tables()

    updated = 0
    skipped = 0
    generated: list[dict] = []

    with SessionLocal() as db:
        query = select(User).where(User.external_user_id.like("fitabase_%")).order_by(User.external_user_id)
        if args.external_user_id:
            query = select(User).where(User.external_user_id == args.external_user_id)

        users = list(db.scalars(query))
        if not users:
            print("No matching fitabase users found.")
            return 1

        for user in users:
            profile = get_profile_or_404(db=db, user_id=user.id)
            has_existing = any(
                (
                    profile.profile_json,
                    profile.goals_json,
                    profile.thresholds_json,
                    profile.baseline_stats_json,
                    profile.system_prompt_prefix,
                )
            )
            if has_existing and not args.force:
                skipped += 1
                continue

            segments = list(
                db.scalars(
                    select(RawSegment)
                    .where(RawSegment.user_id == user.id)
                    .order_by(RawSegment.segment_start)
                )
            )
            if not segments:
                skipped += 1
                continue

            seed = build_fitabase_profile_seed(segments=segments, external_user_id=user.external_user_id)
            generated.append(
                {
                    "external_user_id": user.external_user_id,
                    "profile": seed.profile,
                    "goals": seed.goals,
                    "thresholds": seed.thresholds,
                    "baseline_stats": seed.baseline_stats,
                }
            )

            if args.dry_run:
                continue

            profile.profile_json = seed.profile
            profile.goals_json = seed.goals
            profile.thresholds_json = seed.thresholds
            profile.baseline_stats_json = seed.baseline_stats
            profile.system_prompt_prefix = seed.system_prompt_prefix
            db.add(profile)
            updated += 1

        if not args.dry_run:
            db.commit()

    print(f"Users matched:      {len(users)}")
    print(f"Profiles generated: {len(generated)}")
    print(f"Profiles updated:   {updated}")
    print(f"Profiles skipped:   {skipped}")
    print(f"Dry run:            {args.dry_run}")

    if generated:
        print("Preview:")
        for item in generated[: max(0, args.print_first)]:
            print(json.dumps(item, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
