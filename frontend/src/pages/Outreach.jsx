import { useState, useEffect } from 'react';
import { getOutreachData, updateCandidateStatus } from '../utils/api';
import Header from '../components/Header';

export default function Outreach() {
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchOutreach = async () => {
      try {
        const data = await getOutreachData();

        if (data && Array.isArray(data)) {
          setCandidates(data);
        }
      } catch (err) {
        console.error('Failed to fetch outreach data', err);
      } finally {
        setLoading(false);
      }
    };

    fetchOutreach();
  }, []);

  const handleStatusUpdate = async (jobId, candidateId, status) => {
    try {
      await updateCandidateStatus(jobId, candidateId, status);

      setCandidates(prev =>
        prev.map(candidate =>
          candidate.id === candidateId &&
          candidate.job_id === jobId
            ? {
                ...candidate,
                status,
              }
            : candidate
        )
      );
    } catch (err) {
      console.error('Failed to update status', err);
    }
  };

  const getStatusBadge = (candidate) => {
    const status = candidate.status;
    const intent = candidate.response_intent;

    // Negative response
    if (
      status === 'NOT_INTERESTED' ||
      intent === 'NEGATIVE' ||
      intent === 'NOT_INTERESTED'
    ) {
      return (
        <span className="rounded-xl bg-slate-800/80 px-4 py-2 text-sm font-bold text-slate-400 ring-1 ring-slate-700">
          Not Interested
        </span>
      );
    }

    // Positive response / interview link sent
    if (
      status === 'INTERVIEW_LINK_SENT' ||
      status === 'INTERESTED' ||
      intent === 'POSITIVE' ||
      intent === 'INTERESTED'
    ) {
      return (
        <span className="rounded-xl bg-brand/20 px-4 py-2 text-sm font-bold text-brand ring-1 ring-brand/30 flex items-center gap-2">
          <svg
            className="w-4 h-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M5 13l4 4L19 7"
            />
          </svg>

          Interview link sent
        </span>
      );
    }

    // Candidate replied but intent is unclear
    if (
      candidate.response_text &&
      (!intent || intent === 'UNKNOWN' || intent === 'NEUTRAL')
    ) {
      return (
        <span className="rounded-xl bg-yellow-500/10 px-4 py-2 text-sm font-bold text-yellow-400 ring-1 ring-yellow-500/30">
          Response Received
        </span>
      );
    }

    // Candidate has not replied
    return (
      <span className="rounded-xl bg-blue-500/10 px-4 py-2 text-sm font-bold text-blue-400 ring-1 ring-blue-500/30">
        Awaiting Response
      </span>
    );
  };

  const getIntentLabel = (candidate) => {
    if (!candidate.response_text) return null;

    switch (candidate.response_intent) {
      case 'INTERESTED':
      case 'POSITIVE':
        return (
          <span className="text-xs font-semibold text-emerald-400">
            ✓ Interested
          </span>
        );
      case 'NOT_INTERESTED':
      case 'NEGATIVE':
        return (
          <span className="text-xs font-semibold text-slate-500">
            ✗ Not Interested
          </span>
        );
      case 'UNKNOWN':
      case 'NEUTRAL':
      default:
        return (
          <span className="text-xs font-semibold text-yellow-400">
            ⏳ Awaiting Review
          </span>
        );
    }
  };

  return (
    <div className="relative min-h-screen w-full overflow-hidden antialiased pb-20">

      {/* Background Glow */}
      <div className="glow-bg top-[-30%] left-[-20%] animate-pulse-slow"></div>

      <div
        className="glow-bg bottom-[-20%] right-[-10%] animate-pulse-slow"
        style={{
          animationDelay: '2s',
          background:
            'radial-gradient(circle, rgba(20,184,166,0.1) 0%, rgba(59,130,246,0.05) 40%, rgba(2,6,23,0) 70%)',
        }}
      ></div>

      <Header />

      <main className="relative z-10">
        <div className="mx-auto max-w-5xl px-5 py-8 sm:px-8">

          {/* Header */}
          <div className="mb-10 flex flex-col gap-2 animate-slide-up opacity-0-init animate-delay-100">
            <h1 className="font-display text-4xl font-bold tracking-tight sm:text-5xl text-white">
              Outreach Responses
            </h1>

            <p className="text-base text-slate-400">
              Track WhatsApp responses and candidate interest automatically.
            </p>
          </div>

          {/* Candidates */}
          <div className="space-y-4 animate-slide-up opacity-0-init animate-delay-200">

            {/* Loading */}
            {loading ? (
              <div className="py-12 text-center text-slate-500">
                Loading outreach candidates...
              </div>
            ) : candidates.length === 0 ? (

              /* Empty State */
              <div className="glass-dark rounded-2xl p-12 text-center border border-slate-800">
                <p className="text-lg font-bold text-slate-300">
                  No candidates in outreach.
                </p>

                <p className="text-sm text-slate-500 mt-2">
                  When you send WhatsApp invites or add candidates to outreach,
                  they'll appear here.
                </p>
              </div>

            ) : (

              /* Candidate List */
              candidates.map(candidate => (

                <div
                  key={`${candidate.job_id}-${candidate.id}`}
                  className="glass-dark glass-dark-card rounded-2xl p-6 flex flex-col gap-5"
                >

                  {/* Candidate Information */}
                  <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">

                    <div>
                      <h3 className="text-xl font-bold text-white mb-1">
                        {candidate.name}
                      </h3>

                      <p className="text-sm text-slate-400">
                        {candidate.job}
                      </p>
                    </div>

                    {/* Status */}
                    <div>
                      {getStatusBadge(candidate)}
                    </div>

                  </div>

                  {/* WhatsApp Response */}
                  {candidate.response_text ? (
                    <div className="rounded-xl bg-slate-900/70 border border-slate-800 p-4">

                      <div className="flex items-center justify-between mb-2">

                        <p className="text-xs uppercase tracking-wider font-bold text-slate-500">
                          Candidate Response
                        </p>

                        {getIntentLabel(candidate)}

                      </div>

                      <p className="text-sm text-slate-200 leading-relaxed">
                        "{candidate.response_text}"
                      </p>

                      {candidate.responded_at && (
                        <p className="text-xs text-slate-600 mt-2">
                          Replied: {new Date(
                            candidate.responded_at
                          ).toLocaleString()}
                        </p>
                      )}

                    </div>
                  ) : (

                    /* No Response */
                    <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-4">

                      <p className="text-xs uppercase tracking-wider font-bold text-slate-600 mb-1">
                        WhatsApp Response
                      </p>

                      <p className="text-sm text-slate-500">
                        No response received yet.
                      </p>

                    </div>
                  )}

                  {/* Actions — auto-handled by webhook intent detection */}
                  <div className="flex flex-wrap items-center gap-3">

                    {candidate.status === 'NOT_INTERESTED' || candidate.response_intent === 'NOT_INTERESTED' || candidate.response_intent === 'NEGATIVE' ? (

                      <span className="rounded-xl bg-slate-800/80 px-4 py-2 text-sm font-bold text-slate-500 ring-1 ring-slate-700 flex items-center gap-2">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                        Not Interested
                      </span>

                    ) : candidate.status === 'INTERESTED' || candidate.status === 'INTERVIEW_LINK_SENT' || candidate.response_intent === 'INTERESTED' || candidate.response_intent === 'POSITIVE' ? (

                      <span className="rounded-xl bg-emerald-500/20 px-4 py-2 text-sm font-bold text-emerald-400 ring-1 ring-emerald-500/30 flex items-center gap-2">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                        </svg>
                        Interested — Interview link sent
                      </span>

                    ) : (

                      // Still waiting for response or neutral — allow manual override
                      <>
                        <button
                          onClick={() => handleStatusUpdate(candidate.job_id, candidate.id, 'NOT_INTERESTED')}
                          className="rounded-xl bg-slate-800 hover:bg-slate-700 px-5 py-2.5 text-sm font-bold text-slate-300 transition-colors ring-1 ring-slate-700"
                        >
                          Not Interested
                        </button>
                        <button
                          onClick={() => handleStatusUpdate(candidate.job_id, candidate.id, 'INTERESTED')}
                          className="btn-neon rounded-xl px-5 py-2.5 text-sm font-bold text-white shadow-sm"
                        >
                          Interested
                        </button>
                      </>

                    )}

                  </div>

                </div>

              ))
            )}

          </div>
        </div>
      </main>
    </div>
  );
}