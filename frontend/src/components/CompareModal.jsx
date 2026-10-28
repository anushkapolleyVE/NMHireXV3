import { useState } from 'react';

export default function CompareModal({ isOpen, onClose, baseCandidate, candidatesList }) {
  const [search, setSearch] = useState('');
  const [selectedCandidate, setSelectedCandidate] = useState(null);

  if (!isOpen || !baseCandidate) return null;

  // Filter out the base candidate and apply search
  const filteredCandidates = candidatesList.filter(c => 
    c.candidate_id !== baseCandidate.candidate_id &&
    c.name.toLowerCase().includes(search.toLowerCase())
  );

  const getScoreDelta = (score1, score2) => {
    const diff = score2 - score1;
    if (diff === 0) return null;
    return diff > 0 ? (
      <span className="text-accent flex items-center text-xs">▲</span>
    ) : (
      <span className="text-slate-500 flex items-center text-xs">▼</span>
    );
  };

  const renderComparisonRow = (label, key) => {
    const baseNode = baseCandidate.score_breakdown ? baseCandidate.score_breakdown[key] : { percentage: 0, max_score: 0 };
    const selectedNode = selectedCandidate?.score_breakdown ? selectedCandidate.score_breakdown[key] : { percentage: 0, max_score: 0 };
    
    const score1Display = baseNode.percentage;
    const score2Display = selectedNode.percentage;
    const weight = baseNode.max_score || selectedNode.max_score || 0;

    return (
      <div className="flex items-center justify-between py-4 border-b border-slate-800">
        <div className="flex items-center gap-2 w-1/3">
          <span className="text-sm font-medium text-slate-300">{label}</span>
          {weight && <span className="text-xs text-slate-500">{weight}%</span>}
        </div>
        <div className="w-1/3 text-center font-bold text-white flex items-center justify-center gap-1">
          {score1Display}
        </div>
        <div className="w-1/3 text-right font-bold text-white flex items-center justify-end gap-1">
          {selectedCandidate ? (
            <>
              <span className={score2Display > score1Display ? 'text-accent' : ''}>{score2Display}</span>
              {getScoreDelta(score1Display, score2Display)}
            </>
          ) : '-'}
        </div>
      </div>
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-fade-in">
      <div className="w-full max-w-4xl rounded-2xl bg-slate-900 ring-1 ring-slate-800 shadow-2xl overflow-hidden animate-slide-up flex flex-col max-h-[90vh]">
        
        <div className="p-6 border-b border-slate-800 flex justify-between items-center bg-slate-900/90 z-10 sticky top-0">
          <div>
            <h2 className="text-2xl font-bold text-white">Compare candidates</h2>
            <p className="text-sm text-slate-400">Both candidates were scored against the same job description.</p>
          </div>
          <button onClick={() => {
            setSearch('');
            setSelectedCandidate(null);
            onClose();
          }} className="rounded-xl px-4 py-2 text-sm font-bold text-slate-300 ring-1 ring-slate-700 hover:bg-slate-800 transition-all">
            Close
          </button>
        </div>

        <div className="p-6 overflow-y-auto flex-1">
          <div className="grid grid-cols-2 gap-6 mb-8">
            {/* Base Candidate Card */}
            <div className="bg-slate-800/50 rounded-xl p-5 ring-1 ring-slate-700">
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-2">Comparing</p>
              <h3 className="text-lg font-bold text-white">{baseCandidate.name}</h3>
              <p className="text-xs text-slate-400 mt-1 line-clamp-2">{baseCandidate.email}</p>
              <div className="mt-4 flex items-center gap-3">
                <span className="text-4xl font-display font-bold text-accent">{baseCandidate.score}</span>
                <span className="rounded-full bg-accent/20 px-2 py-1 text-[10px] font-bold text-accent ring-1 ring-accent/30">
                  {baseCandidate.classification?.replace(/_/g, ' ')}
                </span>
              </div>
            </div>

            {/* Selected Candidate Card or Search */}
            <div className="bg-slate-800/50 rounded-xl p-5 ring-1 ring-slate-700 flex flex-col">
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-2">Against</p>
              
              {!selectedCandidate ? (
                <>
                  <input 
                    type="text" 
                    placeholder="Search candidate name..." 
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-white focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand mb-3"
                  />
                  <div className="flex-1 overflow-y-auto max-h-[120px] pr-2 space-y-1 custom-scrollbar">
                    {filteredCandidates.map(c => (
                      <div 
                        key={c.candidate_id} 
                        onClick={() => setSelectedCandidate(c)}
                        className="flex justify-between items-center p-2 rounded hover:bg-slate-700 cursor-pointer transition-colors"
                      >
                        <span className="text-sm font-medium text-slate-300">{c.name}</span>
                        <span className="text-xs font-bold text-slate-500">{c.score}</span>
                      </div>
                    ))}
                    {filteredCandidates.length === 0 && (
                      <p className="text-xs text-slate-500 text-center py-2">No candidates found</p>
                    )}
                  </div>
                </>
              ) : (
                <>
                  <h3 className="text-lg font-bold text-white">{selectedCandidate.name}</h3>
                  <p className="text-xs text-slate-400 mt-1 line-clamp-2">{selectedCandidate.email}</p>
                  <div className="mt-4 flex items-center gap-3">
                    <span className="text-4xl font-display font-bold text-slate-200">{selectedCandidate.score}</span>
                    <span className="rounded-full bg-slate-700 px-2 py-1 text-[10px] font-bold text-slate-300 ring-1 ring-slate-600">
                      {selectedCandidate.classification?.replace(/_/g, ' ')}
                    </span>
                  </div>
                  <button 
                    onClick={() => setSelectedCandidate(null)}
                    className="mt-4 text-xs font-bold text-brand hover:text-brand-light text-left"
                  >
                    Pick someone else
                  </button>
                </>
              )}
            </div>
          </div>

          {/* Scores Table */}
          <div className="px-2">
            {renderComparisonRow('Mandatory skills', 'mandatory_skills')}
            {renderComparisonRow('Experience', 'experience')}
            {renderComparisonRow('Domain', 'domain')}
            {renderComparisonRow('Preferred skills', 'preferred_skills')}
            {renderComparisonRow('Education', 'education')}
            {renderComparisonRow('Location', 'location')}
          </div>
          
          {/* Reasoning */}
          <div className="grid grid-cols-2 gap-6 mt-6 px-2">
            <div className="bg-slate-800/30 rounded-lg p-4">
              <p className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">AI Reasoning</p>
              <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">
                {baseCandidate.reasoning || "No reasoning provided."}
              </p>
            </div>
            <div className="bg-slate-800/30 rounded-lg p-4">
              <p className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">AI Reasoning</p>
              <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">
                {selectedCandidate ? (selectedCandidate.reasoning || "No reasoning provided.") : "-"}
              </p>
            </div>
          </div>
          
        </div>
      </div>
    </div>
  );
}
