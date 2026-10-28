import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import { getUserDashboard } from '../utils/api';

export default function Dashboard() {
  const navigate = useNavigate();
  const [dashboardData, setDashboardData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showApiModal, setShowApiModal] = useState(false);
  const [copiedCurl, setCopiedCurl] = useState(false);

  useEffect(() => {
    const fetchDashboard = async () => {
      try {
        setLoading(true);
        const data = await getUserDashboard();
        setDashboardData(data);
      } catch (err) {
        console.error("Error fetching dashboard:", err);
      } finally {
        setLoading(false);
      }
    };
    fetchDashboard();
  }, []);

  const metrics = dashboardData?.metrics || {};
  const invitesSent = metrics.invites_sent ?? 0;
  const interested = metrics.interested ?? 0;
  const scheduled = metrics.meeting_scheduled ?? 0;
  const notInterested = metrics.not_interested ?? 0;
  const awaiting = metrics.awaiting ?? 0;

  const candidatesList = dashboardData?.recent_candidates || [];

  const sampleCurl = `curl -X POST "http://localhost:8000/api/outreach/send-array" \\
  -H "Content-Type: application/json" \\
  -d '[
    {
      "name": "Rahul Sharma",
      "role": "Software Engineer",
      "no": "917439717970"
    }
  ]'`;

  const copyCurlToClipboard = () => {
    navigator.clipboard.writeText(sampleCurl);
    setCopiedCurl(true);
    setTimeout(() => setCopiedCurl(false), 2000);
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'INTERVIEW_SCHEDULED':
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-bold text-emerald-400 ring-1 ring-emerald-500/30">
            <span className="size-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            Scheduled
          </span>
        );
      case 'INTERESTED':
      case 'INTERVIEW_LINK_SENT':
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-brand/20 px-3 py-1 text-xs font-bold text-brand ring-1 ring-brand/30">
            <span className="size-1.5 rounded-full bg-brand"></span>
            Interested
          </span>
        );
      case 'NOT_INTERESTED':
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-800 px-3 py-1 text-xs font-bold text-slate-400 ring-1 ring-slate-700">
            Not Interested
          </span>
        );
      case 'CONTACTED':
      default:
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-500/15 px-3 py-1 text-xs font-bold text-blue-400 ring-1 ring-blue-500/30">
            Awaiting Reply
          </span>
        );
    }
  };

  const formatScheduledDate = (iso) => {
    if (!iso) return null;
    try {
      const d = new Date(iso);
      return d.toLocaleDateString('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: true,
      });
    } catch {
      return iso;
    }
  };

  return (
    <div className="relative min-h-screen w-full overflow-hidden antialiased pb-20">
      <div className="glow-bg-large top-[-30%] left-[-20%] animate-pulse-slow"></div>
      <div
        className="glow-bg-large bottom-[-20%] right-[-10%] animate-pulse-slow"
        style={{ animationDelay: '2s', background: 'radial-gradient(circle, rgba(20,184,166,0.1) 0%, rgba(59,130,246,0.05) 40%, rgba(2,6,23,0) 70%)' }}
      ></div>

      <Header />

      <main className="relative z-10">
        <div className="mx-auto max-w-7xl px-5 py-8 sm:px-8">
          {/* Header row */}
          <div className="mb-8 flex flex-wrap items-end justify-between gap-6 animate-slide-up opacity-0-init animate-delay-100">
            <div>
              <div className="mb-2 inline-flex items-center gap-2.5 rounded-full bg-slate-800/80 px-3 py-1.5 ring-1 ring-slate-700">
                <span className="size-2 rounded-full bg-brand shadow-[0_0_10px_rgba(59,130,246,0.8)]"></span>
                <p className="text-xs font-bold uppercase tracking-[0.15em] text-slate-300">WhatsApp Recruitment Hub</p>
              </div>
              <h1 className="font-display text-4xl font-bold tracking-tight sm:text-5xl mt-2 text-white">
                Good morning, {dashboardData?.user_name || 'Recruiter'}.
              </h1>
              <p className="mt-3 text-base text-slate-400">
                Real-time tracking of candidate invites, replies, and scheduled interviews.
              </p>
            </div>

            <div className="flex items-center gap-3">
              <button
                onClick={() => setShowApiModal(true)}
                className="flex items-center gap-2 rounded-xl bg-slate-800/90 px-4 py-2.5 text-xs font-bold text-slate-200 ring-1 ring-slate-700 hover:bg-slate-700 hover:text-white transition-all shadow-sm"
              >
                <svg className="w-4 h-4 text-brand" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                </svg>
                External API Endpoint
              </button>
              <Link
                to="/outreach/send"
                className="flex items-center gap-2 rounded-xl bg-brand px-5 py-2.5 text-xs font-bold text-white shadow-[0_0_20px_rgba(59,130,246,0.4)] hover:bg-brand/90 hover:scale-[1.02] transition-all"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
                </svg>
                Send Outreach
              </Link>
            </div>
          </div>

          {/* 4 Primary Metric Cards */}
          <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 animate-slide-up opacity-0-init animate-delay-200">
            {/* Card 1: Invites Sent */}
            <div className="glass-dark glass-dark-card rounded-2xl p-6 relative overflow-hidden group">
              <div className="absolute right-0 top-0 p-4 opacity-5 text-brand transition-transform duration-500 group-hover:scale-110 group-hover:rotate-12">
                <svg className="w-20 h-20" fill="currentColor" viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" /></svg>
              </div>
              <p className="text-xs font-bold uppercase tracking-wider text-slate-400 relative z-10">Invites Sent</p>
              <p className="mt-2 font-display text-5xl font-bold text-white relative z-10">{invitesSent}</p>
              <p className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-brand/20 px-2 py-1 text-[11px] font-bold text-brand ring-1 ring-brand/30 relative z-10">
                <span className="size-1.5 rounded-full bg-brand animate-pulse"></span> {awaiting} awaiting reply
              </p>
            </div>

            {/* Card 2: Interested */}
            <div className="glass-dark glass-dark-card rounded-2xl p-6 relative overflow-hidden group">
              <div className="absolute right-0 top-0 p-4 opacity-5 text-emerald-400 transition-transform duration-500 group-hover:scale-110 group-hover:-rotate-12">
                <svg className="w-20 h-20" fill="currentColor" viewBox="0 0 24 24"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" /></svg>
              </div>
              <p className="text-xs font-bold uppercase tracking-wider text-slate-400 relative z-10">Interested</p>
              <p className="mt-2 font-display text-5xl font-bold text-emerald-400 relative z-10">{interested}</p>
              <p className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-emerald-500/20 px-2 py-1 text-[11px] font-bold text-emerald-300 ring-1 ring-emerald-500/30 relative z-10">
                <span className="size-1.5 rounded-full bg-emerald-400"></span> Link sent to schedule
              </p>
            </div>

            {/* Card 3: Meeting Scheduled */}
            <div className="glass-dark glass-dark-card rounded-2xl p-6 relative overflow-hidden group">
              <div className="absolute right-0 top-0 p-4 opacity-5 text-accent transition-transform duration-500 group-hover:scale-110 group-hover:rotate-12">
                <svg className="w-20 h-20" fill="currentColor" viewBox="0 0 24 24"><path d="M19 3h-1V1h-2v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V8h14v11zM7 10h5v5H7z" /></svg>
              </div>
              <p className="text-xs font-bold uppercase tracking-wider text-slate-400 relative z-10">Meeting Scheduled</p>
              <p className="mt-2 font-display text-5xl font-bold text-accent relative z-10">{scheduled}</p>
              <p className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-accent/20 px-2 py-1 text-[11px] font-bold text-accent ring-1 ring-accent/30 relative z-10">
                <span className="size-1.5 rounded-full bg-accent"></span> Confirmed interviews
              </p>
            </div>

            {/* Card 4: Not Interested */}
            <div className="glass-dark glass-dark-card rounded-2xl p-6 relative overflow-hidden group">
              <div className="absolute right-0 top-0 p-4 opacity-5 text-slate-400 transition-transform duration-500 group-hover:scale-110 group-hover:-rotate-12">
                <svg className="w-20 h-20" fill="currentColor" viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z" /></svg>
              </div>
              <p className="text-xs font-bold uppercase tracking-wider text-slate-400 relative z-10">Not Interested</p>
              <p className="mt-2 font-display text-5xl font-bold text-slate-300 relative z-10">{notInterested}</p>
              <p className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-slate-800 px-2 py-1 text-[11px] font-semibold text-slate-400 ring-1 ring-slate-700 relative z-10">
                Declined invitation
              </p>
            </div>
          </section>

          {/* Outreach Pipeline Table */}
          <div className="mt-8 grid gap-6 lg:grid-cols-12 animate-slide-up opacity-0-init animate-delay-300">
            <section className="glass-dark rounded-[24px] p-6 sm:p-8 lg:col-span-12">
              <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.15em] text-slate-400">Live Funnel</p>
                  <h2 className="mt-1 font-display text-2xl font-bold text-white">Outreach & Scheduling Activity</h2>
                </div>
                <div className="flex items-center gap-2">
                  <Link
                    to="/outreach"
                    className="rounded-xl bg-slate-800/80 px-4 py-2 text-xs font-bold text-slate-300 ring-1 ring-slate-700 hover:bg-slate-700 hover:text-white transition-all"
                  >
                    View All Responses
                  </Link>
                  <Link
                    to="/candidates"
                    className="rounded-xl bg-brand/20 px-4 py-2 text-xs font-bold text-brand ring-1 ring-brand/30 hover:bg-brand/30 transition-all"
                  >
                    View Scheduled Candidates
                  </Link>
                </div>
              </div>

              <div className="overflow-auto max-h-[500px] custom-scrollbar pb-2 pr-1 relative">
                <table className="w-full min-w-[760px] text-left border-collapse">
                  <thead className="sticky top-0 bg-[#0B1121] z-10 before:absolute before:inset-0 before:bg-slate-900/50 before:-z-10 before:backdrop-blur-md">
                    <tr className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                      <th className="pb-4 pt-4 pl-3 border-b border-slate-700">Candidate</th>
                      <th className="pb-4 pt-4 border-b border-slate-700">Role</th>
                      <th className="pb-4 pt-4 border-b border-slate-700">WhatsApp</th>
                      <th className="pb-4 pt-4 border-b border-slate-700">Status</th>
                      <th className="pb-4 pt-4 border-b border-slate-700">Interview Slot / Link</th>
                      <th className="pb-4 pt-4 pr-3 text-right border-b border-slate-700">Action</th>
                    </tr>
                  </thead>
                  <tbody className="text-sm">
                    {loading ? (
                      <tr>
                        <td colSpan="6" className="py-12 text-center text-slate-400">
                          <div className="flex justify-center items-center">
                            <div className="animate-spin rounded-full h-7 w-7 border-b-2 border-brand"></div>
                          </div>
                        </td>
                      </tr>
                    ) : candidatesList.length > 0 ? candidatesList.map((cand) => (
                      <tr key={cand.job_candidate_id || cand.id} className="table-row-hover border-b border-slate-800 group">
                        <td className="py-4 pl-3 rounded-l-lg">
                          <p className="font-bold text-white group-hover:text-brand transition-colors">{cand.name}</p>
                        </td>
                        <td className="py-4 font-medium text-slate-300">
                          {cand.role}
                        </td>
                        <td className="py-4 font-mono text-xs text-slate-400">
                          {cand.phone || '—'}
                        </td>
                        <td className="py-4">
                          {getStatusBadge(cand.status)}
                        </td>
                        <td className="py-4 text-xs">
                          {cand.interview_scheduled_at ? (
                            <div>
                              <p className="font-bold text-emerald-400">{formatScheduledDate(cand.interview_scheduled_at)}</p>
                              {cand.interview_link && (
                                <a
                                  href={cand.interview_link}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="text-[11px] text-brand hover:underline mt-0.5 inline-block"
                                >
                                  Join Meeting →
                                </a>
                              )}
                            </div>
                          ) : (
                            <span className="text-slate-500">—</span>
                          )}
                        </td>
                        <td className="py-4 pr-3 text-right rounded-r-lg">
                          {cand.status === 'INTERVIEW_SCHEDULED' ? (
                            <button
                              onClick={() => navigate('/candidates')}
                              className="rounded-lg bg-emerald-500/20 px-3 py-1.5 text-xs font-bold text-emerald-300 hover:bg-emerald-500/30 transition-all"
                            >
                              View in Candidates
                            </button>
                          ) : (
                            <button
                              onClick={() => navigate('/outreach')}
                              className="rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-bold text-slate-300 hover:bg-slate-700 transition-all"
                            >
                              View Response
                            </button>
                          )}
                        </td>
                      </tr>
                    )) : (
                      <tr>
                        <td colSpan="6" className="py-12 text-center text-slate-400">
                          <div className="max-w-md mx-auto">
                            <p className="font-semibold text-white">No outreach invitations sent yet</p>
                            <p className="text-xs text-slate-400 mt-1">
                              Send your first WhatsApp candidate invitation using the "Send Outreach" button above or via our API.
                            </p>
                            <Link
                              to="/outreach/send"
                              className="mt-4 inline-flex items-center gap-2 rounded-xl bg-brand px-4 py-2 text-xs font-bold text-white shadow-md hover:bg-brand/90 transition-all"
                            >
                              Send First Outreach
                            </Link>
                          </div>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        </div>
      </main>

      {/* External API Integration Modal */}
      {showApiModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="glass-dark border border-slate-700 rounded-2xl max-w-2xl w-full p-6 relative animate-scale-in">
            <div className="flex items-center justify-between pb-4 border-b border-slate-700">
              <div>
                <h3 className="font-display text-xl font-bold text-white">External System API Integration</h3>
                <p className="text-xs text-slate-400 mt-1">Give this API endpoint and format to any external ATS or candidate system</p>
              </div>
              <button
                onClick={() => setShowApiModal(false)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
              >
                ✕
              </button>
            </div>

            <div className="mt-4 space-y-4">
              <div>
                <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Endpoint</span>
                <div className="mt-1 flex items-center gap-2 bg-slate-900 rounded-xl px-4 py-2.5 font-mono text-xs text-emerald-400 border border-slate-800">
                  <span className="font-bold text-brand">POST</span>
                  <span>/api/outreach/send-array</span>
                  <span className="text-slate-500">or</span>
                  <span>/api/outreach/invite</span>
                </div>
              </div>

              <div>
                <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Expected Payload Format</span>
                <p className="text-xs text-slate-400 mt-0.5">Send a single candidate object or an array of candidates with name, role, and phone/no:</p>
                <div className="mt-1 relative bg-slate-950 rounded-xl p-4 font-mono text-xs text-slate-300 border border-slate-800 overflow-x-auto">
                  <pre>{`[
  {
    "name": "Rahul Sharma",
    "role": "Software Engineer",
    "no": "917439717970"
  }
]`}</pre>
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-400">cURL Example</span>
                  <button
                    onClick={copyCurlToClipboard}
                    className="text-xs font-bold text-brand hover:underline"
                  >
                    {copiedCurl ? '✓ Copied!' : 'Copy cURL'}
                  </button>
                </div>
                <div className="mt-1 relative bg-slate-950 rounded-xl p-4 font-mono text-xs text-slate-300 border border-slate-800 overflow-x-auto max-h-40">
                  <pre>{sampleCurl}</pre>
                </div>
              </div>

              <div className="rounded-xl bg-brand/10 p-3 border border-brand/20 text-xs text-slate-300 flex items-start gap-2">
                <span className="text-brand font-bold text-base leading-none">ℹ</span>
                <span>
                  When submitted, WhatsApp invites will immediately be dispatched to each candidate.
                  Replies and scheduled interviews will automatically populate in your dashboard.
                </span>
              </div>
            </div>

            <div className="mt-6 flex justify-end">
              <button
                onClick={() => setShowApiModal(false)}
                className="rounded-xl bg-slate-800 px-5 py-2 text-xs font-bold text-white hover:bg-slate-700 transition-all"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

