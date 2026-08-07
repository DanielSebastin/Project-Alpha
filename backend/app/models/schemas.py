from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ProjectObject(BaseModel):
    model_config = {"populate_by_name": True}

    name: Optional[str] = None
    description: Optional[str] = None
    technologies: list[str] = Field(default_factory=list)


class HackathonObject(BaseModel):
    model_config = {"populate_by_name": True}

    name: Optional[str] = None
    role: Optional[str] = None


class ExperienceObject(BaseModel):
    model_config = {"populate_by_name": True}

    company: Optional[str] = None
    role: Optional[str] = None
    duration: Optional[str] = None
    description: Optional[str] = None


class ResumeProfile(BaseModel):
    model_config = {"populate_by_name": True}

    projects: list[ProjectObject] = Field(default_factory=list)
    technical_skills: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    hackathons: list[HackathonObject] = Field(default_factory=list)
    experience: list[ExperienceObject] = Field(default_factory=list)
