import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import './ScheduleInterview.css';

const rawApi = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || "http://localhost:8000/api";
const API_BASE_URL = rawApi.replace(/\/+$/, "").endsWith("/api")
  ? rawApi.replace(/\/+$/, "")
  : `${rawApi.replace(/\/+$/, "")}/api`;

const Reschedule = () => {
  const { token } = useParams();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [details, setDetails] = useState(null);

  const [dates, setDates] = useState([]);
  const [selectedDate, setSelectedDate] = useState('');
  
  const [slots, setSlots] = useState([]);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [selectedPeriod, setSelectedPeriod] = useState('all');
  const [customTimeInput, setCustomTimeInput] = useState('');

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [meetingLink, setMeetingLink] = useState(null);
  const [copied, setCopied] = useState(false);

  const todayStr = new Date().toISOString().split('T')[0];

  useEffect(() => {
    const fetchAll = async () => {
      try {
        setLoading(true);
        setError(null);

        // Fetch candidate reschedule details
        const res = await fetch(`${API_BASE_URL}/reschedule/${token}`);
        if (!res.ok) {
          throw new Error('Invalid or expired reschedule link. Please check the link or contact your recruiter.');
        }
        const data = await res.json();
        setDetails(data.data);
        if (data.data && data.data.interview_link) {
          setMeetingLink(data.data.interview_link);
        }

        // Fetch dates and 24h slots in parallel
        const [datesRes, slotsRes] = await Promise.all([
          fetch(`${API_BASE_URL}/scheduling/dates`).then(r => r.json()).catch(() => ({ dates: [] })),
          fetch(`${API_BASE_URL}/scheduling/slots`).then(r => r.json()).catch(() => ({ slots: [] })),
        ]);

        const fetchedDates = datesRes.dates || [];
        setDates(fetchedDates);
        if (fetchedDates.length > 0) {
          setSelectedDate(fetchedDates[0].date);
        } else {
          setSelectedDate(todayStr);
        }

        setSlots(slotsRes.slots || []);
      } catch (err) {
        console.error('Reschedule fetch error:', err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    if (token) {
      fetchAll();
    }
  }, [token]);

  // Convert 24-hour "HH:MM" to "hh:mm AM/PM"
  const convert24To12 = (val24) => {
    if (!val24) return '';
    const [hStr, mStr] = val24.split(':');
    let h = parseInt(hStr, 10);
    const ampm = h >= 12 ? 'PM' : 'AM';
    h = h % 12 || 12;
    const formattedH = h < 10 ? `0${h}` : `${h}`;
    return `${formattedH}:${mStr} ${ampm}`;
  };

  // Convert 12-hour "hh:mm AM/PM" to 24-hour "HH:MM"
  const convert12To24 = (val12) => {
    if (!val12) return '';
    const match = val12.match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/i);
    if (!match) return '';
    let h = parseInt(match[1], 10);
    const m = match[2];
    const ampm = match[3].toUpperCase();
    if (ampm === 'PM' && h < 12) h += 12;
    if (ampm === 'AM' && h === 12) h = 0;
    return `${h < 10 ? '0' + h : h}:${m}`;
  };

  const handleSelectSlot = (slot) => {
    setSelectedSlot(slot);
    setCustomTimeInput(convert12To24(slot));
  };

  const handleCustomTimeChange = (time24) => {
    setCustomTimeInput(time24);
    if (time24) {
      const formatted12 = convert24To12(time24);
      setSelectedSlot(formatted12);
    }
  };

  const filterSlot = (slot) => {
    if (selectedPeriod === 'all') return true;
    const match = slot.match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/i);
    if (!match) return true;
    let h = parseInt(match[1], 10);
    const ampm = match[3].toUpperCase();
    if (ampm === 'PM' && h < 12) h += 12;
    if (ampm === 'AM' && h === 12) h = 0;
    
    if (selectedPeriod === 'morning') return h >= 6 && h < 12;
    if (selectedPeriod === 'afternoon') return h >= 12 && h < 17;
    if (selectedPeriod === 'evening') return h >= 17 && h < 21;
    if (selectedPeriod === 'night') return h >= 21 || h < 6;
    return true;
  };

  const filteredSlots = slots.filter(filterSlot);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!selectedDate || !selectedSlot) return;

    setIsSubmitting(true);
    try {
      const res = await fetch(`${API_BASE_URL}/reschedule/${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          new_date: selectedDate,
          new_time: selectedSlot,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Kolkata'
        })
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to reschedule. Please try again.');
      }

      const resData = await res.json();
      if (resData.data && resData.data.link) {
        setMeetingLink(resData.data.link);
      }
      setSuccess(true);
    } catch (err) {
      alert(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const getDayAndMonth = (dateStr) => {
    const [y, m, d] = dateStr.split('-');
    const dateObj = new Date(parseInt(y), parseInt(m) - 1, parseInt(d));
    const day = dateObj.getDate();
    const month = dateObj.toLocaleString('en-US', { month: 'short' });
    const dayOfWeek = dateObj.toLocaleString('en-US', { weekday: 'short' }).toUpperCase();
    return { dayOfWeek, day, month };
  };

  const formatSummary = () => {
    if (!selectedDate || !selectedSlot) return null;
    try {
      const [y, m, d] = selectedDate.split('-');
      const dateObj = new Date(parseInt(y), parseInt(m) - 1, parseInt(d));
      const formattedDate = dateObj.toLocaleDateString('en-US', {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
        year: 'numeric'
      });
      return `${formattedDate} at ${selectedSlot}`;
    } catch {
      return `${selectedDate} at ${selectedSlot}`;
    }
  };

  const formatCurrentSchedule = (isoDate) => {
    if (!isoDate) return 'Not Scheduled';
    try {
      // Strip any UTC / timezone suffix so the candidate's exact scheduled clock time is preserved
      const clean = isoDate.replace(/(\.\d+)?(Z|[+-]\d{2}:\d{2})$/, '');
      const d = new Date(clean);
      return d.toLocaleString('en-US', {
        dateStyle: 'full',
        timeStyle: 'short'
      });
    } catch {
      return isoDate;
    }
  };

  const copyLink = () => {
    if (meetingLink) {
      navigator.clipboard.writeText(meetingLink);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (loading) {
    return (
      <div className="schedule-container dark-theme loading">
        <div className="spinner"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="schedule-container dark-theme">
        <div className="schedule-content glass-card success-state" style={{ borderColor: 'rgba(239, 68, 68, 0.4)' }}>
          <div className="text-red-400 text-5xl mb-4" style={{ fontSize: '48px', marginBottom: '16px' }}>⚠️</div>
          <h2 className="schedule-title" style={{ color: '#f87171' }}>Reschedule Link Error</h2>
          <p className="schedule-subtitle" style={{ color: '#cbd5e1' }}>{error}</p>
        </div>
      </div>
    );
  }

  if (success) {
    return (
      <div className="schedule-container dark-theme">
        <div className="schedule-content glass-card success-state">
          <div className="success-icon">✓</div>
          <h2 className="schedule-title">Successfully Rescheduled!</h2>
          <p className="schedule-subtitle">
            Your interview has been updated. We've sent a WhatsApp confirmation with your new schedule.
          </p>

          <div className="selection-summary-badge" style={{ justifyContent: 'center' }}>
            <span>📅 <strong>{formatSummary()}</strong></span>
          </div>

          {meetingLink && (
            <div className="meeting-link-box">
              <p style={{ color: '#94a3b8', fontSize: '0.8rem', marginBottom: '6px' }}>Your Interview Meeting Link:</p>
              <a href={meetingLink} target="_blank" rel="noreferrer">{meetingLink}</a>
              <div style={{ marginTop: '12px' }}>
                <button className="copy-link-btn" onClick={copyLink}>
                  {copied ? '✓ Copied!' : 'Copy Meeting Link'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="schedule-container dark-theme">
      <div className="schedule-content glass-card">
        <h2 className="schedule-title">Reschedule Interview</h2>
        <p className="schedule-subtitle">{details?.job_title ? `Position: ${details.job_title}` : 'Pick your preferred date & time'}</p>

        {/* Candidate & Current Schedule Box */}
        <div className="current-schedule-box">
          <div className="current-schedule-item">
            <div className="current-schedule-label">Candidate</div>
            <div className="current-schedule-val">{details?.candidate_name || 'Candidate'}</div>
          </div>
          <div className="current-schedule-item">
            <div className="current-schedule-label">Currently Scheduled For</div>
            <div className="current-schedule-val" style={{ color: '#38bdf8' }}>
              {formatCurrentSchedule(details?.current_scheduled_at)}
            </div>
          </div>
        </div>

        {/* 7-Day Quick Select */}
        <div className="section-title">Select New Date</div>
        <div className="date-picker-scroll">
          {dates.map((d, index) => {
            const { dayOfWeek, day, month } = getDayAndMonth(d.date);
            const isSelected = selectedDate === d.date;
            return (
              <div 
                key={index} 
                className={`date-pill ${isSelected ? 'active' : ''}`}
                onClick={() => setSelectedDate(d.date)}
              >
                <span className="dp-day-of-week">{dayOfWeek}</span>
                <span className="dp-day">{day}</span>
                <span className="dp-month">{month}</span>
              </div>
            );
          })}
        </div>

        {/* Custom Date & Preferred Time Picker */}
        <div className="custom-datetime-section">
          <div className="custom-datetime-header">
            <span className="custom-datetime-title">
              📅 Custom Date & Preferred Time
            </span>
            <span className="custom-datetime-hint">24h available</span>
          </div>
          <div className="custom-input-grid">
            <div className="custom-input-group">
              <label className="custom-input-label">Preferred Date</label>
              <input
                type="date"
                className="custom-input-field"
                value={selectedDate || ''}
                min={todayStr}
                onChange={(e) => setSelectedDate(e.target.value)}
              />
            </div>
            <div className="custom-input-group">
              <label className="custom-input-label">Preferred Time</label>
              <input
                type="time"
                className="custom-input-field"
                value={customTimeInput}
                onChange={(e) => handleCustomTimeChange(e.target.value)}
              />
            </div>
          </div>
        </div>

        {/* 24-Hour Time Slot Grid with Period Filters */}
        <div className="section-title mt-4">Available Time Slots (24 Hours)</div>
        
        <div className="period-tabs">
          <button 
            type="button" 
            className={`period-tab ${selectedPeriod === 'all' ? 'active' : ''}`}
            onClick={() => setSelectedPeriod('all')}
          >
            All (24h)
          </button>
          <button 
            type="button" 
            className={`period-tab ${selectedPeriod === 'morning' ? 'active' : ''}`}
            onClick={() => setSelectedPeriod('morning')}
          >
            🌅 Morning
          </button>
          <button 
            type="button" 
            className={`period-tab ${selectedPeriod === 'afternoon' ? 'active' : ''}`}
            onClick={() => setSelectedPeriod('afternoon')}
          >
            ☀️ Afternoon
          </button>
          <button 
            type="button" 
            className={`period-tab ${selectedPeriod === 'evening' ? 'active' : ''}`}
            onClick={() => setSelectedPeriod('evening')}
          >
            🌆 Evening
          </button>
          <button 
            type="button" 
            className={`period-tab ${selectedPeriod === 'night' ? 'active' : ''}`}
            onClick={() => setSelectedPeriod('night')}
          >
            🌙 Night
          </button>
        </div>

        <div className="time-slots-grid" style={{ maxHeight: '240px', overflowY: 'auto', paddingRight: '4px' }}>
          {filteredSlots.length > 0 ? filteredSlots.map((slot, index) => {
            const isSelected = selectedSlot === slot;
            return (
              <button 
                key={index}
                type="button"
                className={`time-pill ${isSelected ? 'active' : ''}`}
                onClick={() => handleSelectSlot(slot)}
              >
                {slot}
              </button>
            );
          }) : (
            <div className="no-slots">No slots in this period. Choose another period or enter custom time above.</div>
          )}
        </div>

        {/* Live Selection Summary */}
        {selectedDate && selectedSlot && (
          <div className="selection-summary-badge">
            <span>New Schedule:</span>
            <strong>{formatSummary()}</strong>
          </div>
        )}

        <button 
          type="button"
          className="confirm-btn" 
          onClick={handleSubmit}
          disabled={!selectedDate || !selectedSlot || isSubmitting}
        >
          {isSubmitting ? 'Confirming Reschedule...' : 'Confirm New Time'}
        </button>
      </div>
    </div>
  );
};

export default Reschedule;
