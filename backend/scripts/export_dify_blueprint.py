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
from app.dify.prompt_builder import build_analysis_payload
from app.dify.workflow_spec import build_workflow_blueprint
from app.models.raw_segment import RawSegment
from app.models.user import User
from app.schemas.segment import PredictionRequest
from app.services.memory_service import build_rolling_memory_summary
from app.services.prediction_service import predict_for_segment
from app.services.segment_service import get_segment_or_404
from app.services.user_service import get_profile_or_404


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a Dify workflow blueprint and optional sample payload.")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT_DIR.parent / "data" / "processed" / "dify-workflow-blueprint.json",
        help="Output path for the generated blueprint JSON.",
    )
    parser.add_argument("--segment-id", help="Optional segment id to embed a sample API payload.")
    parser.add_argument(
        "--external-user-id",
        help="Optional external user id. If provided without --segment-id, the latest segment for that user is used.",
    )
    parser.add_argument(
        "--user-query",
        default="请解释这一段 Fitbit 数据，并给出个性化建议。",
        help="User query to include in the sample payload.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    create_db_and_tables()

    sample_payload = None
    with SessionLocal() as db:
        segment_id = args.segment_id or _latest_segment_id_for_external_user(db=db, external_user_id=args.external_user_id)
        if segment_id:
            sample_payload = build_sample_payload(db=db, segment_id=segment_id, user_query=args.user_query)

    blueprint = build_workflow_blueprint(sample_payload=sample_payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(blueprint, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote Dify workflow blueprint to: {args.output}")
    if sample_payload:
        print(f"Embedded sample payload for segment: {sample_payload['inputs']['segment_id']}")
    else:
        print("No sample payload embedded. Pass --segment-id or --external-user-id if you want one.")
    return 0


def build_sample_payload(*, db, segment_id: str, user_query: str) -> dict:
    segment = get_segment_or_404(db=db, segment_id=segment_id)
    profile = get_profile_or_404(db=db, user_id=segment.user_id)
    prediction = predict_for_segment(db=db, segment_id=segment_id, payload=PredictionRequest())
    memory_summary = build_rolling_memory_summary(db=db, user_id=segment.user_id)

    return build_analysis_payload(
        user_id=segment.user_id,
        segment_id=segment.id,
        profile=profile,
        raw_payload=segment.raw_payload_json,
        model_output={
            "top_label": prediction.top_label,
            "probabilities": prediction.probabilities,
        },
        rolling_memory_summary=memory_summary,
        user_query=user_query,
    )


def _latest_segment_id_for_external_user(*, db, external_user_id: str | None) -> str | None:
    if not external_user_id:
        return None

    user = db.scalar(select(User).where(User.external_user_id == external_user_id))
    if not user:
        return None

    segment = db.scalar(
        select(RawSegment)
        .where(RawSegment.user_id == user.id)
        .order_by(RawSegment.segment_start.desc())
        .limit(1)
    )
    return segment.id if segment else None


if __name__ == "__main__":
    raise SystemExit(main())
