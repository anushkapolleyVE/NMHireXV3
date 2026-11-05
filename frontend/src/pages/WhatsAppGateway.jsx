import { useState, useEffect } from "react";
import Header from "../components/Header";
import {
  gatewayAddCandidate,
  gatewayGetSchedules,
  gatewayGetInterviewResults,
} from "../utils/api";

export default function WhatsAppGateway() {
  const [activeTab, setActiveTab] = useState("add-candidate");

  // Form State
  const [form, setForm] = useState({
    user_name: "",
    email: "",
    contact_no: "",
    current_company: "",
    job_role: "",
    interview_date: new Date().toISOString().split("T")[0],
    interview_time: "11:00",
    requisition_id: "506",
  });
  const [formSubmitting, setFormSubmitting] = useState(false);
  const [formSuccess, setFormSuccess] = useState(null);
  const [formError, setFormError] = useState("");

  // Schedules State
  const [schedules, setSchedules] = useState([]);
  const [schedulesLoading, setSchedulesLoading] = useState(false);
  const [schedFilter, setSchedFilter] = useState({
    startDate: "2026-11-01",
    endDate: "2026-11-30",
    search: "",
  });

  // Results State
  const [results, setResults] = useState([]);
  const [resultsLoading, setResultsLoading] = useState(false);
  const [resFilter, setResFilter] = useState({
    startDate: "2026-11-01",
    endDate: "2026-11-30",
    search: "",
  });

  const handleFormChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const handleAddCandidate = async (e) => {
    e.preventDefault();
    setFormSubmitting(true);
    setFormError("");
    setFormSuccess(null);

    try {
      const res = await gatewayAddCandidate({
        ...form,
        technical_round: 1,
        one2one_round: 1,
        comm_skill_rating: 4,
        cultural_fit_rating: 4,
        operation: "addcandidate",
      });
      setFormSuccess(res);
    } catch (err) {
      setFormError(err.message || "Failed to schedule candidate.");
    } finally {
      setFormSubmitting(false);
    }
  };

  const loadSchedules = async () => {
    setSchedulesLoading(true);
    try {
      const data = await gatewayGetSchedules({
        startDate: schedFilter.startDate,
        endDate: schedFilter.endDate,
        search: schedFilter.search || undefined,
      });
      setSchedules(data.data || []);
    } catch (err) {
      console.error(err);
    } finally {
      setSchedulesLoading(false);
    }
  };

  const loadResults = async () => {
    setResultsLoading(true);
    try {
      const data = await gatewayGetInterviewResults({
        startDate: resFilter.startDate,
        endDate: resFilter.endDate,
        search: resFilter.search || undefined,
      });
      setResults(data.data || []);
    } catch (err) {
      console.error(err);
    } finally {
      setResultsLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === "schedules") {
      loadSchedules();
    } else if (activeTab === "results") {
      loadResults();
    }
  }, [activeTab]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 pb-16">
      <Header />

      <main className="mx-auto max-w-7xl px-5 pt-8 sm:px-8">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-white flex items-center gap-3">
              WhatsApp Integration Gateway
              <span className="rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-400 border border-emerald-500/20">
                Live Integration
              </span>
            </h1>
            <p className="mt-1 text-sm text-slate-400">
              Manage candidate creation, scheduled WhatsApp interviews, and score reports.
            </p>
          </div>

          <div className="flex bg-slate-900 p-1.5 rounded-xl border border-slate-800">
            <button
              onClick={() => setActiveTab("add-candidate")}
              className={`px-4 py-2 text-xs font-bold rounded-lg transition-all ${
                activeTab === "add-candidate"
                  ? "bg-brand text-white shadow-md shadow-brand/30"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Add Candidate
            </button>
            <button
              onClick={() => setActiveTab("schedules")}
              className={`px-4 py-2 text-xs font-bold rounded-lg transition-all ${
                activeTab === "schedules"
                  ? "bg-brand text-white shadow-md shadow-brand/30"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Scheduled ({schedules.length})
            </button>
            <button
              onClick={() => setActiveTab("results")}
              className={`px-4 py-2 text-xs font-bold rounded-lg transition-all ${
                activeTab === "results"
                  ? "bg-brand text-white shadow-md shadow-brand/30"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Interview Results ({results.length})
            </button>
          </div>
        </div>

        {/* TAB 1: ADD CANDIDATE */}
        {activeTab === "add-candidate" && (
          <div className="max-w-3xl mx-auto bg-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-8">
            <div className="mb-6">
              <h2 className="text-xl font-bold text-white">Create Candidate & Schedule Interview</h2>
              <p className="text-xs text-slate-400 mt-1">
                Creates the interview schedule, triggers automated WhatsApp outreach, and generates the registration link.
              </p>
            </div>

            {formError && (
              <div className="mb-6 p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm">
                {formError}
              </div>
            )}

            {formSuccess && (
              <div className="mb-6 p-5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-300">
                <div className="font-semibold text-emerald-200">Candidate created successfully!</div>
                <div className="mt-2 text-xs text-emerald-400/90 break-all">
                  <span className="font-bold">Registration / Meeting URL:</span>{" "}
                  <a
                    href={formSuccess.registrationUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="underline hover:text-emerald-100"
                  >
                    {formSuccess.registrationUrl || "Captured in response"}
                  </a>
                </div>
              </div>
            )}

            <form onSubmit={handleAddCandidate} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Candidate Name *
                </label>
                <input
                  required
                  name="user_name"
                  value={form.user_name}
                  onChange={handleFormChange}
                  placeholder="e.g. Sayank"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-brand"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Email Address *
                </label>
                <input
                  required
                  type="email"
                  name="email"
                  value={form.email}
                  onChange={handleFormChange}
                  placeholder="sayank@gmail.com"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-brand"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Contact Number (with Country Code) *
                </label>
                <input
                  required
                  name="contact_no"
                  value={form.contact_no}
                  onChange={handleFormChange}
                  placeholder="918506002804"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-brand"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Current Company
                </label>
                <input
                  name="current_company"
                  value={form.current_company}
                  onChange={handleFormChange}
                  placeholder="ABCD Technologies Pvt. Ltd"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-brand"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Job Role
                </label>
                <input
                  name="job_role"
                  value={form.job_role}
                  onChange={handleFormChange}
                  placeholder="Software Engineer"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-brand"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Requisition ID *
                </label>
                <input
                  required
                  name="requisition_id"
                  value={form.requisition_id}
                  onChange={handleFormChange}
                  placeholder="506"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-brand"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Interview Date *
                </label>
                <input
                  required
                  type="date"
                  name="interview_date"
                  value={form.interview_date}
                  onChange={handleFormChange}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-brand"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Interview Time *
                </label>
                <input
                  required
                  type="time"
                  name="interview_time"
                  value={form.interview_time}
                  onChange={handleFormChange}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm text-white focus:outline-none focus:border-brand"
                />
              </div>

              <div className="sm:col-span-2 pt-2">
                <button
                  type="submit"
                  disabled={formSubmitting}
                  className="w-full py-3 rounded-xl bg-brand font-bold text-white hover:bg-brand-soft transition-all shadow-lg shadow-brand/20 disabled:opacity-50"
                >
                  {formSubmitting ? "Dispatching to Gateway..." : "Schedule Interview via WhatsApp"}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* TAB 2: SCHEDULED INTERVIEWS */}
        {activeTab === "schedules" && (
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
              <div className="flex flex-wrap items-center gap-3">
                <input
                  type="date"
                  value={schedFilter.startDate}
                  onChange={(e) => setSchedFilter({ ...schedFilter, startDate: e.target.value })}
                  className="bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-xs text-white"
                />
                <span className="text-slate-500 text-xs">to</span>
                <input
                  type="date"
                  value={schedFilter.endDate}
                  onChange={(e) => setSchedFilter({ ...schedFilter, endDate: e.target.value })}
                  className="bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-xs text-white"
                />
                <button
                  onClick={loadSchedules}
                  className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 rounded-xl text-xs font-semibold"
                >
                  Filter
                </button>
              </div>

              <input
                placeholder="Search candidate name or email..."
                value={schedFilter.search}
                onChange={(e) => setSchedFilter({ ...schedFilter, search: e.target.value })}
                onKeyDown={(e) => e.key === "Enter" && loadSchedules()}
                className="bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-xs text-white w-full sm:w-64"
              />
            </div>

            {schedulesLoading ? (
              <div className="py-12 text-center text-slate-500 text-sm">Loading schedules from WhatsApp Gateway...</div>
            ) : schedules.length === 0 ? (
              <div className="py-12 text-center text-slate-500 text-sm">No scheduled interviews found for this date range.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm text-slate-300">
                  <thead className="bg-slate-950/60 text-xs uppercase text-slate-400">
                    <tr>
                      <th className="px-4 py-3">Candidate</th>
                      <th className="px-4 py-3">Contact</th>
                      <th className="px-4 py-3">Interview Date/Time</th>
                      <th className="px-4 py-3">Requisition</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">Next Step</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {schedules.map((row, idx) => (
                      <tr key={row.schedule_id || idx} className="hover:bg-slate-800/40">
                        <td className="px-4 py-3 font-medium text-white">
                          {row.user_name}
                          <div className="text-xs text-slate-400 font-normal">{row.email}</div>
                        </td>
                        <td className="px-4 py-3 font-mono text-xs">{row.contact_no}</td>
                        <td className="px-4 py-3">
                          {row.interview_date} {row.interview_time}
                        </td>
                        <td className="px-4 py-3">{row.requisition_id}</td>
                        <td className="px-4 py-3">
                          <span className="rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20 px-2.5 py-0.5 text-xs">
                            {row.current_status || (row.is_registered ? "Registered" : "Scheduled")}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-xs text-slate-400">{row.next_step || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* TAB 3: INTERVIEW RESULTS */}
        {activeTab === "results" && (
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
              <div className="flex flex-wrap items-center gap-3">
                <input
                  type="date"
                  value={resFilter.startDate}
                  onChange={(e) => setResFilter({ ...resFilter, startDate: e.target.value })}
                  className="bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-xs text-white"
                />
                <span className="text-slate-500 text-xs">to</span>
                <input
                  type="date"
                  value={resFilter.endDate}
                  onChange={(e) => setResFilter({ ...resFilter, endDate: e.target.value })}
                  className="bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-xs text-white"
                />
                <button
                  onClick={loadResults}
                  className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 rounded-xl text-xs font-semibold"
                >
                  Filter
                </button>
              </div>

              <input
                placeholder="Search candidate name or email..."
                value={resFilter.search}
                onChange={(e) => setResFilter({ ...resFilter, search: e.target.value })}
                onKeyDown={(e) => e.key === "Enter" && loadResults()}
                className="bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-xs text-white w-full sm:w-64"
              />
            </div>

            {resultsLoading ? (
              <div className="py-12 text-center text-slate-500 text-sm">Loading interview results from WhatsApp Gateway...</div>
            ) : results.length === 0 ? (
              <div className="py-12 text-center text-slate-500 text-sm">No interview results recorded for this period.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm text-slate-300">
                  <thead className="bg-slate-950/60 text-xs uppercase text-slate-400">
                    <tr>
                      <th className="px-4 py-3">Candidate</th>
                      <th className="px-4 py-3">Test Type</th>
                      <th className="px-4 py-3">Result</th>
                      <th className="px-4 py-3">Score</th>
                      <th className="px-4 py-3">Feedback</th>
                      <th className="px-4 py-3">Requisition</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {results.map((row, idx) => (
                      <tr key={row.interview_id || idx} className="hover:bg-slate-800/40">
                        <td className="px-4 py-3 font-medium text-white">
                          {row.candidate_name}
                          <div className="text-xs text-slate-400 font-normal">{row.candidate_email}</div>
                        </td>
                        <td className="px-4 py-3 text-xs">{row.test_type_name || (row.test_type === 1 ? "Technical" : "One-to-One")}</td>
                        <td className="px-4 py-3">
                          <span
                            className={`rounded-full px-2.5 py-0.5 text-xs font-semibold border ${
                              (row.result || "").toLowerCase() === "pass"
                                ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                                : "bg-rose-500/10 text-rose-400 border-rose-500/20"
                            }`}
                          >
                            {row.result || "N/A"}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-xs font-mono">
                          {row.score !== null ? `${row.score} (${row.score_percentage || 0}%)` : "-"}
                        </td>
                        <td className="px-4 py-3 text-xs max-w-xs truncate text-slate-400">{row.feedback || "-"}</td>
                        <td className="px-4 py-3 text-xs">{row.requisition_id}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

