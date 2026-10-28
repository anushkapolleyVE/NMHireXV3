const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api").replace(/\/+$/, "");
/*
  Your backend requires X-User-Id for:
  - creating a job
  - screening a job
  - fetching candidates

  For now we read it from localStorage.
  Later we can connect this to your login properly.
*/
const getUserId = () => {
  return localStorage.getItem("userId");
};

const getHeaders = () => {
  const token = localStorage.getItem("accessToken");

  return token
    ? {
        "Authorization": `Bearer ${token}`,
      }
    : {};
};

const getErrorMessage = async (response, fallback) => {
  try {
    const data = await response.json();

    if (typeof data === "string") {
      return data;
    }

    return (
      data?.detail ||
      data?.message ||
      data?.error ||
      fallback
    );
  } catch {
    return fallback;
  }
};





// --------------------------------------------------
// GET USER JOBS
// --------------------------------------------------

export const getUserJobs = async () => {
  
  const response = await fetch(
    `${API_BASE_URL}/user/jobs`,
    {
      method: "GET",
      headers: getHeaders(),
    }
  );

  if (!response.ok) {
    throw new Error(
      await getErrorMessage(
        response,
        "Failed to fetch jobs."
      )
    );
  }

  return response.json();
};


// --------------------------------------------------
// GET CANDIDATES FOR JOB
// --------------------------------------------------

export const getJobCandidates = async (jobId) => {
  const response = await fetch(
    `${API_BASE_URL}/user/jobs/${jobId}/candidates`,
    {
      method: "GET",
      headers: getHeaders(),
    }
  );

  if (!response.ok) {
    throw new Error(
      await getErrorMessage(
        response,
        "Failed to fetch candidates."
      )
    );
  }

  return response.json();
};



// --------------------------------------------------
// GET USER DASHBOARD
// --------------------------------------------------

export const getUserDashboard = async () => {
  const response = await fetch(
    `${API_BASE_URL}/user/dashboard`,
    {
      method: "GET",
      headers: getHeaders(),
    }
  );

  if (!response.ok) {
    throw new Error(
      await getErrorMessage(
        response,
        "Failed to fetch dashboard data."
      )
    );
  }

  return response.json();
};

export const markCandidateContacted = async (jobId, candidateId) => {
  const res = await fetch(`${API_BASE_URL}/user/jobs/${jobId}/candidates/${candidateId}/contact`, {
    method: 'POST',
    headers: getHeaders()
  });
  if (!res.ok) throw new Error('Failed to mark contacted');
  return await res.json();
};

export const getAllCandidates = async () => {
  const res = await fetch(`${API_BASE_URL}/user/candidates`, {
    headers: getHeaders()
  });
  if (!res.ok) throw new Error('Failed to fetch candidates');
  return await res.json();
};

export const getOutreachData = async () => {
  const res = await fetch(`${API_BASE_URL}/user/outreach`, {
    headers: getHeaders()
  });
  if (!res.ok) throw new Error('Failed to fetch outreach data');
  return await res.json();
};

export const updateCandidateStatus = async (jobId, candidateId, status, targetPhone = null) => {
  const res = await fetch(`${API_BASE_URL}/user/jobs/${jobId}/candidates/${candidateId}/status`, {
    method: 'POST',
    headers: {
      ...getHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ status, target_phone: targetPhone })
  });
  if (!res.ok) throw new Error('Failed to update candidate status');
  return await res.json();
};

export const bulkUpdateCandidateStatus = async (jobId, candidateIds, status = 'CONTACTED', targetPhone = null) => {
  const res = await fetch(`${API_BASE_URL}/user/jobs/${jobId}/candidates/bulk-status`, {
    method: 'POST',
    headers: {
      ...getHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ candidate_ids: candidateIds, status, target_phone: targetPhone })
  });
  if (!res.ok) throw new Error(await getErrorMessage(res, 'Failed to update candidates in bulk'));
  return await res.json();
};


// --------------------------------------------------
// EXTERNAL RESUME MATCHING API
// --------------------------------------------------

export const getRequisitions = async () => {
  const response = await fetch(`${API_BASE_URL}/resume-matching/requisitions`, {
    method: "GET",
    headers: getHeaders(),
  });
  if (!response.ok) {
    throw new Error(await getErrorMessage(response, "Failed to fetch requisitions."));
  }
  return response.json();
};

export const createJobFromRequisition = async (vereqNumber) => {
  const response = await fetch(`${API_BASE_URL}/resume-matching/requisitions/${vereqNumber}/create-job`, {
    method: "POST",
    headers: getHeaders(),
  });
  if (!response.ok) {
    throw new Error(await getErrorMessage(response, "Failed to create job from requisition."));
  }
  return response.json();
};

export const fetchTopCandidates = async (jobId, vereqNumber) => {
  const response = await fetch(`${API_BASE_URL}/jobs/${jobId}/resume-matching?vereq_number=${vereqNumber}`, {
    method: "POST",
    headers: getHeaders(),
  });
  if (!response.ok) {
    throw new Error(await getErrorMessage(response, "Failed to fetch top candidates."));
  }
  return response.json();
};


// --------------------------------------------------
// NAUKRI-STYLE OUTREACH ARRAY
// --------------------------------------------------

export const sendNaukriOutreach = async ({ jobId, candidates, companyName }) => {
  const payload = {
    candidates,
    ...(jobId ? { job_id: jobId } : {}),
    ...(companyName ? { company_name: companyName } : {}),
  };
  const res = await fetch(`${API_BASE_URL}/outreach/send-array`, {
    method: "POST",
    headers: {
      ...getHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(await getErrorMessage(res, "Failed to send outreach."));
  }
  return res.json();
};

