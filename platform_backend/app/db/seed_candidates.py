"""
Candidate Profiles Seeder
==========================
Generates realistic candidate_profiles rows for the Regular Team Formation
MVP.  A candidate_profiles row requires a users row (user_id FK) and the
browse API joins the profile for name / college / city / github_url /
avatar_url, so each candidate also gets a matching `users` + `profiles` row.

profile_data follows the Phase 1 contract exactly:
    role, ability, behavior, evidence, teamwork, experience, availability
(see app/services/candidate_profile_builder.py for the canonical shape).

Run:
    python -m app.db.seed_candidates                # 75 candidates
    python -m app.db.seed_candidates --count 100    # custom count
    python -m app.db.seed_candidates --clear        # delete seeded candidates first
"""
import random
import uuid
from datetime import datetime, timezone

from app.db.session import SessionLocal
import app.db.base  # noqa: F401 — registers all models with the SQLAlchemy mapper
from app.models.candidate_profile import CandidateProfile
from app.models.profile import ExperienceLevel, Profile
from app.models.user import User
from app.services.candidate_profile import calculate_profile_strength
from app.utils.skill_normalizer import normalize_skill_name

# Emails on a reserved TLD so --clear can target only seeded rows.
EMAIL_SUFFIX = "@hackitup.example"

# ---------------------------------------------------------------------------
# Randomized building blocks
# ---------------------------------------------------------------------------
ROLE_SKILLS: dict[str, list[str]] = {
    "backend_developer": [
        "Python", "FastAPI", "Django", "Node.js", "PostgreSQL", "Redis",
        "SQLAlchemy", "REST APIs", "Docker", "Microservices",
    ],
    "frontend_developer": [
        "React", "TypeScript", "JavaScript", "CSS", "HTML", "Tailwind CSS",
        "Next.js", "Vite", "Redux", "Web Accessibility",
    ],
    "fullstack_developer": [
        "React", "Node.js", "TypeScript", "PostgreSQL", "Express", "Next.js",
        "Docker", "REST APIs", "MongoDB", "Tailwind CSS",
    ],
    "ml_engineer": [
        "Python", "PyTorch", "TensorFlow", "scikit-learn", "Pandas", "NumPy",
        "LangChain", "Transformers", "MLOps", "OpenAI API",
    ],
    "cloud_engineer": [
        "AWS", "Azure", "GCP", "Terraform", "Kubernetes", "Docker",
        "CI/CD", "Linux", "Serverless", "Infrastructure as Code",
    ],
    "devops_engineer": [
        "Docker", "Kubernetes", "Jenkins", "GitHub Actions", "Terraform",
        "AWS", "Linux", "Prometheus", "Grafana", "Ansible",
    ],
    "mobile_developer": [
        "React Native", "Flutter", "Kotlin", "Swift", "Android", "iOS",
        "Firebase", "Expo", "GraphQL", "SQLite",
    ],
    "data_engineer": [
        "Python", "Apache Spark", "SQL", "dbt", "Airflow", "Kafka",
        "PostgreSQL", "BigQuery", "Snowflake", "ETL",
    ],
    "cybersecurity": [
        "Python", "Kali Linux", "Burp Suite", "Network Security", "OWASP",
        "Penetration Testing", "Wireshark", "Cryptography", "Splunk", "SIEM",
    ],
    "other": [
        "Python", "TypeScript", "Linux", "Git", "Docker",
        "REST APIs", "SQL", "Data Analysis",
    ],
}

ROLE_LABELS: dict[str, str] = {
    "backend_developer": "Backend Developer",
    "frontend_developer": "Frontend Developer",
    "fullstack_developer": "Fullstack Developer",
    "ml_engineer": "ML Engineer",
    "cloud_engineer": "Cloud Engineer",
    "devops_engineer": "DevOps Engineer",
    "mobile_developer": "Mobile Developer",
    "data_engineer": "Data Engineer",
    "cybersecurity": "Cybersecurity Analyst",
    "other": "Generalist Developer",
}

SKILL_CATEGORY: dict[str, str] = {
    "Python": "Language", "TypeScript": "Language", "JavaScript": "Language",
    "Java": "Language", "C++": "Language", "Go": "Language", "Rust": "Language",
    "Kotlin": "Language", "Swift": "Language", "SQL": "Language",
    "HTML": "Language", "CSS": "Language",
    "React": "Frontend", "Next.js": "Frontend", "Vue": "Frontend",
    "Tailwind CSS": "Frontend", "Redux": "Frontend", "Vite": "Frontend",
    "Flutter": "Mobile", "React Native": "Mobile", "Expo": "Mobile",
    "Android": "Mobile", "iOS": "Mobile",
    "FastAPI": "Backend", "Django": "Backend", "Node.js": "Backend",
    "Express": "Backend", "REST APIs": "Backend", "SQLAlchemy": "Backend",
    "GraphQL": "Backend", "Microservices": "Backend",
    "PostgreSQL": "Database", "Redis": "Database", "MongoDB": "Database",
    "SQLite": "Database", "BigQuery": "Database", "Snowflake": "Database",
    "PyTorch": "ML/AI", "TensorFlow": "ML/AI", "scikit-learn": "ML/AI",
    "Pandas": "ML/AI", "NumPy": "ML/AI", "LangChain": "ML/AI",
    "Transformers": "ML/AI", "OpenAI API": "ML/AI", "MLOps": "ML/AI",
    "AWS": "Cloud", "Azure": "Cloud", "GCP": "Cloud", "Terraform": "Cloud",
    "Kubernetes": "DevOps", "Docker": "DevOps", "CI/CD": "DevOps",
    "Jenkins": "DevOps", "GitHub Actions": "DevOps", "Ansible": "DevOps",
    "Prometheus": "DevOps", "Grafana": "DevOps", "Linux": "DevOps",
    "Kafka": "Data", "Apache Spark": "Data", "dbt": "Data", "Airflow": "Data",
    "ETL": "Data",
    "Kali Linux": "Security", "Burp Suite": "Security", "OWASP": "Security",
    "Wireshark": "Security", "Cryptography": "Security", "Splunk": "Security",
    "SIEM": "Security", "Network Security": "Security",
    "Penetration Testing": "Security", "Git": "Tooling",
    "Data Analysis": "Data", "Web Accessibility": "Frontend",
    "Serverless": "Cloud", "Infrastructure as Code": "Cloud",
}

SOURCES = ["resume", "github", "assessment", "manual"]
SKILL_SOURCES = ["resume", "github", "assessment"]

# Canonical (normalized) category lookup — profile_data skill names are
# stored lowercase (e.g. "python", "nodejs"), matching skill_normalizer.
NORMALIZED_CATEGORY: dict[str, str] = {
    normalize_skill_name(name): category
    for name, category in SKILL_CATEGORY.items()
}

FIRST_NAMES = [
    "Aarav", "Priya", "Rohan", "Ananya", "Vikram", "Sneha", "Aditya", "Kavya",
    "Arjun", "Meera", "Rahul", "Ishita", "Nikhil", "Divya", "Karan", "Pooja",
    "Ravi", "Sanya", "Varun", "Nandini", "Sameer", "Tanvi", "Harsh", "Aisha",
    "Kunal", "Ritika", "Manav", "Shreya", "Dev", "Anjali",
]
LAST_NAMES = [
    "Sharma", "Patel", "Singh", "Reddy", "Nair", "Iyer", "Gupta", "Mehta",
    "Kulkarni", "Joshi", "Desai", "Bhatt", "Kumar", "Verma", "Malhotra",
    "Rao", "Menon", "Chauhan", "Mishra", "Pillai", "Das", "Bose", "Kapoor",
    "Agarwal", "Saxena", "Trivedi", "Ghosh", "Banerjee", "Chopra", "Sinha",
]
COLLEGES = [
    "IIT Bombay", "IIT Delhi", "IIT Madras", "NIT Trichy", "VIT Vellore",
    "BITS Pilani", "IIIT Hyderabad", "Anna University", "DTU Delhi",
    "Manipal Institute of Technology", "Thapar Institute", "SRM University",
]
DEGREES = [
    ("B.Tech", "Computer Science"),
    ("B.Tech", "Information Technology"),
    ("B.Tech", "Electronics & Communication"),
    ("B.E.", "Computer Science"),
    ("M.Tech", "Computer Science"),
    ("B.Sc.", "Computer Science"),
    ("BCA", "Computer Applications"),
]
CITIES = [
    "Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Chennai", "Pune",
    "Kolkata", "Ahmedabad", "Jaipur", "Chandigarh", "Kochi", "Lucknow",
]
STATES = [
    "Maharashtra", "Delhi", "Karnataka", "Telangana", "Tamil Nadu", "Punjab",
    "West Bengal", "Gujarat", "Rajasthan", "Kerala", "Uttar Pradesh",
]
TIMEZONES = [
    "Asia/Kolkata", "Asia/Kolkata", "Asia/Kolkata", "UTC", "US/Pacific",
    "US/Eastern", "Europe/London", "Asia/Singapore", "Australia/Sydney",
    "Europe/Berlin", "America/Sao_Paulo", "Africa/Lagos",
]
WORKING_HOURS = [
    "9 AM - 5 PM", "10 AM - 6 PM", "Flexible", "Evenings (6 PM - 10 PM)",
    "Mornings (7 AM - 12 PM)", "2 PM - 10 PM",
]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
WEEKEND = ["Saturday", "Sunday"]

WORK_STYLES = [
    "Structured and plan-first", "Fast and iterative",
    "Deep-focus sprints", "Collaborative and adaptive",
]
COMMUNICATION_STYLES = [
    "Direct and concise", "Detailed and thorough",
    "Async-friendly", "Visual and hands-on",
]
STRENGTHS = [
    "Reliability", "Creativity", "Adaptability", "Attention to detail",
    "Strong communicator", "Self-starter", "Team player", "Problem solving",
]
TEAMWORK_DIMENSIONS = [
    "Communication", "Leadership", "Collaboration", "Reliability",
    "Adaptability", "Initiative",
]

# Weighted experience level distribution (beginner ~30%, intermediate ~45%).
EXPERIENCE_LEVELS = [
    "beginner", "intermediate", "intermediate", "experienced", "experienced",
    "experienced",
]

GITHUB_ORG = "github.com"


# ---------------------------------------------------------------------------
# Row generators
# ---------------------------------------------------------------------------
def _confidence_level(score: float) -> str:
    if score < 40:
        return "beginner"
    if score <= 75:
        return "intermediate"
    return "advanced"


def _pick_skills(role: str, experience: str) -> list[str]:
    pool = list(ROLE_SKILLS[role])
    # Beginner profiles know fewer things; experienced ones know more.
    if experience == "beginner":
        count = random.randint(3, 5)
    elif experience == "intermediate":
        count = random.randint(5, 8)
    else:
        count = random.randint(7, 10)
    return random.sample(pool, min(count, len(pool)))


def _build_profile_data(role: str, experience: str, name: str) -> dict:
    """Assemble the Phase 1 profile_data dict for one candidate."""
    skills = _pick_skills(role, experience)

    skill_items = []
    for skill in skills:
        score = round(random.uniform(35, 98), 1)
        normalized = normalize_skill_name(skill)
        skill_items.append(
            {
                "name": normalized,
                "category": NORMALIZED_CATEGORY.get(normalized),
                "source": random.choice(SKILL_SOURCES),
                "confidence_score": score,
                "confidence_level": _confidence_level(score),
            }
        )

    evidence_items = []
    for skill in skills[:4]:
        weight = round(random.uniform(0.4, 1.0), 2)
        normalized = normalize_skill_name(skill)
        source_type = random.choice(["github", "resume", "assessment"])
        source_url = None
        if source_type == "github":
            source_url = f"https://{GITHUB_ORG}/{name.lower().replace(' ', '')}/{normalized}"
        elif source_type == "resume":
            source_url = f"/uploads/resumes/{name.lower().replace(' ', '_')}.pdf"
        evidence_items.append(
            {
                "skill": normalized,
                "source_type": source_type,
                "source_url": source_url,
                "evidence_text": f"Verified {normalized} proficiency from {source_type} history.",
                "weight": weight,
            }
        )

    big_five = {
        "openness": random.randint(35, 98),
        "conscientiousness": random.randint(35, 98),
        "extraversion": random.randint(25, 95),
        "agreeableness": random.randint(40, 98),
        "neuroticism": random.randint(10, 70),
    }

    dimension_scores = []
    for dim in TEAMWORK_DIMENSIONS:
        raw = random.randint(5, 10)
        dimension_scores.append(
            {
                "dimension": dim,
                "raw_score": raw,
                "max_score": 10,
                "percentage": round(raw * 10, 1),
            }
        )

    working_days = list(WEEKDAYS)
    if random.random() < 0.5:
        working_days.extend(random.sample(WEEKEND, random.randint(1, 2)))

    completed_at = datetime.now(timezone.utc).isoformat()

    return {
        "role": {"role": role},
        "experience": {"level": experience},
        "ability": {
            "skills": skill_items,
            "sources": sorted(set(item["source"] for item in skill_items)),
            "skill_count": len(skill_items),
        },
        "evidence": {"items": evidence_items, "count": len(evidence_items)},
        "behavior": {
            "big_five": big_five,
            "work_style": random.choice(WORK_STYLES),
            "communication_style": random.choice(COMMUNICATION_STYLES),
            "preferred_role": ROLE_LABELS[role],
            "strengths": random.sample(STRENGTHS, random.randint(2, 4)),
            "collaboration_notes": "Comfortable pairing and reviewing code with teammates.",
            "completed_at": completed_at,
        },
        "teamwork": {
            "dimension_scores": dimension_scores,
            "completed_at": completed_at,
        },
        "availability": {
            "working_days": working_days,
            "working_hours": random.choice(WORKING_HOURS),
            "timezone": random.choice(TIMEZONES),
            "commitment_level": random.choice(
                ["casual", "part_time", "full_time", "full_time"]
            ),
        },
    }


# ---------------------------------------------------------------------------
# Seeder
# ---------------------------------------------------------------------------
def seed(count: int = 75, clear_existing: bool = False) -> None:
    """Insert `count` synthetic candidates (users + profiles + candidate_profiles)."""
    db = SessionLocal()
    try:
        if clear_existing:
            cleared = (
                db.query(User)
                .filter(User.email.like(f"%{EMAIL_SUFFIX}"))
                .delete(synchronize_session=False)
            )
            db.commit()
            print(f"[seed_candidates] Cleared {cleared} existing seeded candidates.")

        existing = (
            db.query(User)
            .filter(User.email.like(f"%{EMAIL_SUFFIX}"))
            .count()
        )
        if existing > 0:
            print(
                f"[seed_candidates] {existing} seeded candidates already exist. "
                "Pass --clear to re-seed."
            )
            return

        now = datetime.now(timezone.utc)
        created = 0

        for i in range(1, count + 1):
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            full_name = f"{first} {last}"
            degree, course = random.choice(DEGREES)
            college = random.choice(COLLEGES)
            city = random.choice(CITIES)
            role = random.choice(list(ROLE_SKILLS.keys()))
            experience = random.choice(EXPERIENCE_LEVELS)

            profile_data = _build_profile_data(role, experience, full_name)
            avatar_url = (
                f"https://ui-avatars.com/api/?name={first}+{last}"
                "&background=6366f1&color=fff&bold=true&size=128"
            )

            user = User(
                id=uuid.uuid4(),
                email=f"candidate.{i:03d}{EMAIL_SUFFIX}",
                password_hash="$2b$12$seedonly.seedonly.seedonly.seedonly",
                full_name=full_name,
                is_active=True,
                is_verified=True,
                created_at=now,
                updated_at=now,
            )
            db.add(user)
            db.flush()

            profile = Profile(
                id=uuid.uuid4(),
                user_id=user.id,
                name=full_name,
                college=college,
                degree=degree,
                course=course,
                department="Computer Science & Engineering",
                year_of_study=random.randint(2, 4),
                state=random.choice(STATES),
                city=city,
                github_url=f"https://{GITHUB_ORG}/{first.lower()}.{last.lower()}",
                linkedin_url=f"https://linkedin.com/in/{first.lower()}{last.lower()}",
                leetcode_url=f"https://leetcode.com/{first.lower()}{last.lower()}",
                role=role,
                avatar_url=avatar_url,
                experience_level=ExperienceLevel(experience),
                created_at=now,
                updated_at=now,
            )
            db.add(profile)

            db.add(
                CandidateProfile(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    profile_data=profile_data,
                    profile_strength=calculate_profile_strength(profile_data),
                    updated_at=now,
                )
            )
            created += 1

        db.commit()
        print(
            f"[seed_candidates] Seeded {created} candidates successfully "
            f"({count} requested)."
        )

        # Verify distribution
        for role in ROLE_SKILLS:
            rows = (
                db.query(CandidateProfile)
                .filter(
                    CandidateProfile.profile_data["role"]["role"].astext == role
                )
                .count()
            )
            if rows:
                print(f"  {role:20s}: {rows}")

    finally:
        db.close()


if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    n = 75
    if "--count" in args:
        idx = args.index("--count")
        if idx + 1 < len(args):
            try:
                n = int(args[idx + 1])
            except ValueError:
                print("Invalid --count value, using 75.")
    seed(count=n, clear_existing="--clear" in args)
