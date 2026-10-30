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
  const [fatalError, setFatalError] = useState(null);
  const [formError, setFormError] = useState(null);
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

  const getLocalDateStr = (d = new Date()) => {
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };

  const todayStr = getLocalDateStr();
  const userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Kolkata';

  useEffect(() => {
    const fetchAll = async () => {
      try {
        setLoading(true);
        setFatalError(null);
        setFormError(null);

        // Fetch candidate reschedule details
        const res = await fetch(`${API_BASE_URL}/reschedule/${token}`);
        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.detail || 'This reschedule link has already been used or is expired. Interviews can only be rescheduled once.');
        }
        const data = await res.json();
        setDetails(data.data);
        if (data.data && data.data.interview_link) {
          setMeetingLink(data.data.interview_link);
        }

        // Fetch dates with timezone
        const datesRes = await fetch(`${API_BASE_URL}/scheduling/dates?timezone=${encodeURIComponent(userTimezone)}`)
          .then(r => r.json())
          .catch(() => ({ dates: [] }));

        const fetchedDates = datesRes.dates || [];
        setDates(fetchedDates);

        // Pre-select the existing interview date if it's today or in the future
        let initialDate = todayStr;
        if (data.data && data.data.current_scheduled_at) {
          const currentSchedDate = data.data.current_scheduled_at.split('T')[0];
          if (currentSchedDate >= todayStr) {
            initialDate = currentSchedDate;
          } else if (fetchedDates.length > 0) {
            initialDate = fetchedDates[0].date;
          }
        } else if (fetchedDates.length > 0) {
          initialDate = fetchedDates[0].date;
        }
        setSelectedDate(initialDate);
      } catch (err) {
        console.error('Reschedule fetch error:', err);
        setFatalError(err.message);
      } finally {
        setLoading(false);
      }
    };

    if (token) {
      fetchAll();
    }
  }, [token]);

  useEffect(() => {
    if (selectedDate) {
      fetch(`${API_BASE_URL}/scheduling/slots?date=${selectedDate}&timezone=${encodeURIComponent(userTimezone)}`)
        .then(r => r.json())
        .then(data => {
          setSlots(data.slots || []);
        })
        .catch(err => {
          console.error(err);
        });
    }
  }, [selectedDate]);

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

  // Check if a given date & slot is in the past
  const isSlotInPast = (dateStr, slot) => {
    if (!dateStr || !slot) return false;
    // Any future date cannot be in the past
    if (dateStr > todayStr) return false;
    if (dateStr < todayStr) return true;

    const match = slot.match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/i);
    if (!match) return false;
    let h = parseInt(match[1], 10);
    const m = parseInt(match[2], 10);
    const ampm = match[3].toUpperCase();
    if (ampm === 'PM' && h < 12) h += 12;
    if (ampm === 'AM' && h === 12) h = 0;

    const [y, mon, d] = dateStr.split('-').map(Number);
    const slotDate = new Date(y, mon - 1, d, h, m, 0, 0);
    return slotDate.getTime() <= Date.now();
  };

  const handleSelectSlot = (slot) => {
    if (isSlotInPast(selectedDate, slot)) {
      setFormError("This slot is already in the past. Please choose an upcoming time.");
      return;
    }
    setFormError(null);
    setSelectedSlot(slot);
    setCustomTimeInput(convert12To24(slot));
  };

  const handleCustomTimeChange = (time24) => {
    setCustomTimeInput(time24);
    if (time24) {
      const formatted12 = convert24To12(time24);
      if (isSlotInPast(selectedDate, formatted12)) {
        setFormError("Selected time is in the past. Please choose a future time slot.");
        setSelectedSlot(null);
      } else {
        setFormError(null);
        setSelectedSlot(formatted12);
      }
    } else {
      setSelectedSlot(null);
      setFormError(null);
    }
  };

  const handleSelectDate = (newDate) => {
    setSelectedDate(newDate);
    if (selectedSlot && isSlotInPast(newDate, selectedSlot)) {
      setSelectedSlot(null);
      setCustomTimeInput('');
    }
    setFormError(null);
  };

  const filterSlot = (slot) => {
    // Exclude any slot that is in the past
    if (isSlotInPast(selectedDate, slot)) return false;

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
    if (!selectedDate || !selectedSlot) {
      setFormError("Please select a date and time slot.");
      return;
    }
    if (isSlotInPast(selectedDate, selectedSlot)) {
      setFormError("Cannot reschedule an interview to a past time. Please choose an upcoming time.");
      return;
    }

    setIsSubmitting(true);
    setFormError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/reschedule/${token}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          new_date: selectedDate,
          new_time: selectedSlot,
          timezone: userTimezone
        })
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to reschedule. Please choose another slot.');
      }

      const resData = await res.json();
      if (resData.data && resData.data.link) {
        setMeetingLink(resData.data.link);
      }
      setSuccess(true);
    } catch (err) {
      setFormError(err.message);
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

  if (fatalError) {
    return (
      <div className="schedule-container dark-theme">
        <div className="schedule-content glass-card success-state" style={{ borderColor: 'rgba(239, 68, 68, 0.4)' }}>
          <div className="text-red-400 text-5xl mb-4" style={{ fontSize: '48px', marginBottom: '16px' }}>⚠️</div>
          <h2 className="schedule-title" style={{ color: '#f87171' }}>Reschedule Link Error</h2>
          <p className="schedule-subtitle" style={{ color: '#cbd5e1' }}>{fatalError}</p>
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

        {formError && (
          <div className="error-message" style={{ margin: '14px 0', padding: '12px 16px', borderRadius: '8px', backgroundColor: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.3)', color: '#f87171', fontSize: '0.9rem' }}>
            ⚠️ {formError}
          </div>
        )}

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
                onClick={() => handleSelectDate(d.date)}
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
                onChange={(e) => handleSelectDate(e.target.value)}
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
            <div className="no-slots">
              {selectedPeriod === 'morning' && selectedDate === todayStr
                ? "Morning slots for today have already passed. Please select Afternoon, Evening, or pick another day."
                : "No available slots for this period. Choose another period or enter a custom time above."}
            </div>
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
          disabled={!selectedDate || !selectedSlot || isSlotInPast(selectedDate, selectedSlot) || isSubmitting}
        >
          {isSubmitting ? 'Confirming Reschedule...' : 'Confirm New Time'}
        </button>
      </div>
    </div>
  );
};

export default Reschedule;
