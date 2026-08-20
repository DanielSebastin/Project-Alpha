import json
import logging
import random

from groq import Groq
from app.core.config import get_settings

logger = logging.getLogger(__name__)

def generate_report(context: dict) -> str:
    settings = get_settings()
    api_keys = settings.groq_api_keys_list
    
    if not api_keys:
        logger.error("No Groq API keys configured.")
        return "AI recommendations are currently unavailable."

    # Use a random key for rotation
    api_key = random.choice(api_keys)
    client = Groq(api_key=api_key)

    prompt = (
        "You are an expert technical recruiter and team-building coach for hackathons. "
        "Based on the following candidate profile, write a short, encouraging, and highly personalized "
        "recommendation report (2-3 paragraphs) highlighting their strengths and providing actionable advice "
        "on how they can be a great team player.\n\n"
        f"Profile Data: {json.dumps(context, indent=2)}\n\n"
        "Keep the tone professional, motivating, and directly address the candidate as 'You'. "
        "Use markdown formatting."
    )

    try:
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=settings.groq_model,
            temperature=0.7,
        )
        return response.choices[0].message.content or "No recommendation generated."
    except Exception as e:
        logger.error(f"Error generating recommendation report: {e}")
        return "AI recommendations are currently unavailable due to an error."
