import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { Outlet, useNavigate } from 'react-router-dom'
import { X } from 'lucide-react'
import Sidebar from '@/components/layout/Sidebar'
import HelpBar from '@/components/layout/HelpBar'
import ToastItem from '@/components/common/ToastItem'
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
    <div className="flex h-screen overflow-hidden" style={{ background: 'var(--surface-0)' }}>
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden min-w-0">
        {state.showUnauthModal && (
          <div
            role="alert"
            className="flex items-center justify-between gap-3 border-b border-surface-700 bg-surface-800 px-4 py-3 text-sm text-neutral-200"
          >
            <span>You have been signed out. Please sign in to continue.</span>
            <button
              type="button"
              aria-label="Dismiss"
              onClick={() => dispatch({ type: 'DISMISS_UNAUTH_MODAL' })}
              className="shrink-0 rounded p-0.5 text-neutral-400 hover:bg-surface-700 hover:text-neutral-100"
            >
              <X size={14} />
            </button>
          </div>
        )}
        <main className="flex-1 overflow-auto" style={{ color: 'var(--fg-1)' }}>
          <Outlet />
        </main>
        <HelpBar />
      </div>
      {createPortal(
        <div
          style={{
            position: 'fixed',
            bottom: '1rem',
            right: '1rem',
            zIndex: 9999,
            display: 'flex',
            flexDirection: 'column',
            gap: '0.5rem',
            width: '20rem',
            pointerEvents: state.toasts.length > 0 ? 'auto' : 'none',
          }}
        >
          {state.toasts.map((toast) => (
            <ToastItem
              key={toast.id}
              id={toast.id}
              message={toast.message}
              onDismiss={(id) => dispatch({ type: 'DISMISS_TOAST', payload: id })}
            />
          ))}
        </div>,
        document.body
      )}
    </div>
  )
}
