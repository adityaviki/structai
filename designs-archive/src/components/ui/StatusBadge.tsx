import clsx from 'clsx'
import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  CircleHelp,
  Hourglass,
  Loader2,
  Wrench,
  XCircle,
} from 'lucide-react'
import type { DocumentStatus, ImportStatus, PipelineStepStatus } from '../../types'

type AnyStatus = ImportStatus | DocumentStatus | PipelineStepStatus

const config: Record<
  AnyStatus,
  { label: string; tone: string; Icon: React.ComponentType<{ className?: string }>; spin?: boolean }
> = {
  /* Import */
  queued: { label: 'Queued', tone: 'text-zinc-400 bg-zinc-800/60 border-zinc-700/60', Icon: Hourglass },
  profiling: { label: 'Profiling', tone: 'text-sky-300 bg-sky-500/10 border-sky-500/30', Icon: Loader2, spin: true },
  generating: { label: 'Generating', tone: 'text-sky-300 bg-sky-500/10 border-sky-500/30', Icon: Loader2, spin: true },
  executing: { label: 'Executing', tone: 'text-sky-300 bg-sky-500/10 border-sky-500/30', Icon: Loader2, spin: true },
  fixing: { label: 'Fixing', tone: 'text-amber-300 bg-amber-500/10 border-amber-500/30', Icon: Wrench },
  validating: { label: 'Validating', tone: 'text-sky-300 bg-sky-500/10 border-sky-500/30', Icon: Loader2, spin: true },
  needs_clarification: {
    label: 'Needs input',
    tone: 'text-amber-300 bg-amber-500/10 border-amber-500/30',
    Icon: CircleHelp,
  },
  completed: { label: 'Imported', tone: 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30', Icon: CheckCircle2 },
  failed: { label: 'Failed', tone: 'text-red-300 bg-red-500/10 border-red-500/30', Icon: XCircle },

  /* Documents */
  uploaded: { label: 'Ready to import', tone: 'text-zinc-300 bg-zinc-800/60 border-zinc-700/60', Icon: CircleDashed },
  importing: { label: 'Importing', tone: 'text-sky-300 bg-sky-500/10 border-sky-500/30', Icon: Loader2, spin: true },
  imported: { label: 'Imported', tone: 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30', Icon: CheckCircle2 },
  needs_attention: { label: 'Needs input', tone: 'text-amber-300 bg-amber-500/10 border-amber-500/30', Icon: AlertTriangle },

  /* Pipeline */
  pending: { label: 'Pending', tone: 'text-zinc-400 bg-zinc-800/40 border-zinc-700/60', Icon: CircleDashed },
  running: { label: 'Running', tone: 'text-sky-300 bg-sky-500/10 border-sky-500/30', Icon: Loader2, spin: true },
  success: { label: 'Done', tone: 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30', Icon: CheckCircle2 },
  error: { label: 'Error', tone: 'text-red-300 bg-red-500/10 border-red-500/30', Icon: XCircle },
  warning: { label: 'Needs input', tone: 'text-amber-300 bg-amber-500/10 border-amber-500/30', Icon: AlertTriangle },
}

export function StatusBadge({
  status,
  className,
  size = 'sm',
}: {
  status: AnyStatus
  className?: string
  size?: 'sm' | 'md'
}) {
  const c = config[status]
  const Icon = c.Icon
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full border px-2 font-medium',
        size === 'sm' ? 'py-0.5 text-[11px]' : 'py-1 text-xs',
        c.tone,
        className,
      )}
    >
      <Icon className={clsx('h-3 w-3 shrink-0', c.spin && 'animate-spin')} />
      {c.label}
    </span>
  )
}
