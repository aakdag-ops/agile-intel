import React, { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, ReferenceLine } from 'recharts'
import { api } from '../lib/api'

function RiskGauge({ score }) {
  const color = score >= 75 ? 'var(--risk-critical)'
    : score >= 50 ? 'var(--risk-high)'
    : score >= 25 ? 'var(--risk-medium)'
    : 'var(--risk-low)'
  const label = score >= 75 ? 'CRITICAL' : score >= 50 ? 'HIGH' : score >= 25 ? 'MEDIUM' : 'LOW'
  const angle = (score / 100) * 180 - 90

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
      <svg width="190" height="108" viewBox="0 0 190 108">
        {/* Track */}
        <path d="M 22 95 A 73 73 0 0 1 168 95" fill="none" stroke="var(--border)" strokeWidth="9" strokeLinecap="round" />
        {/* Fill */}
        <path d="M 22 95 A 73 73 0 0 1 168 95" fill="none" stroke={color} strokeWidth="9" strokeLinecap="round"
          strokeDasharray={`${(score / 100) * 229} 229`} opacity="0.3" />
        {/* Needle */}
        <g transform={`rotate(${angle}, 95, 95)`}>
          <line x1="95" y1="95" x2="95" y2="30" stroke={color} strokeWidth="2.5" strokeLinecap="round" />
          <circle cx="95" cy="95" r="5" fill={color} />
        </g>
        {/* Score */}
        <text x="95" y="83" textAnchor="middle" fill={color}
          style={{ fontFamily: 'Space Mono, monospace', fontSize: 26, fontWeight: 700 }}>{score}</text>
      </svg>
      <span style={{
        fontFamily: 'var(--font-mono)', fontSize: 12,
        color, background: `${color}18`,
        border: `1px solid ${color}40`,
        borderRadius: 4, padding: '4px 12px', letterSpacing: '0.1em',
      }}>{label} RISK</span>
    </div>
  )
}

function SignalRow({ label, score }) {
  const color = score >= 75 ? 'var(--risk-critical)'
    : score >= 50 ? 'var(--risk-high)'
    : score >= 25 ? 'var(--risk-medium)'
    : 'var(--risk-low)'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '9px 0', borderBottom: '1px solid var(--border)' }}>
      <div style={{ width: 112, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.05em' }}>{label}</div>
      <div style={{ flex: 1, height: 4, background: 'var(--border)', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ width: `${score}%`, height: '100%', background: color, borderRadius: 2, boxShadow: `0 0 6px ${color}` }} />
      </div>
      <div style={{ width: 38, fontFamily: 'var(--font-mono)', fontSize: 13, color, textAlign: 'right', fontWeight: 600 }}>{score}</div>
    </div>
  )
}

function InsightCard({ insight }) {
  const colors = { critical: 'var(--risk-critical)', high: 'var(--risk-high)', medium: 'var(--risk-medium)', low: 'var(--risk-low)' }
  const icons = { blocker: '⛔', risk: '⚠', decision: '◆', sentiment: '◎', dependency: '⇢', scope_change: '⇄' }
  const color = colors[insight.severity] || 'var(--text-muted)'
  return (
    <div style={{
      background: 'var(--bg-deep)', border: `1px solid ${color}30`,
      borderLeft: `3px solid ${color}`,
      borderRadius: 'var(--radius)', padding: '12px 16px',
      animation: 'fadeIn 0.3s ease',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span style={{ fontSize: 13 }}>{icons[insight.insight_type] || '•'}</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color, letterSpacing: '0.06em' }}>
          {insight.source.toUpperCase()} · {insight.insight_type.toUpperCase()}
        </span>
        <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
          {new Date(insight.captured_at).toLocaleDateString()}
        </span>
      </div>
      <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.55 }}>{insight.content}</p>
    </div>
  )
}

export default function Dashboard() {
  const { teamId } = useParams()
  const navigate = useNavigate()
  const [team, setTeam] = useState(null)
  const [snapshot, setSnapshot] = useState(null)
  const [trend, setTrend] = useState(null)
  const [insights, setInsights] = useState([])
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)

  useEffect(() => {
    Promise.all([
      api.getTeam(teamId),
      api.getSnapshot(teamId).catch(() => null),
      api.getTrend(teamId, 14).catch(() => null),
      api.getInsights(teamId, 7).catch(() => []),
    ]).then(([t, s, tr, ins]) => {
      setTeam(t); setSnapshot(s); setTrend(tr); setInsights(ins)
      setLoading(false)
    })
  }, [teamId])

  async function handleSync() {
    setSyncing(true)
    await api.syncJira(teamId)
    setTimeout(async () => {
      await api.refreshRisk(teamId)
      const [s, ins] = await Promise.all([
        api.getSnapshot(teamId).catch(() => null),
        api.getInsights(teamId, 7).catch(() => []),
      ])
      setSnapshot(s); setInsights(ins)
      setSyncing(false)
    }, 8000)
  }

  if (loading) return (
    <div style={{ padding: 40, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>
      LOADING INTEL...
    </div>
  )

  const trendData = trend?.snapshots?.slice().reverse().map((s, i) => ({
    t: new Date(s.snapshot_at).toLocaleDateString('en', { month: 'short', day: 'numeric' }),
    score: s.composite_score,
    wip: s.wip_aging_score,
    pbi: s.pbi_readiness_score,
  })) || []

  const radarData = snapshot ? [
    { signal: 'WIP', score: snapshot.wip_aging_score },
    { signal: 'DEPENDS', score: snapshot.dependency_score },
    { signal: 'VELOCITY', score: snapshot.velocity_trend_score },
    { signal: 'READINESS', score: snapshot.pbi_readiness_score },
    { signal: 'SLACK', score: snapshot.slack_blocker_score },
    { signal: 'SENTIMENT', score: snapshot.sentiment_score },
  ] : []

  return (
    <div style={{ padding: '36px 40px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 32 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)', marginBottom: 6 }}>
            <span style={{ cursor: 'pointer', color: 'var(--amber)' }} onClick={() => navigate('/teams')}>TEAMS</span>
            {' / '}{team?.jira_project_key}
          </div>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 30, fontWeight: 800, letterSpacing: '-0.5px' }}>{team?.name}</h1>
          {team?.active_sprint_name && (
            <div style={{ marginTop: 6, fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--green)' }}>
              ● {team.active_sprint_name}
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button onClick={() => navigate(`/healthcheck/${teamId}`)} style={{
            background: 'var(--bg-card)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius)', padding: '10px 18px',
            color: 'var(--text-secondary)', cursor: 'pointer',
            fontFamily: 'var(--font-mono)', fontSize: 12,
          }}>◈ HEALTHCHECK</button>
          <button onClick={() => navigate(`/transcripts/${teamId}`)} style={{
            background: 'var(--bg-card)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius)', padding: '10px 18px',
            color: 'var(--text-secondary)', cursor: 'pointer',
            fontFamily: 'var(--font-mono)', fontSize: 12,
          }}>◎ TRANSCRIPTS</button>
          <button onClick={() => navigate(`/chat/${teamId}`)} style={{
            background: 'var(--amber)', border: 'none', borderRadius: 'var(--radius)',
            padding: '10px 18px', color: '#000', cursor: 'pointer',
            fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700,
          }}>◆ ASK AI</button>
          <button onClick={handleSync} disabled={syncing} style={{
            background: 'var(--bg-card)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius)', padding: '10px 18px',
            color: syncing ? 'var(--amber)' : 'var(--text-secondary)',
            cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 12,
          }}>{syncing ? '↻ SYNCING...' : '↻ SYNC'}</button>
        </div>
      </div>

      {/* Top row */}
      <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr 1fr', gap: 16, marginBottom: 16 }}>
        {/* Gauge */}
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)', padding: 24,
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        }}>
          <RiskGauge score={snapshot?.composite_score || 0} />
          <div style={{ marginTop: 14, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', textAlign: 'center' }}>
            {trend?.trend_direction === 'worsening' ? '↑ WORSENING' : trend?.trend_direction === 'improving' ? '↓ IMPROVING' : '→ STABLE'}
            {trend?.delta_7d != null && ` (${trend.delta_7d > 0 ? '+' : ''}${trend.delta_7d} 7d)`}
          </div>
        </div>

        {/* Signal bars */}
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)', padding: 24,
        }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.1em', marginBottom: 14 }}>
            SIGNAL BREAKDOWN
          </div>
          {snapshot ? [
            ['WIP AGING', snapshot.wip_aging_score],
            ['DEPENDENCIES', snapshot.dependency_score],
            ['VELOCITY', snapshot.velocity_trend_score],
            ['PBI READINESS', snapshot.pbi_readiness_score],
            ['SLACK SIGNALS', snapshot.slack_blocker_score],
            ['SENTIMENT', snapshot.sentiment_score],
          ].map(([label, score]) => (
            <SignalRow key={label} label={label} score={score} />
          )) : <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>No data yet — run a sync</div>}
        </div>

        {/* Radar */}
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)', padding: 24,
        }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.1em', marginBottom: 10 }}>
            RISK RADAR
          </div>
          <ResponsiveContainer width="100%" height={175}>
            <RadarChart data={radarData}>
              <PolarGrid stroke="var(--border)" />
              <PolarAngleAxis dataKey="signal" tick={{ fill: 'var(--text-muted)', fontSize: 11, fontFamily: 'Space Mono' }} />
              <Radar dataKey="score" stroke="var(--amber)" fill="var(--amber)" fillOpacity={0.2} strokeWidth={1.5} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Trend chart */}
      {trendData.length > 1 && (
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)', padding: 24, marginBottom: 16,
        }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.1em', marginBottom: 14 }}>
            COMPOSITE RISK TREND (14 DAYS)
          </div>
          <ResponsiveContainer width="100%" height={130}>
            <LineChart data={trendData}>
              <XAxis dataKey="t" tick={{ fill: 'var(--text-muted)', fontSize: 11, fontFamily: 'Space Mono' }} axisLine={false} tickLine={false} />
              <YAxis domain={[0, 100]} tick={{ fill: 'var(--text-muted)', fontSize: 11, fontFamily: 'Space Mono' }} axisLine={false} tickLine={false} width={32} />
              <Tooltip contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 6, fontFamily: 'Space Mono', fontSize: 12 }} />
              <ReferenceLine y={50} stroke="var(--risk-high)" strokeDasharray="3 3" opacity={0.4} />
              <ReferenceLine y={75} stroke="var(--risk-critical)" strokeDasharray="3 3" opacity={0.4} />
              <Line dataKey="score" stroke="var(--amber)" strokeWidth={2} dot={false} name="Risk" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Insights */}
      <div style={{
        background: 'var(--bg-card)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)', padding: 24,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.1em' }}>
            RECENT INSIGHTS ({insights.length})
          </div>
          <button onClick={() => navigate(`/timeline/${teamId}`)} style={{
            background: 'none', border: 'none', color: 'var(--amber)',
            cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 11,
          }}>VIEW ALL →</button>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {insights.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontSize: 13, fontFamily: 'var(--font-mono)' }}>NO INSIGHTS YET</div>
          ) : insights.slice(0, 5).map(ins => (
            <InsightCard key={ins.id} insight={ins} />
          ))}
        </div>
      </div>
    </div>
  )
}
