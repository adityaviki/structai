import { Link } from 'react-router-dom'

export function Logo({ to = '/' }: { to?: string }) {
  return (
    <Link
      to={to}
      className="group flex items-center gap-2 text-zinc-100 hover:text-zinc-50 transition-colors"
    >
      <span className="relative inline-flex h-7 w-7 items-center justify-center rounded-md bg-gradient-to-br from-brand-400 to-emerald-700 shadow-[0_0_18px_-4px_rgba(16,185,129,0.5)]">
        <svg viewBox="0 0 24 24" className="h-4 w-4 text-ink" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 6h16" />
          <path d="M4 12h10" />
          <path d="M4 18h7" />
          <path d="m17 14 4 4-4 4" />
        </svg>
      </span>
      <span className="font-semibold tracking-tight">
        struct<span className="text-brand-400">AI</span>
      </span>
    </Link>
  )
}
