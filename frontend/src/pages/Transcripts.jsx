import React, { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'

const SEVERITY_COLORS = {
  critical: 'var(--risk-critical)',
  high:     'var(--risk-high)',
  medium:   'var(--risk-medium)',
  low:      'var(--risk-low)',
}
const TYPE_ICONS = {
  blocker:      '⛔',
  risk:         '⚠',
  decision:     '◆',
  sentiment:    '◎',
  scope_change: '⟳',
}

function InsightCard({ insight }) {
  const color = SEVERITY_COLORS[insight.severity] || 'var(--text-muted)'
  return (
    <div style={{
      background: 'var(--bg-deep)', border: `1px solid ${color}25`,
      borderLeft: `3px solid ${color}`,
      borderRadius: 'var(--radius)', padding: '8px 12px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <span style={{ fontSize: 11 }}>{TYPE_ICONS[insight.insight_type] || '•'}</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color, letterSpacing: '0.06em' }}>
          {insight.insight_type.toUpperCase()} · {insight.severity.toUpperCase()}
        </span>
      </div>
      <p style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5, margin: 0 }}>{insight.content}</p>
      {insight.jira_refs?.length > 0 && (
        <div style={{ marginTop: 6, fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--blue)' }}>
          {insight.jira_refs.join(' · ')}
        </div>
      )}
    </div>
  )
}

function TranscriptRow({ transcript, onDelete }) {
  const [expanded, setExpanded] = useState(false)
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(false)

  async function toggle() {
    if (!expanded && !detail) {
      setLoading(true)
      try {
        const d = await api.getTranscript(transcript.id)
        setDetail(d)
      } catch {}
      setLoading(false)
    }
    setExpanded(!expanded)
  }

  const date = transcript.meeting_date
    ? new Date(transcript.meeting_date).toLocaleDateString('en', { month: 'short', day: 'numeric', year: 'numeric' })
    : new Date(transcript.created_at).toLocaleDateString('en', { month: 'short', day: 'numeric', year: 'numeric' })

  return (
    <div style={{
      background: 'var(--bg-card)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius)', overflow: 'hidden',
    }}>
      <div
        onClick={toggle}
        style={{
          display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px',
          cursor: 'pointer',
        }}
        onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-hover)'}
        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
      >
        <span style={{ fontSize: 16 }}>◎</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-primary)', marginBottom: 2 }}>
            {transcript.title}
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)' }}>
            {date}
            {transcript.source === 'google_drive' && ' · GOOGLE DRIVE'}
            {transcript.participants?.length > 0 && ` · ${transcript.participants.length} PARTICIPANTS`}
          </div>
        </div>
        {transcript.insight_count > 0 && (
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 9,
            color: 'var(--amber)', background: 'var(--amber)18',
            border: '1px solid var(--amber)30',
            borderRadius: 4, padding: '2px 8px',
          }}>
            {transcript.insight_count} INSIGHTS
          </span>
        )}
        {transcript.processed_at ? (
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--green)',
          }}>✓ PROCESSED</span>
        ) : (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)' }}>PENDING</span>
        )}
        <button
          onClick={e => { e.stopPropagation(); onDelete(transcript.id) }}
          style={{
            background: 'none', border: 'none', color: 'var(--risk-critical)',
            cursor: 'pointer', fontSize: 12, padding: '2px 6px', opacity: 0.6,
          }}
          title="Delete"
        >✕</button>
        <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>{expanded ? '▲' : '▼'}</span>
      </div>

      {expanded && (
        <div style={{ borderTop: '1px solid var(--border)', padding: '12px 16px' }}>
          {loading ? (
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>LOADING...</div>
          ) : detail ? (
            <>
              {detail.insights?.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)', marginBottom: 4 }}>
                    EXTRACTED INSIGHTS
                  </div>
                  {detail.insights.map(ins => (
                    <InsightCard key={ins.id} insight={ins} />
                  ))}
                </div>
              ) : (
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
                  {detail.processed_at ? 'NO INSIGHTS EXTRACTED' : 'NOT YET PROCESSED'}
                </div>
              )}
            </>
          ) : null}
        </div>
      )}
    </div>
  )
}

function UploadTab({ teamId, onUploaded }) {
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [meetingDate, setMeetingDate] = useState('')
  const [participants, setParticipants] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!title.trim() || !text.trim()) return
    setSubmitting(true)
    setError(null)
    setSuccess(false)
    try {
      await api.uploadTranscript({
        team_id: teamId,
        title: title.trim(),
        raw_text: text.trim(),
        meeting_date: meetingDate || null,
        participants: participants ? participants.split(',').map(p => p.trim()).filter(Boolean) : [],
        source: 'manual',
      })
      setSuccess(true)
      setTitle(''); setText(''); setMeetingDate(''); setParticipants('')
      onUploaded()
    } catch (err) {
      setError(err.message)
    }
    setSubmitting(false)
  }

  const inputStyle = {
    width: '100%', background: 'var(--bg-deep)', border: '1px solid var(--border)',
    borderRadius: 'var(--radius)', padding: '9px 12px', color: 'var(--text-primary)',
    fontFamily: 'var(--font-mono)', fontSize: 12, outline: 'none', boxSizing: 'border-box',
  }

  return (
    <form onSubmit={handleSubmit} style={{ maxWidth: 680 }}>
      <div style={{ marginBottom: 14 }}>
        <label style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>
          MEETING TITLE *
        </label>
        <input
          value={title}
          onChange={e => setTitle(e.target.value)}
          placeholder="Sprint 23 Planning · Q2 Kickoff · Daily Standup..."
          style={inputStyle}
          required
        />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 14 }}>
        <div>
          <label style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>
            MEETING DATE
          </label>
          <input
            type="date"
            value={meetingDate}
            onChange={e => setMeetingDate(e.target.value)}
            style={inputStyle}
          />
        </div>
        <div>
          <label style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>
            PARTICIPANTS (COMMA-SEPARATED)
          </label>
          <input
            value={participants}
            onChange={e => setParticipants(e.target.value)}
            placeholder="Alice, Bob, Carol..."
            style={inputStyle}
          />
        </div>
      </div>

      <div style={{ marginBottom: 18 }}>
        <label style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>
          TRANSCRIPT TEXT *
        </label>
        <textarea
          value={text}
          onChange={e => setText(e.target.value)}
          placeholder="Paste the full meeting transcript here..."
          rows={14}
          style={{ ...inputStyle, resize: 'vertical', lineHeight: 1.6 }}
          required
        />
      </div>

      {error && (
        <div style={{
          marginBottom: 12, padding: '8px 12px', background: 'var(--risk-critical)18',
          border: '1px solid var(--risk-critical)40', borderRadius: 'var(--radius)',
          fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--risk-critical)',
        }}>
          ERROR: {error}
        </div>
      )}

      {success && (
        <div style={{
          marginBottom: 12, padding: '8px 12px', background: 'var(--green)18',
          border: '1px solid var(--green)40', borderRadius: 'var(--radius)',
          fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--green)',
        }}>
          ✓ TRANSCRIPT UPLOADED AND PROCESSING STARTED
        </div>
      )}

      <button
        type="submit"
        disabled={submitting || !title.trim() || !text.trim()}
        style={{
          background: submitting ? 'var(--bg-card)' : 'var(--amber)',
          border: 'none', borderRadius: 'var(--radius)',
          padding: '10px 20px', color: submitting ? 'var(--text-muted)' : '#000',
          fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700,
          cursor: submitting ? 'not-allowed' : 'pointer',
        }}
      >
        {submitting ? '◌ PROCESSING...' : '↑ UPLOAD & EXTRACT INSIGHTS'}
      </button>
    </form>
  )
}

function HistoryTab({ teamId }) {
  const [transcripts, setTranscripts] = useState([])
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState(30)

  async function load() {
    setLoading(true)
    try {
      const data = await api.listTranscripts(teamId, days)
      setTranscripts(data)
    } catch {}
    setLoading(false)
  }

  useEffect(() => { load() }, [teamId, days])

  async function handleDelete(id) {
    try {
      await api.deleteTranscript(id)
      setTranscripts(prev => prev.filter(t => t.id !== id))
    } catch {}
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)' }}>
          SHOW LAST
        </div>
        {[7, 14, 30, 90].map(d => (
          <button
            key={d}
            onClick={() => setDays(d)}
            style={{
              background: days === d ? 'var(--amber)' : 'var(--bg-card)',
              border: `1px solid ${days === d ? 'var(--amber)' : 'var(--border)'}`,
              borderRadius: 4, padding: '3px 10px',
              color: days === d ? '#000' : 'var(--text-muted)',
              fontFamily: 'var(--font-mono)', fontSize: 9, cursor: 'pointer',
            }}
          >{d}D</button>
        ))}
      </div>

      {loading ? (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>LOADING...</div>
      ) : transcripts.length === 0 ? (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)', padding: '32px 0' }}>
          NO TRANSCRIPTS YET — UPLOAD ONE OR CONNECT GOOGLE DRIVE
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {transcripts.map(t => (
            <TranscriptRow key={t.id} transcript={t} onDelete={handleDelete} />
          ))}
        </div>
      )}
    </div>
  )
}

function GoogleDriveTab({ teamId }) {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [syncingAll, setSyncingAll] = useState(false)
  const [syncResult, setSyncResult] = useState(null)
  const [daysBack, setDaysBack] = useState(30)

  useEffect(() => {
    api.getGoogleStatus()
      .then(setStatus)
      .catch(() => setStatus({ connected: false }))
      .finally(() => setLoading(false))
  }, [])

  async function handleConnect() {
    try {
      const { auth_url } = await api.getGoogleAuthUrl(teamId)
      window.location.href = auth_url
    } catch (err) {
      alert('Failed to get Google auth URL')
    }
  }

  async function handleSync() {
    setSyncing(true)
    setSyncResult(null)
    try {
      const result = await api.syncGoogleDrive(teamId)
      setSyncResult(result)
    } catch (err) {
      setSyncResult({ error: err.message })
    }
    setSyncing(false)
  }

  async function handleSyncAll() {
    setSyncingAll(true)
    setSyncResult(null)
    try {
      const result = await api.syncAllCompany(daysBack)
      setSyncResult({ ...result, isCompanyWide: true })
    } catch (err) {
      setSyncResult({ error: err.message })
    }
    setSyncingAll(false)
  }

  if (loading) return (
    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>LOADING...</div>
  )

  return (
    <div style={{ maxWidth: 520 }}>
      {/* Connection status */}
      <div style={{
        background: 'var(--bg-card)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)', padding: 20, marginBottom: 16,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 8, height: 8, borderRadius: '50%',
            background: status?.connected ? 'var(--green)' : 'var(--text-muted)',
            boxShadow: status?.connected ? '0 0 6px var(--green)' : 'none',
          }} />
          <div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-primary)' }}>
              GOOGLE DRIVE
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)', marginTop: 2 }}>
              {status?.connected ? `CONNECTED · ${status.email || ''}` : 'NOT CONNECTED'}
            </div>
          </div>
          {!status?.connected && (
            <button
              onClick={handleConnect}
              style={{
                marginLeft: 'auto', background: 'var(--amber)', border: 'none',
                borderRadius: 'var(--radius)', padding: '8px 16px',
                color: '#000', cursor: 'pointer',
                fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700,
              }}
            >
              ↗ CONNECT
            </button>
          )}
        </div>
      </div>

      {status?.connected && (
        <>
          {/* Sync info */}
          <div style={{
            background: 'var(--bg-card)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius-lg)', padding: 16, marginBottom: 16,
          }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)', marginBottom: 8 }}>
              SYNC STATUS
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)' }}>
              Auto-syncs every 60 minutes — scans Google Drive for documents with "transcript" or "Meet" in the name.
            </div>
            {status.last_sync && (
              <div style={{ marginTop: 8, fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)' }}>
                LAST SYNC: {new Date(status.last_sync).toLocaleString()}
              </div>
            )}
          </div>

          {/* Company-wide sync */}
          <div style={{
            background: 'var(--bg-card)', border: '1px solid var(--amber)30',
            borderRadius: 'var(--radius-lg)', padding: 16, marginBottom: 12,
          }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--amber)', marginBottom: 10 }}>
              ◈ COMPANY-WIDE SYNC (ADMIN)
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-secondary)', marginBottom: 12, lineHeight: 1.7 }}>
              Scans all drives (personal + shared) and auto-assigns transcripts to teams by Jira key.
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)' }}>LAST</div>
              {[7, 14, 30, 60, 90].map(d => (
                <button key={d} onClick={() => setDaysBack(d)} style={{
                  background: daysBack === d ? 'var(--amber)' : 'var(--bg-deep)',
                  border: `1px solid ${daysBack === d ? 'var(--amber)' : 'var(--border)'}`,
                  borderRadius: 4, padding: '3px 10px',
                  color: daysBack === d ? '#000' : 'var(--text-muted)',
                  fontFamily: 'var(--font-mono)', fontSize: 9, cursor: 'pointer',
                }}>{d}D</button>
              ))}
              <button
                onClick={handleSyncAll}
                disabled={syncingAll}
                style={{
                  marginLeft: 'auto',
                  background: syncingAll ? 'var(--bg-deep)' : 'var(--amber)',
                  border: 'none', borderRadius: 'var(--radius)', padding: '8px 16px',
                  color: syncingAll ? 'var(--amber)' : '#000',
                  fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700,
                  cursor: syncingAll ? 'not-allowed' : 'pointer',
                }}
              >
                {syncingAll ? '↻ SCANNING...' : '↻ SYNC ALL COMPANY'}
              </button>
            </div>
          </div>

          {/* Team-specific sync */}
          <button
            onClick={handleSync}
            disabled={syncing}
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius)', padding: '10px 20px',
              color: syncing ? 'var(--amber)' : 'var(--text-secondary)',
              fontFamily: 'var(--font-mono)', fontSize: 10,
              cursor: syncing ? 'not-allowed' : 'pointer',
            }}
          >
            {syncing ? '↻ SYNCING...' : '↻ SYNC THIS TEAM ONLY'}
          </button>

          {syncResult && (
            <div style={{
              marginTop: 12, padding: '10px 14px',
              background: syncResult.error ? 'var(--risk-critical)18' : 'var(--green)18',
              border: `1px solid ${syncResult.error ? 'var(--risk-critical)' : 'var(--green)'}40`,
              borderRadius: 'var(--radius)',
              fontFamily: 'var(--font-mono)', fontSize: 11,
              color: syncResult.error ? 'var(--risk-critical)' : 'var(--green)',
            }}>
              {syncResult.error
                ? `ERROR: ${syncResult.error}`
                : `✓ ${syncResult.message || 'SYNC STARTED IN BACKGROUND'}`}
            </div>
          )}
        </>
      )}

      {/* Info box */}
      <div style={{
        marginTop: 20, padding: '12px 16px',
        background: 'var(--bg-deep)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
      }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--amber)', marginBottom: 8 }}>
          HOW IT WORKS
        </div>
        <ul style={{ margin: 0, padding: '0 0 0 16px', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)', lineHeight: 2 }}>
          <li>Scans your Google Drive for documents with "transcript" or "Meet" in the name</li>
          <li>Exports each doc as plain text and runs AI extraction</li>
          <li>Creates Insights for blockers, decisions, action items, risks, and scope changes</li>
          <li>Deduplicates — same document is never processed twice</li>
        </ul>
      </div>
    </div>
  )
}

export default function Transcripts() {
  const { teamId } = useParams()
  const navigate = useNavigate()
  const [team, setTeam] = useState(null)
  const [tab, setTab] = useState('upload')
  const [historyKey, setHistoryKey] = useState(0)

  useEffect(() => {
    api.getTeam(teamId).then(setTeam).catch(() => {})
  }, [teamId])

  // Check for Google OAuth callback
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get('google_connected')) {
      setTab('drive')
      window.history.replaceState({}, '', window.location.pathname)
    }
  }, [])

  function handleUploaded() {
    setHistoryKey(k => k + 1)
    setTimeout(() => setTab('history'), 1200)
  }

  const tabs = [
    { id: 'upload', label: '↑ UPLOAD' },
    { id: 'history', label: '◈ HISTORY' },
    { id: 'drive', label: '◎ GOOGLE DRIVE' },
  ]

  return (
    <div style={{ padding: 32 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 24 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>
            <span style={{ cursor: 'pointer', color: 'var(--amber)' }} onClick={() => navigate('/teams')}>TEAMS</span>
            {' / '}
            <span style={{ cursor: 'pointer', color: 'var(--amber)' }} onClick={() => navigate(`/dashboard/${teamId}`)}>
              {team?.jira_project_key || teamId.slice(0, 8)}
            </span>
            {' / TRANSCRIPTS'}
          </div>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 26, fontWeight: 800 }}>
            Meeting Transcripts
          </h1>
          <div style={{ marginTop: 4, fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>
            Upload or auto-fetch meeting transcripts to extract insights
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 24, borderBottom: '1px solid var(--border)', paddingBottom: 0 }}>
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            style={{
              background: 'none', border: 'none',
              borderBottom: tab === t.id ? '2px solid var(--amber)' : '2px solid transparent',
              padding: '8px 16px', marginBottom: -1,
              color: tab === t.id ? 'var(--amber)' : 'var(--text-muted)',
              fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: tab === t.id ? 700 : 400,
              cursor: 'pointer', transition: 'color 0.15s',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === 'upload' && <UploadTab teamId={teamId} onUploaded={handleUploaded} />}
      {tab === 'history' && <HistoryTab key={historyKey} teamId={teamId} />}
      {tab === 'drive' && <GoogleDriveTab teamId={teamId} />}
    </div>
  )
}
