import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'

function RiskBar({ score }) {
  const color = score >= 75 ? 'var(--risk-critical)'
    : score >= 50 ? 'var(--risk-high)'
    : score >= 25 ? 'var(--risk-medium)'
    : 'var(--risk-low)'
  const label = score >= 75 ? 'CRITICAL' : score >= 50 ? 'HIGH' : score >= 25 ? 'MEDIUM' : 'LOW'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div style={{
        flex: 1, height: 4, background: 'var(--border)',
        borderRadius: 2, overflow: 'hidden',
      }}>
        <div style={{
          width: `${score}%`, height: '100%',
          background: color, borderRadius: 2,
          transition: 'width 0.8s ease',
          boxShadow: `0 0 8px ${color}`,
        }} />
      </div>
      <span style={{
        fontFamily: 'var(--font-mono)', fontSize: 12,
        color, minWidth: 54,
      }}>{score}/100</span>
      <span style={{
        fontFamily: 'var(--font-mono)', fontSize: 11,
        color, background: `${color}18`,
        border: `1px solid ${color}30`,
        borderRadius: 3, padding: '2px 7px', minWidth: 60, textAlign: 'center',
      }}>{label}</span>
    </div>
  )
}

function SignalDot({ score, label }) {
  const color = score >= 75 ? 'var(--risk-critical)'
    : score >= 50 ? 'var(--risk-high)'
    : score >= 25 ? 'var(--risk-medium)'
    : 'var(--risk-low)'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5 }}>
      <div style={{
        width: 36, height: 36, borderRadius: '50%',
        background: `${color}20`, border: `2px solid ${color}`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontFamily: 'var(--font-mono)', fontSize: 11, color, fontWeight: 600,
      }}>{score}</div>
      <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', textAlign: 'center', lineHeight: 1.2 }}>{label}</span>
    </div>
  )
}

function TeamCard({ team, onSelect }) {
  const [snapshot, setSnapshot] = useState(null)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    api.getSnapshot(team.id)
      .then(setSnapshot)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [team.id])

  const score = snapshot?.composite_score ?? team.latest_risk_score ?? 0

  return (
    <div style={{
      background: 'var(--bg-card)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)', padding: 24,
      cursor: 'pointer', transition: 'all 0.2s',
      animation: 'fadeIn 0.3s ease',
    }}
    onMouseEnter={e => {
      e.currentTarget.style.borderColor = 'var(--border-bright)'
      e.currentTarget.style.background = 'var(--bg-hover)'
    }}
    onMouseLeave={e => {
      e.currentTarget.style.borderColor = 'var(--border)'
      e.currentTarget.style.background = 'var(--bg-card)'
    }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 12,
              color: 'var(--amber)', background: 'var(--amber-glow)',
              border: '1px solid var(--amber-dim)',
              borderRadius: 3, padding: '2px 8px',
            }}>{team.jira_project_key}</span>
            {team.active_sprint_name && (
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: 11,
                color: 'var(--green)', background: 'rgba(16,185,129,0.1)',
                border: '1px solid rgba(16,185,129,0.3)',
                borderRadius: 3, padding: '2px 7px',
              }}>● ACTIVE SPRINT</span>
            )}
          </div>
          <h2 style={{
            fontFamily: 'var(--font-display)', fontSize: 20,
            fontWeight: 700, color: 'var(--text-primary)',
          }}>{team.name}</h2>
          {team.active_sprint_name && (
            <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 3 }}>
              {team.active_sprint_name}
            </p>
          )}
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 34, fontWeight: 700,
            color: score >= 75 ? 'var(--risk-critical)'
              : score >= 50 ? 'var(--risk-high)'
              : score >= 25 ? 'var(--risk-medium)'
              : 'var(--risk-low)',
            lineHeight: 1,
          }}>{score}</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>RISK SCORE</div>
        </div>
      </div>

      {/* Risk bar */}
      <div style={{ marginBottom: 16 }}>
        <RiskBar score={score} />
      </div>

      {/* Signal dots */}
      {snapshot && (
        <div style={{
          display: 'flex', gap: 12, justifyContent: 'space-around',
          padding: '12px 0', borderTop: '1px solid var(--border)',
          borderBottom: '1px solid var(--border)', marginBottom: 16,
        }}>
          <SignalDot score={snapshot.wip_aging_score} label="WIP" />
          <SignalDot score={snapshot.dependency_score} label="DEPS" />
          <SignalDot score={snapshot.velocity_trend_score} label="VEL" />
          <SignalDot score={snapshot.pbi_readiness_score} label="PBI" />
          <SignalDot score={snapshot.slack_blocker_score} label="SLACK" />
          <SignalDot score={snapshot.sentiment_score} label="SENT" />
        </div>
      )}

      {/* Actions */}
      <div style={{ display: 'flex', gap: 8 }}>
        {[
          { label: '◉ DASHBOARD', path: `/dashboard/${team.id}` },
          { label: '◆ CHAT', path: `/chat/${team.id}` },
          { label: '◈ TIMELINE', path: `/timeline/${team.id}` },
        ].map(btn => (
          <button key={btn.path} onClick={() => navigate(btn.path)} style={{
            flex: 1, background: 'var(--bg-deep)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)', padding: '8px 4px',
            color: 'var(--text-secondary)', cursor: 'pointer',
            fontFamily: 'var(--font-mono)', fontSize: 11,
            letterSpacing: '0.05em', transition: 'all 0.15s',
          }}
          onMouseEnter={e => {
            e.currentTarget.style.borderColor = 'var(--amber)'
            e.currentTarget.style.color = 'var(--amber)'
          }}
          onMouseLeave={e => {
            e.currentTarget.style.borderColor = 'var(--border)'
            e.currentTarget.style.color = 'var(--text-secondary)'
          }}
          >{btn.label}</button>
        ))}
      </div>

      {team.last_jira_sync && (
        <div style={{ marginTop: 10, fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
          LAST SYNC: {new Date(team.last_jira_sync).toLocaleString()}
        </div>
      )}
    </div>
  )
}

export default function Teams() {
  const [teams, setTeams] = useState([])
  const [loading, setLoading] = useState(true)
  const [showNew, setShowNew] = useState(false)
  const [newTeam, setNewTeam] = useState({ name: '', jira_project_key: '', description: '' })
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    api.getTeams().then(t => { setTeams(t); setLoading(false) }).catch(() => setLoading(false))
  }, [])

  async function handleSync(teamId) {
    await api.syncJira(teamId)
    setTimeout(() => {
      api.refreshRisk(teamId)
      api.getTeams().then(setTeams)
    }, 8000)
  }

  async function handleCreate(e) {
    e.preventDefault()
    setCreating(true)
    try {
      const team = await api.createTeam(newTeam)
      setTeams(t => [...t, team])
      setShowNew(false)
      setNewTeam({ name: '', jira_project_key: '', description: '' })
    } catch(err) {}
    setCreating(false)
  }

  return (
    <div style={{ padding: '36px 40px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 32 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)', letterSpacing: '0.1em', marginBottom: 6 }}>
            AGILE INTEL ◈ MISSION CONTROL
          </div>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 30, fontWeight: 800, color: 'var(--text-primary)' }}>
            Projects
          </h1>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button onClick={() => teams.forEach(t => handleSync(t.id))} style={{
            background: 'var(--bg-card)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius)', padding: '10px 18px',
            color: 'var(--text-secondary)', cursor: 'pointer',
            fontFamily: 'var(--font-mono)', fontSize: 12, letterSpacing: '0.06em',
          }}>↻ SYNC ALL</button>
          <button onClick={() => setShowNew(!showNew)} style={{
            background: 'var(--amber)', border: 'none',
            borderRadius: 'var(--radius)', padding: '10px 18px',
            color: '#000', cursor: 'pointer',
            fontFamily: 'var(--font-mono)', fontSize: 12,
            fontWeight: 700, letterSpacing: '0.06em',
          }}>+ NEW TEAM</button>
        </div>
      </div>

      {/* New team form */}
      {showNew && (
        <form onSubmit={handleCreate} style={{
          background: 'var(--bg-card)', border: '1px solid var(--amber)',
          borderRadius: 'var(--radius-lg)', padding: 22, marginBottom: 24,
          display: 'flex', gap: 12, alignItems: 'flex-end',
          animation: 'fadeIn 0.2s ease',
        }}>
          {[
            { key: 'name', label: 'TEAM NAME', placeholder: 'Onabu Engineering' },
            { key: 'jira_project_key', label: 'JIRA KEY', placeholder: 'ONB' },
            { key: 'description', label: 'DESCRIPTION', placeholder: 'Optional' },
          ].map(f => (
            <div key={f.key} style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
              <label style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', letterSpacing: '0.1em' }}>{f.label}</label>
              <input
                value={newTeam[f.key]}
                onChange={e => setNewTeam(n => ({ ...n, [f.key]: e.target.value }))}
                placeholder={f.placeholder}
                style={{
                  background: 'var(--bg-input)', border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)', padding: '9px 12px',
                  color: 'var(--text-primary)', fontSize: 14,
                  fontFamily: 'var(--font-body)', outline: 'none',
                }}
              />
            </div>
          ))}
          <button type="submit" disabled={creating} style={{
            background: 'var(--amber)', border: 'none', borderRadius: 'var(--radius)',
            padding: '10px 20px', color: '#000', cursor: 'pointer',
            fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700,
          }}>{creating ? '...' : 'CREATE'}</button>
        </form>
      )}

      {/* Grid */}
      {loading ? (
        <div style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>
          LOADING PROJECTS...
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(420px, 1fr))',
          gap: 20,
        }}>
          {teams.map(team => (
            <TeamCard key={team.id} team={team} />
          ))}
        </div>
      )}
    </div>
  )
}
