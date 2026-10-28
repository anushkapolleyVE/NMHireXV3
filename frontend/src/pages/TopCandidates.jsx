import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import {
  createJobFromRequisition,
  fetchTopCandidates,
  updateCandidateStatus,
  bulkUpdateCandidateStatus,
  getJobCandidates,
} from '../utils/api';

export default function TopCandidates() {
  const { vereq } = useParams();
  const navigate = useNavigate();
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusText, setStatusText] = useState('Creating job from requisition...');
  
  const [jobId, setJobId] = useState(null);
  const [whatsappContacted, setWhatsappContacted] = useState({});
  const [autoSending, setAutoSending] = useState(false);
  const [autoSendSummary, setAutoSendSummary] = useState(null);

  const autoTriggeredRef = useRef(false);

  // Automatically dispatch WhatsApp outreach to eligible top candidates
  const triggerAutoOutreach = async (jId, candidatesList) => {
    if (autoTriggeredRef.current) return;
    autoTriggeredRef.current = true;

    const top30 = candidatesList.slice(0, 30);
    const eligible = top30.filter(c => {
      const cId = c.candidate_id || c.id;
      const isContacted = c.status === 'CONTACTED' || c.recruitment_status === 'CONTACTED';
      const hasPhone = c.phone && c.phone !== '-' && String(c.phone).trim() !== '';
      return hasPhone && !isContacted;
    });

    if (eligible.length === 0) {
      console.log('No new candidates requiring outreach');
      return;
    }

    setAutoSending(true);

    // 1. Try dedicated bulk backend endpoint first
    try {
      const cIds = eligible.map(c => c.candidate_id || c.id);
      const res = await bulkUpdateCandidateStatus(jId, cIds, 'CONTACTED');
      
      if (res && res.data) {
        const successIds = (res.data.results || [])
          .filter(r => r.status === 'SUCCESS')
          .map(r => r.candidate_id);

        setWhatsappContacted(prev => {
          const next = { ...prev };
          successIds.forEach(id => { next[id] = true; });
          return next;
        });

        setAutoSendSummary({
          sent: res.data.sent ?? successIds.length,
          total: eligible.length,
        });
        setAutoSending(false);
        return;
      }
    } catch (bulkErr) {
      console.warn('Bulk endpoint failed, falling back to sequential dispatch:', bulkErr);
    }

    // 2. Fallback: sequential dispatch
    let sentCount = 0;
    for (let i = 0; i < eligible.length; i++) {
      const c = eligible[i];
      const cId = c.candidate_id || c.id;

      try {
        await updateCandidateStatus(jId, cId, 'CONTACTED');
        setWhatsappContacted(prev => ({ ...prev, [cId]: true }));
        sentCount++;
      } catch (err) {
        console.error(`Failed to auto-send invite to ${c.name}:`, err);
      }
    }

    setAutoSendSummary({ sent: sentCount, total: eligible.length });
    setAutoSending(false);
  };

  useEffect(() => {
    let isMounted = true;
    autoTriggeredRef.current = false;

    const fetchCandidates = async () => {
      try {
        setLoading(true);
        setError(null);
        
        // 1. Create job from requisition
        setStatusText('Creating job from requisition...');
        const jobData = await createJobFromRequisition(vereq);
        const jId = jobData.job_id;
        if (isMounted) setJobId(jId);

        // 2. Check if we already have candidates for this job in local DB
        setStatusText('Checking local database...');
        try {
          const localData = await getJobCandidates(jId);
          let localList = [];
          if (Array.isArray(localData)) localList = localData;
          else if (localData && Array.isArray(localData.data)) localList = localData.data;

          if (localList.length > 0) {
            if (isMounted) {
              setCandidates(localList);
              setLoading(false);
              triggerAutoOutreach(jId, localList);
            }
            return;
          }
        } catch (e) {
          console.warn("Failed to fetch local candidates, proceeding with screening", e);
        }

        // 3. Fetch top candidates via screening
        setStatusText('Sheela is starting to read resumes...');
        
        const loadingMessages = [
          "Analyzing candidate skills...",
          "Extracting domain experience...",
          "Comparing candidates against the JD...",
          "Ranking the best matches...",
          "Almost there, finalizing scores..."
        ];
        let msgIndex = 0;
        const intervalId = setInterval(() => {
          setStatusText(loadingMessages[msgIndex]);
          msgIndex = (msgIndex + 1) % loadingMessages.length;
        }, 4000);

        try {
          const matchData = await fetchTopCandidates(jId, vereq);
          clearInterval(intervalId);
          
          if (isMounted) {
            const apiData = matchData.data || matchData;
            let candidatesList = [];
            
            if (Array.isArray(apiData)) {
              candidatesList = apiData;
            } else if (apiData && Array.isArray(apiData.candidates)) {
              candidatesList = apiData.candidates;
            } else if (apiData && Array.isArray(apiData.matches)) {
              candidatesList = apiData.matches;
            } else if (apiData && Array.isArray(apiData.items)) {
              candidatesList = apiData.items;
            } else if (apiData && Array.isArray(apiData.data)) {
              candidatesList = apiData.data;
            } else if (apiData && Array.isArray(apiData.results)) {
              candidatesList = apiData.results;
            }

            setCandidates(candidatesList);
            setLoading(false);
            triggerAutoOutreach(jId, candidatesList);
          }
        } catch (fetchErr) {
          clearInterval(intervalId);
          throw fetchErr;
        }
      } catch (err) {
        if (isMounted) {
          console.error(err);
          setError(err.message || 'Failed to fetch top candidates');
          setLoading(false);
        }
      }
    };
    
    if (vereq) {
      fetchCandidates();
    }
    
    return () => { isMounted = false; };
  }, [vereq]);

  return (
    <div className="relative min-h-screen w-full overflow-hidden antialiased pb-20">
      <div className="glow-bg top-[-30%] left-[-20%] animate-pulse-slow"></div>
      <div className="glow-bg bottom-[-20%] right-[-10%] animate-pulse-slow"
        style={{ animationDelay: '2s', background: 'radial-gradient(circle, rgba(20,184,166,0.1) 0%, rgba(59,130,246,0.05) 40%, rgba(2,6,23,0) 70%)' }}
      ></div>

      <Header />

      <main className="relative z-10">
        <div className="mx-auto max-w-6xl px-5 py-8 sm:px-8">
          <button 
            onClick={() => navigate('/job-descriptions')}
            className="mb-6 inline-flex items-center text-sm font-medium text-slate-400 hover:text-white transition-colors cursor-pointer"
          >
            &larr; Back to JDs
          </button>
          
          <div className="mb-10 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 animate-slide-up opacity-0-init animate-delay-100">
            <div>
              <div className="mb-2 inline-flex items-center gap-2.5 rounded-full bg-slate-800/80 px-3 py-1.5 ring-1 ring-slate-700 w-max">
                <span className="size-2 rounded-full bg-accent shadow-[0_0_10px_rgba(20,184,166,0.8)]"></span>
                <p className="text-xs font-bold uppercase tracking-[0.15em] text-slate-300">Top Matches</p>
              </div>
              <h1 className="font-display text-4xl font-bold tracking-tight sm:text-5xl text-white">Candidates for {vereq}</h1>
              <p className="text-base text-slate-400">Review the top 30 candidates matched for this requisition.</p>
            </div>

            {/* Auto Outreach Status Badge */}
            <div className="flex items-center gap-3">
              {autoSending ? (
                <div className="inline-flex items-center gap-2.5 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 px-4 py-2.5 text-xs font-semibold text-emerald-400 shadow-sm animate-pulse">
                  <svg className="w-3.5 h-3.5 animate-spin text-emerald-400" viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" strokeDasharray="30 60" className="opacity-75"></circle>
                  </svg>
                  <span>Auto-sending WhatsApp invites...</span>
                </div>
              ) : autoSendSummary?.sent > 0 ? (
                <div className="inline-flex items-center gap-2 rounded-2xl bg-green-500/15 border border-green-500/30 px-4 py-2 text-xs font-bold text-green-300 shadow-sm">
                  <svg className="w-3.5 h-3.5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" />
                  </svg>
                  <span>{autoSendSummary.sent} invites automatically sent</span>
                </div>
              ) : (
                <div className="inline-flex items-center gap-2 rounded-2xl bg-slate-800/80 border border-slate-700 px-4 py-2 text-xs font-semibold text-slate-300 shadow-sm">
                  <span className="size-2 rounded-full bg-green-400"></span>
                  <span>Auto-invite active</span>
                </div>
              )}
            </div>
          </div>

          <div className="glass-dark rounded-[24px] overflow-hidden animate-slide-up opacity-0-init animate-delay-300 border border-slate-800/50">
            <div className="overflow-auto max-h-[600px] custom-scrollbar pb-2 pr-1 relative">
              <table className="w-full min-w-[960px] text-left border-collapse">
                <thead className="sticky top-0 bg-[#0B1121] z-10 before:absolute before:inset-0 before:bg-slate-900/50 before:-z-10 before:backdrop-blur-md">
                  <tr className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                    <th className="py-4 pl-6 border-b border-slate-700">Candidate</th>
                    <th className="py-4 border-b border-slate-700">Email / Phone</th>
                    <th className="py-4 border-b border-slate-700">Classification</th>
                    <th className="py-4 border-b border-slate-700">Score</th>
                    <th className="py-4 pr-6 text-right border-b border-slate-700">Status</th>
                  </tr>
                </thead>
                <tbody className="text-sm">
                  {loading ? (
                    <tr><td colSpan="5" className="py-12 text-center">
                      <div className="inline-flex flex-col items-center gap-3 text-slate-400">
                        <svg className="w-8 h-8 animate-spin text-accent" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                          <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" strokeDasharray="30 60" className="opacity-75"></circle>
                        </svg>
                        <span>{statusText}</span>
                      </div>
                    </td></tr>
                  ) : error ? (
                    <tr><td colSpan="5" className="py-12 text-center text-red-400">
                      Error: {error}
                    </td></tr>
                  ) : candidates.length === 0 ? (
                    <tr><td colSpan="5" className="py-12 text-center text-slate-500">
                      No candidates found for this requisition.
                    </td></tr>
                  ) : (
                    candidates.slice(0, 30).map((c, index) => {
                      const cId = c.candidate_id || c.id;
                      const isInvited = Boolean(
                        whatsappContacted[cId] ||
                        c.status === 'CONTACTED' ||
                        c.recruitment_status === 'CONTACTED'
                      );
                      const hasPhone = Boolean(c.phone && c.phone !== '-' && String(c.phone).trim() !== '');

                      return (
                        <tr key={cId || index} className="table-row-hover border-b border-slate-800/50 group">
                          <td className="py-5 pl-6">
                            <p className="font-bold text-white text-base">{c.name || 'Unknown Name'}</p>
                          </td>
                          <td className="py-5">
                            {c.email && <p className="font-medium text-slate-300">{c.email}</p>}
                            {c.phone && <p className="text-[11px] text-slate-500 font-mono">{c.phone}</p>}
                          </td>
                          <td className="py-5">
                            <span className={`inline-flex rounded-full px-3 py-1 text-[11px] font-bold ring-1 w-max ${c.classification === 'GOOD_FIT' ? 'bg-teal-500/20 text-teal-300 ring-teal-500/30' : 'bg-slate-500/20 text-slate-300 ring-slate-500/30'}`}>
                              {c.classification || 'N/A'}
                            </span>
                          </td>
                          <td className="py-5">
                            <div className="flex items-center gap-2">
                              <div className="h-2 w-24 bg-slate-800 rounded-full overflow-hidden">
                                <div className="h-full bg-accent" style={{ width: `${Math.min(100, Math.max(0, c.score || 0))}%` }}></div>
                              </div>
                              <span className="text-xs font-bold text-white">{Number(c.score || 0).toFixed(0)}</span>
                            </div>
                          </td>
                          <td className="py-5 pr-6 text-right">
                            <div className="flex justify-end items-center gap-2.5">
                              {c.resume_url && (
                                <a 
                                  href={c.resume_url} 
                                  target="_blank" 
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1.5 rounded-xl bg-slate-800 px-3 py-1.5 text-xs font-bold text-white shadow-sm ring-1 ring-slate-700 hover:bg-slate-700 transition-colors"
                                >
                                  <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                  </svg>
                                  Resume
                                </a>
                              )}

                              {isInvited ? (
                                <span className="inline-flex items-center gap-1.5 rounded-xl bg-green-500/20 text-green-400 border border-green-500/30 px-3 py-1.5 text-xs font-bold shadow-sm">
                                  <svg className="w-3.5 h-3.5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" />
                                  </svg>
                                  Invite sent
                                </span>
                              ) : autoSending && hasPhone ? (
                                <span className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 px-3 py-1.5 text-xs font-bold animate-pulse">
                                  <svg className="w-3 h-3 animate-spin text-emerald-400" viewBox="0 0 24 24" fill="none">
                                    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" strokeDasharray="30 60" className="opacity-75"></circle>
                                  </svg>
                                  Sending...
                                </span>
                              ) : !hasPhone ? (
                                <span className="inline-flex items-center gap-1.5 rounded-xl bg-slate-800/80 text-slate-500 border border-slate-700/60 px-3 py-1.5 text-xs font-medium">
                                  No Phone
                                </span>
                              ) : (
                                <span className="inline-flex items-center gap-1.5 rounded-xl bg-green-500/20 text-green-400 border border-green-500/30 px-3 py-1.5 text-xs font-bold shadow-sm">
                                  <svg className="w-3.5 h-3.5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" />
                                  </svg>
                                  Invite sent
                                </span>
                              )}
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
