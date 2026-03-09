import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const data = await api.login(email, password)
      if (data.access_token) {
        localStorage.setItem('token', data.access_token)
        navigate('/teams')
      } else {
        setError(data.detail?.[0]?.msg || data.detail || 'Login failed')
      }
    } catch (err) {
      setError('Connection error — is the API running?')
    }
    setLoading(false)
  }

  return (
    <div style={styles.page}>
      <div style={styles.bg} />
      <div style={styles.card}>
        <div style={styles.logo}>
          <span style={styles.logoIcon}>◈</span>
          <span style={styles.logoText}>AGILE INTEL</span>
        </div>
        <p style={styles.tagline}>Risk Intelligence Platform</p>

        <form onSubmit={handleSubmit} style={styles.form}>
          <div style={styles.field}>
            <label style={styles.label}>EMAIL</label>
            <input
              style={styles.input}
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@company.com"
              required
            />
          </div>
          <div style={styles.field}>
            <label style={styles.label}>PASSWORD</label>
            <input
              style={styles.input}
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />
          </div>
          {error && <div style={styles.error}>{error}</div>}
          <button style={{...styles.btn, opacity: loading ? 0.6 : 1}} type="submit" disabled={loading}>
            {loading ? 'AUTHENTICATING...' : 'SIGN IN →'}
          </button>
        </form>

        <div style={styles.footer}>
          <span style={styles.footerDot} />
          <span style={{color: 'var(--text-muted)', fontSize: 11, fontFamily: 'var(--font-mono)'}}>
            SYSTEM ONLINE
          </span>
        </div>
      </div>
    </div>
  )
}

const styles = {
  page: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'var(--bg-void)',
    position: 'relative',
    overflow: 'hidden',
  },
  bg: {
    position: 'absolute', inset: 0,
    background: 'radial-gradient(ellipse at 50% 0%, rgba(245,158,11,0.06) 0%, transparent 60%)',
    pointerEvents: 'none',
  },
  card: {
    width: 380,
    background: 'var(--bg-card)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-xl)',
    padding: '40px 36px',
    boxShadow: '0 0 60px rgba(0,0,0,0.6), 0 0 0 1px rgba(245,158,11,0.05)',
    position: 'relative',
    animation: 'fadeIn 0.4s ease',
  },
  logo: {
    display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6,
  },
  logoIcon: {
    fontSize: 24, color: 'var(--amber)',
  },
  logoText: {
    fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 800,
    color: 'var(--text-primary)', letterSpacing: '0.08em',
  },
  tagline: {
    color: 'var(--text-muted)', fontSize: 12,
    fontFamily: 'var(--font-mono)', marginBottom: 32, letterSpacing: '0.05em',
  },
  form: { display: 'flex', flexDirection: 'column', gap: 18 },
  field: { display: 'flex', flexDirection: 'column', gap: 6 },
  label: {
    fontSize: 10, fontFamily: 'var(--font-mono)', letterSpacing: '0.1em',
    color: 'var(--text-muted)',
  },
  input: {
    background: 'var(--bg-input)', border: '1px solid var(--border)',
    borderRadius: 'var(--radius)', padding: '10px 14px',
    color: 'var(--text-primary)', fontSize: 14, fontFamily: 'var(--font-body)',
    outline: 'none', transition: 'border-color 0.2s',
  },
  error: {
    background: 'var(--red-dim)', border: '1px solid var(--red)',
    borderRadius: 'var(--radius)', padding: '8px 12px',
    color: 'var(--red)', fontSize: 12,
  },
  btn: {
    background: 'var(--amber)', color: '#000',
    border: 'none', borderRadius: 'var(--radius)',
    padding: '12px', fontFamily: 'var(--font-mono)',
    fontWeight: 700, fontSize: 12, letterSpacing: '0.08em',
    cursor: 'pointer', transition: 'all 0.2s',
    marginTop: 4,
  },
  footer: {
    display: 'flex', alignItems: 'center', gap: 8,
    marginTop: 28, paddingTop: 20,
    borderTop: '1px solid var(--border)',
  },
  footerDot: {
    width: 6, height: 6, borderRadius: '50%',
    background: 'var(--green)',
    animation: 'pulse-dot 2s infinite',
    display: 'inline-block',
  },
}
