import { useEffect, useRef, useState } from 'react'
import { ArrowUp, Bot, Check, CheckCircle2, RotateCcw, Sparkles, User, X } from 'lucide-react'
import clsx from 'clsx'
import { ApiClientError, api } from '../api/client'
import type { ChatMessageWire, ProposedChangeWire } from '../api/types'
import { Markdown } from './ui/Markdown'

const SUGGESTED_PROMPTS = [
  'Lowercase every customer email',
  "Fill missing values with 'unknown'",
  'Add a full_name column',
  'Find duplicate rows',
  'How many rows per category?',
]

function fmtTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

function tempId(): string {
  return `tmp_${Math.random().toString(36).slice(2, 10)}`
}

export function AIChangesPanel({
  projectId,
  tableName,
  onClose,
  onDataChanged,
}: {
  projectId: string
  tableName?: string
  onClose: () => void
  onDataChanged?: () => void
}) {
  const [messages, setMessages] = useState<ChatMessageWire[]>([])
  const [input, setInput] = useState('')
  const [pending, setPending] = useState(false)
  const [loading, setLoading] = useState(true)
  const [turnError, setTurnError] = useState<string | null>(null)
  const [busyChangeId, setBusyChangeId] = useState<string | null>(null)
  const [changeErrors, setChangeErrors] = useState<Record<string, string>>({})
  const scrollerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api.getChat(projectId).then(
      (thread) => {
        if (!cancelled) {
          setMessages(thread.messages)
          setLoading(false)
        }
      },
      () => {
        if (!cancelled) setLoading(false)
      },
    )
    return () => {
      cancelled = true
    }
  }, [projectId])

  useEffect(() => {
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, pending])

  const patchChange = (change: ProposedChangeWire) => {
    setMessages((m) =>
      m.map((msg) => (msg.change && msg.change.id === change.id ? { ...msg, change } : msg)),
    )
  }

  const submit = async (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || pending) return
    const userMsg: ChatMessageWire = {
      id: tempId(),
      role: 'user',
      content: trimmed,
      change: null,
      created_at: new Date().toISOString(),
    }
    setMessages((m) => [...m, userMsg])
    setInput('')
    setPending(true)
    setTurnError(null)
    try {
      const agentMsg = await api.chatTurn(projectId, trimmed)
      setMessages((m) => [...m, agentMsg])
    } catch (err) {
      setTurnError(err instanceof ApiClientError ? err.detail : (err as Error).message)
    } finally {
      setPending(false)
    }
  }

  const runChangeAction = async (
    changeId: string,
    action: (p: string, c: string) => Promise<ProposedChangeWire>,
    refresh: boolean,
  ) => {
    setBusyChangeId(changeId)
    setChangeErrors((e) => {
      const { [changeId]: _omit, ...rest } = e
      return rest
    })
    try {
      const updated = await action(projectId, changeId)
      patchChange(updated)
      if (refresh) onDataChanged?.()
    } catch (err) {
      const detail = err instanceof ApiClientError ? err.detail : (err as Error).message
      setChangeErrors((e) => ({ ...e, [changeId]: detail }))
    } finally {
      setBusyChangeId(null)
    }
  }

  return (
    <aside className="card flex w-[420px] shrink-0 flex-col overflow-hidden">
      <div className="flex items-center justify-between gap-2 border-b border-zinc-800 p-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-gradient-to-br from-brand-400 to-emerald-700 text-ink shadow-[0_0_18px_-4px_rgba(16,185,129,0.5)]">
            <Sparkles className="h-3.5 w-3.5" />
          </span>
          <div>
            <p className="text-sm font-medium text-zinc-100">AI agent</p>
            <p className="text-[11px] text-zinc-500">
              {tableName ? `Working on ${tableName}` : 'Make changes to your data'}
            </p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="rounded-md p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
          title="Close"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div ref={scrollerRef} className="flex-1 overflow-y-auto p-4">
        {loading ? (
          <p className="text-sm text-zinc-500">Loading conversation…</p>
        ) : messages.length === 0 ? (
          <EmptyState onPick={(s) => void submit(s)} />
        ) : (
          <div className="space-y-4">
            {messages.map((msg) =>
              msg.role === 'user' ? (
                <UserBubble key={msg.id} msg={msg} />
              ) : (
                <AgentBubble
                  key={msg.id}
                  msg={msg}
                  busy={!!msg.change && busyChangeId === msg.change.id}
                  error={msg.change ? changeErrors[msg.change.id] : undefined}
                  onApply={() => void runChangeAction(msg.change!.id, api.applyChange, true)}
                  onReject={() => void runChangeAction(msg.change!.id, api.rejectChange, false)}
                  onUndo={() => void runChangeAction(msg.change!.id, api.undoChange, true)}
                />
              ),
            )}
            {pending && <ThinkingBubble />}
            {turnError && (
              <p className="rounded-md border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
                {turnError}
              </p>
            )}
          </div>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          void submit(input)
        }}
        className="border-t border-zinc-800 bg-zinc-900/30 p-3"
      >
        <div className="relative">
          <textarea
            className="input pr-10 text-sm"
            rows={2}
            placeholder="Describe a change — e.g. 'lowercase all emails', 'dedupe customers by email'…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void submit(input)
              }
            }}
          />
          <button
            type="submit"
            className="absolute bottom-2 right-2 inline-flex h-7 w-7 items-center justify-center rounded-md bg-brand-500 text-ink transition-colors hover:bg-brand-400 disabled:opacity-40"
            disabled={!input.trim() || pending}
            aria-label="Send"
          >
            <ArrowUp className="h-3.5 w-3.5" />
          </button>
        </div>
        <p className="mt-1.5 text-[10px] text-zinc-600">
          Press Enter to send · Shift+Enter for newline · The agent proposes; you approve before
          anything runs
        </p>
      </form>
    </aside>
  )
}

function EmptyState({ onPick }: { onPick: (s: string) => void }) {
  return (
    <div className="flex h-full flex-col">
      <div className="text-sm text-zinc-300">
        Ask the agent to inspect or transform your data — rename columns, fill missing values,
        deduplicate, change types, or answer questions about what's in the tables.
      </div>
      <div className="mt-5 space-y-1">
        <p className="text-[10px] uppercase tracking-wider text-zinc-500">Try one of these</p>
        {SUGGESTED_PROMPTS.map((p) => (
          <button
            key={p}
            onClick={() => onPick(p)}
            className="group flex w-full items-start gap-2 rounded-md border border-zinc-800 bg-zinc-900/40 px-3 py-2 text-left text-sm text-zinc-300 transition-colors hover:border-brand-500/40 hover:text-brand-200"
          >
            <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-zinc-500 group-hover:text-brand-400" />
            <span>{p}</span>
          </button>
        ))}
      </div>
      <div className="mt-auto rounded-md border border-zinc-800 bg-zinc-900/40 p-3 text-[11px] text-zinc-500">
        <p className="flex items-center gap-1 text-zinc-300">
          <CheckCircle2 className="h-3 w-3" /> Every change is reviewable and reversible
        </p>
        <p className="mt-1">
          The agent shows the SQL and affected rows. You approve or reject — and an applied change
          can be undone in one click.
        </p>
      </div>
    </div>
  )
}

function UserBubble({ msg }: { msg: ChatMessageWire }) {
  return (
    <div className="flex justify-end gap-2">
      <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-brand-500/15 px-3 py-2 text-sm text-zinc-100">
        {msg.content}
      </div>
      <span className="mt-1 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-zinc-800 bg-zinc-900 text-zinc-400">
        <User className="h-3 w-3" />
      </span>
    </div>
  )
}

function ThinkingBubble() {
  return (
    <div className="flex items-start gap-2">
      <span className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-400 to-emerald-700 text-ink">
        <Sparkles className="h-3 w-3" />
      </span>
      <div className="rounded-2xl rounded-tl-sm border border-zinc-800 bg-zinc-900/40 px-3 py-2 text-sm text-zinc-400">
        <span className="inline-flex gap-1">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-zinc-500 [animation-delay:-0.3s]" />
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-zinc-500 [animation-delay:-0.15s]" />
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-zinc-500" />
        </span>
      </div>
    </div>
  )
}

function AgentBubble({
  msg,
  busy,
  error,
  onApply,
  onReject,
  onUndo,
}: {
  msg: ChatMessageWire
  busy: boolean
  error?: string
  onApply: () => void
  onReject: () => void
  onUndo: () => void
}) {
  const change = msg.change
  return (
    <div className="flex items-start gap-2">
      <span className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-400 to-emerald-700 text-ink">
        <Bot className="h-3 w-3" />
      </span>
      <div className="min-w-0 flex-1 space-y-2">
        {msg.content && (
          <div className="rounded-2xl rounded-tl-sm border border-zinc-800 bg-zinc-900/40 px-3 py-2 text-sm leading-relaxed text-zinc-200">
            <Markdown text={msg.content} />
          </div>
        )}

        {change && (
          <div className="overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950">
            <div className="flex items-center justify-between gap-2 border-b border-zinc-800 px-3 py-1.5 text-[11px]">
              <div className="flex items-center gap-2 text-zinc-400">
                <span>
                  Affects{' '}
                  <span className="font-mono text-zinc-200">
                    {change.affected_rows?.toLocaleString() ?? '—'}
                  </span>
                  {change.total_rows != null && (
                    <>
                      {' '}of <span className="font-mono text-zinc-200">{change.total_rows.toLocaleString()}</span>
                    </>
                  )}{' '}
                  rows
                  {change.target_table && (
                    <>
                      {' '}in <span className="font-mono text-zinc-200">{change.target_table}</span>
                    </>
                  )}
                </span>
              </div>
              <StatusPill status={change.status} />
            </div>

            {change.preview && change.preview.length > 0 && (
              <div className="border-b border-zinc-800 bg-zinc-900/30 px-3 py-2">
                <p className="mb-1 text-[10px] uppercase tracking-wider text-zinc-500">
                  Before → after
                </p>
                <ul className="space-y-1 font-mono text-[11px]">
                  {change.preview.map((p, i) => (
                    <li key={i} className="flex items-center gap-2">
                      <span className="text-zinc-500">{p.column}:</span>
                      <span className="rounded-sm bg-red-500/10 px-1.5 text-red-200 line-through decoration-red-400/60">
                        {p.before}
                      </span>
                      <span className="text-zinc-600">→</span>
                      <span className="rounded-sm bg-emerald-500/10 px-1.5 text-emerald-200">
                        {p.after}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <pre className="overflow-x-auto px-3 py-2 font-mono text-[12px] leading-relaxed text-zinc-200">
              <code>{change.sql}</code>
            </pre>

            {error && (
              <div className="border-t border-rose-500/20 bg-rose-500/5 px-3 py-2 text-xs text-rose-300">
                {error}
              </div>
            )}

            {change.status === 'proposing' && (
              <div className="flex items-center justify-end gap-2 border-t border-zinc-800 bg-zinc-900/30 px-3 py-2">
                <button onClick={onReject} className="btn-ghost text-xs" disabled={busy}>
                  Reject
                </button>
                <button onClick={onApply} className="btn-primary text-xs" disabled={busy}>
                  <Check className="h-3 w-3" />
                  {busy ? 'Applying…' : 'Apply change'}
                </button>
              </div>
            )}
            {change.status === 'applied' && (
              <div className="flex items-center justify-between gap-2 border-t border-emerald-500/20 bg-emerald-500/5 px-3 py-2 text-xs">
                <span className="inline-flex items-center gap-1.5 text-emerald-300">
                  <CheckCircle2 className="h-3 w-3" />
                  Applied{change.applied_at ? ` at ${fmtTime(change.applied_at)}` : ''}
                </span>
                {change.snapshot_available && (
                  <button
                    onClick={onUndo}
                    disabled={busy}
                    className="inline-flex items-center gap-1 text-zinc-400 hover:text-zinc-100 disabled:opacity-40"
                  >
                    <RotateCcw className="h-3 w-3" />
                    {busy ? 'Undoing…' : 'Undo'}
                  </button>
                )}
              </div>
            )}
            {change.status === 'reverted' && (
              <div className="border-t border-zinc-800 bg-zinc-900/30 px-3 py-2 text-xs text-zinc-500">
                Reverted — the project was restored to before this change.
              </div>
            )}
            {change.status === 'rejected' && (
              <div className="border-t border-zinc-800 bg-zinc-900/30 px-3 py-2 text-xs text-zinc-500">
                Rejected — nothing changed.
              </div>
            )}
            {change.status === 'failed' && (
              <div className="border-t border-rose-500/20 bg-rose-500/5 px-3 py-2 text-xs text-rose-300">
                The change failed to apply — nothing changed.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function StatusPill({ status }: { status: ProposedChangeWire['status'] }) {
  if (status === 'applied')
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-300">
        <CheckCircle2 className="h-2.5 w-2.5" />
        Applied
      </span>
    )
  if (status === 'rejected' || status === 'reverted')
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-zinc-700 bg-zinc-800/60 px-1.5 py-0.5 text-[10px] font-medium text-zinc-400">
        {status === 'reverted' ? 'Reverted' : 'Rejected'}
      </span>
    )
  if (status === 'failed')
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-rose-500/30 bg-rose-500/10 px-1.5 py-0.5 text-[10px] font-medium text-rose-300">
        Failed
      </span>
    )
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-300">
      Pending review
    </span>
  )
}
