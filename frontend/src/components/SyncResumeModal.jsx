import { useState } from 'react';

export default function SyncResumeModal({ isOpen, onClose }) {
  const [source, setSource] = useState('local'); // 'local', 'gdrive', 'indeed'
  const [localPath, setLocalPath] = useState('');
  const [gdriveUrl, setGdriveUrl] = useState('');
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState(null);
  const [error, setError] = useState('');

  if (!isOpen) return null;

  const handleSync = async () => {
    setIsSyncing(true);
    setError('');
    setSyncResult(null);

    let payload = { source };
    if (source === 'local') {
      if (!localPath) {
        setError('Please enter a local folder path.');
        setIsSyncing(false);
        return;
      }
      payload.path_or_url = localPath;
    } else if (source === 'gdrive') {
      if (!gdriveUrl) {
        setError('Please enter a Google Drive URL.');
        setIsSyncing(false);
        return;
      }
      payload.path_or_url = gdriveUrl;
    }

    try {
  // Send request to backend
  const res = await fetch(
    `${import.meta.env.VITE_API_BASE_URL}/resumes/sync`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': '00000000-0000-0000-0000-000000000000'
      },
      body: JSON.stringify(payload)
    }
  );

  if (!res.ok) {
    const errData = await res.json();
    throw new Error(errData.detail || 'Sync failed');
  }

  const data = await res.json();
  setSyncResult(data);

} catch (err) {
  setError(err.message);
} finally {
  setIsSyncing(false);
}
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-fade-in">
      <div className="w-full max-w-2xl rounded-2xl bg-slate-900 ring-1 ring-slate-800 shadow-2xl overflow-hidden animate-slide-up relative">
        <div className="p-6 sm:p-8">
          <h2 className="text-2xl font-bold text-white mb-2">Sync resume pool</h2>
          <p className="text-sm text-slate-400 mb-6">Enter the folder to scan for resumes.</p>

          <div className="space-y-4">
            <p className="text-sm font-semibold text-slate-300">Source</p>

            <label className={`flex items-start gap-4 p-4 rounded-xl border-2 cursor-pointer transition-all ${source === 'local' ? 'border-brand bg-brand/10' : 'border-slate-700 bg-slate-800/50 hover:border-slate-600'}`}>
              <input
                type="radio"
                name="source"
                value="local"
                className="mt-1"
                checked={source === 'local'}
                onChange={() => setSource('local')}
              />
              <div className="flex-1">
                <div className="flex justify-between items-center mb-1">
                  <h3 className="font-bold text-white">Local Drive</h3>
                  <span className="text-[10px] font-bold text-accent bg-accent/20 px-2 py-0.5 rounded-full ring-1 ring-accent/30">Available</span>
                </div>
                <p className="text-sm text-slate-400">A folder on this machine or server that HireX can read directly.</p>
              </div>
            </label>

            <label className={`flex items-start gap-4 p-4 rounded-xl border-2 cursor-pointer transition-all ${source === 'gdrive' ? 'border-brand bg-brand/10' : 'border-slate-700 bg-slate-800/50 hover:border-slate-600'}`}>
              <input
                type="radio"
                name="source"
                value="gdrive"
                className="mt-1"
                checked={source === 'gdrive'}
                onChange={() => setSource('gdrive')}
              />
              <div className="flex-1">
                <div className="flex justify-between items-center mb-1">
                  <h3 className="font-bold text-white">Google Drive</h3>
                  <span className="text-[10px] font-bold text-accent bg-accent/20 px-2 py-0.5 rounded-full ring-1 ring-accent/30">Available</span>
                </div>
                <p className="text-sm text-slate-400">Sync candidates sourced from a public Google Drive folder link.</p>
              </div>
            </label>

            <label className={`flex items-start gap-4 p-4 rounded-xl border-2 cursor-not-allowed border-slate-800 bg-slate-900/50 opacity-60`}>
              <input
                type="radio"
                name="source"
                value="indeed"
                className="mt-1"
                disabled
              />
              <div className="flex-1">
                <div className="flex justify-between items-center mb-1">
                  <h3 className="font-bold text-white">Indeed</h3>
                  <span className="text-[10px] font-bold text-slate-400 bg-slate-800 px-2 py-0.5 rounded-full ring-1 ring-slate-700">Coming soon</span>
                </div>
                <p className="text-sm text-slate-400">Sync candidates sourced from Indeed. Needs a one-time Indeed employer account authorization to connect.</p>
              </div>
            </label>
          </div>

          <div className="mt-6">
            {source === 'local' && (
              <>
                <p className="text-sm font-semibold text-slate-300 mb-2">Local folder path</p>
                <input
                  type="text"
                  value={localPath}
                  onChange={(e) => setLocalPath(e.target.value)}
                  placeholder="C:\Users\...\resumes"
                  className="w-full rounded-xl border-2 border-slate-700 bg-slate-800/50 px-4 py-3 text-white focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                />
              </>
            )}

            {source === 'gdrive' && (
              <>
                <p className="text-sm font-semibold text-slate-300 mb-2">Google Drive Folder / ZIP Link</p>
                <input
                  type="text"
                  value={gdriveUrl}
                  onChange={(e) => setGdriveUrl(e.target.value)}
                  placeholder="https://drive.google.com/drive/folders/..."
                  className="w-full rounded-xl border-2 border-slate-700 bg-slate-800/50 px-4 py-3 text-white focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                />
              </>
            )}
          </div>

          {error && <p className="mt-4 text-sm font-bold text-red-400">{error}</p>}
          {syncResult && (
            <div className="mt-4 p-4 rounded-xl bg-slate-800/50 ring-1 ring-slate-700">
              <p className="text-sm text-slate-300"><span className="font-bold text-white">Status:</span> {syncResult.status}</p>
              {syncResult.message && <p className="text-sm text-slate-400 mt-1">{syncResult.message}</p>}
              <div className="mt-2 flex gap-4 text-xs font-bold">
                <span className="text-brand">Total: {syncResult.total}</span>
                <span className="text-accent">Success: {syncResult.successful}</span>
                <span className="text-slate-400">Skipped: {syncResult.skipped}</span>
                {syncResult.failed > 0 && <span className="text-red-400">Failed: {syncResult.failed}</span>}
              </div>
            </div>
          )}

          <div className="mt-8 flex justify-end gap-3">
            <button
              onClick={onClose}
              disabled={isSyncing}
              className="rounded-xl px-5 py-3 text-sm font-bold text-slate-300 hover:bg-slate-800 hover:text-white transition-all disabled:opacity-50"
            >
              {syncResult ? 'Close' : 'Cancel'}
            </button>
            <button
              onClick={handleSync}
              disabled={isSyncing || syncResult?.status === 'SUCCESS'}
              className="rounded-xl bg-brand px-6 py-3 text-sm font-bold text-white hover:bg-brand-light shadow-[0_0_15px_rgba(59,130,246,0.3)] transition-all disabled:opacity-50 flex items-center gap-2"
            >
              {isSyncing ? (
                <>
                  <svg className="animate-spin size-4 text-white" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Syncing...
                </>
              ) : 'Go'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
