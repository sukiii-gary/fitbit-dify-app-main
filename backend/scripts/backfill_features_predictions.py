from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import aliased

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db.session import SessionLocal, create_db_and_tables
from app.ml.feature_engineering import build_feature_vector
from app.ml.predictor import Predictor
from app.models.feature_vector import FeatureVector
from app.models.model_prediction import ModelPrediction
from app.models.raw_segment import RawSegment
from app.models.user import User


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill missing feature vectors and predictions for raw segments.")
    parser.add_argument("--external-user-id", help="Only process segments for one external user id.")
    parser.add_argument("--source-type", help="Only process segments from one source_type.")
    parser.add_argument("--feature-version", default="v1", help="Feature version to backfill.")
    parser.add_argument("--model-name", default="xgboost-fatigue", help="Model name to backfill.")
    parser.add_argument("--model-version", default="v1", help="Model version to backfill.")
    parser.add_argument("--limit", type=int, help="Optional limit on matching segments.")
    parser.add_argument("--offset", type=int, default=0, help="Optional offset for matching segments.")
    parser.add_argument("--batch-size", type=int, default=250, help="Commit every N updated segments.")
    parser.add_argument("--dry-run", action="store_true", help="Count pending work without writing to the database.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    create_db_and_tables()
    predictor = Predictor()

    feature_alias = aliased(FeatureVector)
    prediction_alias = aliased(ModelPrediction)

    filters = [or_(feature_alias.id.is_(None), prediction_alias.id.is_(None))]
    if args.external_user_id:
        filters.append(User.external_user_id == args.external_user_id)
    if args.source_type:
        filters.append(RawSegment.source_type == args.source_type)

    with SessionLocal() as db:
        count_stmt = (
            select(func.count())
            .select_from(RawSegment)
            .join(User, User.id == RawSegment.user_id)
            .outerjoin(
                feature_alias,
                and_(
                    feature_alias.segment_id == RawSegment.id,
                    feature_alias.feature_version == args.feature_version,
                ),
            )
            .outerjoin(
                prediction_alias,
                and_(
                    prediction_alias.feature_vector_id == feature_alias.id,
                    prediction_alias.model_name == args.model_name,
                    prediction_alias.model_version == args.model_version,
                ),
            )
            .where(*filters)
        )
        total = int(db.scalar(count_stmt) or 0)
        if total == 0:
            print("Matching segments needing backfill: 0")
            return 0

        stmt = (
            select(RawSegment, User.external_user_id, feature_alias, prediction_alias)
            .select_from(RawSegment)
            .join(User, User.id == RawSegment.user_id)
            .outerjoin(
                feature_alias,
                and_(
                    feature_alias.segment_id == RawSegment.id,
                    feature_alias.feature_version == args.feature_version,
                ),
            )
            .outerjoin(
                prediction_alias,
                and_(
                    prediction_alias.feature_vector_id == feature_alias.id,
                    prediction_alias.model_name == args.model_name,
                    prediction_alias.model_version == args.model_version,
                ),
            )
            .where(*filters)
            .order_by(User.external_user_id.asc(), RawSegment.segment_start.asc())
            .offset(max(0, args.offset))
        )
        if args.limit:
            stmt = stmt.limit(max(1, args.limit))

        processed = 0
        pending_features = 0
        pending_predictions = 0
        features_created = 0
        predictions_created = 0
        dirty_since_commit = 0

        for segment, external_user_id, feature_vector, prediction in db.execute(stmt):
            processed += 1
            needs_feature = feature_vector is None
            needs_prediction = prediction is None

            if needs_feature:
                pending_features += 1
            if needs_prediction:
                pending_predictions += 1

            if args.dry_run:
                continue

            if feature_vector is None:
                feature_vector = FeatureVector(
                    segment_id=segment.id,
                    feature_version=args.feature_version,
                    features_json=build_feature_vector(segment.raw_payload_json),
                )
                db.add(feature_vector)
                db.flush()
                features_created += 1
                dirty_since_commit += 1

            if prediction is None:
                top_label, probabilities = predictor.predict(
                    features=feature_vector.features_json,
                    model_name=args.model_name,
                    model_version=args.model_version,
                )
                db.add(
                    ModelPrediction(
                        feature_vector_id=feature_vector.id,
                        model_name=args.model_name,
                        model_version=args.model_version,
                        top_label=top_label,
                        probabilities_json=probabilities,
                    )
                )
                predictions_created += 1
                dirty_since_commit += 1

            if dirty_since_commit >= max(1, args.batch_size):
                db.commit()
                dirty_since_commit = 0
                print(
                    f"Processed {processed} segments..."
                    f" features_created={features_created}"
                    f" predictions_created={predictions_created}"
                    f" latest_user={external_user_id}"
                )

        if not args.dry_run and dirty_since_commit > 0:
            db.commit()

    print(f"Matching segments needing backfill: {total}")
    print(f"Processed:                       {processed}")
    print(f"Pending features:                {pending_features}")
    print(f"Pending predictions:             {pending_predictions}")
    print(f"Features created:                {features_created}")
    print(f"Predictions created:             {predictions_created}")
    print(f"Dry run:                         {args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
