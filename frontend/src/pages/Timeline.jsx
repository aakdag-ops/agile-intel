import React, { useState, useEffect } from 'react'
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
  dependency:   '⇢',
  scope_change: '⇄',
  velocity:     '⟳',
  process:      '⊡',
}
const SOURCE_COLORS = {
  jira:       'var(--blue)',
  slack:      'var(--green)',
  transcript: 'var(--amber)',
  meeting:    'var(--amber)',
}

function InsightItem({ insight }) {
  const color = SEVERITY_COLORS[insight.severity] || 'var(--text-muted)'
  const srcColor = SOURCE_COLORS[insight.source] || 'var(--text-muted)'
  const [expanded, setExpanded] = useState(false)

  return (
    <div style={{ display: 'flex', gap: 16, animation: 'fadeIn 0.3s ease' }}>
      {/* Timeline spine */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 20 }}>
        <div style={{
          width: 10, height: 10, borderRadius: '50%', flexShrink: 0,
          background: color, boxShadow: `0 0 6px ${color}`,
          marginTop: 5,
        }} />
        <div style={{ flex: 1, width: 1, background: 'var(--border)', minHeight: 32 }} />
      </div>

      {/* Card */}
      <div
        onClick={() => setExpanded(!expanded)}
        style={{
          flex: 1, marginBottom: 12,
          background: 'var(--bg-card)', border: `1px solid ${color}20`,
          borderLeft: `3px solid ${color}`,
          borderRadius: 'var(--radius)', padding: '12px 16px',
          cursor: 'pointer', transition: 'all 0.15s',
        }}
        onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-hover)'}
        onMouseLeave={e => e.currentTarget.style.background = 'var(--bg-card)'}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: expanded ? 10 : 0 }}>
          <span style={{ fontSize: 14 }}>{TYPE_ICONS[insight.insight_type] || '•'}</span>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 11,
            color: srcColor, background: `${srcColor}15`,
            border: `1px solid ${srcColor}30`,
            borderRadius: 3, padding: '2px 6px',
          }}>{insight.source.toUpperCase()}</span>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 11,
            color: 'var(--text-muted)',
          }}>{insight.insight_type.toUpperCase()}</span>
          <span style={{
            marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 11,
            color: 'var(--text-muted)',
          }}>{new Date(insight.captured_at).toLocaleString()}</span>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 11,
            color, background: `${color}15`,
            border: `1px solid ${color}30`,
            borderRadius: 3, padding: '2px 6px',
          }}>{insight.severity?.toUpperCase()}</span>
        </div>

        <p style={{
          fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6,
          display: expanded ? 'block' : '-webkit-box',
          WebkitLineClamp: expanded ? 'unset' : 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
        }}>{insight.content}</p>

        {insight.extra_data && expanded && (
          <div style={{
            marginTop: 10, padding: 10,
            background: 'var(--bg-deep)', borderRadius: 'var(--radius-sm)',
            fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)',
            whiteSpace: 'pre-wrap',
          }}>
            {JSON.stringify(insight.extra_data, null, 2)}
          </div>
        )}
      </div>
    </div>
  )
}

function DateGroup({ date, insights }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <div style={{
        fontFamily: 'var(--font-mono)', fontSize: 12,
        color: 'var(--text-muted)', letterSpacing: '0.1em',
        marginBottom: 12, marginLeft: 36,
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <div style={{ width: 40, height: 1, background: 'var(--border)' }} />
        {date}
        <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
      </div>
      {insights.map((ins, i) => (
        <InsightItem key={ins.id} insight={ins} isFirst={i === 0} />
      ))}
    </div>
  )
}

export default function Timeline() {
  const { teamId } = useParams()
  const navigate = useNavigate()
  const [team, setTeam] = useState(null)
  const [insights, setInsights] = useState([])
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState(30)
  const [filterSource, setFilterSource] = useState('all')
  const [filterSeverity, setFilterSeverity] = useState('all')

  useEffect(() => {
    Promise.all([
      api.getTeam(teamId),
      api.getInsights(teamId, days).catch(() => []),
    ]).then(([t, ins]) => {
      setTeam(t)
      setInsights(ins)
      setLoading(false)
    })
  }, [teamId, days])

  const filtered = insights.filter(ins => {
    if (filterSource !== 'all' && ins.source !== filterSource) return false
    if (filterSeverity !== 'all' && ins.severity !== filterSeverity) return false
    return true
  })

  const grouped = {}
  for (const ins of filtered) {
    const d = new Date(ins.captured_at).toLocaleDateString('en', { weekday: 'short', month: 'short', day: 'numeric' })
    if (!grouped[d]) grouped[d] = []
    grouped[d].push(ins)
  }

  const filterBtn = (active, color, label, onClick) => (
    <button onClick={onClick} style={{
      background: active ? (color ? `${color}15` : 'var(--bg-hover)') : 'var(--bg-card)',
      border: `1px solid ${active ? (color || 'var(--border-bright)') : 'var(--border)'}`,
      borderRadius: 'var(--radius)', padding: '6px 13px',
      color: active ? (color || 'var(--text-primary)') : 'var(--text-muted)',
      cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 12,
    }}>{label}</button>
  )

  return (
    <div style={{ padding: '36px 40px', maxWidth: 860 }}>
      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)', marginBottom: 6 }}>
          <span style={{ cursor: 'pointer', color: 'var(--amber)' }} onClick={() => navigate('/teams')}>TEAMS</span>
          {' / '}
          <span style={{ cursor: 'pointer', color: 'var(--amber)' }} onClick={() => navigate(`/dashboard/${teamId}`)}>{team?.jira_project_key}</span>
          {' / TIMELINE'}
        </div>
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 800 }}>Insight Timeline</h1>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 5 }}>
          {filtered.length} insights · {days} days
        </p>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 28, flexWrap: 'wrap', alignItems: 'center' }}>
        {[7, 14, 30, 60].map(d => filterBtn(days === d, null, `${d}D`, () => setDays(d)))}
        <div style={{ width: 1, height: 20, background: 'var(--border)', margin: '0 4px' }} />
        {['all', 'jira', 'slack', 'transcript'].map(s => filterBtn(filterSource === s, null, s.toUpperCase(), () => setFilterSource(s)))}
        <div style={{ width: 1, height: 20, background: 'var(--border)', margin: '0 4px' }} />
        {['all', 'critical', 'high', 'medium', 'low'].map(s =>
          filterBtn(filterSeverity === s, SEVERITY_COLORS[s], s.toUpperCase(), () => setFilterSeverity(s))
        )}
      </div>

      {loading ? (
        <div style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>LOADING...</div>
      ) : Object.keys(grouped).length === 0 ? (
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)', padding: 48, textAlign: 'center',
        }}>
          <div style={{ fontSize: 32, marginBottom: 14 }}>◈</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-muted)' }}>
            NO INSIGHTS YET
          </div>
          <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 8 }}>
            Run a risk refresh to generate insights from your Jira data.
          </p>
          <button onClick={() => api.refreshRisk(teamId)} style={{
            marginTop: 18, background: 'var(--amber)', border: 'none',
            borderRadius: 'var(--radius)', padding: '9px 22px',
            color: '#000', cursor: 'pointer',
            fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700,
          }}>↻ REFRESH RISK</button>
        </div>
      ) : (
        Object.entries(grouped).map(([date, ins]) => (
          <DateGroup key={date} date={date} insights={ins} />
        ))
      )}
    </div>
  )
}
