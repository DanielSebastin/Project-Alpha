import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  Sparkles,
  ShieldCheck,
  GitBranch,
  Users,
  Zap,
  FileText,
  CheckCircle2,
  GitFork,
  BrainCircuit,
  Sun,
  Moon,
} from 'lucide-react';
import BrandLogo from '../components/BrandLogo';
import { getInitialTheme, applyTheme, type Theme } from '../utils/theme';

/* ── Scroll-reveal wrapper ──────────────────────────────────── */
const Reveal = ({ children, delay = 0 }: { children: React.ReactNode; delay?: number }) => {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.15 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={`reveal ${visible ? 'visible' : ''}`}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </div>
  );
};

/* ── Feature data ───────────────────────────────────────────── */
const FEATURES = [
  {
    icon: Zap,
    accent: '#6366f1',
    title: 'AI Skill Parser',
    desc: 'Extract technical frameworks, languages, and project technologies straight from your PDF resume in seconds.',
  },
  {
    icon: GitBranch,
    accent: '#22c55e',
    title: 'GitHub Repo Inspector',
    desc: 'Cross-reference every claimed skill against real code, topics, and dependencies in your public repositories.',
  },
  {
    icon: Users,
    accent: '#a855f7',
    title: 'Hackathon Team Matching',
    desc: 'Complete a quick collaboration assessment and get matched with teams that need exactly what you bring.',
  },
];

/* ── How-it-works steps ─────────────────────────────────────── */
const STEPS = [
  { num: '01', title: 'Create your profile', desc: 'Add your education, links, and experience in under two minutes.' },
  { num: '02', title: 'Declare your stack', desc: 'List the languages, frameworks, and tools you actually work with.' },
  { num: '03', title: 'Get verified', desc: 'Prove your skills with an AI quiz or real GitHub repository evidence.' },
  { num: '04', title: 'Ship with a team', desc: 'Land on a verified leaderboard and get matched to hackathon squads.' },
];

/* ── Home ───────────────────────────────────────────────────── */
const Home = () => {
  const navigate = useNavigate();
  const [theme, setTheme] = useState<Theme>(getInitialTheme());

  const handleToggleTheme = () => {
    const next: Theme = theme === 'light' ? 'dark' : 'light';
    applyTheme(next);
    setTheme(next);
  };

  return (
    <div className="home-page">
      {/* ── Background layers ── */}
      <div className="home-bg" aria-hidden="true">
        <div className="home-orb orb-a" />
        <div className="home-orb orb-b" />
        <div className="home-orb orb-c" />
        <div className="home-grid" />
      </div>

      {/* ── Navbar ── */}
      <header className="home-nav">
        <div className="home-nav-inner">
          <button className="home-logo" onClick={() => navigate('/')}>
            <BrandLogo />
          </button>

          <nav className="home-nav-links">
            <a href="#features">Features</a>
            <a href="#how">How it works</a>
          </nav>

          <div className="home-nav-actions" style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <button
              onClick={handleToggleTheme}
              className="hover-bg"
              style={{ background: 'transparent', border: 'none', color: 'var(--text)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '8px', borderRadius: '50%' }}
              title="Toggle Theme"
            >
              {theme === 'light' ? <Sun size={20} /> : <Moon size={20} />}
            </button>
            <button className="btn btn-ghost home-btn" onClick={() => navigate('/login')}>
              Sign in
            </button>
            <button className="btn btn-primary home-btn" onClick={() => navigate('/register')}>
              Sign up <ArrowRight size={14} />
            </button>
          </div>
        </div>
      </header>

      <main>
        {/* ── Hero ── */}
        <section className="home-hero">
          <div className="home-hero-inner">
            <div className="home-badge rise d1">
              <Sparkles size={13} />
              AI-powered skill verification for hackathon teams
            </div>

            <h1 className="home-title rise d2">
              Prove your skills.
              <br />
              <span className="home-grad">Win hackathons.</span>
            </h1>

            <p className="home-sub rise d3">
              Hack It Up validates your technical skills with AI and real GitHub evidence,
              then matches you with teams that need exactly what you bring.
            </p>

            <div className="home-cta rise d4">
              <button className="btn btn-primary btn-lg home-cta-primary" onClick={() => navigate('/register')}>
                Create your profile <ArrowRight size={16} />
              </button>
              <button className="btn btn-secondary btn-lg" onClick={() => navigate('/login')}>
                Sign in
              </button>
            </div>

            <div className="home-stats rise d5">
              <div className="home-stat">
                <CheckCircle2 size={14} color="var(--success)" />
                <span>Dual verification engine</span>
              </div>
              <div className="home-stat">
                <ShieldCheck size={14} color="var(--primary)" />
                <span>Evidence-backed skills</span>
              </div>
              <div className="home-stat">
                <BrainCircuit size={14} color="#a855f7" />
                <span>Team-ready in minutes</span>
              </div>
            </div>
          </div>
        </section>

        {/* ── Features ── */}
        <section id="features" className="home-section">
          <Reveal>
            <div className="home-section-head">
              <div className="home-section-eyebrow">Platform</div>
              <h2 className="home-section-title">Everything you need to stand out</h2>
              <p className="home-section-sub">
                From resume parsing to live code evidence — your profile does the talking.
              </p>
            </div>
          </Reveal>

          <div className="home-feature-grid">
            {FEATURES.map((f, i) => (
              <Reveal key={f.title} delay={i * 90}>
                <div className="home-feature-card">
                  <div className="home-feature-icon" style={{ color: f.accent, borderColor: `${f.accent}33`, background: `${f.accent}0d` }}>
                    <f.icon size={20} />
                  </div>
                  <h3 className="home-feature-title">{f.title}</h3>
                  <p className="home-feature-desc">{f.desc}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </section>

        {/* ── How it works ── */}
        <section id="how" className="home-section">
          <Reveal>
            <div className="home-section-head">
              <div className="home-section-eyebrow">Onboarding</div>
              <h2 className="home-section-title">Verified in four simple steps</h2>
              <p className="home-section-sub">
                No recruiters, no gatekeeping. Just a transparent proof-of-work system.
              </p>
            </div>
          </Reveal>

          <div className="home-steps">
            {STEPS.map((s, i) => (
              <Reveal key={s.num} delay={i * 90}>
                <div className="home-step">
                  <div className="home-step-num">{s.num}</div>
                  <h3 className="home-step-title">{s.title}</h3>
                  <p className="home-step-desc">{s.desc}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </section>

        {/* ── CTA band ── */}
        <section className="home-cta-band">
          <Reveal>
            <div className="home-cta-card">
              <div className="home-cta-card-glow" aria-hidden="true" />
              <FileText size={28} color="var(--primary)" />
              <h2 className="home-cta-title">Your skills deserve proof.</h2>
              <p className="home-cta-desc">
                Create your verified developer profile today and get matched to your next hackathon team.
              </p>
              <button className="btn btn-primary btn-lg" onClick={() => navigate('/register')}>
                Get started free <ArrowRight size={16} />
              </button>
            </div>
          </Reveal>
        </section>
      </main>

      {/* ── Footer ── */}
      <footer className="home-footer">
        <div className="home-footer-inner">
          <div className="flex items-center gap-2">
            <BrandLogo />
          </div>
          <div className="home-footer-links">
            <button className="home-footer-link" onClick={() => navigate('/login')}>Sign in</button>
            <button className="home-footer-link" onClick={() => navigate('/register')}>Sign up</button>
            <a className="home-footer-link" href="https://github.com" target="_blank" rel="noreferrer">
              <GitFork size={14} /> GitHub
            </a>
          </div>
          <p className="home-footer-copy">© {new Date().getFullYear()} Hack It Up. Built for builders.</p>
        </div>
      </footer>
    </div>
  );
};

export default Home;
