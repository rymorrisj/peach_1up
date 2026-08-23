import { Navigate, Outlet, useLocation } from 'react-router-dom';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import { useAppContext } from '@/context/useAppContext';

export function RequireAuth() {
  const { state } = useAppContext();
  const location = useLocation();

  if (!state.authChecked) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-surface-0">
        <LoadingSpinner label="Checking authentication…" />
      </main>
    );
  }

  if (!state.activeUser && !location.pathname.startsWith('/users')) {
    return <Navigate to="/users" replace />;
  }

  return <Outlet />;
}
