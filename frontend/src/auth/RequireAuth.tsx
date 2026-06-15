import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './AuthContext'

/** Gates its children behind a session. A pass-through when auth is disabled. */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { status, authRequired } = useAuth()
  const location = useLocation()

  if (status === 'loading') {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-zinc-500">
        Loading…
      </div>
    )
  }

  if (authRequired && status !== 'authed') {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }

  return <>{children}</>
}
