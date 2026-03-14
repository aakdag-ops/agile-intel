import React, { useState, useEffect, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../lib/api'

// ── Helpers ──────────────────────────────────────────────────────────────────

function timeAgo(iso) {
  const diff = Math.floor((Date.now() - new Date(iso)) / 1000)
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

function formatGroupDate(iso) {
  const d = new Date(iso)
  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(today.getDate() - 1)
  if (d.toDateString() === today.toDateString()) return 'TODAY'
  if (d.toDateString() === yesterday.toDateString()) return 'YESTERDAY'
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }).toUpperCase()
}

const SEVERITY_COLORS = {
  critical: 'var(--risk-critical)',
  high: '#f5a623',
  medium: '#e8c84a',
  low: '#4caf7d',
}

const SOURCE_LABELS = {
  slack: 'SLACK',
  transcript: 'MEETING',
  jira: 'RISK',
}

const STATUS_DOT_COLORS = {
  'Done': '#4caf7d',
  'In Progress': '#f5a623',
  'To Do': '#555',
}

// ── Sub-components ────────────────────────────────────────────────────────────

function IssuePill({ issueKey, issue }) {
  const dotColor = STATUS_DOT_COLORS[issue.status_category] || STATUS_DOT_COLORS['To Do']
  const sp = issue.story_points ? ` [${issue.story_points}sp]` : ''
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      background: 'var(--bg-card)', border: '1px solid var(--border)',
      borderRadius: 4, padding: '3px 8px', marginRight: 6, marginBottom: 4,
      fontFamily: 'var(--font-mono)', fontSize: 10,
    }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: dotColor, flexShrink: 0 }} />
      <span style={{ color: 'var(--amber)', fontWeight: 700 }}>{issueKey}</span>
      <span style={{ color: 'var(--text-muted)' }}>{issue.status}</span>
      {issue.summary && (
        <span style={{ color: 'var(--text-secondary)' }}>· {issue.summary.slice(0, 40)}{issue.summary.length > 40 ? '…' : ''}</span>
      )}
      {sp && <span style={{ color: 'var(--text-muted)' }}>{sp}</span>}
    </span>
  )
}

function FeedCard({ item }) {
  const borderColor = SEVERITY_COLORS[item.severity] || 'var(--border)'
  const sourceLabel = SOURCE_LABELS[item.source] || item.source.toUpperCase()
  const extra = item.extra_data || {}
  const actors = extra.actors || []
  const channel = extra.channel ? `#${extra.channel}` : null
  const rawText = extra.raw_text || ''
  // Merge enriched jira_issues with any issue_key from extra_data (jira-source insights)
  const jiraIssues = { ...(item.jira_issues || {}) }
  if (extra.issue_key && !jiraIssues[extra.issue_key]) {
    jiraIssues[extra.issue_key] = {
      summary: extra.summary || '',
      status: extra.status || '',
      status_category: extra.status_category || 'To Do',
      assignee: extra.assignee || null,
      issue_type: extra.issue_type || null,
      story_points: null,
    }
  }
  const hasIssues = Object.keys(jiraIssues).length > 0

  const contextLabel = item.transcript_title || channel || null

  return (
    <div style={{
      borderLeft: `3px solid ${borderColor}`,
      background: 'var(--bg-card)',
      border: `1px solid var(--border)`,
      borderLeftWidth: 3,
      borderLeftColor: borderColor,
      borderRadius: 'var(--radius)',
      padding: '14px 16px',
      marginBottom: 10,
    }}>
      {/* Header row */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 8,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 9, fontWeight: 700,
            color: 'var(--bg-deep)', background: borderColor,
            borderRadius: 3, padding: '2px 6px', letterSpacing: '0.08em',
          }}>
            {sourceLabel}
          </span>
          {contextLabel && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>
              {contextLabel}
            </span>
          )}
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.06em',
            color: 'var(--text-muted)',
            textTransform: 'uppercase',
          }}>
            {item.insight_type}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>
            {timeAgo(item.captured_at)}
          </span>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 9, fontWeight: 700,
            color: borderColor, border: `1px solid ${borderColor}40`,
            borderRadius: 3, padding: '2px 6px', letterSpacing: '0.08em',
          }}>
            {item.severity.toUpperCase()}
          </span>
        </div>
      </div>

      {/* Content */}
      <p style={{
        fontSize: 13, color: 'var(--text-primary)', lineHeight: 1.6,
        margin: '0 0 10px 0',
      }}>
        {item.content}
      </p>

      {/* Raw quote */}
      {rawText && (
        <p style={{
          fontStyle: 'italic', fontSize: 11, color: 'var(--text-muted)',
          borderLeft: '2px solid var(--border)', paddingLeft: 8,
          margin: '0 0 10px 0',
        }}>
          "{rawText.slice(0, 120)}{rawText.length > 120 ? '…' : ''}"
        </p>
      )}

      {/* Jira issue pills */}
      {hasIssues && (
        <div style={{ display: 'flex', flexWrap: 'wrap', marginBottom: 6 }}>
          {Object.entries(jiraIssues).map(([key, issue]) => (
            <IssuePill key={key} issueKey={key} issue={issue} />
          ))}
        </div>
      )}

      {/* Actors */}
      {actors.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {actors.map((a, i) => (
            <span key={i} style={{
              fontFamily: 'var(--font-mono)', fontSize: 10,
              color: 'var(--text-muted)',
            }}>@{a}</span>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

const SOURCE_FILTERS = ['all', 'slack', 'transcript', 'jira']
const SEVERITY_FILTERS = ['all', 'critical', 'high', 'medium', 'low']

export default function Feed() {
  const { teamId } = useParams()
  const [teamKey, setTeamKey] = useState('')
  const [source, setSource] = useState('all')
  const [severity, setSeverity] = useState('all')
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Load team info for breadcrumb
  useEffect(() => {
    api.getTeam(teamId).then(t => setTeamKey(t.jira_project_key || '')).catch(() => {})
  }, [teamId])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await api.getFeed(teamId, { source, severity, page })
      setData(result)
    } catch (e) {
      setError('Failed to load feed.')
    } finally {
      setLoading(false)
    }
  }, [teamId, source, severity, page])

  useEffect(() => { load() }, [load])

  // Reset to page 1 when filters change
  useEffect(() => { setPage(1) }, [source, severity])

  // Group items by day
  const groups = []
  if (data?.items) {
    for (const item of data.items) {
      const label = formatGroupDate(item.captured_at)
      const last = groups[groups.length - 1]
      if (!last || last.label !== label) {
        groups.push({ label, items: [item] })
      } else {
        last.items.push(item)
      }
    }
  }

  return (
    <div style={{ padding: '32px 40px', maxWidth: 860, margin: '0 auto' }}>
      {/* Breadcrumb */}
      <div style={{
        fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)',
        letterSpacing: '0.1em', marginBottom: 20,
      }}>
        <Link to="/teams" style={{ color: 'var(--text-muted)', textDecoration: 'none' }}>TEAMS</Link>
        {teamKey && <> / <span style={{ color: 'var(--amber)' }}>{teamKey}</span></>}
        {' / FEED'}
      </div>

      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 24,
      }}>
        <h1 style={{
          fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 800,
          letterSpacing: '0.08em', color: 'var(--text-primary)', margin: 0,
        }}>
          TEAM FEED
        </h1>
        {data && (
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)',
          }}>
            {data.total} signals
          </span>
        )}
      </div>

      {/* Filter bar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 24,
        flexWrap: 'wrap',
      }}>
        {/* Source tabs */}
        <div style={{ display: 'flex', gap: 4 }}>
          {SOURCE_FILTERS.map(s => (
            <button
              key={s}
              onClick={() => setSource(s)}
              style={{
                fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.08em',
                padding: '5px 10px', borderRadius: 4,
                border: source === s ? '1px solid var(--amber)' : '1px solid var(--border)',
                background: source === s ? 'var(--amber-glow)' : 'transparent',
                color: source === s ? 'var(--amber)' : 'var(--text-muted)',
                cursor: 'pointer', transition: 'all 0.15s',
              }}
            >
              {s === 'all' ? 'ALL' : s === 'slack' ? 'SLACK' : s === 'transcript' ? 'MEETINGS' : 'RISK'}
            </button>
          ))}
        </div>

        <div style={{ width: 1, height: 20, background: 'var(--border)', margin: '0 4px' }} />

        {/* Severity filter */}
        <div style={{ display: 'flex', gap: 4 }}>
          {SEVERITY_FILTERS.map(sv => {
            const col = SEVERITY_COLORS[sv]
            return (
              <button
                key={sv}
                onClick={() => setSeverity(sv)}
                style={{
                  fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.08em',
                  padding: '5px 10px', borderRadius: 4,
                  border: severity === sv
                    ? `1px solid ${col || 'var(--amber)'}`
                    : '1px solid var(--border)',
                  background: severity === sv ? `${col || '#f5a623'}18` : 'transparent',
                  color: severity === sv ? (col || 'var(--amber)') : 'var(--text-muted)',
                  cursor: 'pointer', transition: 'all 0.15s',
                }}
              >
                {sv.toUpperCase()}
              </button>
            )
          })}
        </div>
      </div>

      {/* Content */}
      {loading && (
        <div style={{
          textAlign: 'center', padding: '60px 0',
          fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)',
        }}>
          Loading feed…
        </div>
      )}

      {error && (
        <div style={{
          background: 'var(--risk-critical)18', border: '1px solid var(--risk-critical)40',
          borderRadius: 'var(--radius)', padding: '12px 16px',
          fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--risk-critical)',
        }}>
          {error}
        </div>
      )}

      {!loading && !error && data?.items?.length === 0 && (
        <div style={{
          textAlign: 'center', padding: '60px 0',
          fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)',
        }}>
          No signals found for the selected filters.
        </div>
      )}

      {!loading && !error && groups.map(group => (
        <div key={group.label}>
          {/* Date group header */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12, marginTop: 8,
          }}>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 9, letterSpacing: '0.14em',
              color: 'var(--text-muted)',
            }}>{group.label}</span>
            <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
          </div>
          {group.items.map(item => <FeedCard key={item.id} item={item} />)}
        </div>
      ))}

      {/* Pagination */}
      {data && data.pages > 1 && (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          gap: 8, marginTop: 24,
        }}>
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page <= 1}
            style={{
              fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.06em',
              padding: '6px 14px', borderRadius: 4,
              border: '1px solid var(--border)', background: 'transparent',
              color: page <= 1 ? 'var(--text-muted)' : 'var(--text-secondary)',
              cursor: page <= 1 ? 'not-allowed' : 'pointer',
            }}
          >
            ← PREV
          </button>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)',
          }}>
            {page} / {data.pages}
          </span>
          <button
            onClick={() => setPage(p => Math.min(data.pages, p + 1))}
            disabled={page >= data.pages}
            style={{
              fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.06em',
              padding: '6px 14px', borderRadius: 4,
              border: '1px solid var(--border)', background: 'transparent',
              color: page >= data.pages ? 'var(--text-muted)' : 'var(--text-secondary)',
              cursor: page >= data.pages ? 'not-allowed' : 'pointer',
            }}
          >
            NEXT →
          </button>
        </div>
      )}
    </div>
  )
}
