import { useEffect } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'
import { X } from 'lucide-react'
import Sidebar from '@/components/layout/Sidebar'
import HelpBar from '@/components/layout/HelpBar'
import { useAppContext } from '@/context/useAppContext'

export default function AppShell() {
  const { state, dispatch } = useAppContext()
  const navigate = useNavigate()

  useEffect(() => {
    if (state.showUnauthModal) {
      navigate('/users')
    }
  }, [state.showUnauthModal, navigate])

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'rgb(var(--surface-0))' }}>
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden min-w-0">
        {state.showUnauthModal && (
          <div
            role="alert"
            className="flex items-center justify-between gap-3 border-b border-border bg-surface-2 px-4 py-3 text-sm text-neutral-200"
          >
            <span>You have been signed out. Please sign in to continue.</span>
            <button
              type="button"
              aria-label="Dismiss"
              onClick={() => dispatch({ type: 'DISMISS_UNAUTH_MODAL' })}
              className="shrink-0 rounded p-0.5 text-neutral-400 hover:bg-surface-3 hover:text-neutral-100"
            >
              <X size={14} />
            </button>
          </div>
        )}
        <main className="flex-1 overflow-auto" style={{ color: 'rgb(var(--fg-1))' }}>
          <Outlet />
        </main>
        <HelpBar />
      </div>
    </div>
  )
}
