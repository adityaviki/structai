import { Link } from 'react-router-dom'
import { ChevronRight, FileSpreadsheet, Zap } from 'lucide-react'
import { StatusBadge } from '../ui/StatusBadge'
import { FileIcon } from '../ui/FileIcon'
import { formatRelative, getDocument, getImports } from '../../data/mockData'
import type { ImportRun } from '../../types'
import clsx from 'clsx'

export function ImportsTab({ projectId }: { projectId: string }) {
  const imports = [...getImports(projectId)].sort(
    (a, b) => new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime(),
  )

  if (imports.length === 0) {
    return (
      <div className="card flex flex-col items-center justify-center p-16 text-center">
        <div className="rounded-full border border-zinc-800 bg-zinc-900 p-3">
          <FileSpreadsheet className="h-6 w-6 text-zinc-500" />
        </div>
        <h3 className="mt-4 text-base font-medium">No imports yet</h3>
        <p className="mt-1 max-w-sm text-sm text-zinc-400">
          Start a new import to kick off the agentic pipeline.
        </p>
      </div>
    )
  }

  return (
    <div className="card divide-y divide-zinc-900 overflow-hidden">
      {imports.map((r) => (
        <ImportRow key={r.id} run={r} projectId={projectId} />
      ))}
    </div>
  )
}

function ImportRow({ run, projectId }: { run: ImportRun; projectId: string }) {
  const doc = getDocument(run.documentId)
  const showProgress = run.status !== 'completed' && run.status !== 'failed' && run.status !== 'queued'
  return (
    <Link
      to={`/projects/${projectId}/imports/${run.id}`}
      className="group flex items-center gap-4 px-4 py-3 hover:bg-zinc-900/40"
    >
      <FileIcon ext={doc?.ext ?? 'csv'} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-medium text-zinc-100">{run.title}</p>
          <StatusBadge status={run.status} />
          {run.autoMode && (
            <span className="inline-flex items-center gap-1 rounded-full border border-brand-500/30 bg-brand-500/10 px-1.5 py-0.5 text-[10px] font-medium text-brand-300">
              <Zap className="h-2.5 w-2.5" />
              Auto
            </span>
          )}
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-500">
          <span>{run.status === 'queued' ? 'Queued' : 'Started'} {formatRelative(run.startedAt)}</span>
          {run.finishedAt && <span>Finished {formatRelative(run.finishedAt)}</span>}
          {run.createdTables && run.createdTables.length > 0 && (
            <span>
              Created{' '}
              {run.createdTables.map((t, i) => (
                <span key={t}>
                  <span className="font-mono text-zinc-300">{t}</span>
                  {i < run.createdTables!.length - 1 && ', '}
                </span>
              ))}
            </span>
          )}
          {typeof run.rowsImported === 'number' && (
            <span>{run.rowsImported.toLocaleString()} rows</span>
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
