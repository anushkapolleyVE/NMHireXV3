import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const Reschedule = () => {
  const { token } = useParams();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [details, setDetails] = useState(null);

  const [newDate, setNewDate] = useState('');
  const [newTime, setNewTime] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    const fetchDetails = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/reschedule/${token}`);
        if (!res.ok) {
          throw new Error('Invalid or expired reschedule link.');
        }
        const data = await res.json();
        setDetails(data.data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    fetchDetails();
  }, [token]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!newDate || !newTime) return;

    setIsSubmitting(true);
    try {
      const formattedTime = formatTime(newTime); // Convert HH:MM (24h) to hh:mm A
      
      const res = await fetch(`${API_BASE}/api/reschedule/${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          new_date: newDate,
          new_time: formattedTime,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone
        })
      });

      if (!res.ok) {
        throw new Error('Failed to reschedule. Please try again.');
      }
      setSuccess(true);
    } catch (err) {
      alert(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const formatTime = (time24) => {
    const [h, m] = time24.split(':');
    const hours = parseInt(h, 10);
    const suffix = hours >= 12 ? 'PM' : 'AM';
    const h12 = hours % 12 || 12;
    const formattedH = h12 < 10 ? `0${h12}` : h12;
    return `${formattedH}:${m} ${suffix}`;
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4">
        <div className="bg-slate-800/50 backdrop-blur-xl border border-red-500/30 p-8 rounded-2xl max-w-md w-full shadow-2xl">
          <div className="text-red-400 text-center text-5xl mb-4">⚠️</div>
          <h2 className="text-xl font-semibold text-white text-center mb-2">Oops!</h2>
          <p className="text-slate-300 text-center">{error}</p>
        </div>
      </div>
    );
  }

  if (success) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4">
        <div className="bg-slate-800/50 backdrop-blur-xl border border-emerald-500/30 p-10 rounded-3xl max-w-md w-full shadow-[0_0_50px_rgba(16,185,129,0.1)] text-center transform transition-all animate-slide-up">
          <div className="text-emerald-400 text-6xl mb-6">✨</div>
          <h2 className="text-2xl font-bold text-white mb-3">Successfully Rescheduled!</h2>
          <p className="text-slate-400 mb-8">
            Your new interview time has been confirmed. We've sent you a WhatsApp message with the updated details.
          </p>
          <button 
            onClick={() => window.close()} 
            className="w-full bg-slate-700 hover:bg-slate-600 text-white font-medium py-3 px-4 rounded-xl transition-colors"
          >
            Close Window
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0B1120] flex items-center justify-center p-4 relative overflow-hidden">
      {/* Decorative background blobs */}
      <div className="absolute top-[-10%] left-[-10%] w-96 h-96 bg-indigo-600/20 rounded-full blur-[100px] pointer-events-none"></div>
      <div className="absolute bottom-[-10%] right-[-10%] w-96 h-96 bg-emerald-600/20 rounded-full blur-[100px] pointer-events-none"></div>

      <div className="bg-slate-900/60 backdrop-blur-2xl border border-slate-700/50 p-8 sm:p-10 rounded-3xl max-w-lg w-full shadow-[0_20px_50px_rgba(0,0,0,0.5)] relative z-10 animate-slide-up">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold text-white tracking-tight mb-2">Reschedule Interview</h1>
          <p className="text-indigo-300 font-medium">{details?.job_title}</p>
        </div>

        <div className="bg-slate-800/50 rounded-2xl p-5 mb-8 border border-slate-700/50">
          <p className="text-sm text-slate-400 mb-1">Candidate Name</p>
          <p className="text-lg text-white font-medium mb-4">{details?.candidate_name}</p>
          
          <p className="text-sm text-slate-400 mb-1">Current Schedule</p>
          <p className="text-lg text-white font-medium">
            {details?.current_scheduled_at ? new Date(details.current_scheduled_at).toLocaleString('en-US', {
              dateStyle: 'full',
              timeStyle: 'short'
            }) : 'Not Scheduled'}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">New Date</label>
              <input
                type="date"
                required
                value={newDate}
                min={new Date().toISOString().split('T')[0]}
                onChange={(e) => setNewDate(e.target.value)}
                className="w-full bg-slate-950/50 border border-slate-700 rounded-xl px-4 py-3 text-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">New Time</label>
              <input
                type="time"
                required
                value={newTime}
                onChange={(e) => setNewTime(e.target.value)}
                className="w-full bg-slate-950/50 border border-slate-700 rounded-xl px-4 py-3 text-white focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
                style={{ colorScheme: 'dark' }}
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isSubmitting || !newDate || !newTime}
            className={`w-full font-medium py-3.5 px-4 rounded-xl text-white transition-all transform ${
              isSubmitting || !newDate || !newTime 
                ? 'bg-slate-700 cursor-not-allowed opacity-70' 
                : 'bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-400 hover:to-purple-500 hover:scale-[1.02] shadow-[0_0_20px_rgba(99,102,241,0.4)]'
            }`}
          >
            {isSubmitting ? (
              <span className="flex items-center justify-center">
                <svg className="animate-spin -ml-1 mr-2 h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Confirming...
              </span>
            ) : (
              'Confirm New Time'
            )}
          </button>
        </form>
      </div>
    </div>
  );
};

export default Reschedule;
