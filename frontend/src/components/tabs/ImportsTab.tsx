import { Link } from 'react-router-dom'
import { useEffect, useRef } from 'react'
import { ChevronRight, FileSpreadsheet, Zap } from 'lucide-react'
import { StatusBadge } from '../ui/StatusBadge'
import { FileIcon } from '../ui/FileIcon'
import { api } from '../../api/client'
import { useAsync } from '../../api/hooks'
import type { ImportRunWire } from '../../api/types'
import { formatRelative } from '../../data/mockData'
import clsx from 'clsx'

const ACTIVE_STATUSES = new Set([
  'queued',
  'profiling',
  'generating',
  'executing',
  'fixing',
  'validating',
  'needs_clarification',
])

export function ImportsTab({ projectId, refreshKey }: { projectId: string; refreshKey?: number }) {
  const { data: imports, loading, error, reload } = useAsync(
    () => api.listImports(projectId),
    [projectId, refreshKey ?? 0],
  )

  // Light polling while any run is active. (SSE-per-run powers the detail view;
  // a list-level SSE stream lands in Phase 6.)
  const lastActiveRef = useRef(false)
  const active = (imports ?? []).some((r) => ACTIVE_STATUSES.has(r.status))
  useEffect(() => {
    if (!active) {
      lastActiveRef.current = false
      return
    }
    lastActiveRef.current = true
    const id = setInterval(reload, 2000)
    return () => clearInterval(id)
  }, [active, reload])

  if (loading) return <p className="text-sm text-zinc-500">Loading imports…</p>
  if (error) return <p className="text-sm text-rose-400">{error.message}</p>

  if ((imports?.length ?? 0) === 0) {
    return (
      <div className="card flex flex-col items-center justify-center p-16 text-center">
        <div className="rounded-full border border-zinc-800 bg-zinc-900 p-3">
          <FileSpreadsheet className="h-6 w-6 text-zinc-500" />
        </div>
        <h3 className="mt-4 text-base font-medium">No imports yet</h3>
        <p className="mt-1 max-w-sm text-sm text-zinc-400">
          Click <span className="text-zinc-300">New import</span> above to kick off the pipeline.
        </p>
      </div>
    )
  }

  return (
    <div className="card divide-y divide-zinc-900 overflow-hidden">
      {(imports ?? []).map((r) => (
        <ImportRow key={r.id} run={r} projectId={projectId} />
      ))}
    </div>
  )
}

function ImportRow({ run, projectId }: { run: ImportRunWire; projectId: string }) {
  const showProgress = !['completed', 'failed', 'queued'].includes(run.status)
  return (
    <Link
      to={`/projects/${projectId}/imports/${run.id}`}
      className="group flex items-center gap-4 px-4 py-3 hover:bg-zinc-900/40"
    >
      <FileIcon ext="csv" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-medium text-zinc-100">{run.title}</p>
          <StatusBadge status={run.status} />
          {run.auto_mode && (
            <span className="inline-flex items-center gap-1 rounded-full border border-brand-500/30 bg-brand-500/10 px-1.5 py-0.5 text-[10px] font-medium text-brand-300">
              <Zap className="h-2.5 w-2.5" />
              Auto
            </span>
          )}
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-500">
          <span>{run.status === 'queued' ? 'Queued' : 'Started'} {formatRelative(run.started_at)}</span>
          {run.finished_at && <span>Finished {formatRelative(run.finished_at)}</span>}
          {run.created_tables && run.created_tables.length > 0 && (
            <span>
              Created{' '}
              {run.created_tables.map((t, i) => (
                <span key={t}>
                  <span className="font-mono text-zinc-300">{t}</span>
                  {run.created_tables && i < run.created_tables.length - 1 && ', '}
                </span>
              ))}
            </span>
          )}
          {typeof run.rows_imported === 'number' && (
            <span>{run.rows_imported.toLocaleString()} rows</span>
          )}
        </div>

        {showProgress && (
          <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-zinc-800">
            <div
              className={clsx(
                'h-full rounded-full transition-all',
                run.status === 'needs_clarification'
                  ? 'bg-gradient-to-r from-amber-500 to-amber-300'
                  : run.status === 'fixing'
                    ? 'bg-gradient-to-r from-amber-500 to-orange-400'
                    : 'bg-gradient-to-r from-brand-500 to-emerald-400',
              )}
              style={{ width: `${run.progress}%` }}
            />
          </div>
        )}
      </div>
      <ChevronRight className="h-4 w-4 text-zinc-700 group-hover:text-zinc-400" />
    </Link>
  )
}
