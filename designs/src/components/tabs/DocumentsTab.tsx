import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, FileUp, Filter, Play, Search, Upload } from 'lucide-react'
import { FileIcon } from '../ui/FileIcon'
import { StatusBadge } from '../ui/StatusBadge'
import { formatBytes, formatRelative, getDocuments } from '../../data/mockData'
import clsx from 'clsx'

const filters: { label: string; statuses?: string[] }[] = [
  { label: 'All' },
  { label: 'Ready to import', statuses: ['uploaded'] },
  { label: 'Importing', statuses: ['importing'] },
  { label: 'Imported', statuses: ['imported'] },
  { label: 'Needs input', statuses: ['needs_attention'] },
  { label: 'Failed', statuses: ['failed'] },
]

export function DocumentsTab({
  projectId,
  onNewImport,
}: {
  projectId: string
  onNewImport: () => void
}) {
  const docs = getDocuments(projectId)
  const [query, setQuery] = useState('')
  const [activeFilter, setActiveFilter] = useState(0)

  const filtered = docs.filter((d) => {
    const matchesQuery = d.name.toLowerCase().includes(query.toLowerCase())
    const f = filters[activeFilter]
    const matchesFilter = !f.statuses || f.statuses.includes(d.status)
    return matchesQuery && matchesFilter
  })

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="card p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-medium text-zinc-100">Documents</h2>
            <p className="text-xs text-zinc-500">
              Files uploaded to this project. Each one can be imported into the database.
            </p>
          </div>
          <button onClick={onNewImport} className="btn-primary">
            <Upload className="h-4 w-4" />
            Upload & import
          </button>
        </div>
      </div>

      {/* Drop zone */}
      <label
        className="card flex cursor-pointer flex-col items-center justify-center gap-2 border-dashed py-10 text-center text-sm text-zinc-400 hover:border-brand-500/40 hover:text-brand-300"
      >
        <FileUp className="h-6 w-6" />
        <span className="font-medium">Drop CSV / TSV / XLSX / JSON files here</span>
        <span className="text-xs text-zinc-500">or click to browse — multiple files supported</span>
        <input type="file" multiple className="sr-only" />
      </label>

      {/* Filters */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1">
          {filters.map((f, i) => (
            <button
              key={f.label}
              onClick={() => setActiveFilter(i)}
              className={clsx(
                'rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
                activeFilter === i
                  ? 'bg-zinc-800 text-zinc-100'
                  : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200',
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500" />
          <input
            className="input w-56 pl-8 py-1.5 text-sm"
            placeholder="Search files"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      </div>

      {/* List */}
      <div className="card divide-y divide-zinc-900 overflow-hidden">
        {filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center gap-2 py-10 text-center text-sm text-zinc-500">
            <Filter className="h-5 w-5" />
            No documents match this filter
          </div>
        )}
        {filtered.map((d) => (
          <div key={d.id} className="group flex items-center gap-4 px-4 py-3">
            <FileIcon ext={d.ext} />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <p className="truncate text-sm font-medium text-zinc-100">{d.name}</p>
                <StatusBadge status={d.status} />
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-x-3 text-xs text-zinc-500">
                <span>{formatBytes(d.sizeBytes)}</span>
                <span>Uploaded {formatRelative(d.uploadedAt)}</span>
                {d.columnsPreview && (
                  <span className="truncate font-mono text-zinc-500">
                    {d.columnsPreview.slice(0, 4).join(', ')}{d.columnsPreview.length > 4 ? '…' : ''}
                  </span>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2 opacity-0 transition-opacity group-hover:opacity-100">
              {d.lastImportId ? (
                <Link
                  to={`/projects/${projectId}/imports/${d.lastImportId}`}
                  className="btn-ghost text-xs"
                >
                  View import <ArrowUpRight className="h-3 w-3" />
                </Link>
              ) : (
                <button
                  onClick={onNewImport}
                  className="btn-secondary text-xs"
                >
                  <Play className="h-3 w-3" />
                  Run import
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
