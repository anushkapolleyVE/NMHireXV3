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

// Exact schema reflecting /api/outreach/send-array
const EMPTY_ROW = {
  name: '',
  role: '',
  no: '',
  email: '',
  company: '',
  experience: '',
  automate: 'yes',
};

const DEFAULT_ROWS = [
  {
    name: 'Rahul Sharma',
    role: 'Software Engineer',
    no: '917439717970',
    email: 'rahul@example.com',
    company: 'Acme Corp',
    experience: 5,
    automate: 'yes',
  },
];

export default function OutreachSend() {
  const [jobs, setJobs] = useState([]);
  const [selectedJobId, setSelectedJobId] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [automate, setAutomate] = useState('yes');
  const [rows, setRows] = useState(DEFAULT_ROWS);
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
    setRows(prev => prev.map((r, i) => (i === index ? { ...r, [field]: value } : r)));
  };

  const addRow = () => {
    setRows(prev => [...prev, { ...EMPTY_ROW, automate }]);
  };

  const removeRow = index => {
    setRows(prev => prev.filter((_, i) => i !== index));
  };

  const handleGlobalAutomateChange = (newVal) => {
    setAutomate(newVal);
    // Sync all rows to match selected global automation preference
    setRows(prev => prev.map(r => ({ ...r, automate: newVal })));
  };

  const switchToJsonMode = () => {
    const list = rows.map(r => ({
      name: r.name || '',
      role: r.role || '',
      no: r.no || '',
      email: r.email || '',
      company: r.company || companyName || '',
      experience: r.experience !== '' && r.experience !== undefined
        ? (!isNaN(Number(r.experience)) ? Number(r.experience) : r.experience)
        : '',
      automate: r.automate || automate || 'yes',
    }));
    setJsonText(JSON.stringify(list, null, 2));
    setJsonMode(true);
    setJsonError('');
  };

  const applyJson = () => {
    setJsonError('');
    try {
      const parsed = JSON.parse(jsonText);
      const list = Array.isArray(parsed) ? parsed : (parsed.candidates || [parsed]);

      if (parsed && !Array.isArray(parsed) && parsed.automate) {
        setAutomate(String(parsed.automate).toLowerCase() === 'no' ? 'no' : 'yes');
      } else if (list.length > 0 && list[0].automate) {
        setAutomate(String(list[0].automate).toLowerCase() === 'no' ? 'no' : 'yes');
      }

      const mapped = list.map((item) => {
        const phoneVal = item.no !== undefined && item.no !== null
          ? String(item.no)
          : (item.phone || item.contact_no || item.mobile || '');
        const autoVal = item.automate !== undefined && item.automate !== null
          ? (String(item.automate).trim().toLowerCase() === 'no' ? 'no' : 'yes')
          : (automate || 'yes');
        return {
          name: item.name || item.user_name || '',
          role: item.role || item.job_role || '',
          no: phoneVal,
          email: item.email || '',
          company: item.company || item.current_company || '',
          experience: item.experience !== undefined
            ? item.experience
            : (item.total_experience_years !== undefined ? item.total_experience_years : ''),
          automate: autoVal,
        };
      });

      setRows(mapped.length > 0 ? mapped : [{ ...EMPTY_ROW, automate }]);
      setJsonMode(false);
    } catch (err) {
      setJsonError(err.message);
    }
  };

  const handleSend = async () => {
    setError('');
    setResult(null);

    const candidates = rows
      .filter(r => (r.name || '').trim() && (String(r.no || '').trim() || String(r.phone || '').trim()))
      .map(r => {
        const phoneNo = String(r.no || r.phone || '').trim();
        const cand = {
          name: r.name.trim(),
          role: r.role.trim() || 'Software Engineer',
          no: phoneNo,
          phone: phoneNo,
          email: (r.email || '').trim(),
          company: (r.company || companyName || '').trim(),
          automate: r.automate || automate || 'yes',
        };
        if (r.experience !== '' && r.experience !== undefined && r.experience !== null) {
          const parsedExp = Number(r.experience);
          cand.experience = !isNaN(parsedExp) ? parsedExp : r.experience;
        }
        return cand;
      });

    if (candidates.length === 0) {
      setError('Please add at least one candidate with a name and phone / no.');
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
      <div
        className="glow-bg bottom-[-20%] right-[-10%] animate-pulse-slow"
        style={{
          animationDelay: '2s',
          background:
            'radial-gradient(circle, rgba(20,184,166,0.08) 0%, rgba(59,130,246,0.04) 40%, transparent 70%)',
        }}
      />
      <Header />
      <main className="relative z-10 mx-auto max-w-6xl px-5 py-8 sm:px-8">
        {/* Header */}
        <div className="mb-8 animate-slide-up opacity-0-init animate-delay-100 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-brand/20 ring-1 ring-brand/30">
                <svg className="w-5 h-5 text-brand" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
                  />
                </svg>
              </div>
              <h1 className="font-display text-3xl font-bold tracking-tight text-white sm:text-4xl">
                Send Outreach
              </h1>
            </div>
            <p className="text-slate-400 text-sm leading-relaxed max-w-2xl">
              Provide the candidate input matching <code className="text-brand font-semibold">/api/outreach/send-array</code> (name, role, no, email, company, experience, automate).
              When <code className="text-amber-300">automate: &quot;yes&quot;</code>, outreach WhatsApp is sent immediately. When <code className="text-amber-300">automate: &quot;no&quot;</code>, candidates queue in Pending Outreach for manual review.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <Link
              to="/outreach/pending"
              className="rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white px-4 py-2.5 text-xs font-bold transition-all ring-1 ring-slate-700 flex items-center gap-2"
            >
              <span className="size-2 rounded-full bg-amber-400" />
              Pending Queue →
            </Link>
            <Link
              to="/outreach"
              className="rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white px-4 py-2.5 text-xs font-bold transition-all ring-1 ring-slate-700 flex items-center gap-2"
            >
              Outreach Responses →
            </Link>
          </div>
        </div>

        {/* Global Controls Card */}
        <div className="glass-dark rounded-2xl p-6 mb-6 border border-slate-800 animate-slide-up opacity-0-init animate-delay-200 grid grid-cols-1 md:grid-cols-3 gap-5">
          <div>
            <label className="block text-xs font-bold uppercase tracking-widest text-slate-500 mb-2">
              Job / Requisition <span className="normal-case text-slate-600 font-normal">(Optional)</span>
            </label>
            <select
              id="outreach-job-select"
              value={selectedJobId}
              onChange={e => setSelectedJobId(e.target.value)}
              className="w-full rounded-xl bg-slate-900 border border-slate-700 text-white px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand/50"
            >
              <option value="">— Auto-detect per candidate role —</option>
              {jobs.map(j => (
                <option key={j.id} value={j.id}>
                  {j.title || j.id}
                </option>
              ))}
            </select>
            {selectedJob && <p className="mt-1 text-xs text-slate-500 truncate">{selectedJob.title}</p>}
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-widest text-slate-500 mb-2">
              Company Name <span className="normal-case text-slate-600 font-normal">(company)</span>
            </label>
            <input
              id="outreach-company-name"
              type="text"
              value={companyName}
              onChange={e => setCompanyName(e.target.value)}
              placeholder="e.g. Acme Corp"
              className="w-full rounded-xl bg-slate-900 border border-slate-700 text-white px-4 py-2.5 text-sm placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-brand/50"
            />
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-widest text-slate-500 mb-2">
              Automate Outreach <span className="normal-case text-slate-600 font-normal">(automate)</span>
            </label>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => handleGlobalAutomateChange('yes')}
                className={`flex-1 rounded-xl py-2.5 px-3 text-xs font-bold transition-all flex items-center justify-center gap-2 ${
                  automate === 'yes'
                    ? 'bg-brand/20 text-brand ring-1 ring-brand/40 shadow-sm'
                    : 'bg-slate-900 border border-slate-700 text-slate-400 hover:text-slate-200'
                }`}
              >
                <span
                  className={`size-2 rounded-full ${
                    automate === 'yes' ? 'bg-brand shadow-[0_0_8px_rgba(59,130,246,0.8)]' : 'bg-slate-600'
                  }`}
                />
                yes (Auto-send)
              </button>
              <button
                type="button"
                onClick={() => handleGlobalAutomateChange('no')}
                className={`flex-1 rounded-xl py-2.5 px-3 text-xs font-bold transition-all flex items-center justify-center gap-2 ${
                  automate === 'no'
                    ? 'bg-amber-500/20 text-amber-300 ring-1 ring-amber-500/40 shadow-sm'
                    : 'bg-slate-900 border border-slate-700 text-slate-400 hover:text-slate-200'
                }`}
              >
                <span
                  className={`size-2 rounded-full ${
                    automate === 'no' ? 'bg-amber-400 shadow-[0_0_8px_rgba(245,158,11,0.8)]' : 'bg-slate-600'
                  }`}
                />
                no (Manual queue)
              </button>
            </div>
            <p className="mt-1 text-[11px] text-slate-500">
              {automate === 'yes'
                ? 'Direct WhatsApp outreach sent via Key 1.'
                : 'Candidates saved to Pending Outreach queue for manual send.'}
            </p>
          </div>
        </div>

        {/* Input Format Table & Paste JSON Card */}
        <div className="glass-dark rounded-2xl border border-slate-800 animate-slide-up opacity-0-init animate-delay-300 overflow-hidden mb-6">
          <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b border-slate-800">
            <div>
              <h2 className="text-sm font-bold text-white uppercase tracking-widest">
                Candidate Input Array ({rows.length})
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Fields: <code className="text-brand">name</code>, <code className="text-brand">role</code>, <code className="text-brand">no</code>, <code className="text-brand">email</code>, <code className="text-brand">company</code>, <code className="text-brand">experience</code>, <code className="text-brand">automate</code>
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  setJsonMode(false);
                  setJsonError('');
                }}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors ${
                  !jsonMode ? 'bg-brand/20 text-brand ring-1 ring-brand/30' : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                Table View
              </button>
              <button
                onClick={switchToJsonMode}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors ${
                  jsonMode ? 'bg-brand/20 text-brand ring-1 ring-brand/30' : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                Paste JSON
              </button>
            </div>
          </div>

          {!jsonMode ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs font-bold uppercase tracking-widest text-slate-500 border-b border-slate-800">
                    <th className="px-3 py-3 text-left w-10">#</th>
                    <th className="px-3 py-3 text-left min-w-[140px]">name *</th>
                    <th className="px-3 py-3 text-left min-w-[130px]">role</th>
                    <th className="px-3 py-3 text-left min-w-[130px]">no (phone) *</th>
                    <th className="px-3 py-3 text-left min-w-[150px]">email</th>
                    <th className="px-3 py-3 text-left min-w-[130px]">company</th>
                    <th className="px-3 py-3 text-left w-24">experience</th>
                    <th className="px-3 py-3 text-left w-28">automate</th>
                    <th className="px-3 py-3 w-8" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {rows.map((row, idx) => (
                    <tr key={idx} className="hover:bg-slate-800/30 transition-colors group">
                      <td className="px-3 py-2 text-slate-500 font-mono text-xs">{idx + 1}</td>

                      {/* name */}
                      <td className="px-3 py-2">
                        <input
                          type="text"
                          value={row.name}
                          onChange={e => updateRow(idx, 'name', e.target.value)}
                          placeholder="Rahul Sharma"
                          className="w-full bg-transparent text-white placeholder:text-slate-700 focus:outline-none border-0 text-sm"
                        />
                      </td>

                      {/* role */}
                      <td className="px-3 py-2">
                        <input
                          type="text"
                          value={row.role}
                          onChange={e => updateRow(idx, 'role', e.target.value)}
                          placeholder="Software Engineer"
                          className="w-full bg-transparent text-white placeholder:text-slate-700 focus:outline-none border-0 text-sm"
                        />
                      </td>

                      {/* no (phone) */}
                      <td className="px-3 py-2">
                        <input
                          type="tel"
                          value={row.no}
                          onChange={e => updateRow(idx, 'no', e.target.value)}
                          placeholder="917439717970"
                          className="w-full bg-transparent text-white placeholder:text-slate-700 focus:outline-none border-0 font-mono text-sm"
                        />
                      </td>

                      {/* email */}
                      <td className="px-3 py-2">
                        <input
                          type="email"
                          value={row.email || ''}
                          onChange={e => updateRow(idx, 'email', e.target.value)}
                          placeholder="rahul@example.com"
                          className="w-full bg-transparent text-white placeholder:text-slate-700 focus:outline-none border-0 text-sm"
                        />
                      </td>

                      {/* company */}
                      <td className="px-3 py-2">
                        <input
                          type="text"
                          value={row.company || ''}
                          onChange={e => updateRow(idx, 'company', e.target.value)}
                          placeholder="Acme Corp"
                          className="w-full bg-transparent text-white placeholder:text-slate-700 focus:outline-none border-0 text-sm"
                        />
                      </td>

                      {/* experience */}
                      <td className="px-3 py-2">
                        <input
                          type="number"
                          min="0"
                          step="0.5"
                          value={row.experience !== undefined ? row.experience : ''}
                          onChange={e => updateRow(idx, 'experience', e.target.value)}
                          placeholder="5"
                          className="w-full bg-transparent text-white placeholder:text-slate-700 focus:outline-none border-0 font-mono text-sm"
                        />
                      </td>

                      {/* automate */}
                      <td className="px-3 py-2">
                        <select
                          value={row.automate || automate || 'yes'}
                          onChange={e => updateRow(idx, 'automate', e.target.value)}
                          className={`rounded-lg px-2 py-1 text-xs font-bold border transition-colors cursor-pointer ${
                            (row.automate || automate) === 'no'
                              ? 'bg-amber-500/10 text-amber-300 border-amber-500/30'
                              : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                          }`}
                        >
                          <option value="yes" className="bg-slate-900 text-emerald-400">yes</option>
                          <option value="no" className="bg-slate-900 text-amber-300">no</option>
                        </select>
                      </td>

                      {/* remove */}
                      <td className="px-3 py-2 text-right">
                        <button
                          onClick={() => removeRow(idx)}
                          className="opacity-0 group-hover:opacity-100 transition-opacity text-slate-600 hover:text-red-400 p-1"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="px-4 py-3 border-t border-slate-800 flex items-center justify-between">
                <button
                  onClick={addRow}
                  className="flex items-center gap-2 text-xs text-slate-500 hover:text-brand transition-colors font-semibold"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  Add candidate
                </button>
                <span className="text-[11px] text-slate-500 font-mono">
                  Rows: {rows.length}
                </span>
              </div>
            </div>
          ) : (
            <div className="p-5">
              <p className="text-xs text-slate-400 mb-2">
                Paste candidate JSON array directly matching <code className="text-brand">/api/outreach/send-array</code>:
              </p>
              <textarea
                id="outreach-json-input"
                value={jsonText}
                onChange={e => {
                  setJsonText(e.target.value);
                  setJsonError('');
                }}
                rows={11}
                placeholder={`[
  {
    "name": "Rahul Sharma",
    "role": "Software Engineer",
    "no": "917439717970",
    "email": "rahul@example.com",
    "company": "Acme Corp",
    "experience": 5,
    "automate": "yes"
  }
]`}
                className="w-full rounded-xl bg-slate-950 border border-slate-700 text-slate-200 font-mono text-xs px-4 py-3 focus:outline-none focus:ring-2 focus:ring-brand/50 resize-none"
              />
              {jsonError && <p className="mt-2 text-xs text-red-400 font-semibold">{jsonError}</p>}
              <div className="flex items-center gap-3 mt-3">
                <button
                  onClick={applyJson}
                  className="btn-neon rounded-xl px-5 py-2 text-sm font-bold text-white shadow-md"
                >
                  Apply JSON to Table
                </button>
                <button
                  onClick={() => setJsonMode(false)}
                  className="rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 px-4 py-2 text-sm font-bold transition-all"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>

        {error && (
          <div className="mb-5 rounded-xl bg-red-500/10 border border-red-500/30 px-5 py-4 text-sm text-red-400 font-semibold">
            {error}
          </div>
        )}

        {/* Submit Actions */}
        <div className="flex items-center justify-between mb-10">
          <p className="text-xs text-slate-500">
            Sending outreach processes candidate profiles, assigns requisitions, and triggers WhatsApp workflows.
          </p>
          <button
            id="outreach-send-btn"
            onClick={handleSend}
            disabled={sending}
            className={`rounded-2xl px-8 py-3.5 text-base font-bold text-white shadow-lg disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-3 transition-all ${
              automate === 'no'
                ? 'bg-amber-600 hover:bg-amber-500 shadow-amber-600/30'
                : 'btn-neon'
            }`}
          >
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
                Save Candidates to Pending Queue
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

        {/* Execution Results */}
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
                <h3 className="text-sm font-bold text-white uppercase tracking-widest">Candidate Batch Results</h3>
              </div>
              <div className="divide-y divide-slate-800/60">
                {(result.results || []).map((r, idx) => {
                  const meta = STATUS_META[r.status] || {
                    label: r.status,
                    color: 'text-slate-400',
                    bg: 'bg-slate-800/60 ring-slate-700',
                  };
                  return (
                    <div
                      key={idx}
                      className="flex items-center justify-between px-6 py-4 hover:bg-slate-800/20 transition-colors"
                    >
                      <div>
                        <p className="font-semibold text-white text-sm">{r.name}</p>
                        <p className="text-xs text-slate-500 font-mono mt-0.5">{r.phone}</p>
                      </div>
                      <span className={`rounded-xl px-3 py-1.5 text-xs font-bold ring-1 ${meta.bg} ${meta.color}`}>
                        {meta.label}
                      </span>
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
