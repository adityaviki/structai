import { useEffect, useRef, useState } from 'react'
import {
  ArrowUp,
  Bot,
  Check,
  CheckCircle2,
  History,
  Sparkles,
  Trash2,
  User,
  X,
} from 'lucide-react'
import clsx from 'clsx'

type ProposedChange = {
  table: string
  affectedRows: number
  totalRows: number
  sql: string
  /** Optional "before / after" snippet to show as a diff hint */
  preview?: { before: string; after: string; column: string }[]
}

type ChatMessage =
  | { id: string; role: 'user'; text: string; ts: string }
  | {
      id: string
      role: 'agent'
      explanation: string
      change?: ProposedChange
      status: 'proposing' | 'applied' | 'rejected' | 'thinking'
      ts: string
    }

const SUGGESTED_PROMPTS = [
  'Lowercase every customer email',
  "Fill missing `segment` values with 'unknown'",
  'Add a `full_name` column to customers',
  'Find duplicate customers by email',
  'Convert all `price_usd` values to cents',
]

const now = () =>
  new Date().toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })

function mockAgentResponse(prompt: string): ChatMessage {
  const p = prompt.toLowerCase()
  const id = `m_${Math.random().toString(36).slice(2, 9)}`

  if (p.includes('email') && (p.includes('lower') || p.includes('case'))) {
    return {
      id,
      role: 'agent',
      explanation:
        "I'll normalize the `email` column in `customers` to lowercase. 3 of the 10 sample rows contain uppercase characters so they'd change.",
      status: 'proposing',
      ts: now(),
      change: {
        table: 'customers',
        affectedRows: 3,
        totalRows: 4821,
        sql: `UPDATE customers
SET email = LOWER(email)
WHERE email <> LOWER(email);`,
        preview: [
          { column: 'email', before: 'Olivia.B@example.co.uk', after: 'olivia.b@example.co.uk' },
          { column: 'email', before: 'D.Muller@example.de', after: 'd.muller@example.de' },
          { column: 'email', before: 'Hiro.Tanaka@example.jp', after: 'hiro.tanaka@example.jp' },
        ],
      },
    }
  }

  if (p.includes('segment') || (p.includes('missing') && p.includes('fill'))) {
    return {
      id,
      role: 'agent',
      explanation:
        "I'll fill rows where `segment` is NULL with `'unknown'`. 1 sample row is affected; the full table has 312 NULLs.",
      status: 'proposing',
      ts: now(),
      change: {
        table: 'customers',
        affectedRows: 312,
        totalRows: 4821,
        sql: `UPDATE customers
SET segment = 'unknown'
WHERE segment IS NULL;`,
        preview: [
          { column: 'segment', before: 'NULL', after: 'unknown' },
        ],
      },
    }
  }

  if (p.includes('full_name') || (p.includes('add') && p.includes('column'))) {
    return {
      id,
      role: 'agent',
      explanation:
        "I'll add a derived `full_name` column to `customers` computed from `first_name || ' ' || last_name`. It'll backfill all 4,821 rows.",
      status: 'proposing',
      ts: now(),
      change: {
        table: 'customers',
        affectedRows: 4821,
        totalRows: 4821,
        sql: `ALTER TABLE customers
  ADD COLUMN full_name TEXT
  GENERATED ALWAYS AS (first_name || ' ' || last_name) STORED;`,
        preview: [
          { column: 'full_name', before: '—', after: 'Amelia Chen' },
          { column: 'full_name', before: '—', after: 'Lukas Bauer' },
        ],
      },
    }
  }

  if (p.includes('duplicate')) {
    return {
      id,
      role: 'agent',
      explanation:
        "I scanned `customers` for duplicate emails — found 14 emails that appear more than once (28 rows total). I can either keep the earliest signup or merge them. Which do you want?",
      status: 'proposing',
      ts: now(),
      change: {
        table: 'customers',
        affectedRows: 14,
        totalRows: 4821,
        sql: `-- Option: keep earliest signup_date, delete the rest
DELETE FROM customers a
USING customers b
WHERE a.email = b.email
  AND a.signup_date > b.signup_date;`,
      },
    }
  }

  if (p.includes('cent') || p.includes('price')) {
    return {
      id,
      role: 'agent',
      explanation:
        "I'll convert `products.price_usd` (numeric) to integer cents. This is a destructive type change so I'll do it via a new column and drop the old one.",
      status: 'proposing',
      ts: now(),
      change: {
        table: 'products',
        affectedRows: 312,
        totalRows: 312,
        sql: `ALTER TABLE products ADD COLUMN price_cents INTEGER;
UPDATE products SET price_cents = ROUND(price_usd * 100);
ALTER TABLE products DROP COLUMN price_usd;
ALTER TABLE products RENAME COLUMN price_cents TO price_usd;`,
        preview: [
          { column: 'price_usd', before: '89.00', after: '8900' },
          { column: 'price_usd', before: '149.00', after: '14900' },
        ],
      },
    }
  }

  // Default fallback
  return {
    id,
    role: 'agent',
    explanation:
      "Here's how I'd approach that. I'd target the `customers` table first since it's the most likely candidate from your request. Take a look at the SQL — let me know if you want to adjust the scope, add a WHERE clause, or apply to a different table.",
    status: 'proposing',
    ts: now(),
    change: {
      table: 'customers',
      affectedRows: 0,
      totalRows: 4821,
      sql: `-- Proposed change — refine the prompt for something more specific
-- (this is a prototype canned response)
SELECT * FROM customers LIMIT 10;`,
    },
  }
}

export function AIChangesPanel({ onClose }: { onClose: () => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [pending, setPending] = useState(false)
  const scrollerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, pending])

  const submit = (text: string) => {
    if (!text.trim()) return
    const userMsg: ChatMessage = {
      id: `u_${Math.random().toString(36).slice(2, 9)}`,
      role: 'user',
      text,
      ts: now(),
    }
    setMessages((m) => [...m, userMsg])
    setInput('')
    setPending(true)
    setTimeout(() => {
      setMessages((m) => [...m, mockAgentResponse(text)])
      setPending(false)
    }, 700)
  }

  const updateStatus = (id: string, status: 'applied' | 'rejected') => {
    setMessages((m) =>
      m.map((msg) =>
        msg.id === id && msg.role === 'agent' ? { ...msg, status } : msg,
      ),
    )
  }

  const handleClear = () => setMessages([])

  return (
    <aside className="card flex w-[420px] shrink-0 flex-col overflow-hidden">
      <div className="flex items-center justify-between gap-2 border-b border-zinc-800 p-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-gradient-to-br from-brand-400 to-emerald-700 text-ink shadow-[0_0_18px_-4px_rgba(16,185,129,0.5)]">
            <Sparkles className="h-3.5 w-3.5" />
          </span>
          <div>
            <p className="text-sm font-medium text-zinc-100">AI agent</p>
            <p className="text-[11px] text-zinc-500">Make changes to your data</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {messages.length > 0 && (
            <button
              onClick={handleClear}
              className="rounded-md p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
              title="Clear conversation"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
            title="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div ref={scrollerRef} className="flex-1 overflow-y-auto p-4">
        {messages.length === 0 ? (
          <EmptyState onPick={submit} />
        ) : (
          <div className="space-y-4">
            {messages.map((msg) =>
              msg.role === 'user' ? (
                <UserBubble key={msg.id} msg={msg} />
              ) : (
                <AgentBubble
                  key={msg.id}
                  msg={msg}
                  onApply={() => updateStatus(msg.id, 'applied')}
                  onReject={() => updateStatus(msg.id, 'rejected')}
                />
              ),
            )}
            {pending && <ThinkingBubble />}
          </div>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          submit(input)
        }}
        className="border-t border-zinc-800 bg-zinc-900/30 p-3"
      >
        <div className="relative">
          <textarea
            className="input pr-10 text-sm"
            rows={2}
            placeholder="Describe a change — e.g. 'lowercase all emails', 'merge orders_old into orders'…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                submit(input)
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
          Press Enter to send · Shift+Enter for newline · Prototype responses are canned
        </p>
      </form>
    </aside>
  )
}

function EmptyState({ onPick }: { onPick: (s: string) => void }) {
  return (
    <div className="flex h-full flex-col">
      <div className="text-sm text-zinc-300">
        Ask the agent to transform your data — rename columns, fill missing values, deduplicate,
        join tables, change types, or anything else you'd write SQL for.
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
          <History className="h-3 w-3" /> Every change creates a reviewable diff
        </p>
        <p className="mt-1">
          The agent always proposes before applying. You see affected rows and a SQL preview, then
          approve or reject.
        </p>
      </div>
    </div>
  )
}

function UserBubble({ msg }: { msg: Extract<ChatMessage, { role: 'user' }> }) {
  return (
    <div className="flex justify-end gap-2">
      <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-brand-500/15 px-3 py-2 text-sm text-zinc-100">
        {msg.text}
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
  onApply,
  onReject,
}: {
  msg: Extract<ChatMessage, { role: 'agent' }>
  onApply: () => void
  onReject: () => void
}) {
  return (
    <div className="flex items-start gap-2">
      <span className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-400 to-emerald-700 text-ink">
        <Bot className="h-3 w-3" />
      </span>
      <div className="min-w-0 flex-1 space-y-2">
        <div className="rounded-2xl rounded-tl-sm border border-zinc-800 bg-zinc-900/40 px-3 py-2 text-sm text-zinc-200">
          {msg.explanation}
        </div>

        {msg.change && (
          <div className="overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950">
            <div className="flex items-center justify-between gap-2 border-b border-zinc-800 px-3 py-1.5 text-[11px]">
              <div className="flex items-center gap-2 text-zinc-400">
                <span>
                  Affects{' '}
                  <span className="font-mono text-zinc-200">{msg.change.affectedRows.toLocaleString()}</span>
                  {' '}of{' '}
                  <span className="font-mono text-zinc-200">{msg.change.totalRows.toLocaleString()}</span>{' '}
                  rows in{' '}
                  <span className="font-mono text-zinc-200">{msg.change.table}</span>
                </span>
              </div>
              <StatusPill status={msg.status} />
            </div>

            {msg.change.preview && msg.change.preview.length > 0 && (
              <div className="border-b border-zinc-800 bg-zinc-900/30 px-3 py-2">
                <p className="mb-1 text-[10px] uppercase tracking-wider text-zinc-500">
                  Before → after
                </p>
                <ul className="space-y-1 font-mono text-[11px]">
                  {msg.change.preview.map((p, i) => (
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
              <code>{msg.change.sql}</code>
            </pre>

            {msg.status === 'proposing' && (
              <div className="flex items-center justify-end gap-2 border-t border-zinc-800 bg-zinc-900/30 px-3 py-2">
                <button onClick={onReject} className="btn-ghost text-xs">
                  Reject
                </button>
                <button onClick={onApply} className="btn-primary text-xs">
                  <Check className="h-3 w-3" />
                  Apply change
                </button>
              </div>
            )}
            {msg.status === 'applied' && (
              <div className="flex items-center justify-between gap-2 border-t border-emerald-500/20 bg-emerald-500/5 px-3 py-2 text-xs">
                <span className="inline-flex items-center gap-1.5 text-emerald-300">
                  <CheckCircle2 className="h-3 w-3" />
                  Applied at {msg.ts}
                </span>
                <button className="text-zinc-500 hover:text-zinc-200">Undo</button>
              </div>
            )}
            {msg.status === 'rejected' && (
              <div className="border-t border-zinc-800 bg-zinc-900/30 px-3 py-2 text-xs text-zinc-500">
                Rejected — nothing changed.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function StatusPill({ status }: { status: 'proposing' | 'applied' | 'rejected' | 'thinking' }) {
  if (status === 'applied')
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-300">
        <CheckCircle2 className="h-2.5 w-2.5" />
        Applied
      </span>
    )
  if (status === 'rejected')
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-zinc-700 bg-zinc-800/60 px-1.5 py-0.5 text-[10px] font-medium text-zinc-400">
        Rejected
      </span>
    )
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-300">
      Pending review
    </span>
  )
}
