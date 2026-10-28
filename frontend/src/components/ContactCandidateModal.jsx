import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { updateCandidateStatus } from '../utils/api';

export default function ContactCandidateModal({ isOpen, onClose, candidate, onStatusUpdate }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isSent, setIsSent] = useState(false);

  const navigate = useNavigate();

  if (!isOpen || !candidate) return null;

  const handleSendInvite = async () => {
    if (isSent) return;
    
    setLoading(true);
    setError(null);
    try {
      await updateCandidateStatus(candidate.job_id, candidate.id, 'CONTACTED');
      onStatusUpdate(candidate.id, 'CONTACTED');
      setIsSent(true);

    } catch (err) {
      setError(err.message || 'Failed to send invite');
    } finally {
      setLoading(false);
    }
  };

  const handleRecordReply = async (status) => {
    setLoading(true);
    setError(null);
    try {
      await updateCandidateStatus(candidate.job_id, candidate.id, status);
      onStatusUpdate(candidate.id, status);
      
      if (status === 'INTERESTED') {
        onClose();
        navigate('/outreach');
      } else {
        onClose();
      }
    } catch (err) {
      setError(err.message || 'Failed to update status');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm transition-opacity" 
        onClick={onClose}
      />
      
      {/* Modal panel - Light theme per design */}
      <div className="relative w-full max-w-md transform overflow-hidden rounded-[24px] bg-white shadow-2xl transition-all flex flex-col animate-slide-up p-8">
        
        <div className="flex items-start gap-4 mb-6">
          <div className="flex-shrink-0 size-12 rounded-full bg-[#f0fdf4] flex items-center justify-center">
            <svg className="w-6 h-6 text-[#22c55e]" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12.031 6.172c-3.181 0-5.767 2.586-5.768 5.766-.001 1.298.38 2.27 1.019 3.287l-.582 2.128 2.182-.573c.978.58 1.711.892 2.81.892 3.181 0 5.767-2.585 5.767-5.766 0-3.18-2.585-5.766-5.767-5.766zm3.333 8.273c-.156.444-.946.853-1.309.897-.323.039-.773.08-2.147-.487-1.666-.688-2.73-2.404-2.81-2.511-.08-.107-.673-.897-.673-1.714 0-.817.427-1.218.578-1.378.151-.16.329-.2.445-.2.116 0 .231 0 .329.004.098.004.227-.04.356.262.133.311.453 1.102.493 1.182.04.08.067.173.013.28-.053.107-.08.173-.16.258-.08.084-.169.191-.235.258-.08.08-.165.17-.067.338.098.169.435.718.934 1.164.646.577 1.182.756 1.343.836.16.08.254.067.347-.04.093-.107.404-.471.516-.631.111-.16.222-.133.364-.08.142.053.898.423 1.054.503.156.08.262.115.302.182.04.067.04.387-.116.831z"/>
            </svg>
          </div>
          <div>
            <h3 className="text-xl font-bold text-slate-900 mt-1">Send WhatsApp invite</h3>
            <p className="text-sm text-slate-500 mt-1">Confirm the number before it goes out.</p>
          </div>
        </div>

        {error && (
          <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-600">
            {error}
          </div>
        )}

        <div className="bg-[#f8fafc] rounded-2xl p-5 mb-5 border border-slate-100">
          <h4 className="text-lg font-bold text-slate-900">{candidate.name}</h4>
          <p className="text-sm text-slate-500 mt-0.5">{candidate.job}</p>
          <p className="text-2xl font-bold text-slate-900 mt-4 tracking-tight">
            {candidate.phone && candidate.phone !== '-' ? candidate.phone : 'No Phone Number'}
          </p>
        </div>

        <p className="text-[13.5px] text-slate-500 leading-relaxed mb-8">
          {isSent 
            ? "Invite sent! You can now record their reply below."
            : "They'll receive a short message asking whether they're interested in the role. You can record their reply on this card afterwards."
          }
        </p>

        <div className="flex items-center justify-end gap-3 mt-auto">
          {!isSent ? (
            <>
              <button 
                onClick={onClose}
                className="px-5 py-2.5 rounded-xl border border-slate-200 text-sm font-bold text-slate-700 bg-white hover:bg-slate-50 transition-colors"
              >
                Cancel
              </button>
              <button 
                onClick={handleSendInvite}
                disabled={loading}
                className="px-6 py-2.5 rounded-xl text-sm font-bold text-white transition-all bg-[#22c55e] hover:bg-[#16a34a] shadow-[0_4px_14px_rgba(34,197,94,0.3)] disabled:opacity-70"
              >
                {loading ? 'Sending...' : 'Send invite'}
              </button>
            </>
          ) : (
            <div className="flex w-full gap-3">
              <button 
                onClick={() => handleRecordReply('INTERESTED')}
                disabled={loading}
                className="flex-1 px-4 py-2.5 rounded-xl text-sm font-bold text-brand bg-brand/10 hover:bg-brand/20 transition-colors disabled:opacity-70"
              >
                He is interested
              </button>
              <button 
                onClick={() => handleRecordReply('NOT_INTERESTED')}
                disabled={loading}
                className="flex-1 px-4 py-2.5 rounded-xl text-sm font-bold text-slate-700 bg-slate-100 hover:bg-slate-200 transition-colors disabled:opacity-70"
              >
                Not interested
              </button>
            </div>
          )}
        </div>

      </div>
    </div>
  );
}
