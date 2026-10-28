import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import Header from '../components/Header';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

export default function Register() {
  const navigate = useNavigate();

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();

    setError('');

    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    if (password.length < 6) {
      setError('Password must be at least 6 characters.');
      return;
    }

    setLoading(true);

    try {
      const formData = new FormData();

      formData.append('name', name);
      formData.append('email', email);
      formData.append('password', password);

      const response = await fetch(`${API_BASE_URL}/auth/register`, {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Registration failed.');
      }

      // Registration successful.
      // Send user to login page.
      navigate('/login', {
        state: {
          message: 'Account created successfully. Please sign in.',
        },
      });

    } catch (err) {
      setError(err.message || 'Registration failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen w-full overflow-hidden antialiased">

      <div className="glow-bg top-[-20%] left-[-10%] animate-pulse-slow"></div>

      <div
        className="glow-bg bottom-[-20%] right-[-10%] animate-pulse-slow"
        style={{
          animationDelay: '2s',
          background:
            'radial-gradient(circle, rgba(20,184,166,0.15) 0%, rgba(59,130,246,0.05) 40%, rgba(2,6,23,0) 70%)',
        }}
      ></div>

      <Header showNav={false} />

      <main className="relative z-10">

        <div className="mx-auto grid min-h-[calc(100vh-120px)] max-w-6xl items-center gap-12 px-5 py-8 sm:px-8 lg:grid-cols-12">

          {/* LEFT */}
          <section className="lg:col-span-7">

            <div className="max-w-xl py-8 lg:py-12">

              <div className="mb-6 inline-flex items-center gap-2.5 rounded-full bg-slate-800/80 px-3 py-1.5 ring-1 ring-slate-700">
                <span className="size-2 rounded-full bg-accent shadow-[0_0_10px_rgba(20,184,166,0.8)]"></span>

                <p className="text-xs font-bold uppercase tracking-[0.15em] text-slate-300">
                  Join NM-HireX
                </p>
              </div>

              <h1 className="font-display text-5xl font-bold leading-[1.05] tracking-tight sm:text-7xl">

                Build your hiring pipeline{' '}

                <span className="bg-gradient-to-r from-brand to-accent bg-clip-text text-transparent">
                  smarter.
                </span>

              </h1>

              <p className="mt-6 max-w-lg text-base leading-relaxed text-slate-400 sm:text-lg">
                Create your recruiter account and start analyzing job
                descriptions, screening candidates, and building your
                recruitment pipeline with AI.
              </p>

            </div>

          </section>

          {/* REGISTER CARD */}
          <section className="lg:col-span-5 relative">

            <div className="absolute -inset-1 rounded-[24px] bg-gradient-to-b from-brand/20 to-accent/20 blur-xl z-0"></div>

            <div className="glass-dark relative z-10 rounded-[24px] p-8 sm:p-10 border border-slate-700/50">

              <div className="mb-6 flex items-center gap-2.5">

                <span className="size-2 rounded-full bg-accent shadow-[0_0_10px_rgba(20,184,166,0.8)]"></span>

                <p className="text-xs font-bold uppercase tracking-[0.15em] text-slate-400">
                  Recruiter registration
                </p>

              </div>

              <h2 className="font-display text-3xl font-bold tracking-tight text-white">
                Create account
              </h2>

              <p className="mb-8 mt-2 text-sm text-slate-400">
                Start your NM-HireX workspace.
              </p>

              <form onSubmit={handleSubmit} className="space-y-5">

                {/* NAME */}
                <div>
                  <label
                    htmlFor="name"
                    className="mb-2 block text-xs font-bold text-slate-300"
                  >
                    Full name
                  </label>

                  <input
                    id="name"
                    type="text"
                    autoComplete="name"
                    placeholder="Your name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                    className="input-dark w-full rounded-xl px-4 py-3.5 text-sm placeholder:text-slate-600"
                  />
                </div>

                {/* EMAIL */}
                <div>
                  <label
                    htmlFor="email"
                    className="mb-2 block text-xs font-bold text-slate-300"
                  >
                    Work email
                  </label>

                  <input
                    id="email"
                    type="email"
                    autoComplete="email"
                    placeholder="recruiter@company.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    className="input-dark w-full rounded-xl px-4 py-3.5 text-sm placeholder:text-slate-600"
                  />
                </div>

                {/* PASSWORD */}
                <div>
                  <label
                    htmlFor="password"
                    className="mb-2 block text-xs font-bold text-slate-300"
                  >
                    Password
                  </label>

                  <input
                    id="password"
                    type="password"
                    autoComplete="new-password"
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    className="input-dark w-full rounded-xl px-4 py-3.5 text-sm placeholder:text-slate-600"
                  />
                </div>

                {/* CONFIRM PASSWORD */}
                <div>
                  <label
                    htmlFor="confirmPassword"
                    className="mb-2 block text-xs font-bold text-slate-300"
                  >
                    Confirm password
                  </label>

                  <input
                    id="confirmPassword"
                    type="password"
                    autoComplete="new-password"
                    placeholder="••••••••"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    required
                    className="input-dark w-full rounded-xl px-4 py-3.5 text-sm placeholder:text-slate-600"
                  />
                </div>

                {/* ERROR */}
                {error && (
                  <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm font-medium text-red-400">
                    {error}
                  </div>
                )}

                {/* REGISTER */}
                <button
                  type="submit"
                  disabled={loading}
                  className="btn-neon mt-4 w-full rounded-xl px-4 py-3.5 text-sm font-bold text-white flex items-center justify-center gap-2 disabled:opacity-60"
                >
                  {loading ? 'Creating account...' : 'Create recruiter account →'}
                </button>

              </form>

              {/* LOGIN LINK */}
              <div className="mt-6 text-center text-sm text-slate-400">

                Already have an account?{' '}

                <Link
                  to="/login"
                  className="font-semibold text-brand hover:text-brand-soft"
                >
                  Sign in
                </Link>

              </div>

            </div>

          </section>

        </div>

      </main>
    </div>
  );
}