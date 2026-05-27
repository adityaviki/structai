import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowLeft,
  Bot,
  CheckCircle2,
  Circle,
  CircleDashed,
  Hash,
  Loader2,
  MessageCircleQuestion,
  Octagon,
  Quote,
  RotateCcw,
  Sparkles,
  Undo2,
  XCircle,
  Zap,
} from 'lucide-react'
import clsx from 'clsx'
import type {
  ClarificationWire,
  ImportRunWire,
  PipelineStepStatus,
  PipelineStepWire,
} from '../../api/types'
import { api, runEventsUrl } from '../../api/client'
import { FileIcon } from '../ui/FileIcon'
import { StatusBadge } from '../ui/StatusBadge'
import { formatDuration, formatRelative } from '../../data/mockData'

const ACTIVE_STATUSES = new Set([
  'queued',
  'profiling',
  'generating',
  'executing',
  'fixing',
  'validating',
  'needs_clarification',
])

const STEP_TITLES: Record<string, string> = {
  profile: 'Profile document',
  generate: 'Generate import script',
  execute: 'Execute import script',
  fix: 'Diagnose & rewrite',
  validate: 'Validate import',
}

export function ImportDetail() {
  const { importId = '' } = useParams()
  const navigate = useNavigate()
  const [run, setRun] = useState<ImportRunWire | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [actionPending, setActionPending] = useState<'cancel' | 'undo' | 'restart' | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [confirmUndo, setConfirmUndo] = useState(false)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    let cancelled = false
    api.getRun(importId).then(
      (r) => {
        if (!cancelled) setRun(r)
      },
      (err: Error) => {
        if (!cancelled) setError(err.message)
      },
    )

    const es = new EventSource(runEventsUrl(importId))
    esRef.current = es

    es.addEventListener('snapshot', (ev) => {
      try {
        const data = JSON.parse((ev as MessageEvent).data) as ImportRunWire
        setRun(data)
      } catch {
        /* ignore */
      }
    })

    es.addEventListener('message', () => {
      // Any backend event → refetch the canonical run for simplicity. Phase 1.
      api.getRun(importId).then(
        (r) => setRun(r),
        () => {},
      )
    })

    es.onerror = () => {
      es.close()
    }

    return () => {
      cancelled = true
      es.close()
    }
  }, [importId])

  if (error) return <p className="text-sm text-rose-400">{error}</p>
  if (!run) return <p className="text-sm text-zinc-500">Loading run…</p>

  const baseSteps = ensureCanonicalSteps(run.steps)
  const projectId = run.project_id
  const isActive = ACTIVE_STATUSES.has(run.status)

  const onStop = async () => {
    if (!confirm('Stop this import? The project database will revert to its state before the import started.')) return
    setActionPending('cancel')
    setActionError(null)
    try {
      await api.cancelRun(run.id)
    } catch (err) {
      setActionError((err as Error).message)
    } finally {
      setActionPending(null)
    }
  }

  const onUndo = async () => {
    setActionPending('undo')
    setActionError(null)
    try {
      const updated = await api.undoRun(run.id)
      setRun(updated)
      setConfirmUndo(false)
    } catch (err) {
      setActionError((err as Error).message)
    } finally {
      setActionPending(null)
    }
  }

  const onRestart = async () => {
    setActionPending('restart')
    setActionError(null)
    try {
      const fresh = await api.restartRun(run.id)
      navigate(`/projects/${run.project_id}/imports/${fresh.id}`)
    } catch (err) {
      setActionError((err as Error).message)
    } finally {
      setActionPending(null)
    }
  }

  const canRestart = ['cancelled', 'failed', 'reverted'].includes(run.status)

  return (
    <div className="space-y-5">
      <div>
        <Link
          to={`/projects/${projectId}/imports`}
          className="inline-flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-200"
        >
          <ArrowLeft className="h-3 w-3" /> All imports
        </Link>
        <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <FileIcon ext="csv" className="h-10 w-10 text-base" />
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-semibold">{run.title}</h1>
                {run.auto_mode && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-brand-500/30 bg-brand-500/10 px-2 py-0.5 text-[11px] font-medium text-brand-300">
                    <Zap className="h-3 w-3" />
                    Auto mode
                  </span>
                )}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-500">
                <StatusBadge status={run.status} />
                <span>{run.status === 'queued' ? 'Queued' : 'Started'} {formatRelative(run.started_at)}</span>
                {run.finished_at && <span>· Finished {formatRelative(run.finished_at)}</span>}
                {typeof run.rows_imported === 'number' && (
                  <span>· {run.rows_imported.toLocaleString()} rows</span>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isActive && run.status !== 'cancelling' && (
              <button
                className="btn-secondary"
                onClick={() => void onStop()}
                disabled={actionPending !== null}
              >
                <Octagon className="h-3.5 w-3.5" />
                {actionPending === 'cancel' ? 'Stopping…' : 'Stop'}
              </button>
            )}
            {canRestart && (
              <button
                className="btn-primary"
                onClick={() => void onRestart()}
                disabled={actionPending !== null}
                title="Start a fresh import on the same document with the same instructions"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                {actionPending === 'restart' ? 'Starting…' : 'Run again'}
              </button>
            )}
            {run.undo_available && (
              <button
                className="btn-secondary"
                onClick={() => setConfirmUndo(true)}
                disabled={actionPending !== null}
              >
                <Undo2 className="h-3.5 w-3.5" />
                Undo
              </button>
            )}
          </div>
        </div>

        {actionError && (
          <p className="mt-2 text-sm text-rose-400">{actionError}</p>
        )}

        <div className="mt-5">
          <Stepper steps={baseSteps} />
        </div>
      </div>

      {confirmUndo && (
        <div className="card border-amber-500/30 bg-amber-500/5 p-4">
          <p className="text-sm font-medium text-amber-100">Undo this import?</p>
          <p className="mt-1 text-xs text-amber-200/80">
            The project database will be restored to its state before this run started.
            Any imports that ran <em>after</em> this one will also be reverted.
          </p>
          <div className="mt-3 flex items-center justify-end gap-2">
            <button
              className="btn-ghost"
              onClick={() => setConfirmUndo(false)}
              disabled={actionPending === 'undo'}
            >
              Cancel
            </button>
            <button
              className="btn-primary"
              onClick={() => void onUndo()}
              disabled={actionPending === 'undo'}
            >
              {actionPending === 'undo' ? 'Undoing…' : 'Confirm undo'}
            </button>
          </div>
        </div>
      )}

      {run.instructions && (
        <div className="card p-4">
          <div className="flex items-start gap-3">
            <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-zinc-800 bg-zinc-900 text-zinc-400">
              <Quote className="h-3.5 w-3.5" />
            </span>
            <div>
              <p className="text-xs font-medium uppercase tracking-wider text-zinc-400">
                Your instructions to the agent
              </p>
              <p className="mt-1 whitespace-pre-line text-sm text-zinc-200">{run.instructions}</p>
            </div>
          </div>
        </div>
      )}

      {(run.clarifications ?? []).filter((c) => !c.answered_at).map((c) => (
        <ClarificationCard key={c.id} clarification={c} onAnswered={(updated) => {
          setRun((prev) => prev ? {
            ...prev,
            clarifications: prev.clarifications.map((x) => x.id === updated.id ? updated : x),
          } : prev)
        }} />
      ))}

      {(run.clarifications ?? []).some((c) => c.auto_decision && c.answered_at) && (
        <div className="card overflow-hidden">
          <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
            <div className="flex items-center gap-2">
              <Zap className="h-4 w-4 text-brand-400" />
              <h2 className="text-sm font-medium text-zinc-100">
                Decisions the agent made on your behalf
              </h2>
            </div>
            <span className="text-xs text-zinc-500">
              {(run.clarifications ?? []).filter((c) => c.auto_decision).length}
            </span>
          </div>
          <ul className="divide-y divide-zinc-900">
            {(run.clarifications ?? [])
              .filter((c) => c.auto_decision && c.answered_at)
              .map((c) => {
                const chosen = c.options.find((o) => o.id === c.answer_choice_id)
                return (
                  <li key={c.id} className="px-4 py-3">
                    <p className="text-sm text-zinc-200">{c.question}</p>
                    <p className="mt-1 text-sm">
                      <span className="text-zinc-500">Chose:</span>{' '}
                      <span className="text-brand-200">{chosen?.label ?? c.answer_choice_id}</span>
                    </p>
                    {c.auto_reasoning && (
                      <p className="mt-1 text-xs text-zinc-500 italic">{c.auto_reasoning}</p>
                    )}
                  </li>
                )
              })}
          </ul>
        </div>
      )}

      {run.error_message && (
        <div className="card border-red-500/30 bg-red-500/5 p-4 text-sm text-red-200">
          <p className="font-medium text-red-100">Run failed</p>
          <p className="mt-1">{run.error_message}</p>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-3">
          {baseSteps.map((s, i) => (
            <StepCard key={`${s.key}-${s.attempts}`} step={s} index={i} />
          ))}
        </div>

        <aside className="space-y-3">
          <div className="card p-4">
            <div className="flex items-center gap-2 text-sm font-medium text-zinc-100">
              <Bot className="h-4 w-4 text-brand-400" />
              Run summary
            </div>
            <dl className="mt-3 space-y-2 text-xs text-zinc-400">
              <Summary label="Status" value={run.status} />
              <Summary label="Progress" value={`${run.progress}%`} />
              {typeof run.rows_imported === 'number' && (
                <Summary label="Rows imported" value={run.rows_imported.toLocaleString()} />
              )}
            </dl>
          </div>

          {run.created_tables && run.created_tables.length > 0 && (
            <div className="card p-4">
              <p className="text-xs font-medium text-zinc-300">Tables created</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {run.created_tables.map((t) => (
                  <Link
                    key={t}
                    to={`/projects/${projectId}/data/${encodeURIComponent(t)}`}
                    className="chip font-mono hover:border-brand-500/40 hover:text-brand-300"
                  >
                    <Hash className="h-3 w-3" /> {t}
                  </Link>
                ))}
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}

function Summary({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-zinc-500">{label}</dt>
      <dd className="text-zinc-200">{value}</dd>
    </div>
  )
}

function ensureCanonicalSteps(received: PipelineStepWire[]): PipelineStepWire[] {
  // Preserve every received step (so all fix attempts show up), but ensure
  // the four canonical ones appear in order even if not yet started. Fix
  // steps slot in between execute attempts.
  const byKeyAttempt = new Map(received.map((s) => [`${s.key}:${s.attempts}`, s] as const))
  const canonical: PipelineStepWire[] = []
  const seen = new Set<string>()

  for (const k of ['profile', 'generate', 'execute', 'validate'] as const) {
    // Find all received entries with this key, sorted by attempts.
    const matches = received.filter((s) => s.key === k).sort((a, b) => a.attempts - b.attempts)
    if (matches.length === 0) {
      canonical.push({
        key: k,
        title: STEP_TITLES[k] ?? k,
        status: 'pending' as PipelineStepStatus,
        summary: null,
        code: null,
        language: null,
        attempts: 1,
        errors: null,
        started_at: null,
        duration_ms: null,
      })
    } else {
      for (const m of matches) {
        canonical.push(m)
        seen.add(`${m.key}:${m.attempts}`)
      }
      // After every execute attempt that failed, insert the matching fix step.
      if (k === 'execute') {
        for (const m of matches) {
          const fixKey: `fix:${number}` = `fix:${m.attempts + 1}`
          const fix = byKeyAttempt.get(fixKey)
          if (fix) {
            canonical.push(fix)
            seen.add(fixKey)
          }
        }
      }
    }
  }

  // Anything left over (defensive).
  for (const s of received) {
    if (!seen.has(`${s.key}:${s.attempts}`)) canonical.push(s)
  }

  return canonical
}

function Stepper({ steps }: { steps: PipelineStepWire[] }) {
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
                      : s.status === 'success' && s.duration_ms
                        ? formatDuration(s.duration_ms)
                        : s.status === 'error'
                          ? 'Errored'
                          : s.status === 'warning'
                            ? 'Warnings'
                            : ''}
                </p>
              </div>
            </div>
            {!isLast && <div className="mx-3 h-px flex-1 bg-zinc-800" />}
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

function StepCard({ step, index }: { step: PipelineStepWire; index: number }) {
  const [open, setOpen] = useState(true)
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
            </div>
            {step.status === 'pending' ? (
              <p className="mt-0.5 text-xs text-zinc-500">Hasn't started yet</p>
            ) : (
              <p className="mt-0.5 text-xs text-zinc-400">
                {step.status === 'running'
                  ? 'Running now…'
                  : step.duration_ms
                    ? `Took ${formatDuration(step.duration_ms)}`
                    : ''}
              </p>
            )}
          </div>
        </div>
        <StatusBadge status={step.status} />
      </button>
      {open && hasBody && (
        <div className="space-y-3 border-t border-zinc-800 p-4">
          {step.summary && <p className="whitespace-pre-line text-sm text-zinc-300">{step.summary}</p>}
          {step.errors && step.errors.length > 0 && (
            <div className="rounded-md border border-red-500/30 bg-red-500/5 p-3 text-xs">
              <p className="mb-1 text-red-300">Error log</p>
              <ul className="space-y-1 font-mono text-red-200/80">
                {step.errors.map((e, i) => (
                  <li key={i} className="whitespace-pre-wrap break-all">{e}</li>
                ))}
              </ul>
            </div>
          )}
          {step.code && (
            <div className="overflow-hidden rounded-md border border-zinc-800 bg-zinc-950">
              <div className="flex items-center justify-between border-b border-zinc-800 px-3 py-1.5 text-[11px] text-zinc-500">
                <span className="font-mono">{step.language ?? 'python'}</span>
              </div>
              <pre className="overflow-x-auto px-3 py-3 font-mono text-[12px] leading-relaxed text-zinc-200">
                <code>{step.code}</code>
              </pre>
            </div>
          )}
        </div>
      )}
      {!open && step.status === 'pending' && (
        <div className="border-t border-zinc-800 px-4 py-3 text-xs text-zinc-500 flex items-center gap-2">
          <CircleDashed className="h-3.5 w-3.5" /> Waiting for previous step to finish
        </div>
      )}
    </div>
  )
}

function ClarificationCard({
  clarification: c,
  onAnswered,
}: {
  clarification: ClarificationWire
  onAnswered: (updated: ClarificationWire) => void
}) {
  const [choice, setChoice] = useState<string | null>(null)
  const [custom, setCustom] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    if (!choice && !custom.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      const updated = await api.answerClarification(c.run_id, c.id, {
        choice_id: choice === '_custom' ? undefined : choice ?? undefined,
        custom: custom.trim() || undefined,
      })
      onAnswered(updated)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="card border-amber-500/30 bg-amber-500/5 p-4">
      <div className="flex items-start gap-3">
        <span className="rounded-full border border-amber-500/30 bg-amber-500/15 p-1.5 text-amber-300">
          <MessageCircleQuestion className="h-4 w-4" />
        </span>
        <div className="flex-1">
          <p className="text-sm font-medium text-amber-100">{c.question}</p>
          {c.context && <p className="mt-1 text-xs text-amber-200/70">{c.context}</p>}
          <div className="mt-3 space-y-2">
            {c.options.map((o) => (
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
                choice === '_custom' ? 'border-brand-500/60 bg-brand-500/5' : 'border-zinc-800',
              )}
            >
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  checked={choice === '_custom'}
                  onChange={() => setChoice('_custom')}
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
                  if (e.target.value) setChoice('_custom')
                }}
              />
            </div>
          </div>
          {error && <p className="mt-2 text-sm text-rose-400">{error}</p>}
          <div className="mt-3 flex items-center justify-end gap-2">
            <button
              className="btn-primary"
              onClick={() => void submit()}
              disabled={submitting || (!choice && !custom.trim()) || (choice === '_custom' && !custom.trim())}
            >
              <Sparkles className="h-3.5 w-3.5" />
              {submitting ? 'Sending…' : 'Continue import'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
