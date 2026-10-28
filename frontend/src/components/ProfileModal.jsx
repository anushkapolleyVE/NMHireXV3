import React from 'react';

const ProfileModal = ({ isOpen, onClose, candidate }) => {
  if (!isOpen || !candidate) return null;

  return (
    <div className="fixed inset-0 z-[100] flex justify-end bg-slate-950/40 backdrop-blur-sm sm:items-center sm:justify-center p-0 sm:p-4 animate-fade-in">
      <div className="flex h-full w-full flex-col bg-white sm:h-auto sm:max-h-[90vh] sm:w-[600px] sm:rounded-xl shadow-2xl overflow-hidden animate-slide-up relative">
        
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4 bg-white sticky top-0 z-10">
          <h2 className="text-lg font-bold text-gray-900">Candidate profile</h2>
          <button 
            onClick={onClose} 
            className="rounded-full p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"></path>
            </svg>
          </button>
        </div>
        
        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-gray-300">
          
          {/* Profile Header section */}
          <div className="flex items-start justify-between mb-4">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">{candidate.name || 'Unnamed Candidate'}</h1>
              <div className="mt-2 text-sm text-gray-500 leading-relaxed max-w-[400px]">
                <p>
                  {candidate.email && `${candidate.email} · `}
                  {candidate.phone && `${candidate.phone} · `}
                  {candidate.location && candidate.location !== '-' && candidate.location}
                </p>
                <p className="mt-1">{candidate.exp || candidate.experience || '0'} years experience</p>
              </div>
            </div>
          </div>
          
          {/* Skills */}
          <div className="mt-8">
            <h3 className="text-sm font-bold text-gray-800 mb-4">Skills</h3>
            <div className="flex flex-wrap gap-2">
              {(() => {
                const skills = candidate.all_skills && candidate.all_skills.length > 0 
                  ? candidate.all_skills 
                  : Array.isArray(candidate.skills) 
                    ? candidate.skills 
                    : typeof candidate.skills === 'string' 
                      ? candidate.skills.split(',') 
                      : [];
                      
                return skills.length > 0 ? (
                  skills.map((skill, idx) => {
                    const skillStr = typeof skill === 'string' ? skill : (skill.name || skill.skill || skill.skill_name || '');
                    if (!skillStr) return null;
                    return (
                      <span 
                        key={idx} 
                        className="rounded-full border border-gray-200 bg-white px-3 py-1 text-[13px] font-medium text-gray-700 shadow-sm"
                      >
                        {skillStr.trim()}
                      </span>
                    );
                  })
                ) : (
                  <p className="text-sm text-gray-500">No skills listed</p>
                );
              })()}
            </div>
          </div>
          
          {/* Experience */}
          <div className="mt-8">
            <h3 className="text-sm font-bold text-gray-800 mb-4">Experience</h3>
            
            {candidate.experience_details && candidate.experience_details.length > 0 ? (
              candidate.experience_details.map((exp, idx) => {
                const dates = exp.dates || exp.duration || ((exp.start_date || exp.end_date) ? `${exp.start_date || ''} - ${exp.end_date || 'Present'}` : 'Dates unknown');
                return (
                  <div key={idx} className="mb-6 last:mb-0">
                    <h4 className="text-base font-bold text-gray-900">{exp.company || 'Unknown Company'}</h4>
                    <p className="text-sm text-gray-700 mt-0.5">{exp.role || exp.title || 'Role unknown'}</p>
                    <p className="text-sm text-gray-500 mt-0.5">{dates}</p>
                    
                    {exp.description && (
                      <p className="mt-3 text-sm text-gray-600 leading-relaxed text-justify">
                        {exp.description}
                      </p>
                    )}
                    {exp.responsibilities && Array.isArray(exp.responsibilities) && exp.responsibilities.length > 0 && (
                      <ul className="mt-3 list-disc pl-5 text-sm text-gray-600 leading-relaxed space-y-1">
                        {exp.responsibilities.map((resp, i) => (
                          <li key={i}>{resp}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                );
              })
            ) : (
              <div className="mb-6">
                <h4 className="text-base font-bold text-gray-900">{candidate.job || 'Role unknown'}</h4>
                <p className="text-sm text-gray-700 mt-0.5">Unknown Company</p>
                
                {candidate.experience_description ? (
                  <p className="mt-3 text-sm text-gray-600 leading-relaxed text-justify">
                    {candidate.experience_description}
                  </p>
                ) : (
                  <p className="mt-3 text-sm text-gray-500 italic">No detailed experience provided.</p>
                )}
              </div>
            )}
          </div>

        </div>
      </div>
    </div>
  );
};

export default ProfileModal;
