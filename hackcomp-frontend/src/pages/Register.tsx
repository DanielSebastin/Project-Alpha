import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { api } from '../api';
import { Loader2, Sun, Moon } from 'lucide-react';
import BrandLogo from '../components/BrandLogo';
import { getInitialTheme, applyTheme, type Theme } from '../utils/theme';

const Register = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [theme, setTheme] = useState<Theme>(getInitialTheme());
  const navigate = useNavigate();

  const handleToggleTheme = () => {
    const next: Theme = theme === 'light' ? 'dark' : 'light';
    applyTheme(next);
    setTheme(next);
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      await api.register({ email, password, full_name: fullName });
      const loginRes = await api.login({ email, password });
      if (loginRes.data.access_token) {
        localStorage.setItem('access_token', loginRes.data.access_token);
        localStorage.setItem('onboarding_step', 'profile');
        navigate('/onboarding/profile');
      }
    } catch (err: any) {
      let errorMsg = 'Registration failed. Please try again.';
      if (err.response?.data?.detail) {
        if (Array.isArray(err.response.data.detail)) {
          errorMsg = err.response.data.detail.map((e: any) => e.msg).join(', ');
        } else {
          errorMsg = err.response.data.detail;
        }
      }
      setError(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-center fade-in">
      <button
        onClick={handleToggleTheme}
        className="hover-bg"
        style={{ position: 'absolute', top: '24px', right: '24px', background: 'transparent', border: 'none', color: 'var(--text)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '8px', borderRadius: '50%' }}
        title="Toggle Theme"
      >
        {theme === 'light' ? <Sun size={20} /> : <Moon size={20} />}
      </button>

      <div style={{ width: '100%', maxWidth: '380px' }}>
        <div className="flex items-center mb-6" style={{ justifyContent: 'center' }}>
          <BrandLogo size={28} />
        </div>

        <div className="card">
          <h2 style={{ fontSize: '18px', marginBottom: '4px' }}>Create an account</h2>
          <p style={{ fontSize: '13px', marginBottom: '24px', color: 'var(--muted)' }}>
            Get started with AI-driven skill evaluation
          </p>

          {error && <div className="alert alert-danger mb-4">{error}</div>}

          <form onSubmit={handleRegister}>
            <div className="form-group">
              <label className="form-label">Full Name</label>
              <input
                id="register-fullname"
                type="text"
                required
                className="form-control"
                placeholder="Alex Morgan"
                value={fullName}
                onChange={e => setFullName(e.target.value)}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Email</label>
              <input
                id="register-email"
                type="email"
                required
                className="form-control"
                placeholder="you@example.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
              />
            </div>
            <div className="form-group" style={{ marginBottom: '20px' }}>
              <label className="form-label">Password</label>
              <input
                id="register-password"
                type="password"
                required
                className="form-control"
                placeholder="••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
              />
            </div>
            <button id="register-submit" type="submit" className="btn btn-primary btn-full btn-lg" disabled={loading}>
              {loading ? <><Loader2 size={15} className="spin" /> Creating account...</> : 'Create account'}
            </button>
          </form>
        </div>

        <p className="text-center mt-4" style={{ fontSize: '13px' }}>
          Already have an account?{' '}
          <Link to="/login" style={{ color: 'var(--primary)' }}>Sign in</Link>
        </p>
      </div>
    </div>
  );
};

export default Register;
