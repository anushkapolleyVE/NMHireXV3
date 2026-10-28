import { Link, useLocation } from 'react-router-dom';
import { useState, useEffect } from 'react';

export default function Header({ showNav = true }) {
  const location = useLocation();
  const [userName, setUserName] = useState('User');
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    const role = localStorage.getItem('userRole');
    const name = localStorage.getItem('userName');
    
    if (role === 'ADMIN' || role === 'admin') {
      setUserName('Admin');
      setIsAdmin(true);
    } else if (name) {
      setUserName(name);
    }
  }, []);

  const firstLetter = userName ? userName.charAt(0).toUpperCase() : 'U';

  const navItems = isAdmin 
    ? [
        { name: 'Dashboard', path: '/dashboard' },
        { name: 'Send Outreach', path: '/outreach/send' },
        { name: 'Outreach Responses', path: '/outreach' },
        { name: 'Candidates', path: '/candidates' },
        { name: 'Recruiters', path: '/admin' }
      ]
    : [
        { name: 'Dashboard', path: '/dashboard' },
        { name: 'Send Outreach', path: '/outreach/send' },
        { name: 'Outreach Responses', path: '/outreach' },
        { name: 'Candidates', path: '/candidates' },
      ];


  return (
    <header className="relative z-20 animate-slide-up opacity-0-init">
      <div className="mx-auto max-w-7xl px-5 pt-6 sm:px-8">
        <div className="glass-dark flex items-center justify-between rounded-2xl px-6 py-4">
          <Link to="/dashboard" className="flex items-center gap-3 group">
            <span className="grid size-9 place-items-center rounded-xl bg-gradient-to-br from-brand to-accent font-display text-base font-bold text-white shadow-[0_0_15px_rgba(59,130,246,0.5)]">
              N
            </span>
            <span className="font-display text-xl font-bold tracking-tight text-white group-hover:text-brand-soft transition-colors">
              NM-HireX
            </span>
            <span className="hidden rounded-full bg-slate-800 px-2.5 py-1 text-[11px] font-semibold text-slate-300 ring-1 ring-slate-700 sm:inline">
              Recruiter OS
            </span>
          </Link>

          {showNav && (
            <nav className="hidden items-center gap-1.5 text-sm md:flex bg-slate-800/50 p-1.5 rounded-full ring-1 ring-slate-700">
              {navItems.map((item) => (
                <Link
                  key={item.path}
                  to={item.path}
                  className={
                    location.pathname === item.path
                      ? "rounded-full bg-slate-700 px-4 py-2 font-semibold text-white shadow-sm ring-1 ring-slate-600"
                      : "nav-link rounded-full px-4 py-2 font-semibold text-slate-400"
                  }
                >
                  {item.name}
                </Link>
              ))}
            </nav>
          )}

          <div className="flex items-center gap-4">
            {showNav ? (
              <>
                <div className="hidden items-center gap-2 sm:flex">
                  <span className="grid size-8 place-items-center rounded-full bg-gradient-to-br from-brand to-accent text-xs font-bold text-white shadow-[0_0_10px_rgba(59,130,246,0.4)]">
                    {firstLetter}
                  </span>
                  <span className="text-sm font-semibold text-white">{userName}</span>
                </div>
                <Link to="/" className="rounded-xl bg-slate-800/80 px-3 py-2 text-xs font-bold text-slate-300 ring-1 ring-slate-700 hover:text-white hover:bg-slate-700 transition-all">
                  Sign out
                </Link>
              </>
            ) : (
              <div className="flex items-center gap-2.5 rounded-full bg-slate-800/80 px-3 py-1.5 ring-1 ring-slate-700">
                <span className="relative flex size-2.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-75"></span>
                  <span className="relative inline-flex rounded-full size-2.5 bg-accent"></span>
                </span>
                <span className="text-xs font-semibold text-slate-300">Platform online</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
