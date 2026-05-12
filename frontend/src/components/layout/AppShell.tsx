import { useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import TopBar from './TopBar'
import { useAppContext } from '@/context/AppContext'
import { apiFetch } from '@/api/client'
import type { User } from '@/types'

export default function AppShell() {
  const { dispatch } = useAppContext()

  useEffect(() => {
    apiFetch<User>('/api/v1/auth/me')
      .then((user) => dispatch({ type: 'SET_ACTIVE_USER', payload: user }))
      .catch(() => {/* auth not yet set up — silently ignore */})
  }, [dispatch])

  return (
    <div className="flex h-screen overflow-hidden bg-white dark:bg-surface-950">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-auto p-[1.5em]">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
