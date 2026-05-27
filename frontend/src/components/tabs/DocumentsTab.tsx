import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, FileUp, Play, Search, Upload } from 'lucide-react'
import { FileIcon } from '../ui/FileIcon'
import { StatusBadge } from '../ui/StatusBadge'
import { api } from '../../api/client'
import { useAsync } from '../../api/hooks'
import { formatBytes, formatRelative } from '../../data/mockData'

export function DocumentsTab({
  projectId,
  onNewImport,
}: {
  projectId: string
  onNewImport: () => void
}) {
  const { data: docs, loading, error, reload } = useAsync(
    () => api.listDocuments(projectId),
    [projectId],
  )
  const [query, setQuery] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const upload = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    setUploading(true)
    setUploadError(null)
    try {
      for (const file of Array.from(files)) {
        await api.uploadDocument(projectId, file)
      }
      reload()
    } catch (err) {
      setUploadError((err as Error).message)
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  const filtered = (docs ?? []).filter((d) =>
    d.name.toLowerCase().includes(query.toLowerCase()),
  )

  return (
    <div className="space-y-4">
      <div className="card p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-medium text-zinc-100">Documents</h2>
            <p className="text-xs text-zinc-500">
              Files uploaded to this project. CSV, TSV, XLSX, JSON.
            </p>
          </div>
          <button onClick={onNewImport} className="btn-primary">
            <Upload className="h-4 w-4" />
            Upload &amp; import
          </button>
        </div>
      </div>

      <label className="card flex cursor-pointer flex-col items-center justify-center gap-2 border-dashed py-10 text-center text-sm text-zinc-400 hover:border-brand-500/40 hover:text-brand-300">
        <FileUp className="h-6 w-6" />
        <span className="font-medium">
          {uploading ? 'Uploading…' : 'Drop CSV / TSV / XLSX / JSON files here'}
        </span>
        <span className="text-xs text-zinc-500">or click to browse — multiple files supported</span>
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.tsv,.xlsx,.json,text/csv,text/tab-separated-values,application/json,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          multiple
          className="sr-only"
          onChange={(e) => void upload(e.target.files)}
        />
      </label>

      {uploadError && <p className="text-sm text-rose-400">{uploadError}</p>}

      <div className="flex items-center justify-end">
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

      {loading && <p className="text-sm text-zinc-500">Loading…</p>}
      {error && <p className="text-sm text-rose-400">{error.message}</p>}

      <div className="card divide-y divide-zinc-900 overflow-hidden">
        {!loading && filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center gap-2 py-10 text-center text-sm text-zinc-500">
            <FileUp className="h-5 w-5" />
            No documents yet — upload one above.
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
                <span>{formatBytes(d.size_bytes)}</span>
                <span>Uploaded {formatRelative(d.uploaded_at)}</span>
              </div>
            </div>
            <div className="flex items-center gap-2 opacity-0 transition-opacity group-hover:opacity-100">
              {d.last_import_id ? (
                <Link
                  to={`/projects/${projectId}/imports/${d.last_import_id}`}
                  className="btn-ghost text-xs"
                >
                  View import <ArrowUpRight className="h-3 w-3" />
                </Link>
              ) : (
                <button onClick={onNewImport} className="btn-secondary text-xs">
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
