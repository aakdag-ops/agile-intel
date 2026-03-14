import React, { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'

// ── Constants ─────────────────────────────────────────────────────────────────

const CRITERIA_META = [
  { key: 'title_clarity',           label: 'Title Clarity',          sub: 'Specific, non-generic title' },
  { key: 'description_quality',     label: 'Description Quality',    sub: 'Scope and context present' },
  { key: 'acceptance_criteria',     label: 'Acceptance Criteria',    sub: 'Clear, testable AC' },
  { key: 'estimation',              label: 'Estimation',             sub: 'Story points assigned' },
  { key: 'dependencies',            label: 'Dependencies',           sub: 'Blockers identified' },
  { key: 'customer_focus',          label: 'Customer Focus',         sub: 'User value stated' },
  { key: 'data_drivenness',         label: 'Data-Driven',            sub: 'Evidence backing need' },
  { key: 'vertical_slicing',        label: 'Vertical Slicing',       sub: 'End-to-end deliverable' },
  { key: 'product_goal_alignment',  label: 'Product Goal',           sub: 'Connected to epic/roadmap' },
  { key: 'okr_alignment',           label: 'OKR Alignment',          sub: 'Traceable to OKR' },
  { key: 'risk_profile',            label: 'Risk Profile',           sub: 'Risks/unknowns mentioned' },
]

const GROUPS = [
  { key: 'completed_last_month', label: 'COMPLETED LAST MONTH' },
  { key: 'planned_this_month',   label: 'PLANNED THIS MONTH' },
  { key: 'next_month',           label: 'NEXT MONTH WORK LIST' },
]

// ── Lead time color ────────────────────────────────────────────────────────────

function leadColor(days) {
  if (days == null) return 'var(--text-muted)'
  if (days < 20) return 'var(--risk-low)'
  if (days <= 40) return 'var(--risk-high)'
  return 'var(--risk-critical)'
}

// ── Lead Time Card ─────────────────────────────────────────────────────────────

function LeadCard({ label, days }) {
  const color = leadColor(days)
  return (
    <div style={{
      background: 'var(--bg-card)', border: '1px solid var(--border)',
      borderTop: `3px solid ${color}`,
      borderRadius: 'var(--radius-lg)', padding: '20px 24px',
      flex: 1,
    }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)', letterSpacing: '0.12em', marginBottom: 12 }}>
        {label}
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 32, fontWeight: 700, color }}>
        {days != null ? `${days}d` : '—'}
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)', marginTop: 6 }}>
        {days == null ? 'NO DATA'
          : days < 20 ? '▼ HEALTHY'
          : days <= 40 ? '▲ MODERATE'
          : '▲ CRITICAL'}
      </div>
    </div>
  )
}

// ── Stacked Bar ────────────────────────────────────────────────────────────────

function StackedBar({ good = 0, medium = 0, critical = 0 }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div style={{ display: 'flex', height: 10, borderRadius: 3, overflow: 'hidden', background: 'var(--bg-deep)' }}>
        {good > 0 && <div style={{ width: `${good}%`, background: 'var(--risk-low)', opacity: 0.85 }} />}
        {medium > 0 && <div style={{ width: `${medium}%`, background: 'var(--risk-high)', opacity: 0.85 }} />}
        {critical > 0 && <div style={{ width: `${critical}%`, background: 'var(--risk-critical)', opacity: 0.85 }} />}
      </div>
      <div style={{ display: 'flex', gap: 6, fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)' }}>
        {good > 0 && <span style={{ color: 'var(--risk-low)' }}>{good.toFixed(0)}%</span>}
        {medium > 0 && <span style={{ color: 'var(--risk-high)' }}>{medium.toFixed(0)}%</span>}
        {critical > 0 && <span style={{ color: 'var(--risk-critical)' }}>{critical.toFixed(0)}%</span>}
      </div>
    </div>
  )
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function Healthcheck() {
  const { teamId } = useParams()
  const navigate = useNavigate()
  const [team, setTeam] = useState(null)
  const [report, setReport] = useState(null)
  const [statusInfo, setStatusInfo] = useState(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const pollRef = useRef(null)

  // Load team + try to fetch latest report
  useEffect(() => {
    Promise.all([
      api.getTeam(teamId),
      api.getHealthcheckStatus(teamId).catch(() => null),
      api.getHealthcheck(teamId).catch(() => null),
    ]).then(([t, status, rpt]) => {
      setTeam(t)
      setStatusInfo(status)
      setReport(rpt)
      setLoading(false)

      // If a job is already running, start polling
      if (status && (status.status === 'pending' || status.status === 'running')) {
        startPolling()
      }
    })
    return () => stopPolling()
  }, [teamId])

  function startPolling() {
    stopPolling()
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.getHealthcheckStatus(teamId)
        setStatusInfo(s)
        if (s.status === 'complete' || s.status === 'failed') {
          stopPolling()
          setGenerating(false)
          if (s.status === 'complete') {
            const rpt = await api.getHealthcheck(teamId)
            setReport(rpt)
          }
        }
      } catch {}
    }, 5000)
  }

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  async function handleGenerate() {
    setGenerating(true)
    setReport(null)
    try {
      const res = await api.generateHealthcheck(teamId)
      setStatusInfo(res)
      startPolling()
    } catch (e) {
      setGenerating(false)
    }
  }

  if (loading) return (
    <div style={{ padding: 40, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>
      LOADING...
    </div>
  )

  const isRunning = statusInfo && (statusInfo.status === 'pending' || statusInfo.status === 'running')
  const lt = report?.lead_times || {}
  const columnStats = report?.column_stats || {}
  const aiInsights = report?.ai_insights || {}
  const topIssues = report?.top_issues || []
  const concreteActions = report?.concrete_actions || []

  return (
    <div style={{ padding: '36px 40px' }}>

      {/* ── Header ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 28 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)', marginBottom: 6 }}>
            <span style={{ cursor: 'pointer', color: 'var(--amber)' }} onClick={() => navigate('/teams')}>TEAMS</span>
            {' / '}
            <span style={{ cursor: 'pointer', color: 'var(--amber)' }} onClick={() => navigate(`/dashboard/${teamId}`)}>
              {team?.jira_project_key}
            </span>
            {' / HEALTHCHECK'}
          </div>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 30, fontWeight: 800, letterSpacing: '-0.5px' }}>
            Backlog Healthcheck
          </h1>
          {report?.generated_at && (
            <div style={{ marginTop: 6, fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
              Last generated: {new Date(report.generated_at).toLocaleString()}
              {' · '}{report.total_items} items analysed · {report.period_days}d period
            </div>
          )}
        </div>
        <button
          onClick={handleGenerate}
          disabled={isRunning || generating}
          style={{
            background: isRunning || generating ? 'var(--bg-card)' : 'var(--amber)',
            border: isRunning || generating ? '1px solid var(--border)' : 'none',
            borderRadius: 'var(--radius)', padding: '10px 20px',
            color: isRunning || generating ? 'var(--amber)' : '#000',
            cursor: isRunning || generating ? 'not-allowed' : 'pointer',
            fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700,
          }}
        >
          {isRunning || generating ? '↻ RUNNING...' : '▶ GENERATE REPORT'}
        </button>
      </div>

      {/* ── Running Banner ── */}
      {isRunning && (
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--amber)30',
          borderLeft: '3px solid var(--amber)',
          borderRadius: 'var(--radius-lg)', padding: '16px 24px',
          marginBottom: 24, display: 'flex', alignItems: 'center', gap: 14,
        }}>
          <span style={{ fontSize: 18, animation: 'spin 1.2s linear infinite', display: 'inline-block' }}>↻</span>
          <div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--amber)', fontWeight: 600 }}>
              ANALYSING BACKLOG
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', marginTop: 3 }}>
              {statusInfo?.total_items > 0
                ? `Scoring ${statusInfo.total_items} backlog items with AI…`
                : 'Fetching issues from Jira…'}
              {' '}Status: {statusInfo?.status?.toUpperCase()}
            </div>
          </div>
        </div>
      )}

      {/* ── Failed Banner ── */}
      {statusInfo?.status === 'failed' && !report && (
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--risk-critical)40',
          borderLeft: '3px solid var(--risk-critical)',
          borderRadius: 'var(--radius-lg)', padding: '16px 24px', marginBottom: 24,
        }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--risk-critical)' }}>
            ANALYSIS FAILED
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
            {statusInfo.error || 'Unknown error. Try generating again.'}
          </div>
        </div>
      )}

      {/* ── Empty State ── */}
      {!report && !isRunning && (
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)', padding: '60px 40px',
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16,
        }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-muted)' }}>
            NO HEALTHCHECK DATA YET
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
            Click <span style={{ color: 'var(--amber)' }}>▶ GENERATE REPORT</span> to analyse the last 6 months of backlog items.
          </div>
        </div>
      )}

      {/* ── Report ── */}
      {report && (
        <>
          {/* Lead Time Cards */}
          <div style={{ display: 'flex', gap: 12, marginBottom: 24 }}>
            <LeadCard label="AVG. LEAD TIME"   days={lt.avg} />
            <LeadCard label="STORY LEAD TIME"  days={lt.story} />
            <LeadCard label="BUG LEAD TIME"    days={lt.bug} />
            <LeadCard label="TASK LEAD TIME"   days={lt.task} />
          </div>

          {/* Backlog Depth Matrix */}
          <div style={{
            background: 'var(--bg-card)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius-lg)', padding: '24px',
            marginBottom: 20,
          }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.1em', marginBottom: 20 }}>
              BACKLOG DEPTH ANALYSIS
            </div>

            {/* Column headers */}
            <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr 1fr 1fr', gap: 12, marginBottom: 12, alignItems: 'end' }}>
              <div />
              {GROUPS.map(g => (
                <div key={g.key} style={{
                  fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--amber)',
                  letterSpacing: '0.1em', textAlign: 'center', fontWeight: 600,
                }}>
                  {g.label}
                  <div style={{ color: 'var(--text-muted)', marginTop: 2, fontSize: 9, letterSpacing: 0 }}>
                    {(report.item_groups?.[g.key] || []).length} items
                  </div>
                </div>
              ))}
            </div>

            {/* Divider */}
            <div style={{ borderTop: '1px solid var(--border)', marginBottom: 12 }} />

            {/* Rows */}
            {CRITERIA_META.map((c, idx) => (
              <div key={c.key} style={{
                display: 'grid', gridTemplateColumns: '200px 1fr 1fr 1fr',
                gap: 12, alignItems: 'center',
                padding: '10px 0',
                borderBottom: idx < CRITERIA_META.length - 1 ? '1px solid var(--border)' : 'none',
              }}>
                {/* Row label */}
                <div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600, color: 'var(--text-primary)' }}>
                    {c.label}
                  </div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                    {c.sub}
                  </div>
                </div>
                {/* Cells */}
                {GROUPS.map(g => {
                  const s = columnStats[g.key]?.[c.key] || {}
                  return (
                    <StackedBar
                      key={g.key}
                      good={s.good || 0}
                      medium={s.medium || 0}
                      critical={s.critical || 0}
                    />
                  )
                })}
              </div>
            ))}

            {/* Legend */}
            <div style={{ display: 'flex', gap: 20, marginTop: 18, justifyContent: 'flex-end' }}>
              {[['var(--risk-low)', 'Good'], ['var(--risk-high)', 'Medium'], ['var(--risk-critical)', 'Critical']].map(([color, label]) => (
                <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <div style={{ width: 10, height: 10, borderRadius: 2, background: color, opacity: 0.85 }} />
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>{label}</span>
                </div>
              ))}
            </div>
          </div>

          {/* AI Insights Row */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 24 }}>
            {GROUPS.map(g => (
              <div key={g.key} style={{
                background: 'var(--bg-card)', border: '1px solid var(--border)',
                borderRadius: 'var(--radius-lg)', padding: '20px',
              }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--amber)', letterSpacing: '0.1em', marginBottom: 12 }}>
                  {g.label}
                </div>
                <p style={{
                  fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.65,
                  fontStyle: 'italic', margin: 0,
                }}>
                  {aiInsights[g.key] || '—'}
                </p>
              </div>
            ))}
          </div>

          {/* Bottom Row: Top 5 + Actions */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>

            {/* Top 5 Issues */}
            <div style={{
              background: 'var(--bg-card)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg)', padding: 24,
            }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.1em', marginBottom: 16 }}>
                TOP 5 ITEMS TO SOLVE
              </div>
              {topIssues.length === 0 ? (
                <div style={{ color: 'var(--text-muted)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>
                  No issues identified.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  {topIssues.map((item, i) => (
                    <div key={item.key} style={{
                      display: 'flex', gap: 12, paddingBottom: 14,
                      borderBottom: i < topIssues.length - 1 ? '1px solid var(--border)' : 'none',
                    }}>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--amber)', fontWeight: 700, minWidth: 70 }}>
                        {item.key}
                      </div>
                      <div>
                        <div style={{ fontSize: 12, color: 'var(--text-primary)', fontWeight: 600, marginBottom: 4 }}>
                          {item.summary}
                        </div>
                        <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.5 }}>
                          {item.root_cause}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Concrete Actions */}
            <div style={{
              background: 'var(--bg-card)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg)', padding: 24,
            }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.1em', marginBottom: 16 }}>
                CONCRETE ACTIONS
              </div>
              {concreteActions.length === 0 ? (
                <div style={{ color: 'var(--text-muted)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>
                  No actions generated.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  {concreteActions.map((action, i) => (
                    <div key={i} style={{
                      display: 'flex', gap: 16, alignItems: 'flex-start',
                      background: 'var(--bg-deep)', borderRadius: 'var(--radius)',
                      padding: '14px 16px',
                    }}>
                      <div style={{
                        fontFamily: 'var(--font-mono)', fontSize: 22, fontWeight: 800,
                        color: 'var(--amber)', opacity: 0.4, lineHeight: 1, minWidth: 32,
                      }}>
                        {String(i + 1).padStart(2, '0')}
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                        {action}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

          </div>
        </>
      )}

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}
