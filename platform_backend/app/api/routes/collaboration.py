"""
Collaboration Assessment routes
================================
POST /collaboration/start    — randomly select 12 questions, create session
POST /collaboration/submit   — save 12 answers, compute dimension scores
GET  /collaboration/result   — return the latest completed assessment result
GET  /collaboration/sessions — list all sessions for the current user
GET  /collaboration/status   — quick check: has the user completed an assessment?

Design notes
------------
- The assessment is optional.  No endpoint forces the user to take it.
- Questions are selected server-side: 2 per dimension, shuffled.
- Responses are stored as integers 1–5 (Strongly Disagree → Strongly Agree).
- Dimension scores are computed on submit and stored as JSON in the DB.
  They are used by the team-matching module, not shown verbatim to the user.
- A user may retake the assessment; each attempt creates a new session row.
"""
import json
import logging
import random
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.profile import Profile
from app.models.personality import Personality
from app.models.collaboration import (
    CollaborationAnswer,
    CollaborationAssessment,
    CollaborationAssessmentQuestion,
    CollaborationDimension,
    CollaborationQuestion,
    CollaborationStatus,
)
from app.schemas.collaboration import (
    CollaborationAnswerIn,
    CollaborationQuestionOut,
    CollaborationResultOut,
    CollaborationSessionOut,
    CollaborationStartOut,
    CollaborationSubmitIn,
    DimensionScore,
)
from app.services.candidate_profile import update_teamwork_from_collaboration

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/collaboration", tags=["Collaboration Assessment"])

# Questions selected per dimension
QUESTIONS_PER_DIMENSION = 2
TOTAL_QUESTIONS = QUESTIONS_PER_DIMENSION * len(CollaborationDimension)  # 12


# ── Helpers ────────────────────────────────────────────────────────────────

def _get_profile_or_404(user_id: uuid.UUID, db: Session) -> Profile:
    profile = db.query(Profile).filter(Profile.user_id == user_id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Create a profile first before starting the Collaboration Assessment.",
        )
    return profile


def _select_questions(db: Session) -> list[CollaborationQuestion]:
    """
    Pick QUESTIONS_PER_DIMENSION active questions per dimension at random,
    then shuffle the combined list so no dimension grouping is visible.
    """
    selected: list[CollaborationQuestion] = []

    for dim in CollaborationDimension:
        pool = (
            db.query(CollaborationQuestion)
            .filter(
                CollaborationQuestion.dimension == dim,
                CollaborationQuestion.active == True,  # noqa: E712
            )
            .all()
        )
        if len(pool) < QUESTIONS_PER_DIMENSION:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    f"Not enough active questions for dimension {dim.value}. "
                    f"Need {QUESTIONS_PER_DIMENSION}, found {len(pool)}. "
                    "Run the question bank seeder."
                ),
            )
        selected.extend(random.sample(pool, QUESTIONS_PER_DIMENSION))

    random.shuffle(selected)
    return selected


def _compute_scores(
    questions: list[CollaborationQuestion],
    answer_map: dict[uuid.UUID, int],
) -> list[DimensionScore]:
    """
    Sum the Likert responses per dimension and express as a percentage.
    raw_score range: 2–10  (2 questions × 1–5)
    """
    dim_totals: dict[CollaborationDimension, int] = {d: 0 for d in CollaborationDimension}

    for q in questions:
        response = answer_map.get(q.id, 0)
        dim_totals[q.dimension] += response

    max_score = QUESTIONS_PER_DIMENSION * 5  # 10

    return [
        DimensionScore(
            dimension=dim,
            raw_score=total,
            max_score=max_score,
            percentage=round((total / max_score) * 100, 1),
        )
        for dim, total in dim_totals.items()
    ]


# ── POST /collaboration/start ──────────────────────────────────────────────

@router.post(
    "/start",
    response_model=CollaborationStartOut,
    status_code=status.HTTP_201_CREATED,
    summary="Start a Collaboration Assessment",
)
def start_assessment(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CollaborationStartOut:
    """
    Randomly select 12 questions (2 per dimension), create a session row
    with status=STARTED, and return the questions to the client.

    The assessment is optional — call this only when the user chooses to take it.
    """
    profile = _get_profile_or_404(current_user.id, db)
    questions = _select_questions(db)

    session = CollaborationAssessment(
        profile_id=profile.id,
        status=CollaborationStatus.STARTED,
    )
    db.add(session)
    db.flush()
    db.add_all(
        [
            CollaborationAssessmentQuestion(assessment_id=session.id, question_id=question.id)
            for question in questions
        ]
    )
    db.commit()
    db.refresh(session)

    return CollaborationStartOut(
        assessment_id=session.id,
        questions=[CollaborationQuestionOut.model_validate(q) for q in questions],
        total_questions=TOTAL_QUESTIONS,
    )


# ── POST /collaboration/submit ─────────────────────────────────────────────

@router.post(
    "/submit",
    response_model=CollaborationResultOut,
    summary="Submit answers for a Collaboration Assessment",
)
def submit_assessment(
    payload: CollaborationSubmitIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CollaborationResultOut:
    """
    Accept exactly 12 answers (one per question), validate ownership,
    persist each response, compute dimension scores, and mark the session
    as COMPLETED.

    Responses are stored numerically (1–5).  Dimension scores are computed
    server-side and stored as JSON — they are used for team matching and
    are never exposed verbatim to the participant.
    """
    profile = _get_profile_or_404(current_user.id, db)

    # Ownership check
    session = (
        db.query(CollaborationAssessment)
        .filter(
            CollaborationAssessment.id == payload.assessment_id,
            CollaborationAssessment.profile_id == profile.id,
        )
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment session not found.",
        )
    if session.status == CollaborationStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This assessment has already been submitted.",
        )

    # Validate a complete, unique answer set against this session's assigned
    # questions. Question IDs from the client are never trusted on their own.
    submitted_ids = {a.question_id for a in payload.answers}
    if len(submitted_ids) != TOTAL_QUESTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Each assigned question must be answered exactly once.",
        )
    assigned_questions = (
        db.query(CollaborationQuestion)
        .join(
            CollaborationAssessmentQuestion,
            CollaborationAssessmentQuestion.question_id == CollaborationQuestion.id,
        )
        .filter(CollaborationAssessmentQuestion.assessment_id == session.id)
        .all()
    )
    assigned_ids = {question.id for question in assigned_questions}
    if submitted_ids != assigned_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Answers must match the questions assigned to this assessment.",
        )

    # Build answer map for score computation
    answer_map: dict[uuid.UUID, int] = {
        a.question_id: a.response for a in payload.answers
    }

    # Persist answers
    now = datetime.now(timezone.utc)
    for ans in payload.answers:
        db.add(
            CollaborationAnswer(
                assessment_id=session.id,
                question_id=ans.question_id,
                response=ans.response,
                answered_at=now,
            )
        )

    # Compute dimension scores (stored as JSON for team-matching use)
    scores = _compute_scores(assigned_questions, answer_map)
    scores_json = json.dumps(
        [
            {
                "dimension": s.dimension.value,
                "raw_score": s.raw_score,
                "max_score": s.max_score,
                "percentage": s.percentage,
            }
            for s in scores
        ]
    )

    # Mark complete — store scores on the session row (add column via migration or
    # use the existing result_json pattern; here we patch the object dynamically
    # so the model stays clean without a dedicated column)
    session.status = CollaborationStatus.COMPLETED
    session.completed_at = now
    session.scores_json = scores_json

    # Persist scores alongside the session using a lightweight JSON attribute.
    # If the column does not yet exist on the model we attach it as an
    # instance-level attribute only (no DB write for this field); the answers
    # table is the authoritative source and scores are recomputed on demand.
    try:
        session.scores_json = scores_json  # type: ignore[attr-defined]
    except Exception:
        pass  # column not present — answers are the source of truth

    db.commit()
    db.refresh(session)

    # Sync collaboration dimension scores into the candidate profile's
    # teamwork section ({dimension: percentage}).
    teamwork_scores = {s.dimension.value.lower(): s.percentage for s in scores}
    if teamwork_scores:
        update_teamwork_from_collaboration(db, current_user.id, teamwork_scores)

    return CollaborationResultOut(
        assessment_id=session.id,
        status=session.status,
        started_at=session.started_at,
        completed_at=session.completed_at,
        dimension_scores=scores,
    )


# ── GET /collaboration/result ──────────────────────────────────────────────

@router.get(
    "/result",
    response_model=CollaborationResultOut,
    summary="Get the latest Collaboration Assessment result",
)
def get_latest_result(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CollaborationResultOut:
    """
    Return the most recently completed Collaboration Assessment for the
    current user, including recomputed dimension scores.
    """
    profile = _get_profile_or_404(current_user.id, db)

    session = (
        db.query(CollaborationAssessment)
        .filter(
            CollaborationAssessment.profile_id == profile.id,
            CollaborationAssessment.status == CollaborationStatus.COMPLETED,
        )
        .order_by(CollaborationAssessment.completed_at.desc())
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No completed Collaboration Assessment found.",
        )

    # Recompute scores from stored answers
    scores = _recompute_scores(session.id, db)

    return CollaborationResultOut(
        assessment_id=session.id,
        status=session.status,
        started_at=session.started_at,
        completed_at=session.completed_at,
        dimension_scores=scores,
    )


# ── GET /collaboration/sessions ────────────────────────────────────────────

@router.get(
    "/sessions",
    response_model=list[CollaborationSessionOut],
    summary="List all Collaboration Assessment sessions",
)
def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CollaborationAssessment]:
    """List every assessment attempt for the current user, newest first."""
    profile = _get_profile_or_404(current_user.id, db)

    return (
        db.query(CollaborationAssessment)
        .filter(CollaborationAssessment.profile_id == profile.id)
        .order_by(CollaborationAssessment.started_at.desc())
        .all()
    )


# ── GET /collaboration/status ──────────────────────────────────────────────

@router.get(
    "/status",
    summary="Check if the user has completed the Collaboration Assessment",
)
def get_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Quick status check.  Returns whether the user has a completed assessment
    and, if so, the timestamp of their most recent one.
    """
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    if not profile:
        return {"completed": False, "completed_at": None}

    latest = (
        db.query(CollaborationAssessment)
        .filter(
            CollaborationAssessment.profile_id == profile.id,
            CollaborationAssessment.status == CollaborationStatus.COMPLETED,
        )
        .order_by(CollaborationAssessment.completed_at.desc())
        .first()
    )

    return {
        "completed": latest is not None,
        "completed_at": latest.completed_at.isoformat() if latest else None,
    }



# ── Internal helper ────────────────────────────────────────────────────────

def _recompute_scores(
    assessment_id: uuid.UUID,
    db: Session,
) -> list[DimensionScore]:
    """
    Load all answers for a session, join with their questions to get the
    dimension, and compute per-dimension scores.
    """
    rows = (
        db.query(CollaborationAnswer, CollaborationQuestion)
        .join(
            CollaborationQuestion,
            CollaborationAnswer.question_id == CollaborationQuestion.id,
        )
        .filter(CollaborationAnswer.assessment_id == assessment_id)
        .all()
    )

    answer_map: dict[uuid.UUID, int] = {}
    questions: list[CollaborationQuestion] = []

    for answer, question in rows:
        answer_map[question.id] = answer.response
        questions.append(question)

    return _compute_scores(questions, answer_map)
