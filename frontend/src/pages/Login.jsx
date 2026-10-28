import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import Header from '../components/Header';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

export default function Login() {
  const navigate = useNavigate();

  const [loginType, setLoginType] = useState('recruiter'); // 'admin' or 'recruiter'
  
  // Recruiter fields
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  
  // Admin fields
  const [userId, setUserId] = useState('');
  const [password, setPassword] = useState('');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();

    setLoading(true);
    setError('');

    try {
      if (loginType === 'admin') {
        // Admin Login Logic
        const formData = new URLSearchParams();
        formData.append('username', userId);
        formData.append('password', password);

        const response = await fetch(`${API_BASE_URL}/auth/login`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
          },
          body: formData,
        });

        const data = await response.json();

        if (!response.ok) {
          throw new Error(data.detail || 'Invalid admin credentials');
        }

        localStorage.setItem('accessToken', data.access_token);
        localStorage.setItem('userId', data.user.id);
        localStorage.setItem('userName', data.user.name);
        localStorage.setItem('userRole', 'ADMIN');

        navigate('/admin');
      } else {
        // Recruiter Login Logic
        const formData = new URLSearchParams();
        formData.append('username', email);
        formData.append('password', password);

        const response = await fetch(`${API_BASE_URL}/auth/login`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
          },
          body: formData,
        });

        const data = await response.json();

        if (!response.ok) {
          throw new Error(data.detail || 'Login failed.');
        }

        localStorage.setItem('accessToken', data.access_token);
        localStorage.setItem('userId', data.user.id);
        localStorage.setItem('userName', data.user.name);
        localStorage.setItem('userEmail', data.user.email);
        localStorage.setItem('userRole', data.user.role);
        
        navigate('/dashboard');
      }
    } catch (err) {
      setError(err.message || 'Login failed. Please try again.');
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

          {/* LEFT SIDE */}
          <section className="lg:col-span-7">
            <div className="max-w-xl py-8 lg:py-12">
              <div className="mb-6 inline-flex items-center gap-2.5 rounded-full bg-slate-800/80 px-3 py-1.5 ring-1 ring-slate-700 animate-slide-up opacity-0-init animate-delay-100">
                <span className="size-2 rounded-full bg-brand shadow-[0_0_10px_rgba(59,130,246,0.8)]"></span>
                <p className="text-xs font-bold uppercase tracking-[0.15em] text-slate-300">
                  AI-powered recruitment
                </p>
              </div>

              <h1 className="font-display text-5xl font-bold leading-[1.05] tracking-tight sm:text-7xl animate-slide-up opacity-0-init animate-delay-200">
                Find the right candidates{' '}
                <span className="bg-gradient-to-r from-brand to-accent bg-clip-text text-transparent filter drop-shadow-[0_0_10px_rgba(59,130,246,0.4)]">
                  faster.
                </span>
              </h1>

              <p className="mt-6 max-w-lg text-base leading-relaxed text-slate-400 sm:text-lg animate-slide-up opacity-0-init animate-delay-300">
                Upload a job description, search connected talent sources,
                screen candidates with explainable AI scoring, and move the
                strongest people into your outreach pipeline.
              </p>

              <div className="mt-10 grid max-w-lg gap-4 sm:grid-cols-3">
                <div className="glass-dark glass-dark-card rounded-2xl p-5 animate-slide-up opacity-0-init animate-delay-400">
                  <div className="mb-3 inline-flex size-8 items-center justify-center rounded-lg bg-brand/20 text-xs font-bold text-brand ring-1 ring-brand/30">
                    01
                  </div>
                  <p className="text-sm font-bold text-white">Analyze JD</p>
                  <p className="mt-1.5 text-xs leading-relaxed text-slate-400">
                    Extract skills, experience and requirements.
                  </p>
                </div>

                <div className="glass-dark glass-dark-card rounded-2xl p-5 animate-slide-up opacity-0-init animate-delay-500">
                  <div className="mb-3 inline-flex size-8 items-center justify-center rounded-lg bg-accent/20 text-xs font-bold text-accent ring-1 ring-accent/30">
                    02
                  </div>
                  <p className="text-sm font-bold text-white">Score talent</p>
                  <p className="mt-1.5 text-xs leading-relaxed text-slate-400">
                    Rank candidates on a transparent 100-point model.
                  </p>
                </div>

                <div className="glass-dark glass-dark-card rounded-2xl p-5 animate-slide-up opacity-0-init" style={{ animationDelay: '600ms' }}>
                  <div className="mb-3 inline-flex size-8 items-center justify-center rounded-lg bg-purple-500/20 text-xs font-bold text-purple-400 ring-1 ring-purple-500/30">
                    03
                  </div>
                  <p className="text-sm font-bold text-white">Contact</p>
                  <p className="mt-1.5 text-xs leading-relaxed text-slate-400">
                    Move eligible candidates into outreach.
                  </p>
                </div>
              </div>
            </div>
          </section>

          {/* LOGIN CARD */}
          <section className="lg:col-span-5 relative animate-slide-up opacity-0-init animate-delay-300">
            <div className="absolute -inset-1 rounded-[24px] bg-gradient-to-b from-brand/20 to-accent/20 blur-xl z-0"></div>

            <div className="glass-dark relative z-10 rounded-[24px] p-8 sm:p-10 border border-slate-700/50">
              <div className="mb-6 flex items-center gap-2.5">
                <span className={`size-2 rounded-full ${loginType === 'admin' ? 'bg-purple-500 shadow-[0_0_10px_rgba(168,85,247,0.8)]' : 'bg-brand shadow-[0_0_10px_rgba(59,130,246,0.8)]'}`}></span>
                <p className="text-xs font-bold uppercase tracking-[0.15em] text-slate-400">
                  {loginType === 'admin' ? 'Admin Access' : 'Recruiter Access'}
                </p>
              </div>

              <h2 className="font-display text-3xl font-bold tracking-tight text-white mb-6">
                Welcome back
              </h2>

              {/* ROLE TOGGLE */}
              <div className="flex rounded-xl bg-slate-800/80 p-1 mb-6 ring-1 ring-slate-700">
                <button
                  type="button"
                  onClick={() => { setLoginType('recruiter'); setError(''); }}
                  className={`flex-1 rounded-lg py-2 text-xs font-bold transition-all ${
                    loginType === 'recruiter' 
                      ? 'bg-slate-700 text-white shadow-sm ring-1 ring-slate-600' 
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Recruiter
                </button>
                <button
                  type="button"
                  onClick={() => { setLoginType('admin'); setError(''); }}
                  className={`flex-1 rounded-lg py-2 text-xs font-bold transition-all ${
                    loginType === 'admin' 
                      ? 'bg-slate-700 text-white shadow-sm ring-1 ring-slate-600' 
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Admin
                </button>
              </div>

              <form onSubmit={handleSubmit} className="space-y-5">

                {loginType === 'recruiter' ? (
                  <>
                    {/* EMAIL */}
                    <div>
                      <label htmlFor="email" className="mb-2 block text-xs font-bold text-slate-300">
                        Work email
                      </label>
                      <input
                        id="email"
                        type="email"
                        placeholder="recruiter@company.com"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        required
                        className="input-dark w-full rounded-xl px-4 py-3.5 text-sm placeholder:text-slate-600"
                      />
                    </div>
                    {/* PASSWORD */}
                    <div>
                      <label htmlFor="password" className="mb-2 block text-xs font-bold text-slate-300">
                        Password
                      </label>
                      <input
                        id="password"
                        type="password"
                        placeholder="••••••••"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                        className="input-dark w-full rounded-xl px-4 py-3.5 text-sm placeholder:text-slate-600"
                      />
                    </div>
                  </>
                ) : (
                  <>
                    {/* USER ID */}
                    <div>
                      <label htmlFor="userid" className="mb-2 block text-xs font-bold text-slate-300">
                        Admin User ID
                      </label>
                      <input
                        id="userid"
                        type="text"
                        placeholder="admin_id"
                        value={userId}
                        onChange={(e) => setUserId(e.target.value)}
                        required
                        className="input-dark w-full rounded-xl px-4 py-3.5 text-sm placeholder:text-slate-600"
                      />
                    </div>
                    {/* PASSWORD */}
                    <div>
                      <label htmlFor="password" className="mb-2 block text-xs font-bold text-slate-300">
                        Password
                      </label>
                      <input
                        id="password"
                        type="password"
                        placeholder="••••••••"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                        className="input-dark w-full rounded-xl px-4 py-3.5 text-sm placeholder:text-slate-600"
                      />
                    </div>
                  </>
                )}

                {/* ERROR */}
                {error && (
                  <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm font-medium text-red-400">
                    {error}
                  </div>
                )}

                {/* LOGIN BUTTON */}
                <button
                  type="submit"
                  disabled={loading}
                  className="btn-neon mt-4 w-full rounded-xl px-4 py-3.5 text-sm font-bold text-white flex items-center justify-center gap-2 group disabled:opacity-60"
                >
                  {loading ? 'Signing in...' : (
                    <>
                      Sign in as {loginType === 'admin' ? 'Admin' : 'Recruiter'}
                      <span className="transition-transform group-hover:translate-x-1">→</span>
                    </>
                  )}
                </button>
              </form>

              {loginType === 'recruiter' && (
                <div className="mt-6 text-center text-sm text-slate-400">
                  Don't have an account?{' '}
                  <Link to="/register" className="font-semibold text-brand hover:text-brand-soft">
                    Apply for access
                  </Link>
                </div>
              )}
            </div>
          </section>

        </div>
      </main>
    </div>
  );
}