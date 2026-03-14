import React, { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../lib/api'

// ── Helpers ──────────────────────────────────────────────────────────────────

const STATUS_COLOR = {
  pending:   'var(--text-muted)',
  running:   'var(--amber)',
  completed: 'var(--risk-low)',
  failed:    'var(--risk-critical)',
  skipped:   'var(--text-muted)',
}

const STATUS_ICON = {
  pending:   '○',
  running:   '◉',
  completed: '✓',
  failed:    '✗',
  skipped:   '—',
}

const AGENT_ICONS = {
  solution_architect: '⬡',
  pbi_generator:      '◈',
  dependency_agent:   '◆',
  backlog_dispatcher: '▦',
}

function ms(duration_ms) {
  if (!duration_ms) return ''
  if (duration_ms < 1000) return `${duration_ms}ms`
  return `${(duration_ms / 1000).toFixed(1)}s`
}

function timeAgo(dt) {
  if (!dt) return ''
  const diff = Date.now() - new Date(dt).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

// ── Sub-components ────────────────────────────────────────────────────────────

function AgentStep({ step, isActive }) {
  const [expanded, setExpanded] = useState(false)
  const color = STATUS_COLOR[step.status] || 'var(--text-muted)'
  const icon = AGENT_ICONS[step.agent_name] || '◉'

  return (
    <div style={{
      border: `1px solid ${isActive ? 'var(--amber)' : 'var(--border)'}`,
      borderRadius: 'var(--radius)',
      marginBottom: 8,
      background: isActive ? 'var(--amber-glow)' : 'var(--bg-panel)',
      transition: 'all 0.2s',
    }}>
      <div
        onClick={() => step.output && setExpanded(!expanded)}
        style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '12px 16px',
          cursor: step.output ? 'pointer' : 'default',
        }}
      >
        {/* Step number */}
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 11,
          color: 'var(--text-muted)', minWidth: 20, textAlign: 'center',
        }}>{step.step_order}</span>

        {/* Agent icon */}
        <span style={{ color: isActive ? 'var(--amber)' : 'var(--text-muted)', fontSize: 16 }}>
          {icon}
        </span>

        {/* Label */}
        <div style={{ flex: 1 }}>
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 13,
            color: isActive ? 'var(--amber)' : 'var(--text-primary)',
            letterSpacing: '0.05em',
          }}>{step.agent_label}</div>
          {step.duration_ms && (
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
              {ms(step.duration_ms)}
            </div>
          )}
        </div>

        {/* Status badge */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {step.status === 'running' && (
            <span style={{
              display: 'inline-block', width: 8, height: 8,
              borderRadius: '50%', background: 'var(--amber)',
              animation: 'pulse 1s infinite',
            }} />
          )}
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 11,
            color, letterSpacing: '0.08em',
          }}>
            {STATUS_ICON[step.status]} {step.status.toUpperCase()}
          </span>
        </div>

        {step.output && (
          <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
            {expanded ? '▲' : '▼'}
          </span>
        )}
      </div>

      {/* Error */}
      {step.error && (
        <div style={{
          padding: '8px 16px 12px 46px',
          fontSize: 12, color: 'var(--risk-critical)',
          fontFamily: 'var(--font-mono)',
        }}>{step.error}</div>
      )}

      {/* Output panel */}
      {expanded && step.output && (
        <StepOutput agentName={step.agent_name} output={step.output} />
      )}
    </div>
  )
}

function StepOutput({ agentName, output }) {
  const pad = { padding: '0 16px 16px 46px' }

  if (agentName === 'solution_architect') {
    return (
      <div style={pad}>
        <OutputSection title="Architecture Proposal">
          <pre style={preStyle}>{output.architecture_proposal}</pre>
        </OutputSection>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12 }}>
          <TagList title="Affected Components" items={output.affected_components} color="var(--risk-medium)" />
          <TagList title="New Components" items={output.new_components} color="var(--risk-low)" />
        </div>
        <div style={{ display: 'flex', gap: 16, marginTop: 12, flexWrap: 'wrap' }}>
          <KV label="Complexity" value={output.complexity} />
          <KV label="Est. Effort" value={output.estimated_effort_days ? `${output.estimated_effort_days}d` : 'N/A'} />
          <KV label="GitHub Context" value={output.github_context_used ? 'Used' : 'Not used'} />
        </div>
        {output.risks?.length > 0 && (
          <OutputSection title="Risks" style={{ marginTop: 12 }}>
            {output.risks.map((r, i) => (
              <div key={i} style={{ fontSize: 12, color: 'var(--risk-high)', marginBottom: 4 }}>⚠ {r}</div>
            ))}
          </OutputSection>
        )}
      </div>
    )
  }

  if (agentName === 'pbi_generator') {
    return (
      <div style={pad}>
        <div style={{ marginBottom: 10, fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>
          {output.total_story_points} story points total · {output.epics?.length || 0} epics
        </div>
        {output.epics?.map((epic, ei) => (
          <div key={ei} style={{
            border: '1px solid var(--border)', borderRadius: 4,
            marginBottom: 10, overflow: 'hidden',
          }}>
            <div style={{
              padding: '8px 12px', background: 'rgba(255,180,0,0.06)',
              fontFamily: 'var(--font-mono)', fontSize: 12,
              color: 'var(--amber)', letterSpacing: '0.06em',
            }}>
              ◆ EPIC: {epic.title}
            </div>
            {epic.stories?.map((story, si) => (
              <div key={si} style={{
                padding: '8px 12px', borderTop: '1px solid var(--border)',
              }}>
                <div style={{ fontSize: 12, color: 'var(--text-primary)', marginBottom: 4 }}>
                  <strong>{story.title}</strong>
                  <span style={{
                    marginLeft: 8, fontFamily: 'var(--font-mono)', fontSize: 11,
                    color: 'var(--amber)', background: 'var(--amber-glow)',
                    padding: '1px 6px', borderRadius: 3,
                  }}>{story.story_points}sp</span>
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{story.description}</div>
                {story.acceptance_criteria?.length > 0 && (
                  <div style={{ marginTop: 6 }}>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginBottom: 3 }}>AC:</div>
                    {story.acceptance_criteria.map((ac, ai) => (
                      <div key={ai} style={{ fontSize: 11, color: 'var(--text-secondary)', paddingLeft: 10, marginBottom: 2 }}>
                        · {ac}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        ))}
      </div>
    )
  }

  if (agentName === 'dependency_agent') {
    return (
      <div style={pad}>
        <div style={{ display: 'flex', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
          <KV label="Risk Level" value={output.total_risk_level?.toUpperCase()} color={STATUS_COLOR[output.total_risk_level === 'low' ? 'completed' : output.total_risk_level === 'critical' ? 'failed' : 'running']} />
          <KV label="Internal Deps" value={output.internal_dependencies?.length || 0} />
          <KV label="External Deps" value={output.external_dependencies?.length || 0} />
        </div>
        {output.blockers?.length > 0 && (
          <OutputSection title="Blockers">
            {output.blockers.map((b, i) => (
              <div key={i} style={{ fontSize: 12, color: 'var(--risk-critical)', marginBottom: 4 }}>🚫 {b}</div>
            ))}
          </OutputSection>
        )}
        {output.internal_dependencies?.length > 0 && (
          <OutputSection title="Internal Dependencies" style={{ marginTop: 10 }}>
            {output.internal_dependencies.map((d, i) => (
              <div key={i} style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>
                <span style={{ color: 'var(--amber)' }}>{d.from_story}</span>
                <span style={{ color: 'var(--text-muted)' }}> → {d.type} → </span>
                <span style={{ color: 'var(--amber)' }}>{d.to_story}</span>
                <span style={{ color: 'var(--text-muted)' }}> ({d.reason})</span>
              </div>
            ))}
          </OutputSection>
        )}
        {output.risk_assessment && (
          <OutputSection title="Risk Assessment" style={{ marginTop: 10 }}>
            <p style={{ fontSize: 12, color: 'var(--text-secondary)', margin: 0, lineHeight: 1.6 }}>
              {output.risk_assessment}
            </p>
          </OutputSection>
        )}
      </div>
    )
  }

  if (agentName === 'backlog_dispatcher') {
    return (
      <div style={pad}>
        {output.sprint_recommendations?.length > 0 && (
          <OutputSection title="Sprint Plan">
            {output.sprint_recommendations.map((s, i) => (
              <div key={i} style={{
                border: '1px solid var(--border)', borderRadius: 4,
                padding: '8px 12px', marginBottom: 8,
              }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--amber)', marginBottom: 4 }}>
                  Sprint {s.sprint} · {s.total_sp}sp{s.goal ? ` · ${s.goal}` : ''}
                </div>
                {s.stories?.map((st, si) => (
                  <div key={si} style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 2 }}>· {st}</div>
                ))}
              </div>
            ))}
          </OutputSection>
        )}
        {output.follow_up_checklist?.length > 0 && (
          <OutputSection title="Follow-up Checklist" style={{ marginTop: 12 }}>
            {output.follow_up_checklist.map((item, i) => (
              <div key={i} style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>
                ☐ {item}
              </div>
            ))}
          </OutputSection>
        )}
        {output.success_metrics?.length > 0 && (
          <OutputSection title="Success Metrics" style={{ marginTop: 12 }}>
            {output.success_metrics.map((m, i) => (
              <div key={i} style={{ fontSize: 12, color: 'var(--risk-low)', marginBottom: 4 }}>◈ {m}</div>
            ))}
          </OutputSection>
        )}
        {output.auto_created && output.created_issues?.length > 0 && (
          <OutputSection title={`Created in Jira (${output.created_issues.length})`} style={{ marginTop: 12 }}>
            {output.created_issues.map((issue, i) => (
              <div key={i} style={{ fontSize: 12, color: 'var(--amber)', marginBottom: 4, fontFamily: 'var(--font-mono)' }}>
                [{issue.key}] {issue.type} - {issue.title}
              </div>
            ))}
          </OutputSection>
        )}
      </div>
    )
  }

  return (
    <div style={pad}>
      <pre style={{ ...preStyle, maxHeight: 300 }}>{JSON.stringify(output, null, 2)}</pre>
    </div>
  )
}

function OutputSection({ title, children, style }) {
  return (
    <div style={style}>
      <div style={{
        fontFamily: 'var(--font-mono)', fontSize: 10,
        color: 'var(--text-muted)', letterSpacing: '0.12em', marginBottom: 6,
      }}>{title.toUpperCase()}</div>
      {children}
    </div>
  )
}

function TagList({ title, items, color }) {
  if (!items?.length) return null
  return (
    <div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)', marginBottom: 6 }}>
        {title.toUpperCase()}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
        {items.map((item, i) => (
          <span key={i} style={{
            fontSize: 11, fontFamily: 'var(--font-mono)',
            color, background: `${color}15`,
            border: `1px solid ${color}30`,
            borderRadius: 3, padding: '2px 7px',
          }}>{item}</span>
        ))}
      </div>
    </div>
  )
}

function KV({ label, value, color }) {
  return (
    <div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: color || 'var(--text-primary)', marginTop: 2 }}>
        {value}
      </div>
    </div>
  )
}

const preStyle = {
  background: 'var(--bg-deep)', border: '1px solid var(--border)',
  borderRadius: 4, padding: '10px 14px',
  fontSize: 11, color: 'var(--text-secondary)',
  fontFamily: 'var(--font-mono)', whiteSpace: 'pre-wrap',
  wordBreak: 'break-word', margin: 0, maxHeight: 400, overflowY: 'auto',
}

// ── Settings Modal ────────────────────────────────────────────────────────────

function SettingsModal({ teamId, config, onClose, onSaved }) {
  const [form, setForm] = useState({
    request_board_id: config?.request_board_id || '',
    request_jql: config?.request_jql || '',
    target_project_key: config?.target_project_key || '',
    github_repo_url: config?.github_repo_url || '',
    github_token: config?.github_token || '',
    enable_solution_architect: config?.enable_solution_architect ?? true,
    enable_pbi_generator: config?.enable_pbi_generator ?? true,
    enable_dependency_agent: config?.enable_dependency_agent ?? true,
    enable_backlog_dispatcher: config?.enable_backlog_dispatcher ?? true,
    auto_create_jira_issues: config?.auto_create_jira_issues ?? false,
    poll_interval_minutes: config?.poll_interval_minutes || 30,
  })
  const [saving, setSaving] = useState(false)

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    try {
      const payload = {
        ...form,
        request_board_id: form.request_board_id ? parseInt(form.request_board_id) : null,
        poll_interval_minutes: parseInt(form.poll_interval_minutes) || 30,
      }
      await api.upsertAgentConfig(teamId, payload)
      onSaved()
      onClose()
    } catch (err) {
      alert('Save failed: ' + err.message)
    } finally {
      setSaving(false)
    }
  }

  const inputStyle = {
    width: '100%', background: 'var(--bg-deep)', border: '1px solid var(--border)',
    borderRadius: 4, color: 'var(--text-primary)', fontSize: 13,
    padding: '8px 10px', fontFamily: 'var(--font-mono)',
    boxSizing: 'border-box',
  }

  const labelStyle = {
    fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)',
    letterSpacing: '0.08em', display: 'block', marginBottom: 5,
  }

  const toggleStyle = (enabled) => ({
    display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0',
    cursor: 'pointer',
  })

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }}>
      <div style={{
        background: 'var(--bg-panel)', border: '1px solid var(--border)',
        borderRadius: 8, width: 560, maxHeight: '90vh', overflowY: 'auto',
        padding: 28,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
            AGENT SETTINGS
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 18 }}>✕</button>
        </div>

        <form onSubmit={save}>
          {/* Jira Request Board */}
          <div style={{ marginBottom: 18 }}>
            <div style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--amber)', letterSpacing: '0.1em', marginBottom: 12 }}>
              JIRA REQUEST BOARD
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label style={labelStyle}>BOARD ID</label>
                <input style={inputStyle} type="number" placeholder="e.g. 42"
                  value={form.request_board_id}
                  onChange={e => setForm({ ...form, request_board_id: e.target.value })} />
              </div>
              <div>
                <label style={labelStyle}>TARGET PROJECT KEY</label>
                <input style={inputStyle} placeholder="e.g. MYPROJ"
                  value={form.target_project_key}
                  onChange={e => setForm({ ...form, target_project_key: e.target.value })} />
              </div>
            </div>
            <div style={{ marginTop: 12 }}>
              <label style={labelStyle}>JQL FILTER (optional)</label>
              <input style={inputStyle} placeholder='e.g. issuetype = "Feature Request" AND status = "Open"'
                value={form.request_jql}
                onChange={e => setForm({ ...form, request_jql: e.target.value })} />
            </div>
            <div style={{ marginTop: 12 }}>
              <label style={labelStyle}>POLL INTERVAL (MINUTES)</label>
              <input style={{ ...inputStyle, width: 120 }} type="number" min="5"
                value={form.poll_interval_minutes}
                onChange={e => setForm({ ...form, poll_interval_minutes: e.target.value })} />
            </div>
          </div>

          {/* GitHub */}
          <div style={{ marginBottom: 18, paddingTop: 16, borderTop: '1px solid var(--border)' }}>
            <div style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--amber)', letterSpacing: '0.1em', marginBottom: 12 }}>
              GITHUB ARCHITECTURE CONTEXT
            </div>
            <div style={{ marginBottom: 12 }}>
              <label style={labelStyle}>REPOSITORY URL</label>
              <input style={inputStyle} placeholder="https://github.com/org/repo"
                value={form.github_repo_url}
                onChange={e => setForm({ ...form, github_repo_url: e.target.value })} />
            </div>
            <div>
              <label style={labelStyle}>PERSONAL ACCESS TOKEN (optional)</label>
              <input style={inputStyle} type="password" placeholder="ghp_..."
                value={form.github_token}
                onChange={e => setForm({ ...form, github_token: e.target.value })} />
            </div>
          </div>

          {/* Agent toggles */}
          <div style={{ paddingTop: 16, borderTop: '1px solid var(--border)' }}>
            <div style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--amber)', letterSpacing: '0.1em', marginBottom: 12 }}>
              ACTIVE AGENTS
            </div>
            {[
              { key: 'enable_solution_architect', label: '⬡  Solution Architect', desc: 'Analyses architecture & proposes solution' },
              { key: 'enable_pbi_generator', label: '◈  PBI Generator', desc: 'Generates Epics, Stories & Tasks' },
              { key: 'enable_dependency_agent', label: '◆  Dependency Analyzer', desc: 'Maps dependencies & identifies blockers' },
              { key: 'enable_backlog_dispatcher', label: '▦  Backlog Dispatcher', desc: 'Plans sprints & dispatches to Jira' },
            ].map(({ key, label, desc }) => (
              <div key={key} style={toggleStyle(form[key])} onClick={() => setForm({ ...form, [key]: !form[key] })}>
                <div style={{
                  width: 36, height: 20, borderRadius: 10,
                  background: form[key] ? 'var(--amber)' : 'var(--border)',
                  position: 'relative', transition: 'background 0.2s', flexShrink: 0,
                }}>
                  <div style={{
                    position: 'absolute', top: 2, left: form[key] ? 18 : 2,
                    width: 16, height: 16, borderRadius: '50%',
                    background: 'white', transition: 'left 0.2s',
                  }} />
                </div>
                <div>
                  <div style={{ fontSize: 13, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>{label}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{desc}</div>
                </div>
              </div>
            ))}

            <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
              <div style={toggleStyle(form.auto_create_jira_issues)} onClick={() => setForm({ ...form, auto_create_jira_issues: !form.auto_create_jira_issues })}>
                <div style={{
                  width: 36, height: 20, borderRadius: 10,
                  background: form.auto_create_jira_issues ? 'var(--risk-critical)' : 'var(--border)',
                  position: 'relative', transition: 'background 0.2s', flexShrink: 0,
                }}>
                  <div style={{
                    position: 'absolute', top: 2, left: form.auto_create_jira_issues ? 18 : 2,
                    width: 16, height: 16, borderRadius: '50%',
                    background: 'white', transition: 'left 0.2s',
                  }} />
                </div>
                <div>
                  <div style={{ fontSize: 13, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
                    Auto-create Issues in Jira
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                    When disabled: preview mode only (recommended)
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 24 }}>
            <button type="button" onClick={onClose} style={{
              background: 'none', border: '1px solid var(--border)',
              color: 'var(--text-muted)', borderRadius: 4, padding: '8px 16px',
              cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 12,
            }}>CANCEL</button>
            <button type="submit" disabled={saving} style={{
              background: 'var(--amber)', border: 'none',
              color: '#000', borderRadius: 4, padding: '8px 20px',
              cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700,
            }}>{saving ? 'SAVING...' : 'SAVE'}</button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Trigger Modal ─────────────────────────────────────────────────────────────

function TriggerModal({ teamId, onClose, onTriggered }) {
  const [form, setForm] = useState({ issue_key: '', issue_summary: '', description: '' })
  const [loading, setLoading] = useState(false)

  async function submit(e) {
    e.preventDefault()
    if (!form.issue_key || !form.issue_summary) return
    setLoading(true)
    try {
      await api.triggerAgentPipeline(teamId, {
        issue_key: form.issue_key,
        issue_summary: form.issue_summary,
        issue_data: form.description ? { description: form.description } : null,
      })
      onTriggered()
      onClose()
    } catch (err) {
      alert('Trigger failed: ' + err.message)
    } finally {
      setLoading(false)
    }
  }

  const inputStyle = {
    width: '100%', background: 'var(--bg-deep)', border: '1px solid var(--border)',
    borderRadius: 4, color: 'var(--text-primary)', fontSize: 13,
    padding: '8px 10px', fontFamily: 'var(--font-mono)', boxSizing: 'border-box',
  }
  const labelStyle = {
    fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)',
    letterSpacing: '0.08em', display: 'block', marginBottom: 5,
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }}>
      <div style={{
        background: 'var(--bg-panel)', border: '1px solid var(--border)',
        borderRadius: 8, width: 480, padding: 28,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
            TRIGGER PIPELINE
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 18 }}>✕</button>
        </div>
        <form onSubmit={submit}>
          <div style={{ marginBottom: 14 }}>
            <label style={labelStyle}>ISSUE KEY</label>
            <input style={inputStyle} placeholder="e.g. REQ-42" required
              value={form.issue_key}
              onChange={e => setForm({ ...form, issue_key: e.target.value })} />
          </div>
          <div style={{ marginBottom: 14 }}>
            <label style={labelStyle}>SUMMARY</label>
            <input style={inputStyle} placeholder="Short description of the request" required
              value={form.issue_summary}
              onChange={e => setForm({ ...form, issue_summary: e.target.value })} />
          </div>
          <div style={{ marginBottom: 20 }}>
            <label style={labelStyle}>DESCRIPTION (optional)</label>
            <textarea style={{ ...inputStyle, minHeight: 80, resize: 'vertical' }}
              placeholder="Detailed description of the requirement..."
              value={form.description}
              onChange={e => setForm({ ...form, description: e.target.value })} />
          </div>
          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
            <button type="button" onClick={onClose} style={{
              background: 'none', border: '1px solid var(--border)',
              color: 'var(--text-muted)', borderRadius: 4, padding: '8px 16px',
              cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 12,
            }}>CANCEL</button>
            <button type="submit" disabled={loading} style={{
              background: 'var(--amber)', border: 'none',
              color: '#000', borderRadius: 4, padding: '8px 20px',
              cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700,
            }}>{loading ? 'TRIGGERING...' : '▶ RUN'}</button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function Agents() {
  const { teamId } = useParams()
  const [pipelines, setPipelines] = useState([])
  const [config, setConfig] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [showSettings, setShowSettings] = useState(false)
  const [showTrigger, setShowTrigger] = useState(false)
  const [polling, setPolling] = useState(false)
  const [loading, setLoading] = useState(true)

  const selected = pipelines.find(p => p.id === selectedId) || null
  const hasRunning = pipelines.some(p => p.status === 'running')

  const load = useCallback(async () => {
    try {
      const [pl, cfg] = await Promise.allSettled([
        api.listAgentPipelines(teamId),
        api.getAgentConfig(teamId),
      ])
      if (pl.status === 'fulfilled') setPipelines(pl.value)
      if (cfg.status === 'fulfilled') setConfig(cfg.value)
    } catch {}
    setLoading(false)
  }, [teamId])

  useEffect(() => {
    load()
  }, [load])

  // Auto-refresh while a pipeline is running
  useEffect(() => {
    if (!hasRunning) return
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [hasRunning, load])

  // Auto-select latest pipeline
  useEffect(() => {
    if (pipelines.length > 0 && !selectedId) {
      setSelectedId(pipelines[0].id)
    }
  }, [pipelines, selectedId])

  async function pollBoard() {
    setPolling(true)
    try {
      const res = await api.pollAgentBoard(teamId)
      await load()
      if (res.triggered_pipelines > 0) {
        setSelectedId(null) // will auto-select newest
      } else {
        alert(`Board polled — no new issues found.\n\nMake sure:\n• Request Board ID is set in SETTINGS\n• Jira credentials are configured\n• There are unprocessed issues on the board`)
      }
    } catch (err) {
      // Try to extract server error detail
      let msg = err.message
      try {
        const body = await err.response?.json?.()
        if (body?.detail) msg = body.detail
      } catch {}
      alert('Poll failed: ' + msg)
    } finally {
      setPolling(false)
    }
  }

  if (loading) {
    return (
      <div style={{ padding: 40, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>
        Loading...
      </div>
    )
  }

  return (
    <div style={{ padding: 28, height: '100%', display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <div style={{
            fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 800,
            letterSpacing: '0.12em', color: 'var(--text-primary)',
          }}>AGENT PIPELINE</div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 3, fontFamily: 'var(--font-mono)' }}>
            Autonomous request processing · 4-step AI pipeline
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => setShowSettings(true)} style={btnStyle('secondary')}>
            ⚙ SETTINGS
          </button>
          <button onClick={pollBoard} disabled={polling} style={btnStyle('secondary')}>
            {polling ? '⟳ POLLING...' : '⟳ POLL BOARD'}
          </button>
          <button onClick={() => setShowTrigger(true)} style={btnStyle('primary')}>
            ▶ TRIGGER
          </button>
        </div>
      </div>

      {/* Pipeline flow diagram */}
      <PipelineFlowDiagram config={config} activePipeline={selected} />

      {/* Main content: list + detail */}
      <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: 16, flex: 1, minHeight: 0 }}>
        {/* Pipeline list */}
        <div style={{
          border: '1px solid var(--border)', borderRadius: 6,
          background: 'var(--bg-panel)', overflowY: 'auto',
        }}>
          <div style={{
            padding: '12px 16px', borderBottom: '1px solid var(--border)',
            fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.1em',
          }}>PIPELINE RUNS ({pipelines.length})</div>

          {pipelines.length === 0 ? (
            <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
              No pipeline runs yet.<br />Configure a board or trigger manually.
            </div>
          ) : (
            pipelines.map(p => (
              <div
                key={p.id}
                onClick={() => setSelectedId(p.id)}
                style={{
                  padding: '12px 16px', cursor: 'pointer',
                  borderBottom: '1px solid var(--border)',
                  background: selectedId === p.id ? 'var(--amber-glow)' : 'transparent',
                  borderLeft: selectedId === p.id ? '2px solid var(--amber)' : '2px solid transparent',
                  transition: 'all 0.15s',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  {p.status === 'running' && (
                    <span style={{
                      display: 'inline-block', width: 7, height: 7,
                      borderRadius: '50%', background: 'var(--amber)',
                      animation: 'pulse 1s infinite',
                    }} />
                  )}
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: 12,
                    color: STATUS_COLOR[p.status],
                  }}>{STATUS_ICON[p.status]} {p.status.toUpperCase()}</span>
                  <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-muted)' }}>
                    {timeAgo(p.created_at)}
                  </span>
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--amber)' }}>
                  {p.trigger_issue_key}
                </div>
                <div style={{
                  fontSize: 12, color: 'var(--text-secondary)', marginTop: 2,
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>{p.trigger_issue_summary}</div>
                {/* Mini step progress */}
                <div style={{ display: 'flex', gap: 3, marginTop: 8 }}>
                  {(p.steps || []).map(s => (
                    <div key={s.id} style={{
                      flex: 1, height: 3, borderRadius: 2,
                      background: STATUS_COLOR[s.status],
                      opacity: s.status === 'pending' ? 0.3 : 1,
                    }} />
                  ))}
                  {(p.steps || []).length === 0 && [1,2,3,4].map(i => (
                    <div key={i} style={{
                      flex: 1, height: 3, borderRadius: 2,
                      background: 'var(--border)',
                    }} />
                  ))}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Pipeline detail */}
        <div style={{
          border: '1px solid var(--border)', borderRadius: 6,
          background: 'var(--bg-panel)', overflowY: 'auto',
        }}>
          {!selected ? (
            <div style={{
              height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: 'var(--text-muted)', fontSize: 13, fontFamily: 'var(--font-mono)',
            }}>
              Select a pipeline run to view details
            </div>
          ) : (
            <div style={{ padding: 20 }}>
              {/* Pipeline header */}
              <div style={{
                display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
                marginBottom: 20, paddingBottom: 16, borderBottom: '1px solid var(--border)',
              }}>
                <div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, color: 'var(--amber)', fontWeight: 700 }}>
                    {selected.trigger_issue_key}
                  </div>
                  <div style={{ fontSize: 14, color: 'var(--text-primary)', marginTop: 4 }}>
                    {selected.trigger_issue_summary}
                  </div>
                  <div style={{ display: 'flex', gap: 16, marginTop: 8 }}>
                    <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                      Created: {new Date(selected.created_at).toLocaleString()}
                    </span>
                    {selected.completed_at && (
                      <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                        Completed: {new Date(selected.completed_at).toLocaleString()}
                      </span>
                    )}
                  </div>
                </div>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 12,
                  color: STATUS_COLOR[selected.status],
                  background: `${STATUS_COLOR[selected.status]}15`,
                  border: `1px solid ${STATUS_COLOR[selected.status]}40`,
                  borderRadius: 4, padding: '4px 10px',
                }}>
                  {STATUS_ICON[selected.status]} {selected.status.toUpperCase()}
                </span>
              </div>

              {/* Agent steps */}
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.1em', marginBottom: 12 }}>
                AGENT STEPS
              </div>
              {selected.status === 'pending' && (selected.steps || []).length === 0 ? (
                <div style={{ color: 'var(--text-muted)', fontSize: 12, fontFamily: 'var(--font-mono)', textAlign: 'center', padding: 30 }}>
                  Pipeline queued — starting shortly...
                </div>
              ) : (
                (selected.steps || []).map(step => (
                  <AgentStep
                    key={step.id}
                    step={step}
                    isActive={step.status === 'running'}
                  />
                ))
              )}

              {selected.error && (
                <div style={{
                  marginTop: 12, padding: '12px 16px',
                  background: 'rgba(255,50,50,0.08)', border: '1px solid rgba(255,50,50,0.3)',
                  borderRadius: 6, fontSize: 12, color: 'var(--risk-critical)', fontFamily: 'var(--font-mono)',
                }}>
                  ERROR: {selected.error}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {showSettings && (
        <SettingsModal
          teamId={teamId}
          config={config}
          onClose={() => setShowSettings(false)}
          onSaved={load}
        />
      )}
      {showTrigger && (
        <TriggerModal
          teamId={teamId}
          onClose={() => setShowTrigger(false)}
          onTriggered={load}
        />
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
      `}</style>
    </div>
  )
}

// ── Pipeline Flow Diagram ─────────────────────────────────────────────────────

function PipelineFlowDiagram({ config, activePipeline }) {
  const steps = activePipeline?.steps || []

  const agents = [
    { name: 'solution_architect', label: 'Solution\nArchitect', icon: '⬡', enabled: config?.enable_solution_architect ?? true },
    { name: 'pbi_generator', label: 'PBI\nGenerator', icon: '◈', enabled: config?.enable_pbi_generator ?? true },
    { name: 'dependency_agent', label: 'Dependency\nAnalyzer', icon: '◆', enabled: config?.enable_dependency_agent ?? true },
    { name: 'backlog_dispatcher', label: 'Backlog\nDispatcher', icon: '▦', enabled: config?.enable_backlog_dispatcher ?? true },
  ]

  function getStatus(agentName) {
    const step = steps.find(s => s.agent_name === agentName)
    return step?.status || 'pending'
  }

  return (
    <div style={{
      border: '1px solid var(--border)', borderRadius: 6,
      background: 'var(--bg-panel)', padding: '16px 24px',
      display: 'flex', alignItems: 'center', gap: 0,
    }}>
      {/* Trigger */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', marginRight: 8 }}>
        <div style={{
          width: 44, height: 44, borderRadius: '50%',
          background: 'var(--amber-glow)', border: '2px solid var(--amber)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 18,
        }}>◉</div>
        <div style={{ fontSize: 9, fontFamily: 'var(--font-mono)', color: 'var(--amber)', marginTop: 5, letterSpacing: '0.08em', textAlign: 'center' }}>
          JIRA<br />REQUEST
        </div>
      </div>

      {agents.map((agent, i) => {
        const status = getStatus(agent.name)
        const color = STATUS_COLOR[status]
        const isEnabled = agent.enabled

        return (
          <React.Fragment key={agent.name}>
            {/* Arrow */}
            <div style={{
              flex: 1, height: 2, minWidth: 20,
              background: isEnabled ? (status !== 'pending' ? 'var(--amber)' : 'var(--border)') : 'var(--border)',
              position: 'relative',
            }}>
              <div style={{
                position: 'absolute', right: -6, top: -4,
                color: isEnabled ? (status !== 'pending' ? 'var(--amber)' : 'var(--text-muted)') : 'var(--border)',
                fontSize: 14,
              }}>›</div>
            </div>

            {/* Agent box */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
              <div style={{
                width: 64, height: 52, borderRadius: 6,
                border: `2px solid ${isEnabled ? color : 'var(--border)'}`,
                background: status === 'running' ? 'var(--amber-glow)' : status === 'completed' ? 'rgba(80,220,100,0.06)' : 'var(--bg-deep)',
                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                gap: 3, opacity: isEnabled ? 1 : 0.4,
                transition: 'all 0.3s',
              }}>
                <span style={{ fontSize: 18, color: isEnabled ? color : 'var(--text-muted)' }}>{agent.icon}</span>
                {status === 'running' && (
                  <span style={{
                    display: 'inline-block', width: 6, height: 6,
                    borderRadius: '50%', background: 'var(--amber)',
                    animation: 'pulse 1s infinite',
                  }} />
                )}
                {status === 'completed' && <span style={{ fontSize: 10, color: 'var(--risk-low)' }}>✓</span>}
                {status === 'failed' && <span style={{ fontSize: 10, color: 'var(--risk-critical)' }}>✗</span>}
              </div>
              <div style={{
                fontSize: 9, fontFamily: 'var(--font-mono)',
                color: isEnabled ? 'var(--text-muted)' : 'var(--border)',
                marginTop: 6, letterSpacing: '0.05em', textAlign: 'center',
                whiteSpace: 'pre-line', lineHeight: 1.4,
              }}>{agent.label}</div>
            </div>
          </React.Fragment>
        )
      })}

      {/* Output */}
      <div style={{
        flex: 1, height: 2, minWidth: 20,
        background: activePipeline?.status === 'completed' ? 'var(--amber)' : 'var(--border)',
      }} />
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        <div style={{
          width: 44, height: 44, borderRadius: '50%',
          background: activePipeline?.status === 'completed' ? 'rgba(80,220,100,0.1)' : 'var(--bg-deep)',
          border: `2px solid ${activePipeline?.status === 'completed' ? 'var(--risk-low)' : 'var(--border)'}`,
          display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18,
          color: activePipeline?.status === 'completed' ? 'var(--risk-low)' : 'var(--text-muted)',
        }}>▦</div>
        <div style={{ fontSize: 9, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', marginTop: 5, letterSpacing: '0.08em', textAlign: 'center' }}>
          BACKLOG<br />OUTPUT
        </div>
      </div>
    </div>
  )
}

function btnStyle(variant) {
  const base = {
    padding: '8px 14px', borderRadius: 4,
    cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 12,
    letterSpacing: '0.06em', fontWeight: 600,
  }
  if (variant === 'primary') return {
    ...base, background: 'var(--amber)', border: 'none', color: '#000',
  }
  return {
    ...base, background: 'none', border: '1px solid var(--border)', color: 'var(--text-secondary)',
  }
}
