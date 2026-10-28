import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import './ScheduleInterview.css';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";

const ScheduleInterview = () => {
  const { candidateId } = useParams();
  const navigate = useNavigate();
  
  const [dates, setDates] = useState([]);
  const [selectedDate, setSelectedDate] = useState(null);
  
  const [slots, setSlots] = useState([]);
  const [selectedSlot, setSelectedSlot] = useState(null);
  
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [meetingLink, setMeetingLink] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Fetch available dates
    fetch(`${API_BASE_URL}/scheduling/dates`)
      .then(res => res.json())
      .then(data => {
        setDates(data.dates || []);
        if (data.dates && data.dates.length > 0) {
          setSelectedDate(data.dates[0].date);
        }
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setError("Failed to load available dates.");
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (selectedDate) {
      // Fetch slots for the selected date
      fetch(`${API_BASE_URL}/scheduling/slots?date=${selectedDate}`)
        .then(res => res.json())
        .then(data => {
          setSlots(data.slots || []);
          setSelectedSlot(null); // Reset slot selection when date changes
        })
        .catch(err => {
          console.error(err);
        });
    }
  }, [selectedDate]);

  const handleConfirm = () => {
    if (!selectedDate || !selectedSlot) return;
    
    setSubmitting(true);
    
    fetch(`${API_BASE_URL}/scheduling/confirm`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        job_candidate_id: candidateId,
        interview_date: selectedDate,
        interview_time: selectedSlot,
        timezone: 'Asia/Kolkata'
      })
    })
    .then(res => {
      if (!res.ok) throw new Error("Failed to confirm slot. It might be already booked.");
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
    const d = new Date(dateStr);
    const day = d.getDate();
    const month = d.toLocaleString('en-US', { month: 'short' });
    const dayOfWeek = d.toLocaleString('en-US', { weekday: 'short' }).toUpperCase();
    return { dayOfWeek, day, month };
  };

  if (loading) {
    return <div className="schedule-container loading"><div className="spinner"></div></div>;
  }

  if (success) {
    return (
      <div className="schedule-container dark-theme">
        <div className="schedule-content glass-card success-state">
          <div className="success-icon">✓</div>
          <h2 className="schedule-title">Interview Confirmed!</h2>
          <p className="schedule-subtitle">We have sent you a confirmation on WhatsApp.</p>
          {meetingLink && (
            <div className="meeting-link-box">
              <p>Your Meeting Link:</p>
              <a href={meetingLink} target="_blank" rel="noreferrer">{meetingLink}</a>
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
        <p className="schedule-subtitle">Select your preferred date and time</p>
        
        {error && <div className="error-message">{error}</div>}

        <div className="section-title">Your next 7 days</div>
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

        <div className="section-title mt-4">Available Time Slots</div>
        <div className="time-slots-grid">
          {slots.length > 0 ? slots.map((slot, index) => {
            const isSelected = selectedSlot === slot;
            return (
              <button 
                key={index}
                className={`time-pill ${isSelected ? 'active' : ''}`}
                onClick={() => setSelectedSlot(slot)}
              >
                {slot}
              </button>
            );
          }) : (
            <div className="no-slots">No slots available for this date.</div>
          )}
        </div>

        <button 
          className="confirm-btn" 
          onClick={handleConfirm}
          disabled={!selectedDate || !selectedSlot || submitting}
        >
          {submitting ? 'Confirming...' : 'Confirm Interview'}
        </button>
      </div>
    </div>
  );
};

export default ScheduleInterview;
