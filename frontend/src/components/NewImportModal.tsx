import { useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bot, Check, FileUp, MessageCircleQuestion, Sparkles, Zap } from 'lucide-react'
import { Modal } from './ui/Modal'
import { FileIcon } from './ui/FileIcon'
import { StatusBadge } from './ui/StatusBadge'
import { api } from '../api/client'
import { useAsync } from '../api/hooks'
import { formatBytes, formatRelative } from '../data/mockData'
import { INSTRUCTION_SUGGESTIONS } from '../data/suggestions'
import clsx from 'clsx'

export function NewImportModal({
  open,
  onClose,
  projectId,
  onStarted,
}: {
  open: boolean
  onClose: () => void
  projectId: string
  onStarted?: () => void
}) {
  const { data: docs, reload } = useAsync(() => api.listDocuments(projectId), [projectId, open])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [instructions, setInstructions] = useState('')
  const [autoMode, setAutoMode] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()

  const importable = useMemo(
    () => (docs ?? []).filter((d) => d.status === 'uploaded' || d.status === 'failed' || d.status === 'needs_attention'),
    [docs],
  )

  const toggle = (id: string) =>
    setSelected((s) => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const close = () => {
    onClose()
    setSelected(new Set())
    setInstructions('')
    setAutoMode(false)
    setError(null)
    setUploadError(null)
  }

  const upload = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    setUploading(true)
    setUploadError(null)
    const fresh = new Set<string>()
    try {
      for (const f of Array.from(files)) {
        const uploaded = await api.uploadDocument(projectId, f)
        fresh.add(uploaded.id)
      }
      reload()
      // Auto-select the newly uploaded docs so the user can hit Start immediately.
      setSelected((prev) => {
        const next = new Set(prev)
        for (const id of fresh) next.add(id)
        return next
      })
    } catch (err) {
      setUploadError((err as Error).message)
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const start = async () => {
    setSubmitting(true)
    setError(null)
    try {
      const ids = Array.from(selected)
      const runs = await Promise.all(
        ids.map((doc_id) =>
          api.createImport(projectId, {
            document_id: doc_id,
            instructions: instructions.trim() || undefined,
            auto_mode: autoMode,
          }),
        ),
      )
      reload()
      onStarted?.()
      close()
      if (runs.length === 1) {
        navigate(`/projects/${projectId}/imports/${runs[0].id}`)
      } else {
        navigate(`/projects/${projectId}/imports`)
      }
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  const addSuggestion = (s: string) => {
    setInstructions((prev) => {
      if (!prev.trim()) return s
      if (prev.includes(s)) return prev
      const sep = prev.endsWith('\n') ? '' : '\n'
      return prev + sep + s
    })
  }

  return (
    <Modal
      open={open}
      onClose={close}
      title="New import"
      description="Select one or more documents. Each gets its own pipeline and they run one at a time."
      size="lg"
      footer={
        <>
          <button className="btn-ghost" onClick={close}>Cancel</button>
          <button className="btn-primary" disabled={selected.size === 0 || submitting} onClick={() => void start()}>
            <Sparkles className="h-3.5 w-3.5" />
            {submitting
              ? 'Starting…'
              : selected.size === 0
                ? 'Select files'
                : selected.size === 1
                  ? 'Start import'
                  : `Queue ${selected.size} imports`}
          </button>
        </>
      }
    >
      <div className="space-y-5">
        <label
          className={clsx(
            'flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed py-6 text-center text-sm transition-colors',
            uploading
              ? 'border-brand-500/40 bg-brand-500/5 text-brand-200'
              : 'border-zinc-800 bg-zinc-900/40 text-zinc-400 hover:border-brand-500/40 hover:text-brand-300',
          )}
        >
          <FileUp className="h-5 w-5" />
          <span className="font-medium">
            {uploading ? 'Uploading…' : 'Drop CSV / TSV / XLSX / JSON files'}
          </span>
          <span className="text-xs text-zinc-500">
            or click to browse — uploaded files are auto-selected for import
          </span>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.tsv,.xlsx,.json,text/csv,text/tab-separated-values,application/json,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            multiple
            className="sr-only"
            onChange={(e) => void upload(e.target.files)}
          />
        </label>
        {uploadError && <p className="text-sm text-rose-400">{uploadError}</p>}

        <div>
          <div className="mb-2 flex items-baseline justify-between">
            <h3 className="text-xs font-medium uppercase tracking-wider text-zinc-400">Documents</h3>
            <button
              className="text-xs text-zinc-500 hover:text-zinc-200"
              onClick={() => {
                if (selected.size === importable.length) setSelected(new Set())
                else setSelected(new Set(importable.map((d) => d.id)))
              }}
            >
              {selected.size === importable.length && importable.length > 0
                ? 'Clear'
                : 'Select all importable'}
            </button>
          </div>
          <div className="max-h-72 space-y-1 overflow-y-auto pr-1">
            {(docs ?? []).length === 0 && (
              <p className="text-xs text-zinc-500">
                No documents in this project yet — upload one from the Documents tab.
              </p>
            )}
            {(docs ?? []).map((d) => {
              const isSelected = selected.has(d.id)
              const isImportable =
                d.status === 'uploaded' ||
                d.status === 'failed' ||
                d.status === 'needs_attention'
              return (
                <label
                  key={d.id}
                  className={clsx(
                    'flex items-center gap-3 rounded-md border px-3 py-2 text-sm transition-colors',
                    isSelected ? 'border-brand-500/40 bg-brand-500/5' : 'border-zinc-800 hover:border-zinc-700',
                    !isImportable && 'opacity-60',
                  )}
                >
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={isSelected}
                    onChange={() => isImportable && toggle(d.id)}
                    disabled={!isImportable}
                  />
                  <span
                    className={clsx(
                      'inline-flex h-4 w-4 shrink-0 items-center justify-center rounded border',
                      isSelected ? 'border-brand-500 bg-brand-500 text-zinc-950' : 'border-zinc-700 bg-zinc-900',
                    )}
                  >
                    {isSelected && <Check className="h-3 w-3" />}
                  </span>
                  <FileIcon ext={d.ext} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="truncate text-zinc-100">{d.name}</p>
                      <StatusBadge status={d.status} />
                    </div>
                    <p className="mt-0.5 text-xs text-zinc-500">
                      {formatBytes(d.size_bytes)} · {formatRelative(d.uploaded_at)}
                    </p>
                  </div>
                </label>
              )
            })}
          </div>
        </div>

        <div>
          <div className="mb-2 flex items-center gap-2">
            <Bot className="h-3.5 w-3.5 text-brand-400" />
            <h3 className="text-xs font-medium uppercase tracking-wider text-zinc-400">
              Instructions to the agent <span className="ml-1 normal-case text-zinc-600">(optional)</span>
            </h3>
          </div>
          <textarea
            className="input font-mono text-[13px]"
            rows={4}
            placeholder="Anything the agent should know? e.g. 'Use snake_case for column names', 'Treat empty cells as NULL'…"
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
          />
          <div className="mt-2 flex flex-wrap gap-1.5">
            <span className="text-[11px] text-zinc-500">Quick add:</span>
            {INSTRUCTION_SUGGESTIONS.map((s) => {
              const added = instructions.includes(s)
              return (
                <button
                  key={s}
                  type="button"
                  onClick={() => addSuggestion(s)}
                  className={clsx(
                    'rounded-full border px-2 py-0.5 text-[11px] transition-colors',
                    added
                      ? 'border-brand-500/40 bg-brand-500/10 text-brand-200'
                      : 'border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200',
                  )}
                >
                  {added && '✓ '}{s}
                </button>
              )
            })}
          </div>
        </div>

        <button
          type="button"
          onClick={() => setAutoMode((v) => !v)}
          className={clsx(
            'flex w-full items-start gap-3 rounded-lg border p-3 text-left transition-colors',
            autoMode ? 'border-brand-500/40 bg-brand-500/5' : 'border-zinc-800 hover:border-zinc-700',
          )}
        >
          <span className={clsx(
            'inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md transition-colors',
            autoMode ? 'bg-brand-500/20 text-brand-300' : 'bg-zinc-900 text-zinc-400',
          )}>
            {autoMode ? <Zap className="h-4 w-4" /> : <MessageCircleQuestion className="h-4 w-4" />}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-zinc-100">Auto mode</span>
              <span className={clsx(
                'inline-flex items-center rounded-full px-1.5 text-[10px] font-medium uppercase tracking-wider',
                autoMode ? 'bg-brand-500/20 text-brand-300' : 'bg-zinc-800 text-zinc-400',
              )}>
                {autoMode ? 'On' : 'Off'}
              </span>
            </div>
            <p className="mt-0.5 text-xs text-zinc-400">
              {autoMode
                ? "Agent makes its own decisions and won't stop to ask. (Clarifications land in Phase 3 — Phase 1 always runs straight through.)"
                : 'Agent will pause for clarification when needed. (Clarifications land in Phase 3.)'}
            </p>
          </div>
        </button>

        {error && <p className="text-sm text-rose-400">{error}</p>}
      </div>
    </Modal>
  )
}
