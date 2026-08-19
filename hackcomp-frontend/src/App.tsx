import React, { useEffect, useRef, useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, Link, useNavigate, useLocation } from 'react-router-dom';
import Home from './pages/Home';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import ProfilePage from './pages/ProfilePage';
import ProfileForm from './pages/ProfileForm';
import SkillAssessment from './pages/SkillAssessment';
import ResumeVerification from './pages/ResumeVerification';
import HackathonDetailsPage from './pages/HackathonDetailsPage';
import BlueprintFormationWizard from './pages/BlueprintFormationWizard';
import BlueprintBrowsePage from './pages/BlueprintBrowsePage';
import BlueprintRecommendationsPage from './pages/BlueprintRecommendationsPage';
import BlueprintInvitationsPage from './pages/BlueprintInvitationsPage';
import BlueprintDashboardPage from './pages/BlueprintDashboardPage';
import OnboardingProfile from './pages/onboarding/OnboardingProfile';
import OnboardingSkills from './pages/onboarding/OnboardingSkills';
import BrandLogo from './components/BrandLogo';
import Avatar from './components/Avatar';
import { api } from './api';
import { getInitialTheme, applyTheme } from './utils/theme';
import type { Theme } from './utils/theme';
import { LogOut, User, Sun, Moon } from 'lucide-react';

// ── Helpers ────────────────────────────────────────────────────
const isLoggedIn = () => !!localStorage.getItem('access_token');
const onboardingDone = () => localStorage.getItem('onboarding_step') === 'complete';

// ── Guard: requires logged in + onboarding complete ──────────
const AppGuard = ({ children }: { children: React.ReactNode }) => {
  if (!isLoggedIn()) return <Navigate to="/" replace />;
  if (!onboardingDone()) {
    const step = localStorage.getItem('onboarding_step');
    switch (step) {
      case 'skills':      return <Navigate to="/onboarding/skills" replace />;
      default:            return <Navigate to="/onboarding/profile" replace />;
    }
  }
  return <>{children}</>;
};

// ── Guard: onboarding steps require login ────────────────────
const OnboardingStepGuard = ({ children }: { children: React.ReactNode }) => {
  if (!isLoggedIn()) return <Navigate to="/login" replace />;
  if (onboardingDone()) return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
};

// ── Top navigation bar ────────────────────────────────────────
const Navigation = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const token = localStorage.getItem('access_token');

  const [profile, setProfile] = useState<any>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [theme, setTheme] = useState<Theme>(getInitialTheme());
  const menuRef = useRef<HTMLDivElement>(null);

  const handleToggleTheme = () => {
    const next: Theme = theme === 'light' ? 'dark' : 'light';
    applyTheme(next);
    setTheme(next);
  };

  // Load profile for the avatar in the navbar
  useEffect(() => {
    if (!token) return;
    api.getProfile()
      .then((res) => setProfile(res.data))
      .catch(() => setProfile(null));
  }, [token, location.pathname]);

  // Close the menu when clicking outside
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const handleLogout = () => {
    localStorage.clear();
    navigate('/', { replace: true });
  };

  const isOnboarding = location.pathname.startsWith('/onboarding')
    || location.pathname === '/login'
    || location.pathname === '/register';

  if (!token || isOnboarding) return null;

  return (
    <nav className="navbar">
      <Link to="/dashboard" className="navbar-brand">
        <BrandLogo />
      </Link>

      <div className="navbar-right" ref={menuRef}>
        <button
          type="button"
          className={`navbar-avatar-btn ${menuOpen ? 'open' : ''}`}
          onClick={() => setMenuOpen((open) => !open)}
          aria-label="Account menu"
          aria-haspopup="menu"
          aria-expanded={menuOpen}
        >
          <Avatar name={profile?.name} avatarUrl={profile?.avatar_url} size={34} />
        </button>

        {menuOpen && (
          <div className="user-menu" role="menu">
            <div className="user-menu-head">
              <Avatar name={profile?.name} avatarUrl={profile?.avatar_url} size={36} />
              <div className="flex flex-col" style={{ minWidth: 0 }}>
                <span className="user-menu-name">{profile?.name || 'Developer'}</span>
                <span className="text-subtle text-xs" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {profile?.college || 'Developer profile'}
                </span>
              </div>
            </div>

            <Link to="/profile/edit" className="user-menu-item" role="menuitem" onClick={() => setMenuOpen(false)}>
              <User size={15} /> Edit Profile
            </Link>

            <button
              type="button"
              className="user-menu-item theme-toggle-row"
              role="switch"
              aria-checked={theme === 'light'}
              onClick={handleToggleTheme}
            >
              {theme === 'light' ? <Sun size={15} /> : <Moon size={15} />}
              <span style={{ flex: 1 }}>Light Mode</span>
              <span className={`theme-toggle ${theme === 'light' ? 'on' : ''}`}>
                <span className="theme-toggle-track">
                  <span className="theme-toggle-thumb" />
                </span>
              </span>
            </button>

            <div className="divider" style={{ margin: '6px 0' }} />

            <button type="button" className="user-menu-item" role="menuitem" onClick={handleLogout}>
              <LogOut size={15} /> Sign out
            </button>
          </div>
        )}
      </div>
    </nav>
  );
};

function App() {
  return (
    <Router>
      <Navigation />
      <div className="container">
        <Routes>
          {/* ── Root — landing page for logged-out users ── */}
          <Route path="/" element={
            !isLoggedIn()
              ? <Home />
              : onboardingDone()
                ? <Navigate to="/dashboard" replace />
                : <Navigate to="/onboarding/profile" replace />
          } />

          {/* ── Landing / auth ── */}
          <Route path="/login" element={
            isLoggedIn() && onboardingDone()
              ? <Navigate to="/dashboard" replace />
              : <Login />
          } />
          <Route path="/register" element={
            isLoggedIn() && onboardingDone()
              ? <Navigate to="/dashboard" replace />
              : <Register />
          } />

          {/* ── Onboarding steps (require login, not complete) ── */}
          <Route path="/onboarding/profile" element={
            <OnboardingStepGuard><OnboardingProfile /></OnboardingStepGuard>
          } />
          <Route path="/onboarding/skills" element={
            <OnboardingStepGuard><OnboardingSkills /></OnboardingStepGuard>
          } />

          {/* ── App routes (require login + onboarding complete) ── */}
          <Route path="/dashboard" element={<AppGuard><Dashboard /></AppGuard>} />
          <Route path="/profile" element={<AppGuard><ProfilePage /></AppGuard>} />
          <Route path="/profile/edit" element={<AppGuard><ProfileForm /></AppGuard>} />
          <Route path="/verification" element={<AppGuard><ResumeVerification /></AppGuard>} />
          <Route path="/assessment" element={<AppGuard><SkillAssessment /></AppGuard>} />
          <Route path="/hackathons/:id" element={<AppGuard><HackathonDetailsPage /></AppGuard>} />
          <Route path="/hackathons/:id/team/create" element={<AppGuard><BlueprintFormationWizard /></AppGuard>} />
          <Route path="/blueprints/:id/dashboard" element={<AppGuard><BlueprintDashboardPage /></AppGuard>} />
          <Route path="/blueprints/:id/recommendations" element={<AppGuard><BlueprintRecommendationsPage /></AppGuard>} />
          <Route path="/blueprints/my-invitations" element={<AppGuard><BlueprintInvitationsPage /></AppGuard>} />
          <Route path="/blueprints/browse" element={<AppGuard><BlueprintBrowsePage /></AppGuard>} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;
