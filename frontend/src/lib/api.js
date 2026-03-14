const BASE = '/api/v1'

function getToken() {
  return localStorage.getItem('token')
}

function authHeaders() {
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${getToken()}`
  }
}

async function request(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: authHeaders(),
    ...opts,
  })
  if (res.status === 401) {
    localStorage.removeItem('token')
    window.location.href = '/login'
    return
  }
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export const api = {
  // Auth
  login: (email, password) =>
    fetch(`${BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    }).then(r => r.json()),

  // Teams
  getTeams: () => request('/teams/'),
  getTeam: (id) => request(`/teams/${id}`),
  createTeam: (data) => request('/teams/', { method: 'POST', body: JSON.stringify(data) }),

  // Risk
  getSnapshot: (teamId) => request(`/risk/teams/${teamId}/snapshot`),
  getTrend: (teamId, days = 14) => request(`/risk/teams/${teamId}/trend?days=${days}`),
  getInsights: (teamId, days = 7) => request(`/risk/teams/${teamId}/insights?days=${days}`),
  getStatus: (teamId) => request(`/risk/teams/${teamId}/status`),
  refreshRisk: (teamId) => request(`/risk/teams/${teamId}/refresh`, { method: 'POST' }),

  // Integrations
  syncJira: (teamId) => request(`/integrations/jira/sync/${teamId}`, { method: 'POST' }),
  verifyJira: () => request('/integrations/jira/verify'),

  // Chat
  chat: (message, teamId, sessionId) =>
    request('/chat/', {
      method: 'POST',
      body: JSON.stringify({ message, team_id: teamId, session_id: sessionId })
    }),
  getChatHistory: (sessionId) => request(`/chat/history/${sessionId}`),

  // Transcripts
  uploadTranscript: (data) => request('/transcripts/upload', { method: 'POST', body: JSON.stringify(data) }),
  listTranscripts: (teamId, days = 30) => request(`/transcripts/?team_id=${teamId}&days=${days}`),
  getTranscript: (id) => request(`/transcripts/${id}`),
  deleteTranscript: (id) => request(`/transcripts/${id}`, { method: 'DELETE' }),
  syncGoogleDrive: (teamId) => request(`/transcripts/sync/${teamId}`, { method: 'POST' }),
  syncAllCompany: (daysBack = 30) => request(`/transcripts/sync/all?days_back=${daysBack}`, { method: 'POST' }),
  getGoogleAuthUrl: (teamId) => request(`/transcripts/google/auth?team_id=${teamId}`),
  getGoogleStatus: () => request('/transcripts/google/status'),

  // Healthcheck
  generateHealthcheck: (teamId) => request(`/healthcheck/teams/${teamId}/generate`, { method: 'POST' }),
  getHealthcheck: (teamId) => request(`/healthcheck/teams/${teamId}/latest`),
  getHealthcheckStatus: (teamId) => request(`/healthcheck/teams/${teamId}/status`),

  // Feed
  getFeed: (teamId, { source = 'all', severity = 'all', issueKey, page = 1, limit = 20 } = {}) => {
    const params = new URLSearchParams({ source, severity, page, limit })
    if (issueKey) params.set('issue_key', issueKey)
    return request(`/feed/teams/${teamId}?${params}`)
  },

  // Agent Pipeline
  getAgentConfig: (teamId) => request(`/agents/teams/${teamId}/config`).catch(() => null),
  upsertAgentConfig: (teamId, data) => request(`/agents/teams/${teamId}/config`, { method: 'PUT', body: JSON.stringify(data) }),
  listAgentPipelines: (teamId, limit = 20) => request(`/agents/teams/${teamId}/pipelines?limit=${limit}`),
  getAgentPipeline: (teamId, pipelineId) => request(`/agents/teams/${teamId}/pipelines/${pipelineId}`),
  triggerAgentPipeline: (teamId, data) => request(`/agents/teams/${teamId}/trigger`, { method: 'POST', body: JSON.stringify(data) }),
  pollAgentBoard: (teamId) => request(`/agents/teams/${teamId}/poll`, { method: 'POST' }),
  deleteAgentPipeline: (teamId, pipelineId) => request(`/agents/teams/${teamId}/pipelines/${pipelineId}`, { method: 'DELETE' }),

  // Streaming chat
  streamChat: async function* (message, teamId, sessionId) {
    const res = await fetch(`${BASE}/chat/stream`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ message, team_id: teamId, session_id: sessionId })
    })
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6)
          if (data === '[DONE]') return
          try {
            const parsed = JSON.parse(data)
            if (parsed.text) yield parsed.text.replace(/\\n/g, '\n')
            if (parsed.session_id) yield { sessionId: parsed.session_id }
          } catch {}
        }
      }
    }
  }
}

export { getToken }
