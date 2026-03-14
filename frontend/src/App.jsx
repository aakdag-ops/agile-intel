import React, { useState, useEffect } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { getToken } from './lib/api'
import Login from './pages/Login'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Chat from './pages/Chat'
import Timeline from './pages/Timeline'
import Teams from './pages/Teams'
import Transcripts from './pages/Transcripts'
import Healthcheck from './pages/Healthcheck'
import Feed from './pages/Feed'
import Agents from './pages/Agents'

function RequireAuth({ children }) {
  const token = getToken()
  const location = useLocation()
  if (!token) return <Navigate to="/login" state={{ from: location }} replace />
  return children
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={
        <RequireAuth>
          <Layout />
        </RequireAuth>
      }>
        <Route index element={<Navigate to="/teams" replace />} />
        <Route path="teams" element={<Teams />} />
        <Route path="dashboard/:teamId" element={<Dashboard />} />
        <Route path="chat/:teamId?" element={<Chat />} />
        <Route path="timeline/:teamId" element={<Timeline />} />
        <Route path="transcripts/:teamId" element={<Transcripts />} />
        <Route path="healthcheck/:teamId" element={<Healthcheck />} />
        <Route path="feed/:teamId" element={<Feed />} />
        <Route path="agents/:teamId" element={<Agents />} />
      </Route>
    </Routes>
  )
}
