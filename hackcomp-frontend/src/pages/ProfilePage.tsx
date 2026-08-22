import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import SkillBadge from '../components/SkillBadge';
import { getSkillBadge, loadVerifiedSkills, passedSkillNames } from '../utils/skillBadges';
import {
  User, Loader2, PenLine, MapPin, Link2, GitBranch, ExternalLink, Target,
  Wrench, ShieldCheck, ClipboardCheck, Sparkles, Circle, CheckCircle2, Brain,
} from 'lucide-react';

const pretty = (value: any) =>
  value ? String(value).replace(/_/g, ' ') : '—';

const statusCounts = (skills: any[]) => {
  const counts = { advanced: 0, intermediate: 0, beginner: 0 };
  skills.forEach((s: any) => {
    const level = String(s.level || '').toLowerCase();
    if (level in counts) counts[level as keyof typeof counts] += 1;
  });
  return counts;
};

const ProfileLink = ({ label, url, icon }: { label: string; url?: string | null; icon: ReactNode }) => (
  url ? (
    <a href={url} target="_blank" rel="noreferrer" className="profile-link">
      <span className="profile-link-icon">{icon}</span>
      <span className="flex flex-col">
        <span className="dash-summary-label">{label}</span>
        <span className="profile-link-url">{url.replace(/^https?:\/\/(www\.)?/, '')}</span>
      </span>
      <ExternalLink size={13} className="profile-link-ext" />
    </a>
  ) : (
    <div className="profile-link is-empty">
      <span className="profile-link-icon">{icon}</span>
      <span className="flex flex-col">
        <span className="dash-summary-label">{label}</span>
        <span className="text-subtle">Not added</span>
      </span>
    </div>
  )
);

const ProfilePage = () => {
  const [profile, setProfile] = useState<any>(null);
  const [skills, setSkills] = useState<any[]>([]);
  const [skillResult, setSkillResult] = useState<any>(null);
  const [personality, setPersonality] = useState<any>(null);
  const [collab, setCollab] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchAll = async () => {
      try {
        const [p, sk, sr, pr, cr] = await Promise.all([
          api.getProfile().catch(() => ({ data: null })),
          api.getSkills().catch(() => ({ data: [] })),
          api.getSkillResults().catch(() => ({ data: null })),
          api.getPersonalityResult().catch(() => ({ data: null })),
          api.getCollabResult().catch(() => ({ data: null })),
        ]);
        setProfile(p.data);
        setSkills(sk.data || []);
        setSkillResult(sr.data);
        setPersonality(pr.data);
        setCollab(cr.data);
      } finally {
        setLoading(false);
      }
    };
    fetchAll();
  }, []);

  if (loading) {
    return (
      <div className="main-workspace flex items-center justify-center" style={{ minHeight: '60vh' }}>
        <Loader2 size={24} className="spin" color="var(--primary)" />
      </div>
    );
  }

  const skillCounts = statusCounts(skills);
  const skillAssessmentDone = skillResult?.status === 'completed';
  const assessedNames = passedSkillNames(skillResult?.skills || []);
  const collabTop = collab?.dimension_scores?.length
    ? [...collab.dimension_scores].sort((a: any, b: any) => b.percentage - a.percentage)[0]
    : null;

  return (
    <div className="main-workspace fade-in">

      {/* ── Page header ── */}
      <div className="flex items-center justify-between mb-6 pb-4" style={{ borderBottom: '1px solid var(--border)' }}>
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="badge badge-primary flex items-center gap-1">
              <User size={11} /> Developer Profile
            </span>
          </div>
          <h1 style={{ fontSize: '22px', marginBottom: '4px' }}>{profile?.name || 'Your Profile'}</h1>
          <p style={{ fontSize: '13px', color: 'var(--muted)' }}>
            A snapshot of your developer profile, skills, and assessment status.
          </p>
        </div>
        <Link to="/profile/edit" className="btn btn-primary btn-sm">
          <PenLine size={13} /> Edit Profile
        </Link>
      </div>

      {/* ── Personal information ── */}
      <div className="grid-2 gap-6 items-start mb-6">
        <div className="card">
          <div className="card-header">
            <h3 className="card-title flex items-center gap-2">
              <User size={15} color="var(--primary)" /> Personal Information
            </h3>
          </div>
          <div className="profile-grid">
            <div className="dash-summary-item">
              <span className="dash-summary-label">Name</span>
              <span className="dash-summary-value">{profile?.name || '—'}</span>
            </div>
            <div className="dash-summary-item">
              <span className="dash-summary-label">College</span>
              <span className="dash-summary-value">{profile?.college || '—'}</span>
            </div>
            <div className="dash-summary-item">
              <span className="dash-summary-label">Degree</span>
              <span className="dash-summary-value">{profile?.degree || '—'}</span>
            </div>
            <div className="dash-summary-item">
              <span className="dash-summary-label">Department</span>
              <span className="dash-summary-value">{profile?.department || '—'}</span>
            </div>
            <div className="dash-summary-item">
              <span className="dash-summary-label">Year of Study</span>
              <span className="dash-summary-value">{profile?.year_of_study || '—'}</span>
            </div>
            <div className="dash-summary-item">
              <span className="dash-summary-label">Experience Level</span>
              <span className="dash-summary-value" style={{ textTransform: 'capitalize' }}>
                {pretty(profile?.experience_level)}
              </span>
            </div>
            <div className="dash-summary-item">
              <span className="dash-summary-label">Role</span>
              <span className="dash-summary-value" style={{ textTransform: 'capitalize' }}>
                {pretty(profile?.role)}
              </span>
            </div>
          </div>
        </div>

        {/* ── Location + Professional links ── */}
        <div className="flex flex-col gap-6">
          <div className="card">
            <div className="card-header">
              <h3 className="card-title flex items-center gap-2">
                <MapPin size={15} color="var(--primary)" /> Location
              </h3>
            </div>
            <div className="profile-grid profile-grid-2">
              <div className="dash-summary-item">
                <span className="dash-summary-label">City</span>
                <span className="dash-summary-value">{profile?.city || '—'}</span>
              </div>
              <div className="dash-summary-item">
                <span className="dash-summary-label">State</span>
                <span className="dash-summary-value">{profile?.state || '—'}</span>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <h3 className="card-title flex items-center gap-2">
                <Link2 size={15} color="var(--primary)" /> Professional Links
              </h3>
            </div>
            <div className="flex flex-col gap-2">
              <ProfileLink label="GitHub" url={profile?.github_url} icon={<GitBranch size={15} />} />
              <ProfileLink label="LinkedIn" url={profile?.linkedin_url} icon={<Link2 size={15} />} />
              <ProfileLink label="LeetCode" url={profile?.leetcode_url} icon={<Target size={15} />} />
            </div>
          </div>
        </div>
      </div>

      {/* ── Skills ── */}
      <div className="card mb-6">
        <div className="card-header">
          <h3 className="card-title flex items-center gap-2">
            <Wrench size={15} color="var(--primary)" /> Skills
          </h3>
          <span className="badge badge-primary">{skills.length} skills</span>
        </div>
        {skills.length ? (
          <div className="flex wrap gap-2">
            {skills.map((s: any) => (
              <span key={s.id} className="skill-tag">
                {s.name}
                <SkillBadge badge={getSkillBadge(s.name, assessedNames, loadVerifiedSkills())} />
              </span>
            ))}
          </div>
        ) : (
          <p className="text-subtle">No skills added yet.</p>
        )}
      </div>

      {/* ── Verification + Assessment summary ── */}
      <div className="grid-2 gap-6 items-start">
        <div className="card">
          <div className="card-header">
            <h3 className="card-title flex items-center gap-2">
              <ShieldCheck size={15} color="var(--primary)" /> Verification Summary
            </h3>
          </div>

          <div className="dash-summary-grid">
            <div className="dash-summary-item">
              <span className="dash-summary-label">Total Skills</span>
              <span className="dash-summary-value">{skills.length}</span>
            </div>
            <div className="dash-summary-item">
              <span className="dash-summary-label">Advanced</span>
              <span className="dash-summary-value" style={{ color: 'var(--success)' }}>{skillCounts.advanced}</span>
            </div>
            <div className="dash-summary-item">
              <span className="dash-summary-label">Intermediate</span>
              <span className="dash-summary-value" style={{ color: '#f59e0b' }}>{skillCounts.intermediate}</span>
            </div>
            <div className="dash-summary-item">
              <span className="dash-summary-label">Beginner</span>
              <span className="dash-summary-value" style={{ color: 'var(--muted)' }}>{skillCounts.beginner}</span>
            </div>
          </div>

          <div className="divider" style={{ margin: '16px 0' }} />
          <p className="text-subtle text-xs mb-3" style={{ lineHeight: 1.6 }}>
            Confidence levels are derived from resume parsing and GitHub repository analysis.
          </p>
          <Link to="/verification" className="btn btn-secondary btn-sm">
            <ShieldCheck size={13} /> Run Resume & GitHub Verification
          </Link>
        </div>

        <div className="card">
          <div className="card-header">
            <h3 className="card-title flex items-center gap-2">
              <ClipboardCheck size={15} color="var(--primary)" /> Assessment Summary
            </h3>
          </div>

          <div className="widget-status-list">
            <div className="widget-status-item">
              <span className={`widget-status-icon ${skillAssessmentDone ? 'done' : ''}`}>
                {skillAssessmentDone ? <CheckCircle2 size={16} /> : <Circle size={16} />}
              </span>
              <span className="widget-status-name">Skill Assessment</span>
              <span className={`badge ${skillAssessmentDone ? 'badge-success' : 'badge-neutral'}`}>
                {skillAssessmentDone ? 'Completed' : 'Not Completed'}
              </span>
            </div>
            {skillAssessmentDone && (
              <p className="text-subtle text-xs" style={{ margin: '2px 0 0 26px' }}>
                {skillResult.skills?.length || 0} skills assessed · {pretty(skillResult.experience_level)}
              </p>
            )}

            <div className="widget-status-item">
              <span className={`widget-status-icon ${personality ? 'done' : ''}`}>
                {personality ? <CheckCircle2 size={16} /> : <Circle size={16} />}
              </span>
              <span className="widget-status-name">Personal Style Test</span>
              <span className={`badge ${personality ? 'badge-success' : 'badge-neutral'}`}>
                {personality ? 'Completed' : 'Not Completed'}
              </span>
            </div>
            {personality && (
              <p className="text-subtle text-xs" style={{ margin: '2px 0 0 26px' }}>
                {pretty(personality.work_style)} · {pretty(personality.communication_style)}
              </p>
            )}

            <div className="widget-status-item">
              <span className={`widget-status-icon ${collab ? 'done' : ''}`}>
                {collab ? <CheckCircle2 size={16} /> : <Circle size={16} />}
              </span>
              <span className="widget-status-name">Team Collaboration Test</span>
              <span className={`badge ${collab ? 'badge-success' : 'badge-neutral'}`}>
                {collab ? 'Completed' : 'Not Completed'}
              </span>
            </div>
            {collabTop && (
              <p className="text-subtle text-xs" style={{ margin: '2px 0 0 26px' }}>
                Top trait: {pretty(collabTop.dimension)} ({Math.round(collabTop.percentage)}%)
              </p>
            )}
          </div>

          <div className="divider" style={{ margin: '16px 0' }} />
          <div className="flex wrap gap-2">
            <Link to="/assessment" className="btn btn-secondary btn-sm">
              <Brain size={13} /> Take Skill Assessment
            </Link>
            <Link to="/assessment" className="btn btn-secondary btn-sm">
              <Sparkles size={13} /> Take this test
            </Link>
          </div>
        </div>
      </div>

    </div>
  );
};

export default ProfilePage;
