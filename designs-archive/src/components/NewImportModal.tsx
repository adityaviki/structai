import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bot, Check, FileUp, MessageCircleQuestion, Sparkles, Zap } from 'lucide-react'
import { Modal } from './ui/Modal'
import { FileIcon } from './ui/FileIcon'
import { formatBytes, formatRelative, getDocuments } from '../data/mockData'
import { INSTRUCTION_SUGGESTIONS } from '../data/suggestions'
import { StatusBadge } from './ui/StatusBadge'
import clsx from 'clsx'

export function NewImportModal({
  open,
  onClose,
  projectId,
}: {
  open: boolean
  onClose: () => void
  projectId: string
}) {
  const docs = getDocuments(projectId)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [instructions, setInstructions] = useState('')
  const [autoMode, setAutoMode] = useState(false)
  const navigate = useNavigate()

  const importable = useMemo(
    () => docs.filter((d) => d.status === 'uploaded' || d.status === 'failed' || d.status === 'needs_attention'),
    [docs],
  )

  const toggle = (id: string) =>
    setSelected((s) => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const start = () => {
    onClose()
    setSelected(new Set())
    setInstructions('')
    setAutoMode(false)
    if (selected.size === 1) {
      // navigate to the import detail using the first doc's last import id, or imports tab
      const doc = docs.find((d) => selected.has(d.id))
      navigate(`/projects/${projectId}/imports${doc?.lastImportId ? `/${doc.lastImportId}` : ''}`)
    } else {
      navigate(`/projects/${projectId}/imports`)
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
      onClose={onClose}
      title="New import"
      description="Select one or more documents. Each gets its own pipeline and they run one at a time, in the order you pick them."
      size="lg"
      footer={
        <>
          <button className="btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn-primary"
            disabled={selected.size === 0}
            onClick={start}
          >
            <Sparkles className="h-3.5 w-3.5" />
            {selected.size === 0
              ? 'Select files'
              : selected.size === 1
                ? 'Start import'
                : `Queue ${selected.size} imports`}
          </button>
        </>
      }
    >
      <div className="space-y-5">
        {/* Drop zone */}
        <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-zinc-800 bg-zinc-900/40 py-6 text-center text-sm text-zinc-400 hover:border-brand-500/40 hover:text-brand-300">
          <FileUp className="h-5 w-5" />
          <span className="font-medium">Drop new files or click to upload</span>
          <span className="text-xs text-zinc-500">CSV · TSV · XLSX · JSON</span>
          <input type="file" multiple className="sr-only" />
        </label>

        <div>
          <div className="mb-2 flex items-baseline justify-between">
            <h3 className="text-xs font-medium uppercase tracking-wider text-zinc-400">
              Existing documents
            </h3>
            <button
              className="text-xs text-zinc-500 hover:text-zinc-200"
              onClick={() => {
                if (selected.size === importable.length) setSelected(new Set())
                else setSelected(new Set(importable.map((d) => d.id)))
              }}
            >
              {selected.size === importable.length ? 'Clear' : 'Select all importable'}
            </button>
          </div>
          <div className="max-h-72 space-y-1 overflow-y-auto pr-1">
            {docs.map((d) => {
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
                    isSelected
                      ? 'border-brand-500/40 bg-brand-500/5'
                      : 'border-zinc-800 hover:border-zinc-700',
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
                      isSelected
                        ? 'border-brand-500 bg-brand-500 text-zinc-950'
                        : 'border-zinc-700 bg-zinc-900',
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
                      {formatBytes(d.sizeBytes)} · {formatRelative(d.uploadedAt)}
                    </p>
                  </div>
                </label>
              )
            })}
          </div>
        </div>

        {/* Instructions to the agent */}
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
            placeholder={selected.size > 1
              ? "Anything the agent should know across all of these imports? e.g. 'Treat empty cells as NULL', 'Keep table names lowercase', 'Trim whitespace from text columns'…"
              : "Anything the agent should know? e.g. 'Use snake_case for column names', 'Skip rows where email is missing', 'order_date is in MM/DD/YYYY format'…"}
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
          {selected.size > 1 && (
            <p className="mt-2 text-[11px] text-zinc-500">
              These instructions apply to all {selected.size} selected imports.
            </p>
          )}
        </div>

        {/* Auto mode toggle */}
        <button
          type="button"
          onClick={() => setAutoMode((v) => !v)}
          className={clsx(
            'flex w-full items-start gap-3 rounded-lg border p-3 text-left transition-colors',
            autoMode
              ? 'border-brand-500/40 bg-brand-500/5'
              : 'border-zinc-800 hover:border-zinc-700',
          )}
        >
          <span
            className={clsx(
              'inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md transition-colors',
              autoMode
                ? 'bg-brand-500/20 text-brand-300'
                : 'bg-zinc-900 text-zinc-400',
            )}
          >
            {autoMode ? <Zap className="h-4 w-4" /> : <MessageCircleQuestion className="h-4 w-4" />}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-zinc-100">Auto mode</span>
              <span
                className={clsx(
                  'inline-flex items-center rounded-full px-1.5 text-[10px] font-medium uppercase tracking-wider',
                  autoMode
                    ? 'bg-brand-500/20 text-brand-300'
                    : 'bg-zinc-800 text-zinc-400',
                )}
              >
                {autoMode ? 'On' : 'Off'}
              </span>
            </div>
            <p className="mt-0.5 text-xs text-zinc-400">
              {autoMode
                ? "The agent will make its own best-effort decisions and won't stop to ask. Decisions get logged so you can review them later."
                : 'The agent will pause and ask whenever it has to make a judgment call you should be aware of.'}
            </p>
          </div>
          <span
            className={clsx(
              'relative mt-0.5 inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors',
              autoMode ? 'bg-brand-500' : 'bg-zinc-700',
            )}
          >
            <span
              className={clsx(
                'inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform',
                autoMode ? 'translate-x-4' : 'translate-x-0.5',
              )}
            />
          </span>
        </button>

        {selected.size > 1 && (
          <div className="rounded-md border border-sky-500/30 bg-sky-500/5 p-3 text-xs text-sky-100">
            <strong>{selected.size} pipelines</strong> will be queued — the first starts now, the
            rest run one after another. Watch progress on the Imports tab.
          </div>
        )}
      </div>
    </Modal>
  )
}
