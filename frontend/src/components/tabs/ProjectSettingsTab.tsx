import { useState } from 'react'
import { Pin, PinOff, Trash2 } from 'lucide-react'
import { api } from '../../api/client'
import { useAsync } from '../../api/hooks'
import { formatBytes, formatRelative } from '../../data/mockData'
import type { ProjectWire, SnapshotWire } from '../../api/types'

const MODEL_OPTIONS = [
  { id: '', label: 'Use global default' },
  { id: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6' },
  { id: 'claude-opus-4-7', label: 'Claude Opus 4.7' },
]

export function ProjectSettingsTab({ project }: { project: ProjectWire & { model_override?: string | null } }) {
  const [model, setModel] = useState<string>(project.model_override ?? '')
  const [savingModel, setSavingModel] = useState(false)
  const [modelMsg, setModelMsg] = useState<string | null>(null)

  const { data: snapshots, loading, error, reload } = useAsync(
    () => api.listSnapshots(project.id),
    [project.id],
  )

  const saveModel = async () => {
    setSavingModel(true)
    setModelMsg(null)
    try {
      await api.setProjectModel(project.id, model.trim() || null)
      setModelMsg('Saved.')
    } catch (err) {
      setModelMsg((err as Error).message)
    } finally {
      setSavingModel(false)
    }
  }

  const pin = async (s: SnapshotWire) => {
    try {
      await api.pinSnapshot(project.id, s.run_id)
      reload()
    } catch (err) {
      console.error(err)
    }
  }

  const drop = async (s: SnapshotWire) => {
    if (!confirm('Delete this snapshot? The corresponding import can no longer be undone.')) return
    try {
      await api.deleteSnapshot(project.id, s.run_id)
      reload()
    } catch (err) {
      console.error(err)
    }
  }

  return (
    <div className="space-y-6">
      <section className="card p-5">
        <h2 className="text-sm font-medium text-zinc-100">Model</h2>
        <p className="mt-1 text-xs text-zinc-500">
          Overrides the global default for this project's imports.
        </p>
        <div className="mt-3 flex items-center gap-3">
          <select
            className="input"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          >
            {MODEL_OPTIONS.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
          <button className="btn-primary" disabled={savingModel} onClick={() => void saveModel()}>
            {savingModel ? 'Saving…' : 'Save'}
          </button>
          {modelMsg && <span className="text-xs text-zinc-400">{modelMsg}</span>}
        </div>
      </section>

      <section className="card overflow-hidden">
        <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
          <div>
            <h2 className="text-sm font-medium text-zinc-100">Snapshots</h2>
            <p className="text-xs text-zinc-500">
              Each completed import keeps a snapshot used by Undo. Pin to protect from the
              retention sweeper.
            </p>
          </div>
          <span className="text-xs text-zinc-500">
            {(snapshots ?? []).length} kept
          </span>
        </div>
        {loading && <p className="p-4 text-sm text-zinc-500">Loading…</p>}
        {error && <p className="p-4 text-sm text-rose-400">{error.message}</p>}
        {!loading && (snapshots?.length ?? 0) === 0 && (
          <p className="p-4 text-sm text-zinc-500">No snapshots yet — they appear after a successful import.</p>
        )}
        {(snapshots ?? []).length > 0 && (
          <ul className="divide-y divide-zinc-900">
            {(snapshots ?? []).map((s) => (
              <li key={s.run_id} className="group flex items-center gap-3 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-mono text-[13px] text-zinc-200">
                    {s.snapshot_db}
                  </p>
                  <p className="mt-0.5 flex items-center gap-2 text-xs text-zinc-500">
                    <span>{formatBytes(s.size_bytes)}</span>
                    {s.finished_at && <span>· kept since {formatRelative(s.finished_at)}</span>}
                    {s.pinned && (
                      <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-1.5 text-[10px] text-amber-300">
                        pinned
                      </span>
                    )}
                  </p>
                </div>
                <button
                  className="btn-ghost text-xs"
                  onClick={() => void pin(s)}
                  title={s.pinned ? 'Unpin' : 'Pin'}
                >
                  {s.pinned ? <PinOff className="h-3.5 w-3.5" /> : <Pin className="h-3.5 w-3.5" />}
                </button>
                <button
                  className="btn-ghost text-xs text-rose-300/80 hover:bg-rose-500/10 hover:text-rose-200"
                  onClick={() => void drop(s)}
                  title="Drop snapshot"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
