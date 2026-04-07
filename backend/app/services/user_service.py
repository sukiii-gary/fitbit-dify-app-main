from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.raw_segment import RawSegment
from app.models.user import User
from app.models.user_profile import UserProfile
from app.schemas.user import UserCreateRequest, UserProfileUpdateRequest


def create_user(db: Session, payload: UserCreateRequest) -> User:
    existing = db.scalar(select(User).where(User.external_user_id == payload.external_user_id))
    if existing:
        return existing

    user = User(
        external_user_id=payload.external_user_id,
        name=payload.name,
        timezone=payload.timezone,
    )
    profile = UserProfile(user=user)
    db.add_all([user, profile])
    db.commit()
    db.refresh(user)
    return user


def get_user_or_404(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if not user:
        raise ValueError("User not found")
    return user


def get_profile_or_404(db: Session, user_id: str) -> UserProfile:
    user = get_user_or_404(db=db, user_id=user_id)
    if not user.profile:
        user.profile = UserProfile(user_id=user.id)
        db.add(user.profile)
        db.commit()
        db.refresh(user.profile)
    return user.profile


def list_users(db: Session, *, q: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    normalized_limit = max(1, min(limit, 200))
    normalized_offset = max(0, offset)

    filters = []
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        filters.append(or_(User.external_user_id.ilike(pattern), User.name.ilike(pattern)))

    total_query = select(func.count()).select_from(User)
    if filters:
        total_query = total_query.where(*filters)
    total = int(db.scalar(total_query) or 0)

    stmt = (
        select(
            User.id,
            User.external_user_id,
            User.name,
            User.timezone,
            User.created_at,
            func.count(RawSegment.id).label("segment_count"),
            func.max(RawSegment.segment_start).label("last_segment_at"),
        )
        .select_from(User)
        .outerjoin(RawSegment, RawSegment.user_id == User.id)
        .group_by(User.id)
        .order_by(func.max(RawSegment.segment_start).desc().nullslast(), User.external_user_id.asc())
        .limit(normalized_limit)
        .offset(normalized_offset)
    )
    if filters:
        stmt = stmt.where(*filters)

    rows = db.execute(stmt).all()
    items = [
        {
            "id": row.id,
            "external_user_id": row.external_user_id,
            "name": row.name,
            "timezone": row.timezone,
            "created_at": row.created_at,
            "segment_count": int(row.segment_count or 0),
            "last_segment_at": row.last_segment_at,
        }
        for row in rows
    ]
    return items, total


def update_profile(db: Session, user_id: str, payload: UserProfileUpdateRequest) -> UserProfile:
    profile = get_profile_or_404(db=db, user_id=user_id)
    profile.profile_json = payload.profile
    profile.goals_json = payload.goals
    profile.thresholds_json = payload.thresholds
    profile.baseline_stats_json = payload.baseline_stats
    profile.system_prompt_prefix = payload.system_prompt_prefix
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile
