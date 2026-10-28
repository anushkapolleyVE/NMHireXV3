import { useState, useEffect } from 'react';
import { getAllCandidates } from '../utils/api';
import Header from '../components/Header';

import ProfileModal from '../components/ProfileModal';

const formatScheduledTime = (isoStr) => {
  if (!isoStr) return null;
  try {
    const d = new Date(isoStr);
    const date = d.toLocaleDateString('en-IN', {
      weekday: 'short', day: '2-digit', month: 'short', year: 'numeric',
    });
    const time = d.toLocaleTimeString('en-IN', {
      hour: '2-digit', minute: '2-digit', hour12: true,
    });
    return { date, time };
  } catch {
    return null;
  }
};

export default function Candidates() {
  const [search, setSearch] = useState('');
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [copiedId, setCopiedId] = useState(null);


  useEffect(() => {
    const fetchCandidates = async () => {
      try {
        const data = await getAllCandidates();
        const enrichedData = data.map(c => {
          const scheduled = formatScheduledTime(c.interview_scheduled_at);
          const dateStr = scheduled ? `${scheduled.date} ${scheduled.time}` : '';
          return {
            ...c,
            searchStr: `${c.name} ${c.job || ''} ${c.skills || ''} ${dateStr}`.toLowerCase()
          };
        });
        setCandidates(enrichedData);
      } catch (err) {
        console.error('Failed to fetch candidates', err);
      } finally {
        setLoading(false);
      }
    };
    fetchCandidates();
  }, []);

  const filtered = candidates.filter(c =>
    c.searchStr.includes(search.toLowerCase())
  );

  const scheduledCount = candidates.filter(c => !!c.interview_scheduled_at).length;

  const FALLBACK_TEAMS_LINK = 'https://teams.microsoft.com/l/meetup-join/interview';

  const handleCopyMeetingLink = (candidateId, interviewLink) => {
    const link = interviewLink || FALLBACK_TEAMS_LINK;
    navigator.clipboard.writeText(link).catch(() => {});
    setCopiedId(candidateId);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleOpenMeetingLink = (interviewLink) => {
    window.open(interviewLink || FALLBACK_TEAMS_LINK, '_blank');
  };

  return (
    <div className="relative min-h-screen w-full overflow-hidden antialiased pb-20">
      <div className="glow-bg top-[-30%] left-[-20%] animate-pulse-slow"></div>
      <div className="glow-bg bottom-[-20%] right-[-10%] animate-pulse-slow"
        style={{ animationDelay: '2s', background: 'radial-gradient(circle, rgba(20,184,166,0.1) 0%, rgba(59,130,246,0.05) 40%, rgba(2,6,23,0) 70%)' }}
      ></div>

      <Header />
      <ProfileModal isOpen={!!selectedCandidate} onClose={() => setSelectedCandidate(null)} candidate={selectedCandidate} />


      <main className="relative z-10">
        <div className="mx-auto max-w-6xl px-5 py-8 sm:px-8">

          <div className="mb-10 flex flex-col sm:flex-row justify-between items-start gap-4 animate-slide-up opacity-0-init animate-delay-100">
            <div>
              <div className="mb-2 inline-flex items-center gap-2.5 rounded-full bg-slate-800/80 px-3 py-1.5 ring-1 ring-slate-700 w-max">
                <span className="size-2 rounded-full bg-accent shadow-[0_0_10px_rgba(20,184,166,0.8)]"></span>
                <p className="text-xs font-bold uppercase tracking-[0.15em] text-slate-300">Ready for Interview</p>
              </div>
              <h1 className="font-display text-4xl font-bold tracking-tight sm:text-5xl text-white">Interested Candidates</h1>
              <p className="text-base text-slate-400">Review candidates who have accepted your outreach invitation.</p>
            </div>

          </div>

          <div className="mb-8 flex flex-wrap items-center gap-4 animate-slide-up opacity-0-init animate-delay-200">
            <div className="glass-dark glass-dark-card rounded-2xl p-6 flex-1 relative overflow-hidden group min-w-[180px]">
              <p className="text-xs font-bold uppercase tracking-wider text-slate-400 relative z-10">Total Interested</p>
              <p className="mt-2 font-display text-4xl font-bold text-white relative z-10">{candidates.length}</p>
              <p className="mt-2 text-[11px] font-semibold text-slate-400 relative z-10">Waiting for next steps</p>
            </div>

            <div className="glass-dark glass-dark-card rounded-2xl p-6 flex-1 relative overflow-hidden group min-w-[180px]"
              style={{ background: 'linear-gradient(135deg, rgba(20,184,166,0.08) 0%, rgba(15,23,42,0.6) 100%)' }}>
              <p className="text-xs font-bold uppercase tracking-wider text-teal-400 relative z-10">Interviews Scheduled</p>
              <p className="mt-2 font-display text-4xl font-bold text-white relative z-10">{scheduledCount}</p>
              <p className="mt-2 text-[11px] font-semibold text-slate-400 relative z-10">Time &amp; date confirmed</p>
              <svg className="absolute right-4 bottom-4 w-10 h-10 text-teal-500/20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
            </div>

            <div className="relative flex-[2] min-w-[300px] self-end">
              <svg className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <input className="input-dark w-full rounded-xl pl-10 pr-4 py-4 text-sm placeholder:text-slate-500"
                placeholder="Search candidates by name, skill, or date..."
                value={search} onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          </div>

          <div className="glass-dark rounded-[24px] overflow-hidden animate-slide-up opacity-0-init animate-delay-300">
            <div className="overflow-x-auto pb-2">
              <table className="w-full min-w-[960px] text-left border-collapse">
                <thead>
                  <tr className="border-b border-slate-700 bg-slate-900/50 text-[11px] font-bold uppercase tracking-wider text-slate-400">
                    <th className="py-4 pl-6">Candidate</th>
                    <th className="py-4">Job / Role</th>
                    <th className="py-4">Status</th>
                    <th className="py-4">
                      <span className="flex items-center gap-1.5">
                        <svg className="w-3.5 h-3.5 text-teal-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                        </svg>
                        Interview Scheduled
                      </span>
                    </th>
                    <th className="py-4 pr-6 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="text-sm">
                  {loading ? (
                    <tr><td colSpan="5" className="py-12 text-center text-slate-500">Loading interested candidates...</td></tr>
                  ) : filtered.length === 0 ? (
                    <tr><td colSpan="5" className="py-12 text-center text-slate-500">
                      {search ? 'No candidates found matching your search.' : 'No candidates have accepted outreach invites yet.'}
                    </td></tr>
                  ) : (
                    filtered.map(c => {
                      const scheduled = formatScheduledTime(c.interview_scheduled_at);
                      const isScheduled = !!scheduled;
                      return (
                        <tr key={c.id} className="table-row-hover border-b border-slate-800/50 group">

                          <td className="py-5 pl-6">
                            <p className="font-bold text-white text-base">{c.name}</p>
                            {c.email && <p className="text-xs text-slate-400 mt-1">{c.email}</p>}
                          </td>

                          <td className="py-5">
                            <p className="font-medium text-slate-300">{c.job || 'Role unknown'}</p>
                            <p className="mt-1 text-[11px] text-slate-500 line-clamp-1 max-w-[200px]">{c.skills || ''}</p>
                          </td>

                          <td className="py-5">
                            {isScheduled ? (
                              <span className="inline-flex rounded-full bg-teal-500/20 px-3 py-1 text-[11px] font-bold text-teal-300 ring-1 ring-teal-500/30 shadow-[0_0_8px_rgba(20,184,166,0.15)] items-center gap-1.5 w-max flex">
                                <span className="size-1.5 rounded-full bg-teal-400"></span>Scheduled
                              </span>
                            ) : c.stage === 'INTERESTED' ? (
                              <span className="inline-flex rounded-full bg-amber-500/15 px-3 py-1 text-[11px] font-bold text-amber-300 ring-1 ring-amber-500/30 items-center gap-1.5 w-max flex">
                                <span className="size-1.5 rounded-full bg-amber-400 animate-pulse"></span>Awaiting Time
                              </span>
                            ) : (
                              <span className="inline-flex rounded-full bg-accent/20 px-3 py-1 text-[11px] font-bold text-accent ring-1 ring-accent/30 shadow-[0_0_8px_rgba(20,184,166,0.15)] items-center gap-1.5 w-max flex">
                                <span className="size-1.5 rounded-full bg-accent animate-pulse"></span>Interested
                              </span>
                            )}
                          </td>

                          <td className="py-5">
                            {scheduled ? (
                              <div className="flex flex-col gap-0.5">
                                <span className="flex items-center gap-1.5 text-teal-300 font-semibold text-xs">
                                  <svg className="w-3.5 h-3.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                  </svg>
                                  {scheduled.date}
                                </span>
                                <span className="flex items-center gap-1.5 text-slate-400 text-xs pl-5">
                                  <svg className="w-3 h-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                                  </svg>
                                  {scheduled.time}
                                </span>
                              </div>
                            ) : (
                              <span className="text-slate-600 text-xs italic">Not selected yet</span>
                            )}
                          </td>

                          <td className="py-5 pr-6">
                            <div className="flex items-center justify-end gap-3">
                              <button onClick={() => setSelectedCandidate(c)}
                                className="rounded-xl bg-slate-800 px-4 py-2 text-xs font-bold text-white ring-1 ring-slate-700 hover:bg-slate-700 transition-all flex items-center gap-2">
                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                                </svg>
                                View Profile
                              </button>
                              <div className="flex items-center gap-1">
                                <button onClick={() => handleCopyMeetingLink(c.id, c.interview_link)}
                                  title={c.interview_link ? 'Copy interview link' : 'Copy placeholder link'}
                                  className={`rounded-l-xl px-4 py-2 text-xs font-bold text-white flex items-center gap-2 transition-all ${c.interview_link ? 'btn-neon' : 'bg-slate-700 hover:bg-slate-600 ring-1 ring-slate-600'}`}>
                                  {copiedId === c.id ? (
                                    <><svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" /></svg>Copied!</>
                                  ) : (
                                    <><svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                                      {c.interview_link ? 'Copy link' : 'Copy meeting link'}</>
                                  )}
                                </button>
                                {c.interview_link && (
                                  <button onClick={() => handleOpenMeetingLink(c.interview_link)}
                                    title="Open in Teams"
                                    className="btn-neon rounded-r-xl px-3 py-2 text-xs font-bold text-white flex items-center transition-all border-l border-white/20">
                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                    </svg>
                                  </button>
                                )}
                              </div>
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
