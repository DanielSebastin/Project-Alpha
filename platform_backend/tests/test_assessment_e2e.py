import uuid, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal
from app.models.user import User
from app.models.personality import Personality
from app.models.collaboration import CollaborationAssessment, CollaborationAnswer

client = TestClient(app)

email = f"assess_e2e_{uuid.uuid4().hex[:8]}@example.com"

r = client.post("/api/v1/auth/register", json={"email": email, "password": "Test@12345", "full_name": "E2E Assess User"})
assert r.status_code == 201, r.text
r = client.post("/api/v1/auth/login", json={"email": email, "password": "Test@12345"})
assert r.status_code == 200, r.text
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
assessment_id = None

r = client.post("/api/v1/profile/", json={"name": "E2E Assess User"}, headers=headers)
assert r.status_code == 201, r.text
print("profile created OK")

try:
    # ── Personality assessment ─────────────────────────────────
    r = client.get("/api/v1/personality/start", headers=headers)
    assert r.status_code == 200, r.text
    pq = r.json()["questions"]
    assert len(pq) == 12, r.text

    ans = [{"question_id": q["id"], "response": 5} for q in pq]
    r = client.post("/api/v1/personality/submit", json={"answers": ans}, headers=headers)
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    for k in ("openness_score", "conscientiousness_score", "extraversion_score", "agreeableness_score", "neuroticism_score"):
        assert res[k] is not None and 0 <= res[k] <= 100, (k, res[k])
    assert r.json()["strengths"], r.text
    assert res["completed_at"] is not None, r.text
    print("personality submit OK, scores:", [res[k] for k in ("openness_score", "conscientiousness_score", "extraversion_score", "agreeableness_score", "neuroticism_score")])

    r = client.get("/api/v1/personality/result", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == res["id"]
    r = client.get("/api/v1/personality/status", headers=headers)
    assert r.json()["completed"] is True, r.text
    print("personality result/status OK")

    # ── Collaboration assessment ───────────────────────────────
    r = client.post("/api/v1/collaboration/start", headers=headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assessment_id = body["assessment_id"]
    cq = body["questions"]
    assert len(cq) == 12, r.text
    dims = {q["dimension"] for q in cq}
    assert len(dims) == 6, dims
    print("collaboration start OK, assessment_id:", assessment_id)

    cans = [{"question_id": q["id"], "response": 5} for q in cq]
    r = client.post("/api/v1/collaboration/submit", json={"assessment_id": assessment_id, "answers": cans}, headers=headers)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["status"] == "COMPLETED", r.text
    assert s["completed_at"] is not None, r.text
    assert len(s["dimension_scores"]) == 6, r.text
    for ds in s["dimension_scores"]:
        assert 0 <= ds["percentage"] <= 100, ds
    assert all(ds["raw_score"] == 10 for ds in s["dimension_scores"]), s["dimension_scores"]
    print("collaboration submit OK")

    r = client.get("/api/v1/collaboration/result", headers=headers)
    assert r.status_code == 200, r.text
    assert len(r.json()["dimension_scores"]) == 6
    r = client.get("/api/v1/collaboration/status", headers=headers)
    assert r.json()["completed"] is True, r.text
    print("collaboration result/status OK")

    # ── Profile verification status (no verification done) ────
    r = client.get("/api/v1/profile/verification-status", headers=headers)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["completed"] is False and v["verification_percentage"] == 0, v
    print("verification-status OK")

    print("ALL ASSESSMENT E2E TESTS PASSED")
finally:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        profile_id = user.profile.id if user and user.profile else None
        if user:
            db.delete(user)  # cascades -> profile, personality, collab sessions/answers
            db.commit()
        if profile_id:
            assert db.query(Personality).filter(Personality.profile_id == profile_id).first() is None
            assert db.query(CollaborationAssessment).filter(CollaborationAssessment.profile_id == profile_id).first() is None
        assert db.query(CollaborationAnswer).filter(CollaborationAnswer.assessment_id == assessment_id).first() is None
        print("cleanup verified (cascade removed all assessment rows)")
    finally:
        db.close()
