import React, { useState, useEffect } from 'react'
import { Outlet, NavLink, useNavigate, useParams } from 'react-router-dom'
import { api } from '../lib/api'

const NAV = [
  { icon: '▦', label: 'TEAMS', path: '/teams' },
]

function RiskBadge({ score }) {
  if (score == null) return null
  const color = score >= 75 ? 'var(--risk-critical)'
    : score >= 50 ? 'var(--risk-high)'
    : score >= 25 ? 'var(--risk-medium)'
    : 'var(--risk-low)'
  return (
    <span style={{
      fontFamily: 'var(--font-mono)', fontSize: 10,
      color, background: `${color}18`,
      border: `1px solid ${color}40`,
      borderRadius: 3, padding: '1px 5px',
    }}>{score}</span>
  )
}

export default function Layout() {
  const navigate = useNavigate()
  const [teams, setTeams] = useState([])
  const [collapsed, setCollapsed] = useState(false)

  useEffect(() => {
    api.getTeams().then(setTeams).catch(() => {})
  }, [])

  function logout() {
    localStorage.removeItem('token')
    navigate('/login')
  }

  const sideW = collapsed ? 56 : 260

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      {/* Sidebar */}
      <aside style={{
        width: sideW, minWidth: sideW,
        background: 'var(--bg-deep)',
        borderRight: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column',
        transition: 'width 0.2s ease',
        overflow: 'hidden',
      }}>
        {/* Logo */}
        <div style={{
          padding: collapsed ? '20px 16px' : '20px 20px',
          borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'space-between',
        }}>
          {!collapsed && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ color: 'var(--amber)', fontSize: 18 }}>◈</span>
              <span style={{
                fontFamily: 'var(--font-display)', fontSize: 15,
                fontWeight: 800, letterSpacing: '0.1em', color: 'var(--text-primary)',
              }}>AGILE INTEL</span>
            </div>
          )}
          {collapsed && <span style={{ color: 'var(--amber)', fontSize: 18 }}>◈</span>}
          <button onClick={() => setCollapsed(!collapsed)} style={{
            background: 'none', border: 'none', color: 'var(--text-muted)',
            cursor: 'pointer', fontSize: 14, padding: 2,
          }}>{collapsed ? '»' : '«'}</button>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: '12px 0', overflowY: 'auto' }}>
          {/* Static links */}
          {[
            { icon: '▦', label: 'TEAMS', path: '/teams' },
          ].map(item => (
            <NavLink key={item.path} to={item.path} style={({ isActive }) => ({
              display: 'flex', alignItems: 'center',
              gap: 10, padding: collapsed ? '10px 16px' : '10px 20px',
              color: isActive ? 'var(--amber)' : 'var(--text-secondary)',
              background: isActive ? 'var(--amber-glow)' : 'transparent',
              textDecoration: 'none', fontSize: 13,
              fontFamily: 'var(--font-mono)', letterSpacing: '0.08em',
              borderLeft: isActive ? '2px solid var(--amber)' : '2px solid transparent',
              transition: 'all 0.15s',
            })}>
              <span style={{ fontSize: 15, minWidth: 16, textAlign: 'center' }}>{item.icon}</span>
              {!collapsed && item.label}
            </NavLink>
          ))}

          {/* Teams list */}
          {teams.length > 0 && !collapsed && (
            <div style={{ marginTop: 16 }}>
              <div style={{
                padding: '6px 20px', fontSize: 11,
                fontFamily: 'var(--font-mono)', color: 'var(--text-muted)',
                letterSpacing: '0.12em',
              }}>PROJECTS</div>
              {teams.map(team => (
                <div key={team.id} style={{ marginBottom: 4 }}>
                  {/* Team name header */}
                  <div style={{
                    padding: '8px 20px 4px 20px',
                    fontSize: 11, fontFamily: 'var(--font-mono)',
                    color: 'var(--text-muted)', letterSpacing: '0.1em',
                    display: 'flex', alignItems: 'center', gap: 6,
                  }}>
                    <span style={{ color: 'var(--amber)', fontSize: 10 }}>◆</span>
                    {team.jira_project_key} · {team.name}
                  </div>
                  {/* Sub-links */}
                  {[
                    { icon: '◉', label: 'DASHBOARD', path: `/dashboard/${team.id}` },
                    { icon: '◆', label: 'CHAT', path: `/chat/${team.id}` },
                    { icon: '◈', label: 'TIMELINE', path: `/timeline/${team.id}` },
                    { icon: '⬡', label: 'FEED', path: `/feed/${team.id}` },
                    { icon: '▶', label: 'AGENTS', path: `/agents/${team.id}` },
                  ].map(item => (
                    <NavLink key={item.path} to={item.path} style={({ isActive }) => ({
                      display: 'flex', alignItems: 'center',
                      gap: 8, padding: '8px 20px 8px 32px',
                      color: isActive ? 'var(--amber)' : 'var(--text-muted)',
                      background: isActive ? 'var(--amber-glow)' : 'transparent',
                      textDecoration: 'none', fontSize: 12,
                      fontFamily: 'var(--font-mono)', letterSpacing: '0.06em',
                      borderLeft: isActive ? '2px solid var(--amber)' : '2px solid transparent',
                      transition: 'all 0.15s',
                    })}>
                      <span style={{ fontSize: 12 }}>{item.icon}</span>
                      {item.label}
                    </NavLink>
                  ))}
                </div>
              ))}
            </div>
          )}
        </nav>

        {/* Bottom */}
        <div style={{
          padding: collapsed ? '16px' : '16px 20px',
          borderTop: '1px solid var(--border)',
        }}>
          <button onClick={logout} style={{
            background: 'none', border: '1px solid var(--border)',
            borderRadius: 'var(--radius)', color: 'var(--text-muted)',
            cursor: 'pointer', fontSize: 12,
            fontFamily: 'var(--font-mono)', letterSpacing: '0.06em',
            padding: collapsed ? '8px' : '8px 12px',
            width: '100%', transition: 'all 0.15s',
          }}>
            {collapsed ? '⇐' : 'SIGN OUT'}
          </button>
        </div>
      </aside>

      {/* Main */}
      <main style={{
        flex: 1, overflow: 'auto',
        background: 'var(--bg-void)',
      }}>
        <Outlet />
      </main>
    </div>
  )
}
