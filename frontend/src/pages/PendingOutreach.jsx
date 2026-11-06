import { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import Header from '../components/Header';
import { getPendingOutreach, sendPendingOutreach } from '../utils/api';

// Official WhatsApp Logo SVG
const WhatsAppIcon = ({ className = "w-5 h-5" }) => (
  <svg
    className={className}
    viewBox="0 0 24 24"
    fill="currentColor"
    xmlns="http://www.w3.org/2000/svg"
  >
    <path d="M12.04 2C6.58 2 2.13 6.45 2.13 11.91C2.13 13.66 2.59 15.36 3.45 16.86L2.05 22L7.3 20.62C8.75 21.41 10.38 21.83 12.04 21.83C17.5 21.83 21.95 17.38 21.95 11.92C21.95 9.27 20.92 6.78 19.05 4.91C17.18 3.03 14.69 2 12.04 2ZM12.05 20.16C10.57 20.16 9.12 19.76 7.85 19.01L7.55 18.83L4.43 19.65L5.26 16.61L5.06 16.29C4.24 14.99 3.8 13.47 3.8 11.91C3.8 7.37 7.5 3.67 12.05 3.67C14.25 3.67 16.31 4.53 17.87 6.09C19.42 7.65 20.28 9.72 20.28 11.92C20.28 16.46 16.59 20.16 12.05 20.16ZM16.57 14.33C16.32 14.2 15.1 13.6 14.87 13.52C14.65 13.44 14.48 13.4 14.31 13.65C14.14 13.9 13.66 14.47 13.51 14.64C13.37 14.81 13.22 14.83 12.97 14.71C12.72 14.58 11.92 14.32 10.97 13.47C10.23 12.81 9.73 11.99 9.58 11.74C9.44 11.49 9.56 11.36 9.69 11.23C9.8 11.12 9.94 10.94 10.07 10.79C10.2 10.64 10.24 10.53 10.32 10.37C10.4 10.2 10.36 10.06 10.3 9.93C10.24 9.81 9.74 8.58 9.53 8.08C9.33 7.59 9.12 7.66 8.97 7.65C8.82 7.64 8.65 7.64 8.48 7.64C8.31 7.64 8.04 7.7 7.81 7.95C7.58 8.2 6.94 8.8 6.94 10.02C6.94 11.24 7.83 12.42 7.95 12.58C8.07 12.75 9.69 15.25 12.18 16.32C12.77 16.58 13.23 16.73 13.59 16.85C14.19 17.04 14.73 17.01 15.16 16.95C15.64 16.88 16.64 16.34 16.85 15.75C17.06 15.16 17.06 14.66 17 14.56C16.94 14.47 16.82 14.45 16.57 14.33Z" />
  </svg>
);

export default function PendingOutreach() {
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState(null);

  const fetchCandidates = async () => {
    try {
      setLoading(true);
      setError('');
      const data = await getPendingOutreach();
      const list = Array.isArray(data) ? data : (data?.data || []);
      setCandidates(list);
      // Clear selection of items no longer present
      setSelectedIds(new Set());
    } catch (err) {
      console.error('Failed to fetch pending outreach', err);
      setError(err.message || 'Failed to load pending outreach queue.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCandidates();
  }, []);

  const filteredCandidates = useMemo(() => {
    if (!searchTerm.trim()) return candidates;
    const q = searchTerm.toLowerCase();
    return candidates.filter(c =>
      (c.name && c.name.toLowerCase().includes(q)) ||
      (c.phone && c.phone.toLowerCase().includes(q)) ||
      (c.role && c.role.toLowerCase().includes(q)) ||
      (c.company && c.company.toLowerCase().includes(q)) ||
      (c.email && c.email.toLowerCase().includes(q))
    );
  }, [candidates, searchTerm]);

  // Selection handlers
  const isAllSelected =
    filteredCandidates.length > 0 &&
    filteredCandidates.every(c => selectedIds.has(c.job_candidate_id));

  const toggleSelectAll = () => {
    if (isAllSelected) {
      setSelectedIds(new Set());
    } else {
      const next = new Set(selectedIds);
      filteredCandidates.forEach(c => next.add(c.job_candidate_id));
      setSelectedIds(next);
    }
  };

  const toggleSelectOne = (jcId) => {
    const next = new Set(selectedIds);
    if (next.has(jcId)) {
      next.delete(jcId);
    } else {
      next.add(jcId);
    }
    setSelectedIds(next);
  };

  const handleSendSelected = async (targetIds = null) => {
    const idsToSend = targetIds || Array.from(selectedIds);
    if (idsToSend.length === 0) return;

    setSending(true);
    setSendResult(null);
    setError('');

    try {
      const res = await sendPendingOutreach(idsToSend);
      const resData = res.data ?? res;
      setSendResult({
        total: idsToSend.length,
        sent: resData.sent ?? 0,
        failed: resData.failed ?? 0,
        skipped: resData.skipped ?? 0,
      });

      // Refetch queue to remove successfully contacted candidates
      await fetchCandidates();
    } catch (err) {
      setError(err.message || 'Failed to send WhatsApp messages.');
    } finally {
      setSending(false);
    }
  };

  const handleSendSingle = (jcId) => {
    handleSendSelected([jcId]);
  };

  return (
    <div className="relative min-h-screen w-full overflow-hidden antialiased pb-24">
      <div className="glow-bg top-[-30%] left-[-20%] animate-pulse-slow" />
      <div
        className="glow-bg bottom-[-20%] right-[-10%] animate-pulse-slow"
        style={{
          animationDelay: '2s',
          background:
            'radial-gradient(circle, rgba(37,211,102,0.08) 0%, rgba(59,130,246,0.04) 40%, transparent 70%)',
        }}
      />
      <Header />

      <main className="relative z-10 mx-auto max-w-6xl px-5 py-8 sm:px-8">
        {/* Page Header */}
        <div className="mb-8 animate-slide-up opacity-0-init animate-delay-100 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-[#25D366]/20 ring-1 ring-[#25D366]/40 text-[#25D366] shadow-[0_0_15px_rgba(37,211,102,0.3)]">
                <WhatsAppIcon className="w-5 h-5" />
              </div>
              <h1 className="font-display text-3xl font-bold tracking-tight text-white sm:text-4xl">
                Pending Outreach
              </h1>
            </div>
            <p className="text-slate-400 text-sm leading-relaxed max-w-2xl">
              Candidates added with manual review (<code className="text-amber-400">automate: &quot;no&quot;</code>).
              Select candidate(s) and click the WhatsApp button to trigger their initial interview outreach message.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <Link
              to="/outreach/send"
              className="rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white px-4 py-2.5 text-xs font-bold transition-all ring-1 ring-slate-700 flex items-center gap-2"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Add Candidates
            </Link>
            <Link
              to="/outreach"
              className="rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white px-4 py-2.5 text-xs font-bold transition-all ring-1 ring-slate-700 flex items-center gap-2"
            >
              Outreach Responses →
            </Link>
          </div>
        </div>

        {/* Feedback Alerts */}
        {error && (
          <div className="mb-6 rounded-xl bg-red-500/10 border border-red-500/30 px-5 py-4 text-sm text-red-400 font-semibold flex items-center gap-3">
            <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>{error}</span>
          </div>
        )}

        {sendResult && (
          <div className="mb-6 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 animate-slide-up">
            <div className="flex items-center gap-3">
              <div className="size-10 rounded-xl bg-[#25D366]/20 ring-1 ring-[#25D366]/40 flex items-center justify-center shrink-0 text-[#25D366]">
                <WhatsAppIcon className="size-5" />
              </div>
              <div>
                <h4 className="text-sm font-bold text-emerald-300">
                  WhatsApp Outreach Sent Successfully
                </h4>
                <p className="text-xs text-slate-300 mt-0.5">
                  Delivered to <strong className="text-emerald-400">{sendResult.sent}</strong> candidate{sendResult.sent > 1 ? 's' : ''}.
                  {sendResult.failed > 0 && ` (${sendResult.failed} failed)`}
                  {sendResult.skipped > 0 && ` (${sendResult.skipped} skipped)`}
                  {' '}Candidates have been moved to Contacted. Responses will appear in Outreach Responses.
                </p>
              </div>
            </div>
            <Link
              to="/outreach"
              className="rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 px-4 py-2 text-xs font-bold transition-all shrink-0 shadow-md shadow-emerald-500/20"
            >
              View Outreach Responses →
            </Link>
          </div>
        )}

        {/* Action Bar & Search */}
        <div className="glass-dark rounded-2xl p-4 sm:p-5 mb-6 border border-slate-800 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4 animate-slide-up opacity-0-init animate-delay-200">
          <div className="flex items-center gap-3 flex-1">
            <div className="relative flex-1 max-w-md">
              <input
                type="text"
                placeholder="Search by name, phone, role or company…"
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                className="w-full rounded-xl bg-slate-900 border border-slate-700 text-white pl-10 pr-4 py-2.5 text-sm placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-[#25D366]/50"
              />
              <svg
                className="w-4 h-4 text-slate-500 absolute left-3.5 top-3.5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
            <button
              onClick={fetchCandidates}
              title="Refresh queue"
              className="rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white p-2.5 ring-1 ring-slate-700 transition-all"
            >
              <svg className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
          </div>

          {/* Action Trigger Button */}
          <div className="flex items-center gap-3">
            <div className="text-right hidden sm:block">
              <p className="text-xs text-slate-400 font-semibold">
                <strong className="text-white">{selectedIds.size}</strong> of {filteredCandidates.length} selected
              </p>
            </div>

            <button
              id="send-whatsapp-batch-btn"
              onClick={() => handleSendSelected()}
              disabled={selectedIds.size === 0 || sending}
              className={`rounded-2xl px-6 py-2.5 text-sm font-bold text-white shadow-lg flex items-center gap-2.5 transition-all ${
                selectedIds.size > 0 && !sending
                  ? 'bg-[#25D366] hover:bg-[#20ba59] shadow-[#25D366]/30 hover:scale-[1.02] cursor-pointer'
                  : 'bg-slate-800 text-slate-500 border border-slate-700 cursor-not-allowed opacity-60'
              }`}
            >
              {sending ? (
                <>
                  <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                  </svg>
                  Sending Outreach…
                </>
              ) : (
                <>
                  <WhatsAppIcon className="w-5 h-5 text-white" />
                  <span>
                    Send WhatsApp Outreach {selectedIds.size > 0 ? `(${selectedIds.size})` : ''}
                  </span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Candidates Table */}
        <div className="glass-dark rounded-2xl border border-slate-800 overflow-hidden animate-slide-up opacity-0-init animate-delay-300">
          <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={isAllSelected}
                  onChange={toggleSelectAll}
                  disabled={filteredCandidates.length === 0}
                  className="size-4 rounded bg-slate-900 border-slate-700 text-[#25D366] focus:ring-[#25D366]/50 cursor-pointer"
                />
                <span className="text-xs font-bold uppercase tracking-widest text-slate-400">
                  Select All
                </span>
              </label>
              {selectedIds.size > 0 && (
                <button
                  onClick={() => setSelectedIds(new Set())}
                  className="text-xs text-slate-500 hover:text-slate-300 underline"
                >
                  Clear ({selectedIds.size})
                </button>
              )}
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-slate-500 uppercase tracking-widest">
                Pending Queue: {filteredCandidates.length}
              </span>
            </div>
          </div>

          {loading ? (
            <div className="p-12 text-center">
              <div className="inline-block size-8 animate-spin rounded-full border-2 border-slate-600 border-t-[#25D366]" />
              <p className="mt-3 text-xs text-slate-400 font-semibold">Loading pending candidates…</p>
            </div>
          ) : filteredCandidates.length === 0 ? (
            <div className="p-16 text-center">
              <div className="size-14 mx-auto mb-4 rounded-2xl bg-slate-800/80 ring-1 ring-slate-700 flex items-center justify-center text-slate-500">
                <WhatsAppIcon className="size-7 opacity-50" />
              </div>
              <h3 className="text-base font-bold text-white mb-1">
                {searchTerm ? 'No matching candidates found' : 'No Candidates in Pending Queue'}
              </h3>
              <p className="text-xs text-slate-400 max-w-sm mx-auto mb-6">
                {searchTerm
                  ? 'Try searching with a different candidate name, role, phone or company.'
                  : 'All shortlisted candidates have been contacted. When you add candidates with automate: "no", they will appear here.'}
              </p>
              <Link
                to="/outreach/send"
                className="btn-neon inline-flex items-center gap-2 rounded-xl px-5 py-2.5 text-xs font-bold text-white shadow-md"
              >
                Go to Send Outreach
              </Link>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs font-bold uppercase tracking-widest text-slate-500 border-b border-slate-800">
                    <th className="px-4 py-3.5 text-left w-12" />
                    <th className="px-4 py-3.5 text-left min-w-[180px]">Candidate & Role</th>
                    <th className="px-4 py-3.5 text-left min-w-[140px]">Phone Number</th>
                    <th className="px-4 py-3.5 text-left min-w-[160px]">Email</th>
                    <th className="px-4 py-3.5 text-left min-w-[150px]">Company & Exp</th>
                    <th className="px-4 py-3.5 text-left w-36">Status</th>
                    <th className="px-4 py-3.5 text-right w-24">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {filteredCandidates.map(candidate => {
                    const isSelected = selectedIds.has(candidate.job_candidate_id);
                    return (
                      <tr
                        key={candidate.job_candidate_id}
                        onClick={() => toggleSelectOne(candidate.job_candidate_id)}
                        className={`transition-colors cursor-pointer group ${
                          isSelected ? 'bg-[#25D366]/5 hover:bg-[#25D366]/10' : 'hover:bg-slate-800/30'
                        }`}
                      >
                        {/* Checkbox */}
                        <td className="px-4 py-3.5" onClick={e => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleSelectOne(candidate.job_candidate_id)}
                            className="size-4 rounded bg-slate-900 border-slate-700 text-[#25D366] focus:ring-[#25D366]/50 cursor-pointer"
                          />
                        </td>

                        {/* Name & Role */}
                        <td className="px-4 py-3.5">
                          <p className="font-semibold text-white group-hover:text-[#25D366] transition-colors">
                            {candidate.name}
                          </p>
                          <p className="text-xs text-slate-400 mt-0.5">
                            {candidate.role}
                          </p>
                        </td>

                        {/* Phone */}
                        <td className="px-4 py-3.5">
                          <span className="font-mono text-xs text-slate-300">
                            {candidate.phone}
                          </span>
                        </td>

                        {/* Email */}
                        <td className="px-4 py-3.5">
                          <span className="text-xs text-slate-400">
                            {candidate.email || '—'}
                          </span>
                        </td>

                        {/* Company & Experience */}
                        <td className="px-4 py-3.5">
                          <p className="text-xs text-white">
                            {candidate.company || '—'}
                          </p>
                          {candidate.experience !== null && candidate.experience !== undefined && (
                            <p className="text-[11px] text-slate-500 mt-0.5">
                              {candidate.experience} yr{Number(candidate.experience) === 1 ? '' : 's'} exp
                            </p>
                          )}
                        </td>

                        {/* Status Badge */}
                        <td className="px-4 py-3.5">
                          <span className="inline-flex items-center gap-1.5 rounded-xl bg-amber-500/10 px-3 py-1 text-xs font-bold text-amber-300 ring-1 ring-amber-500/30">
                            <span className="size-1.5 rounded-full bg-amber-400" />
                            Pending Outreach
                          </span>
                        </td>

                        {/* Direct WhatsApp Send Button */}
                        <td className="px-4 py-3.5 text-right" onClick={e => e.stopPropagation()}>
                          <button
                            type="button"
                            onClick={() => handleSendSingle(candidate.job_candidate_id)}
                            disabled={sending}
                            title={`Send WhatsApp message to ${candidate.name}`}
                            className="inline-flex items-center justify-center size-9 rounded-xl bg-[#25D366]/10 hover:bg-[#25D366] text-[#25D366] hover:text-white ring-1 ring-[#25D366]/30 hover:ring-[#25D366] transition-all group/btn shadow-sm"
                          >
                            <WhatsAppIcon className="size-4" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
