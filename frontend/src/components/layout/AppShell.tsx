import { useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from '@/components/layout/Sidebar'
import HelpBar from '@/components/layout/HelpBar'
import { useAppContext } from '@/context/AppContext'
import { apiFetch } from '@/api/client'
import type { components } from '@shared/types'
type User = components['schemas']['UserRead']

export default function AppShell() {
  const { dispatch } = useAppContext()

  useEffect(() => {
    apiFetch<User>('/api/v1/auth/me')
      .then((user) => dispatch({ type: 'SET_ACTIVE_USER', payload: user }))
      .catch(() => {/* auth not yet set up */})
  }, [dispatch])

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'var(--surface-0)' }}>
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden min-w-0">
        <main className="flex-1 overflow-auto" style={{ color: 'var(--fg-1)' }}>
          <Outlet />
        </main>
        <HelpBar />
      </div>
    </div>
  )
}
