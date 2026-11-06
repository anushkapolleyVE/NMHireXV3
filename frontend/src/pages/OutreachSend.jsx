import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import Header from '../components/Header';
import { getUserJobs, sendNaukriOutreach } from '../utils/api';

const STATUS_META = {
  SENT:                      { label: 'Sent',                 color: 'text-emerald-400', bg: 'bg-emerald-500/10 ring-emerald-500/30' },
  QUEUED_MANUAL:             { label: 'Queued (Manual)',     color: 'text-brand',       bg: 'bg-brand/10 ring-brand/30' },
  PENDING_OUTREACH:          { label: 'Pending Outreach',    color: 'text-brand',       bg: 'bg-brand/10 ring-brand/30' },
  SKIPPED_ALREADY_CONTACTED: { label: 'Already contacted',   color: 'text-yellow-400',  bg: 'bg-yellow-500/10 ring-yellow-500/30' },
  SKIPPED_INVALID_PHONE:     { label: 'Invalid phone',        color: 'text-orange-400',  bg: 'bg-orange-500/10 ring-orange-500/30' },
  SKIPPED_MISSING_FIELDS:    { label: 'Missing fields',       color: 'text-red-400',     bg: 'bg-red-500/10 ring-red-500/30' },
  FAILED_SEND:               { label: 'Send failed',          color: 'text-red-400',     bg: 'bg-red-500/10 ring-red-500/30' },
  FAILED_TEST_MODE_NO_NUMBER:{ label: 'No test number',       color: 'text-red-400',     bg: 'bg-red-500/10 ring-red-500/30' },
};

const EMPTY_ROW = { no: '', name: '', role: '', phone: '', email: '', company: '', experience: '' };

export default function OutreachSend() {
  const [jobs, setJobs] = useState([]);
  const [selectedJobId, setSelectedJobId] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [automate, setAutomate] = useState('yes');
  const [rows, setRows] = useState([{ ...EMPTY_ROW, no: 1 }]);
  const [jsonMode, setJsonMode] = useState(false);
  const [jsonText, setJsonText] = useState('');
  const [jsonError, setJsonError] = useState('');
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    getUserJobs()
      .then(data => {
        const list = Array.isArray(data) ? data : (data?.jobs || []);
        setJobs(list);
        if (list.length > 0) setSelectedJobId(list[0].id);
      })
      .catch(() => {});
  }, []);

  const updateRow = (index, field, value) => {
    setRows(prev => prev.map((r, i) => i === index ? { ...r, [field]: value } : r));
  };

  const addRow = () => {
    setRows(prev => [...prev, { ...EMPTY_ROW, no: prev.length + 1 }]);
  };

  const removeRow = index => {
    setRows(prev => prev.filter((_, i) => i !== index));
  };

  const applyJson = () => {
    setJsonError('');
    try {
      const parsed = JSON.parse(jsonText);
      if (parsed && typeof parsed === 'object') {
        if (parsed.automate !== undefined) {
          setAutomate(String(parsed.automate).toLowerCase() === 'no' ? 'no' : 'yes');
        } else if (Array.isArray(parsed) && parsed.length > 0 && parsed[0].automate !== undefined) {
          setAutomate(String(parsed[0].automate).toLowerCase() === 'no' ? 'no' : 'yes');
        }
      }
      const list = Array.isArray(parsed) ? parsed : (parsed.candidates || [parsed]);
      const mapped = list.map((item, idx) => {
        const phoneVal = item.phone || item.contact_no || item.mobile || (typeof item.no === 'string' && item.no.length >= 6 ? item.no : (String(item.no || '').length >= 6 ? String(item.no) : ''));
        const noVal = (typeof item.no === 'number' || (typeof item.no === 'string' && item.no.length < 6)) ? item.no : (idx + 1);
        return {
          no: noVal,
          name: item.name || item.user_name || '',
          role: item.role || item.job_role || '',
          phone: phoneVal,
          email: item.email || '',
          company: item.company || item.current_company || '',
          experience: item.experience !== undefined ? item.experience : (item.total_experience_years !== undefined ? item.total_experience_years : ''),
        };
      });
      setRows(mapped);
      setJsonMode(false);
    } catch (err) {
      setJsonError(err.message);
    }
  };

  const handleSend = async () => {
    setError('');
    setResult(null);
    const candidates = rows.filter(r => (r.name || '').trim() && ((r.phone || '').trim() || String(r.no).length >= 6)).map(r => {
      const cand = {
        no: r.no,
        name: r.name.trim(),
        role: r.role.trim() || 'Software Engineer',
        phone: (r.phone.trim() || String(r.no)).trim(),
        automate: automate,
      };
      if (r.email && r.email.trim()) cand.email = r.email.trim();
      if (r.company && r.company.trim()) cand.company = r.company.trim();
      if (r.experience !== '' && r.experience !== undefined && r.experience !== null) {
        const parsedExp = Number(r.experience);
        cand.experience = !isNaN(parsedExp) ? parsedExp : r.experience;
      }
      return cand;
    });

    if (candidates.length === 0) {
      setError('Add at least one candidate with a name and phone number.');
      return;
    }
    setSending(true);
    try {
      const res = await sendNaukriOutreach({
        jobId: selectedJobId || null,
        candidates,
        companyName: companyName.trim() || null,
        automate,
      });
      setResult(res.data ?? res);
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
    }
  };


  const selectedJob = jobs.find(j => j.id === selectedJobId);

  return (
    <div className="relative min-h-screen w-full overflow-hidden antialiased pb-24">
      <div className="glow-bg top-[-30%] left-[-20%] animate-pulse-slow" />
      <div className="glow-bg bottom-[-20%] right-[-10%] animate-pulse-slow"
        style={{ animationDelay: '2s', background: 'radial-gradient(circle, rgba(20,184,166,0.08) 0%, rgba(59,130,246,0.04) 40%, transparent 70%)' }} />
      <Header />
      <main className="relative z-10 mx-auto max-w-5xl px-5 py-8 sm:px-8">

        <div className="mb-10 animate-slide-up opacity-0-init animate-delay-100">
          <div className="flex items-center gap-3 mb-3">
            <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-brand/20 ring-1 ring-brand/30">
              <svg className="w-5 h-5 text-brand" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
            </div>
            <h1 className="font-display text-3xl font-bold tracking-tight text-white sm:text-4xl">Send Outreach</h1>
          </div>
          <p className="text-slate-400 text-sm leading-relaxed max-w-xl">
            Enter or paste a list of shortlisted candidates. The{' '}
            <span className="text-brand font-semibold">candidate_shortlisted_outreach</span>{' '}
            WhatsApp template will be sent to each phone number. Responses appear automatically in{' '}
            <strong className="text-slate-300">Outreach Responses</strong>.
          </p>
        </div>

        <div className="glass-dark rounded-2xl p-6 mb-6 border border-slate-800 animate-slide-up opacity-0-init animate-delay-200 grid grid-cols-1 md:grid-cols-3 gap-5">
          <div>
            <label className="block text-xs font-bold uppercase tracking-widest text-slate-500 mb-2">
              Job / Requisition <span className="normal-case text-slate-600 font-normal">(Optional)</span>
            </label>
            <select id="outreach-job-select" value={selectedJobId} onChange={e => setSelectedJobId(e.target.value)}
              className="w-full rounded-xl bg-slate-900 border border-slate-700 text-white px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand/50">
              <option value="">— Auto-detect per candidate role —</option>
              {jobs.map(j => <option key={j.id} value={j.id}>{j.title || j.id}</option>)}
            </select>
            {selectedJob && <p className="mt-1 text-xs text-slate-500 truncate">{selectedJob.title}</p>}
          </div>
          <div>
            <label className="block text-xs font-bold uppercase tracking-widest text-slate-500 mb-2">
              Company Name <span className="normal-case text-slate-600 font-normal">(in template)</span>
            </label>
            <input id="outreach-company-name" type="text" value={companyName} onChange={e => setCompanyName(e.target.value)}
              placeholder="e.g. Acme Corp"
              className="w-full rounded-xl bg-slate-900 border border-slate-700 text-white px-4 py-2.5 text-sm placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-brand/50" />
          </div>
          <div>
            <label className="block text-xs font-bold uppercase tracking-widest text-slate-500 mb-2">
              Automate Outreach <span className="normal-case text-slate-600 font-normal">(automate)</span>
            </label>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setAutomate('yes')}
                className={`flex-1 rounded-xl py-2.5 px-3 text-xs font-bold transition-all flex items-center justify-center gap-2 ${
                  automate === 'yes'
                    ? 'bg-brand/20 text-brand ring-1 ring-brand/40 shadow-sm'
                    : 'bg-slate-900 border border-slate-700 text-slate-400 hover:text-slate-200'
                }`}
              >
                <span className={`size-2 rounded-full ${automate === 'yes' ? 'bg-brand shadow-[0_0_8px_rgba(59,130,246,0.8)]' : 'bg-slate-600'}`} />
                Yes (Auto-send)
              </button>
              <button
                type="button"
                onClick={() => setAutomate('no')}
                className={`flex-1 rounded-xl py-2.5 px-3 text-xs font-bold transition-all flex items-center justify-center gap-2 ${
                  automate === 'no'
                    ? 'bg-amber-500/20 text-amber-300 ring-1 ring-amber-500/40 shadow-sm'
                    : 'bg-slate-900 border border-slate-700 text-slate-400 hover:text-slate-200'
                }`}
              >
                <span className={`size-2 rounded-full ${automate === 'no' ? 'bg-amber-400 shadow-[0_0_8px_rgba(245,158,11,0.8)]' : 'bg-slate-600'}`} />
                No (Manual queue)
              </button>
            </div>
            <p className="mt-1 text-[11px] text-slate-500">
              {automate === 'yes' ? 'Sends WhatsApp template immediately.' : 'Saves candidate to Pending Outreach page for manual send.'}
            </p>
          </div>
        </div>


        <div className="glass-dark rounded-2xl border border-slate-800 animate-slide-up opacity-0-init animate-delay-300 overflow-hidden mb-6">
          <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b border-slate-800">
            <h2 className="text-sm font-bold text-white uppercase tracking-widest">Candidate List</h2>
            <div className="flex items-center gap-2">
              <button onClick={() => { setJsonMode(false); setJsonError(''); }}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors ${!jsonMode ? 'bg-brand/20 text-brand ring-1 ring-brand/30' : 'text-slate-500 hover:text-slate-300'}`}>
                Table
              </button>
              <button onClick={() => { setJsonText(JSON.stringify(rows, null, 2)); setJsonMode(true); setJsonError(''); }}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors ${jsonMode ? 'bg-brand/20 text-brand ring-1 ring-brand/30' : 'text-slate-500 hover:text-slate-300'}`}>
                Paste JSON
              </button>
            </div>
          </div>

          {!jsonMode ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs font-bold uppercase tracking-widest text-slate-500 border-b border-slate-800">
                    <th className="px-3 py-3 text-left w-12">#</th>
                    <th className="px-3 py-3 text-left min-w-[140px]">Name *</th>
                    <th className="px-3 py-3 text-left min-w-[130px]">Role</th>
                    <th className="px-3 py-3 text-left min-w-[130px]">Phone *</th>
                    <th className="px-3 py-3 text-left min-w-[150px]">Email</th>
                    <th className="px-3 py-3 text-left min-w-[120px]">Company</th>
                    <th className="px-3 py-3 text-left w-20">Exp (Yrs)</th>
                    <th className="px-3 py-3 w-8" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {rows.map((row, idx) => (
                    <tr key={idx} className="hover:bg-slate-800/30 transition-colors group">
                      <td className="px-3 py-2 text-slate-500 font-mono text-xs">{idx + 1}</td>
                      <td className="px-3 py-2">
                        <input type="text" value={row.name} onChange={e => updateRow(idx, 'name', e.target.value)}
                          placeholder="Rahul Sharma"
                          className="w-full bg-transparent text-white placeholder:text-slate-700 focus:outline-none border-0 text-sm" />
                      </td>
                      <td className="px-3 py-2">
                        <input type="text" value={row.role} onChange={e => updateRow(idx, 'role', e.target.value)}
                          placeholder="Software Engineer"
                          className="w-full bg-transparent text-white placeholder:text-slate-700 focus:outline-none border-0 text-sm" />
                      </td>
                      <td className="px-3 py-2">
                        <input type="tel" value={row.phone} onChange={e => updateRow(idx, 'phone', e.target.value)}
                          placeholder="917439717970"
                          className="w-full bg-transparent text-white placeholder:text-slate-700 focus:outline-none border-0 font-mono text-sm" />
                      </td>
                      <td className="px-3 py-2">
                        <input type="email" value={row.email || ''} onChange={e => updateRow(idx, 'email', e.target.value)}
                          placeholder="rahul@example.com"
                          className="w-full bg-transparent text-white placeholder:text-slate-700 focus:outline-none border-0 text-sm" />
                      </td>
                      <td className="px-3 py-2">
                        <input type="text" value={row.company || ''} onChange={e => updateRow(idx, 'company', e.target.value)}
                          placeholder="Acme Corp"
                          className="w-full bg-transparent text-white placeholder:text-slate-700 focus:outline-none border-0 text-sm" />
                      </td>
                      <td className="px-3 py-2">
                        <input type="number" min="0" step="0.5" value={row.experience !== undefined ? row.experience : ''} onChange={e => updateRow(idx, 'experience', e.target.value)}
                          placeholder="5"
                          className="w-full bg-transparent text-white placeholder:text-slate-700 focus:outline-none border-0 font-mono text-sm" />
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button onClick={() => removeRow(idx)}
                          className="opacity-0 group-hover:opacity-100 transition-opacity text-slate-600 hover:text-red-400 p-1">
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="px-4 py-3 border-t border-slate-800">
                <button onClick={addRow} className="flex items-center gap-2 text-xs text-slate-500 hover:text-brand transition-colors font-semibold">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  Add candidate
                </button>
              </div>
            </div>
          ) : (
            <div className="p-5">
              <p className="text-xs text-slate-500 mb-3">
                Paste a JSON array matching the <code className="text-brand">/api/outreach/send-array</code> specification:
              </p>
              <textarea id="outreach-json-input" value={jsonText} onChange={e => { setJsonText(e.target.value); setJsonError(''); }}
                rows={10}
                placeholder={`[
  {
    "name": "Rahul Sharma",
    "role": "Software Engineer",
    "no": "917439717970",
    "email": "rahul@example.com",
    "company": "Acme Corp",
    "experience": 5,
    "automate": "no"
  }
]`}
                className="w-full rounded-xl bg-slate-950 border border-slate-700 text-slate-200 font-mono text-xs px-4 py-3 focus:outline-none focus:ring-2 focus:ring-brand/50 resize-none" />
              {jsonError && <p className="mt-2 text-xs text-red-400 font-semibold">{jsonError}</p>}
              <button onClick={applyJson} className="mt-3 btn-neon rounded-xl px-5 py-2 text-sm font-bold text-white">Apply JSON</button>
            </div>
          )}
        </div>

        {error && (
          <div className="mb-5 rounded-xl bg-red-500/10 border border-red-500/30 px-5 py-4 text-sm text-red-400 font-semibold">{error}</div>
        )}

        <div className="flex justify-end mb-10">
          <button id="outreach-send-btn" onClick={handleSend} disabled={sending}
            className={`rounded-2xl px-8 py-3.5 text-base font-bold text-white shadow-lg disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-3 transition-all ${
              automate === 'no'
                ? 'bg-amber-600 hover:bg-amber-500 shadow-amber-600/30'
                : 'btn-neon'
            }`}>
            {sending ? (
              <>
                <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                </svg>
                {automate === 'no' ? 'Saving to Queue…' : 'Sending…'}
              </>
            ) : automate === 'no' ? (
              <>
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
                </svg>
                Save to Pending Outreach Queue
              </>
            ) : (
              <>
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
                Send WhatsApp Outreach
              </>
            )}
          </button>
        </div>

        {result && (
          <div className="animate-slide-up opacity-0-init animate-delay-100">
            {result.queued > 0 && (
              <div className="mb-6 rounded-2xl bg-amber-500/10 border border-amber-500/30 p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className="size-10 rounded-xl bg-amber-500/20 ring-1 ring-amber-500/40 flex items-center justify-center shrink-0">
                    <svg className="size-5 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-amber-300">Candidates Queued for Manual Review</h4>
                    <p className="text-xs text-slate-400 mt-0.5">
                      {result.queued} candidate{result.queued > 1 ? 's' : ''} saved in Pending Outreach. You can review and trigger WhatsApp messages individually or in bulk.
                    </p>
                  </div>
                </div>
                <Link
                  to="/outreach/pending"
                  className="rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 px-4 py-2 text-xs font-bold transition-all shrink-0 flex items-center gap-2 shadow-md shadow-amber-500/20"
                >
                  Open Pending Outreach →
                </Link>
              </div>
            )}

            <div className={`grid gap-4 mb-6 ${result.queued > 0 ? 'grid-cols-2 sm:grid-cols-5' : 'grid-cols-2 sm:grid-cols-4'}`}>
              {[
                { label: 'Total',   value: result.total,   color: 'text-white' },
                ...(result.queued > 0 ? [{ label: 'Queued', value: result.queued, color: 'text-amber-400' }] : []),
                { label: 'Sent',    value: result.sent,    color: 'text-emerald-400' },
                { label: 'Skipped', value: result.skipped, color: 'text-yellow-400' },
                { label: 'Failed',  value: result.failed,  color: 'text-red-400' },
              ].map(stat => (
                <div key={stat.label} className="glass-dark rounded-2xl p-4 border border-slate-800 text-center">
                  <p className={`text-3xl font-bold ${stat.color}`}>{stat.value}</p>
                  <p className="text-xs text-slate-500 font-bold uppercase tracking-widest mt-1">{stat.label}</p>
                </div>
              ))}
            </div>
            <div className="glass-dark rounded-2xl border border-slate-800 overflow-hidden">
              <div className="px-6 py-4 border-b border-slate-800">
                <h3 className="text-sm font-bold text-white uppercase tracking-widest">Results</h3>
              </div>
              <div className="divide-y divide-slate-800/60">
                {(result.results || []).map((r, idx) => {
                  const meta = STATUS_META[r.status] || { label: r.status, color: 'text-slate-400', bg: 'bg-slate-800/60 ring-slate-700' };
                  return (
                    <div key={idx} className="flex items-center justify-between px-6 py-4 hover:bg-slate-800/20 transition-colors">
                      <div>
                        <p className="font-semibold text-white text-sm">{r.name}</p>
                        <p className="text-xs text-slate-500 font-mono mt-0.5">{r.phone}</p>
                      </div>
                      <span className={`rounded-xl px-3 py-1.5 text-xs font-bold ring-1 ${meta.bg} ${meta.color}`}>{meta.label}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
