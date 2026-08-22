def _normalize(s: str) -> str:
    if not s:
        return ""
    return str(s).strip().lower()

def _skill_names(data: dict) -> list[str]:
    ability = data.get("ability", {})
    if isinstance(ability, dict):
        skills = ability.get("skills", [])
        if isinstance(skills, list):
            return [s.get("name") for s in skills if isinstance(s, dict) and s.get("name")]
    return []

def _build_bio(profile, data: dict) -> str:
    if profile and profile.bio:
        return profile.bio
    personality = data.get("personality", {})
    if isinstance(personality, dict):
        return personality.get("work_style", "No bio available")
    return "No bio available"

def _assessment_compatibility(data: dict) -> int:
    # Basic heuristic for assessment score out of 30.
    has_personality = bool(data.get("personality"))
    has_teamwork = bool(data.get("teamwork"))
    
    if has_personality and has_teamwork:
        return 30
    if has_personality or has_teamwork:
        return 20
    return 15
