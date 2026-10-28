import { useState, useEffect } from 'react';
import Header from '../components/Header';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

export default function AdminDashboard() {
  const [recruiters, setRecruiters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchRecruiters();
  }, []);

  const fetchRecruiters = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch(`${API_BASE_URL}/admin/recruiters`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('accessToken')}`
        }
      });
      if (!response.ok) {
        throw new Error('Failed to fetch recruiters');
      }
      const data = await response.json();
      setRecruiters(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (userId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/admin/recruiters/${userId}/approve`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('accessToken')}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        // Update local state
        setRecruiters(recruiters.map(r => 
          r.id === userId ? { ...r, status: data.status || 'APPROVED' } : r
        ));
      }
    } catch (err) {
      console.error("Error approving:", err);
    }
  };

  const handleReject = async (userId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/admin/recruiters/${userId}/reject`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('accessToken')}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        setRecruiters(recruiters.map(r => 
          r.id === userId ? { ...r, status: data.status || 'REJECTED' } : r
        ));
      }
    } catch (err) {
      console.error("Error rejecting:", err);
    }
  };

  const getStatusBadge = (status) => {
    switch(status) {
      case 'APPROVED':
        return <span className="inline-flex rounded-full bg-accent/20 px-3 py-1.5 text-xs font-bold text-accent ring-1 ring-accent/40 shadow-[0_0_10px_rgba(20,184,166,0.1)]">Approved</span>;
      case 'REJECTED':
        return <span className="inline-flex rounded-full bg-red-500/20 px-3 py-1.5 text-xs font-bold text-red-400 ring-1 ring-red-500/40 shadow-[0_0_10px_rgba(239,68,68,0.1)]">Rejected</span>;
      case 'PENDING':
      default:
        return <span className="inline-flex rounded-full bg-yellow-500/20 px-3 py-1.5 text-xs font-bold text-yellow-400 ring-1 ring-yellow-500/40 shadow-[0_0_10px_rgba(234,179,8,0.1)]">Pending</span>;
    }
  };

  return (
    <div className="relative min-h-screen w-full overflow-hidden antialiased pb-20">
      <div className="glow-bg-large top-[-30%] left-[-20%] animate-pulse-slow"></div>
      <div
        className="glow-bg-large bottom-[-20%] right-[-10%] animate-pulse-slow"
        style={{ animationDelay: '2s', background: 'radial-gradient(circle, rgba(168,85,247,0.1) 0%, rgba(59,130,246,0.05) 40%, rgba(2,6,23,0) 70%)' }}
      ></div>

      <Header />

      <main className="relative z-10">
        <div className="mx-auto max-w-7xl px-5 py-8 sm:px-8">
          <div className="mb-8 flex flex-wrap items-end justify-between gap-6 animate-slide-up opacity-0-init animate-delay-100">
            <div>
              <div className="mb-2 inline-flex items-center gap-2.5 rounded-full bg-slate-800/80 px-3 py-1.5 ring-1 ring-slate-700">
                <span className="size-2 rounded-full bg-purple-500 shadow-[0_0_10px_rgba(168,85,247,0.8)]"></span>
                <p className="text-xs font-bold uppercase tracking-[0.15em] text-slate-300">Admin Control Panel</p>
              </div>
              <h1 className="font-display text-4xl font-bold tracking-tight sm:text-5xl mt-2 text-white">
                Recruiter Management
              </h1>
              <p className="mt-3 text-base text-slate-400">Review and manage recruiter access to the platform.</p>
            </div>
          </div>

          <div className="mt-6 grid gap-6 animate-slide-up opacity-0-init animate-delay-200">
            <section className="glass-dark rounded-[24px] p-6 sm:p-8">
              <div className="mb-6 flex items-center justify-between">
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.15em] text-slate-400">Access Control</p>
                  <h2 className="mt-1 font-display text-2xl font-bold text-white">Recruiter Requests</h2>
                </div>
              </div>

              {error && (
                <div className="mb-6 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm font-medium text-red-400">
                  Error: {error}. Please try logging in as Admin again.
                </div>
              )}

              {loading ? (
                <div className="py-12 flex justify-center">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand"></div>
                </div>
              ) : (
                <div className="overflow-x-auto pb-2">
                  <table className="w-full min-w-[760px] text-left border-collapse">
                    <thead>
                      <tr className="border-b border-slate-700 text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        <th className="pb-4 pl-2">Recruiter Name</th>
                        <th className="pb-4">Email</th>
                        <th className="pb-4">Role</th>
                        <th className="pb-4">Applied On</th>
                        <th className="pb-4">Status</th>
                        <th className="pb-4 pr-2 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="text-sm">
                      {recruiters.length === 0 ? (
                        <tr>
                          <td colSpan="6" className="py-8 text-center text-slate-400">
                            No recruiters found.
                          </td>
                        </tr>
                      ) : (
                        recruiters.map((recruiter) => (
                          <tr key={recruiter.id} className="table-row-hover border-b border-slate-800 group transition-colors">
                            <td className="py-4 pl-2 rounded-l-lg">
                              <p className="font-bold text-white">{recruiter.name}</p>
                              <p className="mt-1 text-[10px] text-slate-500 font-mono break-all">{recruiter.id}</p>
                            </td>
                            <td className="py-4 text-slate-300">
                              {recruiter.email}
                            </td>
                            <td className="py-4">
                              <span className="inline-flex items-center gap-1.5 rounded-lg bg-slate-800 px-2 py-1 text-xs font-semibold ring-1 ring-slate-700 text-slate-300">
                                {recruiter.role}
                              </span>
                            </td>
                            <td className="py-4 text-slate-400 text-xs">
                              {new Date(recruiter.created_at).toLocaleDateString()}
                            </td>
                            <td className="py-4">
                              {getStatusBadge(recruiter.status)}
                            </td>
                            <td className="py-4 pr-2 text-right rounded-r-lg">
                              {recruiter.status === 'PENDING' ? (
                                <div className="flex justify-end gap-2">
                                  <button
                                    onClick={() => handleApprove(recruiter.id)}
                                    className="rounded-lg bg-accent/20 px-3 py-1.5 text-xs font-bold text-accent ring-1 ring-accent/40 hover:bg-accent hover:text-slate-900 transition-all shadow-[0_0_10px_rgba(20,184,166,0.1)]"
                                  >
                                    Approve
                                  </button>
                                  <button
                                    onClick={() => handleReject(recruiter.id)}
                                    className="rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-bold text-slate-300 ring-1 ring-slate-700 hover:bg-red-500 hover:text-white hover:ring-red-500 transition-all"
                                  >
                                    Reject
                                  </button>
                                </div>
                              ) : (
                                <span className="text-xs text-slate-500 italic">Actioned</span>
                              )}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </div>
        </div>
      </main>
    </div>
  );
}
