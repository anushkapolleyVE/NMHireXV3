import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import './ScheduleInterview.css';

const rawApi = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || "http://localhost:8000/api";
const API_BASE_URL = rawApi.replace(/\/+$/, "").endsWith("/api")
  ? rawApi.replace(/\/+$/, "")
  : `${rawApi.replace(/\/+$/, "")}/api`;

const ScheduleInterview = () => {
  const { candidateId } = useParams();
  const navigate = useNavigate();
  
  const [dates, setDates] = useState([]);
  const [selectedDate, setSelectedDate] = useState('');
  
  const [slots, setSlots] = useState([]);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [selectedPeriod, setSelectedPeriod] = useState('all');
  const [customTimeInput, setCustomTimeInput] = useState('');
  
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [meetingLink, setMeetingLink] = useState(null);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);

  // Today in local YYYY-MM-DD
  const getLocalDateStr = (d = new Date()) => {
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };

  const todayStr = getLocalDateStr();
  const userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Kolkata';

  useEffect(() => {
    // Fetch available dates with candidate timezone
    fetch(`${API_BASE_URL}/scheduling/dates?timezone=${encodeURIComponent(userTimezone)}`)
      .then(res => res.json())
      .then(data => {
        const fetchedDates = data.dates || [];
        setDates(fetchedDates);
        if (fetchedDates.length > 0) {
          setSelectedDate(fetchedDates[0].date);
        } else {
          setSelectedDate(todayStr);
        }
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setError("Failed to load available dates.");
        setSelectedDate(todayStr);
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (selectedDate) {
      // Fetch slots for the selected date with timezone
      fetch(`${API_BASE_URL}/scheduling/slots?date=${selectedDate}&timezone=${encodeURIComponent(userTimezone)}`)
        .then(res => res.json())
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

  // Handle slot pill selection
  const handleSelectSlot = (slot) => {
    if (isSlotInPast(selectedDate, slot)) {
      setError("This slot is already in the past. Please choose an upcoming time.");
      return;
    }
    setError(null);
    setSelectedSlot(slot);
    setCustomTimeInput(convert12To24(slot));
  };

  // Handle custom time picker change
  const handleCustomTimeChange = (time24) => {
    setCustomTimeInput(time24);
    if (time24) {
      const formatted12 = convert24To12(time24);
      if (isSlotInPast(selectedDate, formatted12)) {
        setError("Selected time is in the past. Please choose a future time slot.");
        setSelectedSlot(null);
      } else {
        setError(null);
        setSelectedSlot(formatted12);
      }
    } else {
      setSelectedSlot(null);
    }
  };

  // Handle date selection change
  const handleSelectDate = (newDate) => {
    setSelectedDate(newDate);
    if (selectedSlot && isSlotInPast(newDate, selectedSlot)) {
      setSelectedSlot(null);
      setCustomTimeInput('');
    }
    setError(null);
  };

  // Slot filter for 24 hours + exclude past slots
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

  const handleConfirm = () => {
    if (!selectedDate || !selectedSlot) return;
    if (isSlotInPast(selectedDate, selectedSlot)) {
      setError("Cannot schedule an interview in the past. Please choose an upcoming time.");
      return;
    }
    
    setSubmitting(true);
    setError(null);
    
    fetch(`${API_BASE_URL}/scheduling/confirm`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        job_candidate_id: candidateId,
        interview_date: selectedDate,
        interview_time: selectedSlot,
        timezone: userTimezone
      })
    })
    .then(async res => {
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to confirm slot. It might be in the past or already booked.");
      }
      return res.json();
    })
    .then(data => {
      setSuccess(true);
      if (data.data && data.data.link) {
        setMeetingLink(data.data.link);
      }
      setSubmitting(false);
    })
    .catch(err => {
      console.error(err);
      setError(err.message);
      setSubmitting(false);
    });
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

  const copyLink = () => {
    if (meetingLink) {
      navigator.clipboard.writeText(meetingLink);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (loading) {
    return <div className="schedule-container dark-theme loading"><div className="spinner"></div></div>;
  }

  if (success) {
    return (
      <div className="schedule-container dark-theme">
        <div className="schedule-content glass-card success-state">
          <div className="success-icon">✓</div>
          <h2 className="schedule-title">Interview Confirmed!</h2>
          <p className="schedule-subtitle">We have sent you a confirmation on WhatsApp.</p>
          
          <div className="selection-summary-badge" style={{ justifyContent: 'center' }}>
            <span>📅 <strong>{formatSummary()}</strong></span>
          </div>

          {meetingLink && (
            <div className="meeting-link-box">
              <p style={{ color: '#94a3b8', fontSize: '0.8rem', marginBottom: '6px' }}>Your Meeting Link:</p>
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
        <h2 className="schedule-title">Schedule Interview</h2>
        <p className="schedule-subtitle">Pick from 24-hour slots or enter your custom preferred time</p>
        
        {error && <div className="error-message">{error}</div>}

        {/* 7-Day Quick Select */}
        <div className="section-title">Your next 7 days</div>
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
            <span>Selected Slot:</span>
            <strong>{formatSummary()}</strong>
          </div>
        )}

        <button 
          className="confirm-btn" 
          onClick={handleConfirm}
          disabled={!selectedDate || !selectedSlot || isSlotInPast(selectedDate, selectedSlot) || submitting}
        >
          {submitting ? 'Confirming...' : 'Confirm Interview'}
        </button>
      </div>
    </div>
  );
};

export default ScheduleInterview;
