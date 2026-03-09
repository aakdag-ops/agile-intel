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
  blocker:    '⛔',
  risk:       '⚠',
  decision:   '◆',
  sentiment:  '◎',
  dependency: '⇢',
  velocity:   '⟳',
  process:    '⊡',
}
const SOURCE_COLORS = {
  jira:     'var(--blue)',
  slack:    'var(--green)',
  meeting:  'var(--amber)',
}

function InsightItem({ insight, isFirst }) {
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
          marginTop: 4,
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
          borderRadius: 'var(--radius)', padding: '10px 14px',
          cursor: 'pointer', transition: 'all 0.15s',
        }}
        onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-hover)'}
        onMouseLeave={e => e.currentTarget.style.background = 'var(--bg-card)'}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: expanded ? 8 : 0 }}>
          <span style={{ fontSize: 13 }}>{TYPE_ICONS[insight.insight_type] || '•'}</span>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 9,
            color: srcColor, background: `${srcColor}15`,
            border: `1px solid ${srcColor}30`,
            borderRadius: 3, padding: '1px 5px',
          }}>{insight.source.toUpperCase()}</span>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 9,
            color: 'var(--text-muted)',
          }}>{insight.insight_type.toUpperCase()}</span>
          <span style={{
            marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 9,
            color: 'var(--text-muted)',
          }}>{new Date(insight.captured_at).toLocaleString()}</span>
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 9,
            color, background: `${color}15`,
            border: `1px solid ${color}30`,
            borderRadius: 3, padding: '1px 5px',
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
            marginTop: 8, padding: 8,
            background: 'var(--bg-deep)', borderRadius: 'var(--radius-sm)',
            fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)',
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
        fontFamily: 'var(--font-mono)', fontSize: 10,
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

  // Group by date
  const grouped = {}
  for (const ins of filtered) {
    const d = new Date(ins.captured_at).toLocaleDateString('en', { weekday: 'short', month: 'short', day: 'numeric' })
    if (!grouped[d]) grouped[d] = []
    grouped[d].push(ins)
  }

  return (
    <div style={{ padding: 32, maxWidth: 800 }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>
          <span style={{ cursor: 'pointer', color: 'var(--amber)' }} onClick={() => navigate('/teams')}>TEAMS</span>
          {' / '}
          <span style={{ cursor: 'pointer', color: 'var(--amber)' }} onClick={() => navigate(`/dashboard/${teamId}`)}>{team?.jira_project_key}</span>
          {' / TIMELINE'}
        </div>
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 26, fontWeight: 800 }}>Insight Timeline</h1>
        <p style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4 }}>
          {filtered.length} insights · {days} days
        </p>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 28, flexWrap: 'wrap' }}>
        {/* Days */}
        {[7, 14, 30, 60].map(d => (
          <button key={d} onClick={() => setDays(d)} style={{
            background: days === d ? 'var(--amber)' : 'var(--bg-card)',
            border: `1px solid ${days === d ? 'var(--amber)' : 'var(--border)'}`,
            borderRadius: 'var(--radius)', padding: '5px 12px',
            color: days === d ? '#000' : 'var(--text-muted)',
            cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 10,
          }}>{d}D</button>
        ))}
        <div style={{ width: 1, background: 'var(--border)' }} />
        {/* Source */}
        {['all', 'jira', 'slack', 'meeting'].map(s => (
          <button key={s} onClick={() => setFilterSource(s)} style={{
            background: filterSource === s ? 'var(--bg-hover)' : 'var(--bg-card)',
            border: `1px solid ${filterSource === s ? 'var(--border-bright)' : 'var(--border)'}`,
            borderRadius: 'var(--radius)', padding: '5px 12px',
            color: filterSource === s ? 'var(--text-primary)' : 'var(--text-muted)',
            cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 10,
          }}>{s.toUpperCase()}</button>
        ))}
        <div style={{ width: 1, background: 'var(--border)' }} />
        {/* Severity */}
        {['all', 'critical', 'high', 'medium', 'low'].map(s => {
          const c = SEVERITY_COLORS[s] || 'var(--text-muted)'
          return (
            <button key={s} onClick={() => setFilterSeverity(s)} style={{
              background: filterSeverity === s ? `${c}15` : 'var(--bg-card)',
              border: `1px solid ${filterSeverity === s ? c : 'var(--border)'}`,
              borderRadius: 'var(--radius)', padding: '5px 12px',
              color: filterSeverity === s ? c : 'var(--text-muted)',
              cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 10,
            }}>{s.toUpperCase()}</button>
          )
        })}
      </div>

      {loading ? (
        <div style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>LOADING...</div>
      ) : Object.keys(grouped).length === 0 ? (
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)', padding: 40, textAlign: 'center',
        }}>
          <div style={{ fontSize: 28, marginBottom: 12 }}>◈</div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>
            NO INSIGHTS YET
          </div>
          <p style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 8 }}>
            Run a risk refresh to generate insights from your Jira data.
          </p>
          <button onClick={() => api.refreshRisk(teamId)} style={{
            marginTop: 16, background: 'var(--amber)', border: 'none',
            borderRadius: 'var(--radius)', padding: '8px 20px',
            color: '#000', cursor: 'pointer',
            fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700,
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
