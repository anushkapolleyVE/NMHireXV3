import { Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import AdminDashboard from './pages/AdminDashboard';

import Candidates from './pages/Candidates';
import JobDescriptions from './pages/JobDescriptions';
import Outreach from './pages/Outreach';
import OutreachSend from './pages/OutreachSend';
import Register from './pages/Register';
import ScheduleInterview from './pages/ScheduleInterview';
import TopCandidates from './pages/TopCandidates';
import Reschedule from './pages/Reschedule';

function App() {
  return (
    <Routes>
      <Route path="/" element={<Login />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      <Route path="/admin" element={<AdminDashboard />} />
      <Route path="/dashboard" element={<Dashboard />} />

      <Route path="/candidates" element={<Candidates />} />
      <Route path="/job-descriptions" element={<Navigate to="/dashboard" replace />} />
      <Route path="/outreach" element={<Outreach />} />
      <Route path="/outreach/send" element={<OutreachSend />} />
      <Route path="/schedule/:candidateId" element={<ScheduleInterview />} />
      <Route path="/reschedule/:token" element={<Reschedule />} />
      <Route path="/requisitions/:vereq/matches" element={<TopCandidates />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;