import React, { useState, useEffect } from 'react';
import { getRequisitions } from '../utils/api';
import { useNavigate } from 'react-router-dom';
import Header from '../components/Header';

const EyeIcon = ({ className }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
);

const EyeOffIcon = ({ className }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <path d="M9.88 9.88a3 3 0 1 0 4.24 4.24" />
    <path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68" />
    <path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61" />
    <line x1="2" x2="22" y1="2" y2="22" />
  </svg>
);
export default function JobDescriptions() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const [expandedJobId, setExpandedJobId] = useState(null);

  const toggleDescription = (id) => {
    setExpandedJobId(expandedJobId === id ? null : id);
  };

  useEffect(() => {
    const fetchJobs = async () => {
      try {
        const res = await getRequisitions();
        const apiData = res.data || res;
        
        let jobsList = [];
        if (Array.isArray(apiData)) {
          jobsList = apiData;
        } else if (apiData && Array.isArray(apiData.requisitions)) {
          jobsList = apiData.requisitions;
        } else if (apiData && Array.isArray(apiData.items)) {
          jobsList = apiData.items;
        } else if (apiData && Array.isArray(apiData.data)) {
          jobsList = apiData.data;
        } else if (apiData && Array.isArray(apiData.results)) {
          jobsList = apiData.results;
        }
        
        setJobs(jobsList);
      } catch (err) {
        console.error('Failed to fetch jobs', err);
      } finally {
        setLoading(false);
      }
    };
    fetchJobs();
  }, []);

  return (
    <div className="relative min-h-screen w-full overflow-hidden antialiased pb-20">
      <div className="glow-bg top-[-30%] left-[-20%] animate-pulse-slow"></div>
      <div className="glow-bg bottom-[-20%] right-[-10%] animate-pulse-slow"
        style={{ animationDelay: '2s', background: 'radial-gradient(circle, rgba(20,184,166,0.1) 0%, rgba(59,130,246,0.05) 40%, rgba(2,6,23,0) 70%)' }}
      ></div>

      <Header />

      <main className="relative z-10">
        <div className="mx-auto max-w-6xl px-5 py-8 sm:px-8">
          <div className="mb-10 flex flex-col sm:flex-row justify-between items-start gap-4 animate-slide-up opacity-0-init animate-delay-100">
            <div>
              <div className="mb-2 inline-flex items-center gap-2.5 rounded-full bg-slate-800/80 px-3 py-1.5 ring-1 ring-slate-700 w-max">
                <span className="size-2 rounded-full bg-accent shadow-[0_0_10px_rgba(20,184,166,0.8)]"></span>
                <p className="text-xs font-bold uppercase tracking-[0.15em] text-slate-300">Job Descriptions</p>
              </div>
              <h1 className="font-display text-4xl font-bold tracking-tight sm:text-5xl text-white">All JDs</h1>
              <p className="text-base text-slate-400">Review all the job descriptions stored in the system.</p>
            </div>
          </div>

          <div className="glass-dark rounded-[24px] overflow-hidden animate-slide-up opacity-0-init animate-delay-300">
            <div className="overflow-x-auto pb-2">
              <table className="w-full min-w-[960px] text-left border-collapse">
                <thead>
                  <tr className="border-b border-slate-700 bg-slate-900/50 text-[11px] font-bold uppercase tracking-wider text-slate-400">
                    <th className="py-4 pl-6 w-1/3">Job Title</th>
                    <th className="py-4 w-1/6">Location</th>
                    <th className="py-4 w-1/6">Work Mode</th>
                    <th className="py-4 w-1/12">Status</th>
                    <th className="py-4 w-1/12">Created At</th>
                    <th className="py-4 pr-6 text-right w-1/6">Action</th>
                  </tr>
                </thead>
                <tbody className="text-sm">
                  {loading ? (
                    <tr><td colSpan="6" className="py-12 text-center text-slate-500">Loading jobs...</td></tr>
                  ) : jobs.length === 0 ? (
                    <tr><td colSpan="6" className="py-12 text-center text-slate-500">
                      No jobs found.
                    </td></tr>
                  ) : (
                    jobs.map((job, index) => (
                      <React.Fragment key={job.id || job.job_id || index}>
                        <tr className="table-row-hover border-b border-slate-800/50 group">
                          <td className="py-5 pl-6">
                            <p className="font-bold text-white text-base">{job.title || 'Untitled Job'}</p>
                          </td>
                          <td className="py-5 whitespace-nowrap">
                            <p className="font-medium text-slate-300">{job.location || 'N/A'}</p>
                          </td>
                          <td className="py-5 whitespace-nowrap">
                            <p className="font-medium text-slate-300">{job.work_mode || 'N/A'}</p>
                          </td>
                          <td className="py-5 whitespace-nowrap">
                            <span className="inline-flex rounded-full bg-accent/20 px-3 py-1 text-[11px] font-bold text-accent ring-1 ring-accent/30 shadow-[0_0_8px_rgba(20,184,166,0.15)] items-center gap-1.5 w-max flex">
                              <span className="size-1.5 rounded-full bg-accent animate-pulse"></span>
                              {job.status || 'Open'}
                            </span>
                          </td>
                          <td className="py-5 whitespace-nowrap">
                            <p className="text-slate-400 text-sm">
                              {job.created_at ? new Date(job.created_at).toLocaleDateString('en-IN') : 'N/A'}
                            </p>
                          </td>
                          <td className="py-5 pr-6 text-right whitespace-nowrap">
                            <div className="flex items-center justify-end gap-2">
                              <button 
                                onClick={() => navigate(`/requisitions/${job.vereq_number || job.label || job.vereQ || job.requisition_number}/matches`)}
                                className="rounded-xl bg-accent px-4 py-2 text-xs font-bold text-white shadow-[0_0_15px_rgba(20,184,166,0.4)] hover:bg-teal-400 hover:-translate-y-0.5 transition-all whitespace-nowrap"
                              >
                                Top 30 Candidates
                              </button>
                              <button 
                                onClick={() => toggleDescription(job.id || job.vereq_number || job.label || index)}
                                className="p-2 rounded-full hover:bg-slate-700/50 text-slate-400 hover:text-white transition-colors"
                                title={expandedJobId === (job.id || job.vereq_number || job.label || index) ? "Hide Description" : "Show Description"}
                              >
                                {expandedJobId === (job.id || job.vereq_number || job.label || index) ? <EyeOffIcon className="size-5" /> : <EyeIcon className="size-5" />}
                              </button>
                            </div>
                          </td>
                        </tr>
                        {expandedJobId === (job.id || job.vereq_number || job.label || index) && (
                          <tr className="bg-slate-900/30 border-b border-slate-800/50 animate-slide-up opacity-0-init">
                            <td colSpan="6" className="py-6 px-8">
                              <div className="text-slate-300">
                                <h4 className="text-white font-bold mb-3 text-lg">Job Description</h4>
                                <div className="whitespace-pre-wrap text-sm max-h-[400px] overflow-y-auto custom-scrollbar p-4 bg-slate-950/50 rounded-xl border border-slate-800/50">
                                  {job.description || 'No description available for this job.'}
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
