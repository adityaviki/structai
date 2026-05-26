import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowLeft,
  Bot,
  CheckCircle2,
  Circle,
  CircleDashed,
  Code2,
  Hash,
  Hourglass,
  Loader2,
  MessageCircleQuestion,
  Pause,
  Pencil,
  Plus,
  Quote,
  RotateCcw,
  Zap,
  Sparkles,
  XCircle,
} from 'lucide-react'
import { INSTRUCTION_SUGGESTIONS } from '../../data/suggestions'
import clsx from 'clsx'
import {
  formatDuration,
  formatRelative,
  getDocument,
  getImport,
} from '../../data/mockData'
import { FileIcon } from '../ui/FileIcon'
import { StatusBadge } from '../ui/StatusBadge'
import type { Clarification, ImportStatus, PipelineStep, PipelineStepStatus } from '../../types'

export function ImportDetail({ projectId }: { projectId: string }) {
  const { importId = '' } = useParams()
  const navigate = useNavigate()
  const run = getImport(importId)
  if (!run) {
    navigate(`/projects/${projectId}/imports`)
    return null
  }
  const doc = getDocument(run.documentId)
  // Local override so the prototype demonstrates edits without persisting to mock data
  const [instructions, setInstructions] = useState<string>(run.instructions ?? '')
  const editable = run.status !== 'completed' && run.status !== 'failed'

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <Link
          to={`/projects/${projectId}/imports`}
          className="inline-flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-200"
        >
          <ArrowLeft className="h-3 w-3" /> All imports
        </Link>
        <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <FileIcon ext={doc?.ext ?? 'csv'} className="h-10 w-10 text-base" />
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-semibold">{run.title}</h1>
                {run.autoMode && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-brand-500/30 bg-brand-500/10 px-2 py-0.5 text-[11px] font-medium text-brand-300">
                    <Zap className="h-3 w-3" />
                    Auto mode
                  </span>
                )}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-500">
                <StatusBadge status={run.status} />
                <span>{run.status === 'queued' ? 'Queued' : 'Started'} {formatRelative(run.startedAt)}</span>
                {run.finishedAt && <span>· Finished {formatRelative(run.finishedAt)}</span>}
                {typeof run.totalRows === 'number' && (
                  <span>· {(run.rowsImported ?? Math.round((run.progress / 100) * run.totalRows)).toLocaleString()} / {run.totalRows.toLocaleString()} rows</span>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {['executing', 'fixing', 'profiling', 'generating', 'validating'].includes(run.status) && (
              <button className="btn-secondary">
                <Pause className="h-3.5 w-3.5" />
                Pause
              </button>
            )}
            {run.status === 'failed' && (
              <button className="btn-secondary">
                <RotateCcw className="h-3.5 w-3.5" />
                Retry
              </button>
            )}
          </div>
        </div>

        {/* Stepper */}
        <div className="mt-5">
          <Stepper steps={run.steps} />
        </div>
      </div>

      {/* User instructions (editable) */}
      <InstructionsCard
        value={instructions}
        onChange={setInstructions}
        editable={editable}
        autoMode={run.autoMode}
        runStatus={run.status}
      />

      {/* Auto-mode decisions */}
      {run.autoMode && run.autoDecisions && run.autoDecisions.length > 0 && (
        <div className="card overflow-hidden">
          <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
            <div className="flex items-center gap-2">
              <Zap className="h-4 w-4 text-brand-400" />
              <h2 className="text-sm font-medium text-zinc-100">Decisions the agent made on your behalf</h2>
            </div>
            <span className="text-xs text-zinc-500">{run.autoDecisions.length}</span>
          </div>
          <ul className="divide-y divide-zinc-900">
            {run.autoDecisions.map((d, i) => (
              <li key={i} className="px-4 py-3">
                <p className="text-sm text-zinc-200">{d.question}</p>
                <p className="mt-1 text-sm">
                  <span className="text-zinc-500">Chose:</span>{' '}
                  <span className="text-brand-200">{d.choice}</span>
                </p>
                {d.reasoning && (
                  <p className="mt-1 text-xs text-zinc-500 italic">{d.reasoning}</p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Clarifications */}
      {run.clarifications && run.clarifications.length > 0 && (
        <div className="space-y-3">
          {run.clarifications.map((c) => (
            <ClarificationCard key={c.id} clar={c} />
          ))}
        </div>
      )}

      {/* Steps detail */}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-3">
          {run.steps.map((s, idx) => (
            <StepCard key={s.key} step={s} index={idx} />
          ))}
        </div>

        {/* Right rail: agent summary */}
        <aside className="space-y-3">
          <div className="card p-4">
            <div className="flex items-center gap-2 text-sm font-medium text-zinc-100">
              <Bot className="h-4 w-4 text-brand-400" />
              Agent activity
            </div>
            <ul className="mt-3 space-y-3 text-xs text-zinc-400">
              {run.status === 'queued' ? (
                <AgentEvent
                  icon={<Hourglass className="h-3 w-3 text-zinc-400" />}
                  title="Waiting in queue"
                  meta="now"
                  detail="Will start automatically when the running pipeline finishes."
                />
              ) : (
                <>
                  <AgentEvent
                    icon={<Sparkles className="h-3 w-3 text-brand-400" />}
                    title="Profile complete"
                    meta="2s"
                    detail="Inferred 7 columns and 1 PK from sampling 200 rows."
                  />
                  <AgentEvent
                    icon={<Code2 className="h-3 w-3 text-sky-400" />}
                    title="Generated import script"
                    meta="6s"
                    detail="Chose COPY with NULL='' based on detected sentinels."
                  />
                  {run.status === 'fixing' && (
                    <AgentEvent
                      icon={<RotateCcw className="h-3 w-3 text-amber-400" />}
                      title="Fixing date parser"
                      meta="now"
                      detail='Found mixed "7/31/2024" and "2024-07-31" formats; rewrote parser.'
                    />
                  )}
                  {run.status === 'needs_clarification' && (
                    <AgentEvent
                      icon={<MessageCircleQuestion className="h-3 w-3 text-amber-400" />}
                      title="Asked for clarification"
                      meta="2m"
                      detail="Mixed currency rows — needs a decision before continuing."
                    />
                  )}
                  {run.status === 'completed' && (
                    <AgentEvent
                      icon={<CheckCircle2 className="h-3 w-3 text-emerald-400" />}
                      title="Validated"
                      meta="3s"
                      detail="Row counts match. No coercion errors."
                    />
                  )}
                  {run.status === 'failed' && (
                    <AgentEvent
                      icon={<XCircle className="h-3 w-3 text-red-400" />}
                      title="Gave up after 4 fix attempts"
                      meta="2m"
                      detail="Schema mismatch can't be reconciled automatically."
                    />
                  )}
                </>
              )}
            </ul>
          </div>

          {run.createdTables && run.createdTables.length > 0 && (
            <div className="card p-4">
              <p className="text-xs font-medium text-zinc-300">Tables created</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {run.createdTables.map((t) => (
                  <Link
                    key={t}
                    to={`/projects/${projectId}/data`}
                    className="chip font-mono hover:border-brand-500/40 hover:text-brand-300"
                  >
                    <Hash className="h-3 w-3" /> {t}
                  </Link>
                ))}
              </div>
            </div>
          )}

          <div className="card p-4 text-xs text-zinc-400">
            <p className="text-zinc-300">Source document</p>
            <div className="mt-2 flex items-center gap-2">
              <FileIcon ext={doc?.ext ?? 'csv'} />
              <div className="min-w-0">
                <p className="truncate text-zinc-100">{doc?.name}</p>
                <p className="text-[11px] text-zinc-500">
                  Uploaded {doc && formatRelative(doc.uploadedAt)}
                </p>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  )
}

function Stepper({ steps }: { steps: PipelineStep[] }) {
  return (
    <ol className="flex items-center">
      {steps.map((s, i) => {
        const isLast = i === steps.length - 1
        return (
          <li key={s.key} className="flex flex-1 items-center">
            <div className="flex items-center gap-2">
              <StepDot status={s.status} />
              <div>
                <p className="text-xs font-medium text-zinc-200">{s.title}</p>
                <p className="text-[10px] text-zinc-500">
                  {s.status === 'running'
                    ? 'In progress…'
                    : s.status === 'pending'
                      ? 'Waiting'
                      : s.status === 'success' && s.durationMs
                        ? formatDuration(s.durationMs)
                        : s.status === 'error'
                          ? 'Errored'
                          : s.status === 'warning'
                            ? 'Needs input'
                            : ''}
                </p>
              </div>
            </div>
            {!isLast && (
              <div className="mx-3 h-px flex-1 bg-gradient-to-r from-zinc-800 via-zinc-800 to-zinc-800" />
            )}
          </li>
        )
      })}
    </ol>
  )
}

function StepDot({ status }: { status: PipelineStepStatus }) {
  if (status === 'success')
    return (
      <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
        <CheckCircle2 className="h-3.5 w-3.5" />
      </span>
    )
  if (status === 'running')
    return (
      <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-sky-500/15 text-sky-300 border border-sky-500/30">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      </span>
    )
  if (status === 'error')
    return (
      <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-red-500/15 text-red-300 border border-red-500/30">
        <XCircle className="h-3.5 w-3.5" />
      </span>
    )
  if (status === 'warning')
    return (
      <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30">
        <AlertTriangle className="h-3.5 w-3.5" />
      </span>
    )
  return (
    <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-zinc-900 text-zinc-500 border border-zinc-800">
      <Circle className="h-3 w-3" />
    </span>
  )
}

function StepCard({ step, index }: { step: PipelineStep; index: number }) {
  const [open, setOpen] = useState(step.status === 'running' || step.status === 'error' || step.status === 'warning' || step.status === 'success')
  const hasBody = step.summary || step.code || (step.errors && step.errors.length > 0)
  return (
    <div
      className={clsx(
        'card overflow-hidden transition-colors',
        step.status === 'error' && 'border-red-500/30',
        step.status === 'warning' && 'border-amber-500/30',
        step.status === 'running' && 'border-sky-500/30',
      )}
    >
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <div className="flex min-w-0 items-center gap-3">
          <StepDot status={step.status} />
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-[10px] uppercase tracking-wider text-zinc-500">Step {index + 1}</span>
              <h3 className="text-sm font-medium text-zinc-100">{step.title}</h3>
              {step.attempts && step.attempts > 1 && (
                <span className="chip text-amber-300 border-amber-500/30 bg-amber-500/10">
                  attempt {step.attempts}
                </span>
              )}
            </div>
            {step.status === 'pending' ? (
              <p className="mt-0.5 text-xs text-zinc-500">Hasn't started yet</p>
            ) : (
              <p className="mt-0.5 text-xs text-zinc-400">
                {step.status === 'running'
                  ? 'Running now…'
                  : step.durationMs
                    ? `Took ${formatDuration(step.durationMs)}`
                    : ''}
              </p>
            )}
          </div>
        </div>
        <StatusBadge status={step.status} />
      </button>
      {open && hasBody && (
        <div className="space-y-3 border-t border-zinc-800 p-4">
          {step.summary && (
            <p className="text-sm text-zinc-300">{step.summary}</p>
          )}
          {step.errors && step.errors.length > 0 && (
            <div className="rounded-md border border-red-500/30 bg-red-500/5 p-3 text-xs">
              <p className="mb-1 text-red-300">Error log</p>
              <ul className="space-y-1 font-mono text-red-200/80">
                {step.errors.map((e, i) => (
                  <li key={i} className="break-all">{e}</li>
                ))}
              </ul>
            </div>
          )}
          {step.code && (
            <div className="overflow-hidden rounded-md border border-zinc-800 bg-zinc-950">
              <div className="flex items-center justify-between border-b border-zinc-800 px-3 py-1.5 text-[11px] text-zinc-500">
                <span className="font-mono">{step.language ?? 'sql'}</span>
                <button className="text-zinc-500 hover:text-zinc-200">Copy</button>
              </div>
              <pre className="overflow-x-auto px-3 py-3 font-mono text-[12px] leading-relaxed text-zinc-200">
                <code>{step.code}</code>
              </pre>
            </div>
          )}
        </div>
      )}
      {!open && (step.status === 'pending') && (
        <div className="border-t border-zinc-800 px-4 py-3 text-xs text-zinc-500 flex items-center gap-2">
          <CircleDashed className="h-3.5 w-3.5" /> Waiting for previous step to finish
        </div>
      )}
    </div>
  )
}

function InstructionsCard({
  value,
  onChange,
  editable,
  autoMode,
  runStatus,
}: {
  value: string
  onChange: (v: string) => void
  editable: boolean
  autoMode?: boolean
  runStatus: ImportStatus
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)

  const begin = () => {
    setDraft(value)
    setEditing(true)
  }
  const save = () => {
    onChange(draft.trim())
    setEditing(false)
  }
  const cancel = () => {
    setDraft(value)
    setEditing(false)
  }
  const addSuggestion = (s: string) => {
    setDraft((prev) => {
      if (!prev.trim()) return s
      if (prev.includes(s)) return prev
      return prev + (prev.endsWith('\n') ? '' : '\n') + s
    })
  }

  // Empty + read-only (completed/failed) — nothing to show
  if (!value && !editable && !editing) return null

  // Empty + editable — show an "Add instructions" prompt
  if (!value && !editing) {
    return (
      <button
        type="button"
        onClick={begin}
        className="card flex w-full items-center justify-between gap-3 border-dashed p-4 text-left text-sm text-zinc-400 hover:border-brand-500/40 hover:text-brand-300"
      >
        <span className="flex items-center gap-3">
          <span className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-zinc-800 bg-zinc-900">
            <Plus className="h-3.5 w-3.5" />
          </span>
          <span>
            <span className="font-medium text-zinc-200">Add instructions for the agent</span>
            <span className="ml-2 text-xs text-zinc-500">
              Steer how this import should be handled
            </span>
          </span>
        </span>
        <span className="text-xs text-zinc-500">Optional</span>
      </button>
    )
  }

  if (editing) {
    return (
      <div className="card p-4">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Quote className="h-3.5 w-3.5 text-zinc-400" />
            <p className="text-xs font-medium uppercase tracking-wider text-zinc-400">
              {value ? 'Edit instructions' : 'New instructions'}
            </p>
          </div>
          <span className="text-[10px] text-zinc-500">
            {runStatus === 'queued'
              ? 'Will apply when this import starts'
              : 'Will apply to remaining steps'}
          </span>
        </div>
        <textarea
          autoFocus
          className="input mt-3 font-mono text-[13px]"
          rows={4}
          placeholder="e.g. 'Use snake_case for column names', 'Skip rows where email is missing'…"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <div className="mt-2 flex flex-wrap gap-1.5">
          <span className="text-[11px] text-zinc-500">Quick add:</span>
          {INSTRUCTION_SUGGESTIONS.map((s) => {
            const added = draft.includes(s)
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
                {added && '✓ '}
                {s}
              </button>
            )
          })}
        </div>
        <div className="mt-3 flex items-center justify-end gap-2">
          <button className="btn-ghost" onClick={cancel}>
            Cancel
          </button>
          <button className="btn-primary" onClick={save} disabled={draft.trim() === value.trim()}>
            Save instructions
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="card p-4">
      <div className="flex items-start gap-3">
        <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-zinc-800 bg-zinc-900 text-zinc-400">
          <Quote className="h-3.5 w-3.5" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <p className="text-xs font-medium uppercase tracking-wider text-zinc-400">
                Your instructions to the agent
              </p>
              {autoMode && (
                <span className="text-[10px] text-brand-300">· Auto mode — no questions asked</span>
              )}
            </div>
            {editable && (
              <button
                className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
                onClick={begin}
              >
                <Pencil className="h-3 w-3" />
                Edit
              </button>
            )}
          </div>
          <p className="mt-1 whitespace-pre-line text-sm text-zinc-200">{value}</p>
        </div>
      </div>
    </div>
  )
}

function ClarificationCard({ clar }: { clar: Clarification }) {
  const [choice, setChoice] = useState<string | null>(null)
  const [custom, setCustom] = useState('')
  return (
    <div className="card border-amber-500/30 bg-amber-500/5 p-4">
      <div className="flex items-start gap-3">
        <span className="rounded-full border border-amber-500/30 bg-amber-500/15 p-1.5 text-amber-300">
          <MessageCircleQuestion className="h-4 w-4" />
        </span>
        <div className="flex-1">
          <p className="text-sm font-medium text-amber-100">{clar.question}</p>
          <p className="mt-1 text-xs text-amber-200/70">{clar.context}</p>
          <div className="mt-3 space-y-2">
            {clar.options.map((o) => (
              <label
                key={o.id}
                className={clsx(
                  'flex cursor-pointer items-start gap-3 rounded-md border p-3 text-sm transition-colors',
                  choice === o.id
                    ? 'border-brand-500/60 bg-brand-500/5'
                    : 'border-zinc-800 hover:border-zinc-700',
                )}
              >
                <input
                  type="radio"
                  checked={choice === o.id}
                  onChange={() => setChoice(o.id)}
                  className="mt-0.5 accent-brand-500"
                />
                <div>
                  <div className="font-medium text-zinc-100">{o.label}</div>
                  {o.description && (
                    <div className="mt-0.5 text-xs text-zinc-400">{o.description}</div>
                  )}
                </div>
              </label>
            ))}
            <div
              className={clsx(
                'rounded-md border p-3',
                choice === 'custom'
                  ? 'border-brand-500/60 bg-brand-500/5'
                  : 'border-zinc-800',
              )}
            >
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  checked={choice === 'custom'}
                  onChange={() => setChoice('custom')}
                  className="accent-brand-500"
                />
                Custom instruction
              </label>
              <textarea
                className="input mt-2"
                rows={2}
                placeholder="Tell the agent how you'd like to handle this…"
                value={custom}
                onChange={(e) => {
                  setCustom(e.target.value)
                  if (e.target.value) setChoice('custom')
                }}
              />
            </div>
          </div>
          <div className="mt-3 flex items-center justify-end gap-2">
            <button className="btn-ghost">Skip for now</button>
            <button
              className="btn-primary"
              disabled={!choice || (choice === 'custom' && !custom)}
            >
              Continue import
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function AgentEvent({
  icon,
  title,
  meta,
  detail,
}: {
  icon: React.ReactNode
  title: string
  meta: string
  detail: string
}) {
  return (
    <li className="relative pl-5">
      <span className="absolute left-0 top-0.5 flex h-4 w-4 items-center justify-center rounded-full border border-zinc-800 bg-zinc-950">
        {icon}
      </span>
      <div className="flex items-center justify-between text-zinc-200">
        <span className="font-medium">{title}</span>
        <span className="text-[10px] text-zinc-500">{meta}</span>
      </div>
      <p className="mt-0.5 text-zinc-500">{detail}</p>
    </li>
  )
}
