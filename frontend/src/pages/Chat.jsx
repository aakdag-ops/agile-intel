import React, { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'

function parseMarkdown(text) {
  return text
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>')
    .replace(/^---$/gm, '<hr>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/^(?!<[hul]|<hr)(.+)$/gm, '<p>$1</p>')
}

function Message({ msg, isStreaming }) {
  const isUser = msg.role === 'user'
  return (
    <div style={{
      display: 'flex', gap: 12,
      flexDirection: isUser ? 'row-reverse' : 'row',
      animation: 'fadeIn 0.2s ease',
      marginBottom: 20,
    }}>
      {/* Avatar */}
      <div style={{
        width: 30, height: 30, borderRadius: '50%', flexShrink: 0,
        background: isUser ? 'var(--blue-dim)' : 'var(--amber-dim)',
        border: `1px solid ${isUser ? 'var(--blue)' : 'var(--amber)'}40`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontFamily: 'var(--font-mono)', fontSize: 11,
        color: isUser ? 'var(--blue)' : 'var(--amber)',
      }}>
        {isUser ? 'U' : '◈'}
      </div>

      {/* Bubble */}
      <div style={{
        maxWidth: '75%',
        background: isUser ? 'var(--blue-dim)' : 'var(--bg-card)',
        border: `1px solid ${isUser ? 'var(--blue)30' : 'var(--border)'}`,
        borderRadius: isUser ? '12px 4px 12px 12px' : '4px 12px 12px 12px',
        padding: '12px 16px',
      }}>
        {isUser ? (
          <p style={{ color: 'var(--text-primary)', fontSize: 13, lineHeight: 1.6 }}>{msg.content}</p>
        ) : (
          <div
            className="chat-content"
            dangerouslySetInnerHTML={{ __html: parseMarkdown(msg.content) }}
          />
        )}
        {isStreaming && (
          <span style={{
            display: 'inline-block', width: 8, height: 14,
            background: 'var(--amber)', marginLeft: 2, verticalAlign: 'middle',
            animation: 'blink 0.8s infinite',
          }} />
        )}
        <div style={{
          marginTop: 6, fontSize: 9, color: 'var(--text-muted)',
          fontFamily: 'var(--font-mono)', textAlign: isUser ? 'right' : 'left',
        }}>
          {msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : ''}
          {msg.sources?.length > 0 && (
            <span style={{ marginLeft: 8 }}>
              {msg.sources.map(s => (
                <span key={s} style={{
                  background: 'var(--amber-glow)', color: 'var(--amber)',
                  border: '1px solid var(--amber-dim)',
                  borderRadius: 3, padding: '0 4px', marginLeft: 3, fontSize: 8,
                }}>{s.toUpperCase()}</span>
              ))}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

const STARTERS = [
  'What are the main risks in this sprint?',
  'Which issues have been stuck the longest?',
  'Will we hit the sprint goal?',
  'Who is most overloaded right now?',
  'What should we fix before the next standup?',
]

export default function Chat() {
  const { teamId } = useParams()
  const navigate = useNavigate()
  const [teams, setTeams] = useState([])
  const [selectedTeam, setSelectedTeam] = useState(teamId || '')
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [sessionId, setSessionId] = useState(null)
  const [snapshot, setSnapshot] = useState(null)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    api.getTeams().then(t => {
      setTeams(t)
      if (!selectedTeam && t.length > 0) setSelectedTeam(t[0].id)
    })
  }, [])

  useEffect(() => {
    if (selectedTeam) {
      api.getSnapshot(selectedTeam).then(setSnapshot).catch(() => {})
      setMessages([])
      setSessionId(null)
    }
  }, [selectedTeam])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function send(text) {
    if (!text.trim() || !selectedTeam || streaming) return
    const userMsg = { role: 'user', content: text, timestamp: new Date().toISOString() }
    setMessages(m => [...m, userMsg])
    setInput('')
    setStreaming(true)

    const assistantMsg = { role: 'assistant', content: '', timestamp: new Date().toISOString(), sources: [] }
    setMessages(m => [...m, assistantMsg])

    try {
      let fullText = ''
      let sid = sessionId
      for await (const chunk of api.streamChat(text, selectedTeam, sessionId)) {
        if (typeof chunk === 'object' && chunk.sessionId) {
          sid = chunk.sessionId
          setSessionId(sid)
        } else {
          fullText += chunk
          setMessages(m => {
            const updated = [...m]
            updated[updated.length - 1] = { ...assistantMsg, content: fullText }
            return updated
          })
        }
      }
    } catch (err) {
      // Fallback to non-streaming
      try {
        const data = await api.chat(text, selectedTeam, sessionId)
        if (data.session_id) setSessionId(data.session_id)
        setMessages(m => {
          const updated = [...m]
          updated[updated.length - 1] = {
            ...assistantMsg, content: data.message,
            sources: data.sources_used || [],
          }
          return updated
        })
      } catch(e) {
        setMessages(m => {
          const updated = [...m]
          updated[updated.length - 1] = { ...assistantMsg, content: 'Error connecting to API.' }
          return updated
        })
      }
    }
    setStreaming(false)
    inputRef.current?.focus()
  }

  const team = teams.find(t => t.id === selectedTeam)
  const riskScore = snapshot?.composite_score
  const riskColor = riskScore >= 75 ? 'var(--risk-critical)' : riskScore >= 50 ? 'var(--risk-high)' : riskScore >= 25 ? 'var(--risk-medium)' : 'var(--risk-low)'

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{
        padding: '14px 24px', borderBottom: '1px solid var(--border)',
        background: 'var(--bg-deep)',
        display: 'flex', alignItems: 'center', gap: 16,
        flexShrink: 0,
      }}>
        <span style={{ color: 'var(--amber)', fontSize: 18 }}>◆</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 700 }}>
            AI Risk Coach
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)' }}>
            POWERED BY CLAUDE · GROUNDED IN YOUR JIRA DATA
          </div>
        </div>

        {/* Team selector */}
        <select
          value={selectedTeam}
          onChange={e => setSelectedTeam(e.target.value)}
          style={{
            background: 'var(--bg-card)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius)', padding: '6px 10px',
            color: 'var(--text-primary)', fontFamily: 'var(--font-mono)',
            fontSize: 11, outline: 'none', cursor: 'pointer',
          }}
        >
          {teams.map(t => <option key={t.id} value={t.id}>{t.jira_project_key} — {t.name}</option>)}
        </select>

        {riskScore != null && (
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 11,
            color: riskColor, background: `${riskColor}15`,
            border: `1px solid ${riskColor}40`,
            borderRadius: 'var(--radius)', padding: '5px 10px',
          }}>RISK {riskScore}/100</div>
        )}

        {team && (
          <button onClick={() => navigate(`/dashboard/${team.id}`)} style={{
            background: 'none', border: '1px solid var(--border)',
            borderRadius: 'var(--radius)', padding: '6px 10px',
            color: 'var(--text-muted)', cursor: 'pointer',
            fontFamily: 'var(--font-mono)', fontSize: 9,
          }}>◉ DASHBOARD</button>
        )}
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '24px' }}>
        {messages.length === 0 && (
          <div style={{ maxWidth: 540, margin: '40px auto', textAlign: 'center' }}>
            <div style={{ fontSize: 36, marginBottom: 12 }}>◈</div>
            <h2 style={{
              fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 800,
              color: 'var(--text-primary)', marginBottom: 8,
            }}>What do you want to know?</h2>
            <p style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 28 }}>
              Ask me anything about {team?.name || 'your project'} — sprint health, blockers, velocity, team load.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {STARTERS.map(s => (
                <button key={s} onClick={() => send(s)} style={{
                  background: 'var(--bg-card)', border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-lg)', padding: '10px 16px',
                  color: 'var(--text-secondary)', cursor: 'pointer',
                  fontFamily: 'var(--font-body)', fontSize: 13,
                  textAlign: 'left', transition: 'all 0.15s',
                }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--amber)'; e.currentTarget.style.color = 'var(--amber)' }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text-secondary)' }}
                >{s}</button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <Message
            key={i}
            msg={msg}
            isStreaming={streaming && i === messages.length - 1 && msg.role === 'assistant'}
          />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{
        padding: '16px 24px', borderTop: '1px solid var(--border)',
        background: 'var(--bg-deep)', flexShrink: 0,
      }}>
        <div style={{
          display: 'flex', gap: 10,
          background: 'var(--bg-card)', border: '1px solid var(--border-bright)',
          borderRadius: 'var(--radius-lg)', padding: '8px 8px 8px 16px',
          transition: 'border-color 0.2s',
        }}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) }
            }}
            placeholder="Ask about sprint risks, blockers, velocity..."
            rows={1}
            style={{
              flex: 1, background: 'none', border: 'none', outline: 'none',
              color: 'var(--text-primary)', fontFamily: 'var(--font-body)',
              fontSize: 14, resize: 'none', lineHeight: 1.5,
              maxHeight: 120, overflowY: 'auto',
            }}
          />
          <button
            onClick={() => send(input)}
            disabled={!input.trim() || streaming || !selectedTeam}
            style={{
              background: streaming ? 'var(--bg-deep)' : 'var(--amber)',
              border: 'none', borderRadius: 10,
              width: 38, height: 38, cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 16, flexShrink: 0,
              opacity: (!input.trim() || streaming || !selectedTeam) ? 0.4 : 1,
              transition: 'all 0.15s',
            }}
          >
            {streaming ? (
              <div style={{
                width: 14, height: 14, border: '2px solid var(--amber)',
                borderTopColor: 'transparent', borderRadius: '50%',
                animation: 'spin 0.7s linear infinite',
              }} />
            ) : '↑'}
          </button>
        </div>
        <div style={{ marginTop: 6, fontSize: 9, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', textAlign: 'center' }}>
          ENTER TO SEND · SHIFT+ENTER FOR NEW LINE · CONTEXT: JIRA{snapshot ? ' · RISK SCORE LOADED' : ''}
        </div>
      </div>
    </div>
  )
}
