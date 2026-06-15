import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, setUnauthorizedHandler } from '../api/client'

type AuthStatus = 'loading' | 'authed' | 'anon'

interface AuthState {
  status: AuthStatus
  // True when the server requires a login at all. When false (no password
  // configured), the whole app is open and the login screen is never shown.
  authRequired: boolean
  username: string | null
}

interface AuthContextValue extends AuthState {
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    status: 'loading',
    authRequired: false,
    username: null,
  })

  const refresh = useCallback(async () => {
    try {
      const s = await api.me()
      setState({
        status: s.authenticated ? 'authed' : 'anon',
        authRequired: s.auth_required,
        username: s.username,
      })
    } catch {
      // /me never 401s, so a failure here is a network/server problem. Treat as
      // anonymous-but-required so the user lands on the login screen.
      setState({ status: 'anon', authRequired: true, username: null })
    }
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const s = await api.login(username, password)
    setState({ status: 'authed', authRequired: s.auth_required, username: s.username })
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.logout()
    } finally {
      setState((prev) => ({ status: 'anon', authRequired: prev.authRequired, username: null }))
    }
  }, [])

  // A 401 from any non-auth request means the session lapsed; flip to anon so
  // the route guard sends the user to /login.
  useEffect(() => {
    setUnauthorizedHandler(() =>
      setState((prev) =>
        prev.status === 'authed' ? { ...prev, status: 'anon', username: null } : prev,
      ),
    )
    return () => setUnauthorizedHandler(null)
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return (
    <AuthContext.Provider value={{ ...state, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
