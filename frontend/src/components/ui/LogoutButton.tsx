import { LogOut } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../auth/AuthContext'

/** Sign-out control. Renders nothing when auth is disabled on the server. */
export function LogoutButton() {
  const { authRequired, username, logout } = useAuth()
  const navigate = useNavigate()

  if (!authRequired) return null

  const onClick = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <button
      onClick={onClick}
      className="btn-ghost"
      title={username ? `Sign out (${username})` : 'Sign out'}
      aria-label="Sign out"
    >
      <LogOut className="h-4 w-4" />
    </button>
  )
}
