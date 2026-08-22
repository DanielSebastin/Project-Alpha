from __future__ import annotations

import uuid
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.candidate_profile import CandidateProfile
from app.models.profile import Profile
from app.models.blueprint import (
    Blueprint,
    BlueprintMember,
    BlueprintInvitation,
    BlueprintInvitationStatus,
    BlueprintStatus,
)

from app.models.user import User
from app.schemas.blueprint import SlotRecommendation, BlueprintRecommendationsResponse
from app.services.recommendations import (
    _assessment_compatibility,
    _skill_names,
    _build_bio,
    _normalize,
)

ROLE_WEIGHT = 20
SKILL_WEIGHT = 30
EXPERIENCE_WEIGHT = 10
AVAILABILITY_WEIGHT = 10
ASSESSMENT_WEIGHT = 30


def recommend_for_blueprint(
    db: Session,
    blueprint_id: uuid.UUID,
    requester: User,
    limit_per_slot: int = 10,
) -> List[BlueprintRecommendationsResponse]:
    blueprint = db.query(Blueprint).filter(Blueprint.id == blueprint_id).first()
    if not blueprint:
        raise ValueError("Blueprint not found")

    membership = (
        db.query(BlueprintMember)
        .filter(
            BlueprintMember.blueprint_id == blueprint_id,
            BlueprintMember.user_id == requester.id,
        )
        .first()
    )
    if not membership:
        raise ValueError("Only members can view recommendations")

    # ── Build exclusion set ────────────────────────────────────────────────────

    # 1. Members of this blueprint
    blueprint_member_ids = {m.user_id for m in blueprint.members}



    # 3. Members of any FULL blueprint (the new system) — exclude people already
    #    committed to another complete blueprint team.
    full_blueprint_user_ids = set(
        db.execute(
            select(BlueprintMember.user_id)
            .join(Blueprint, Blueprint.id == BlueprintMember.blueprint_id)
            .filter(
                Blueprint.status == BlueprintStatus.FULL,
                Blueprint.id != blueprint_id,  # don't exclude own blueprint members twice
            )
        )
        .scalars()
        .all()
    )

    # 4. Users who already have a pending invitation from this blueprint
    pending_receiver_ids = set(
        db.execute(
            select(BlueprintInvitation.receiver_id)
            .filter(
                BlueprintInvitation.blueprint_id == blueprint_id,
                BlueprintInvitation.status == BlueprintInvitationStatus.PENDING,
            )
        )
        .scalars()
        .all()
    )

    excluded_ids = (
        blueprint_member_ids
        | full_blueprint_user_ids
        | pending_receiver_ids
    )

    # ── Fetch candidates ───────────────────────────────────────────────────────
    query = (
        db.query(CandidateProfile, Profile, User)
        .join(Profile, Profile.user_id == CandidateProfile.user_id)
        .join(User, User.id == CandidateProfile.user_id)
        .filter(CandidateProfile.profile_data["ability"].has_key("skills"))
    )
    if excluded_ids:
        query = query.filter(~User.id.in_(excluded_ids))

    rows = query.all()

    # ── Score per slot ─────────────────────────────────────────────────────────
    results = []

    for slot in blueprint.slots:
        if slot.status.value != "OPEN":
            continue

        slot_role = _normalize(slot.role)
        slot_skills = {_normalize(s.name) for s in slot.preferred_skills}

        slot_recommendations = []

        for candidate, profile, user in rows:
            data = candidate.profile_data or {}
            cand_role = (data.get("role") or {}).get("role") or "unknown"

            # Role match (20 pts)
            role_score = ROLE_WEIGHT if _normalize(cand_role) == slot_role else 0

            # Skill match (30 pts) — proportional to overlap fraction
            candidate_skills = _skill_names(data)
            skill_overlap = [s for s in candidate_skills if _normalize(s) in slot_skills]
            if slot_skills:
                skill_score = round(SKILL_WEIGHT * len(skill_overlap) / len(slot_skills))
            else:
                skill_score = SKILL_WEIGHT // 2

            # Experience (10 pts) — present = full points
            exp_level = (data.get("experience") or {}).get("level") or "unknown"
            exp_score = EXPERIENCE_WEIGHT if exp_level != "unknown" else 0

            # Availability (10 pts)
            commitment = (data.get("availability") or {}).get("commitment_level") or ""
            avail_score = AVAILABILITY_WEIGHT if commitment else 0

            # Assessment compatibility (30 pts)
            assessment_score = _assessment_compatibility(data)

            total = role_score + skill_score + exp_score + avail_score + assessment_score

            slot_recommendations.append(
                SlotRecommendation(
                    user_id=user.id,
                    name=profile.name,
                    avatar_url=profile.avatar_url,
                    college=profile.college,
                    city=profile.city,
                    github_url=profile.github_url,
                    bio=_build_bio(profile, data),
                    role=cand_role,
                    skills=candidate_skills,
                    experience_level=exp_level,
                    commitment_level=commitment,
                    profile_strength=candidate.profile_strength or 0,
                    compatibility_score=total,
                    skill_overlap=skill_overlap,
                )
            )

        slot_recommendations.sort(key=lambda r: r.compatibility_score, reverse=True)

        results.append(
            BlueprintRecommendationsResponse(
                slot_id=slot.id,
                slot_role=slot.role,
                recommendations=slot_recommendations[:limit_per_slot],
            )
        )

    return results
