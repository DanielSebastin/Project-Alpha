"""
This module's sole purpose is to make every table known to
Base.metadata so that Alembic autogenerate and create_all() work.

Import this module (not base_class) in:
  - alembic/env.py
  - app/db/init_db.py

Application code (models, schemas, routes) should import Base from
app.db.base_class to avoid circular imports.
"""
from app.db.base_class import Base  # noqa: F401

# ── Model imports ─────────────────────────────────────────────
from app.models.user import User                                    # noqa: F401, E402
from app.models.profile import Profile                              # noqa: F401, E402
from app.models.availability import Availability                    # noqa: F401, E402
from app.models.project import Project                              # noqa: F401, E402
from app.models.skill import Skill, SkillEvidence                   # noqa: F401, E402
from app.models.personality import Personality                      # noqa: F401, E402
from app.models.resume import Resume                                # noqa: F401, E402
from app.models.resume_verification import ResumeVerification       # noqa: F401, E402
from app.models.assessment import AssessmentSession                 # noqa: F401, E402
from app.models.collaboration import (                              # noqa: F401, E402
    CollaborationQuestion,
    CollaborationAssessment,
    CollaborationAssessmentQuestion,
    CollaborationAnswer,
)
from app.models.candidate_profile import CandidateProfile           # noqa: F401, E402
from app.models.blueprint import Blueprint                          # noqa: F401, E402
