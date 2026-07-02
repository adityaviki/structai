import type { ReactNode } from 'react'

// A small, dependency-free renderer for the markdown subset the agent emits in
// chat: paragraphs, **bold**, *italics*, `inline code`, ```fenced code```,
// bullet / numbered lists, and [links](url). Not a full CommonMark parser — it
// covers conversational replies, not arbitrary documents.

const INLINE_RULES: [RegExp, (m: RegExpMatchArray, key: string) => ReactNode][] = [
  [
    /`([^`]+)`/,
    (m, key) => (
      <code
        key={key}
        className="rounded bg-zinc-800 px-1 py-0.5 font-mono text-[12px] text-brand-200"
      >
        {m[1]}
      </code>
    ),
  ],
  [
    /\*\*([^*]+)\*\*/,
    (m, key) => (
      <strong key={key} className="font-semibold text-zinc-100">
        {m[1]}
      </strong>
    ),
  ],
  [/\*([^*]+)\*/, (m, key) => <em key={key}>{m[1]}</em>],
  [/_([^_]+)_/, (m, key) => <em key={key}>{m[1]}</em>],
  [
    /\[([^\]]+)\]\(([^)\s]+)\)/,
    (m, key) => (
      <a
        key={key}
        href={m[2]}
        target="_blank"
        rel="noreferrer"
        className="text-brand-300 underline hover:text-brand-200"
      >
        {m[1]}
      </a>
    ),
  ],
]

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const out: ReactNode[] = []
  let rest = text
  let k = 0
  while (rest.length > 0) {
    let best: { idx: number; len: number; node: ReactNode } | null = null
    for (const [re, render] of INLINE_RULES) {
      const m = rest.match(re)
      if (m && m.index !== undefined && (best === null || m.index < best.idx)) {
        best = { idx: m.index, len: m[0].length, node: render(m, `${keyPrefix}-${k}`) }
      }
    }
    if (best === null) {
      out.push(rest)
      break
    }
    if (best.idx > 0) out.push(rest.slice(0, best.idx))
    out.push(best.node)
    rest = rest.slice(best.idx + best.len)
    k++
  }
  return out
}

const BULLET = /^\s*[-*]\s+/
const NUMBERED = /^\s*\d+\.\s+/
const FENCE = /^\s*```/

export function Markdown({ text }: { text: string }) {
  const lines = text.split('\n')
  const blocks: ReactNode[] = []
  let i = 0
  let key = 0

  while (i < lines.length) {
    const line = lines[i]

    if (FENCE.test(line)) {
      i++
      const code: string[] = []
      while (i < lines.length && !FENCE.test(lines[i])) {
        code.push(lines[i])
        i++
      }
      if (i < lines.length) i++ // closing fence
      blocks.push(
        <pre
          key={key++}
          className="overflow-x-auto rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 font-mono text-[12px] text-zinc-200"
        >
          <code>{code.join('\n')}</code>
        </pre>,
      )
      continue
    }

    if (BULLET.test(line)) {
      const items: string[] = []
      while (i < lines.length && BULLET.test(lines[i])) {
        items.push(lines[i].replace(BULLET, ''))
        i++
      }
      const k = key++
      blocks.push(
        <ul key={k} className="list-disc space-y-0.5 pl-5">
          {items.map((it, j) => (
            <li key={j}>{renderInline(it, `ul-${k}-${j}`)}</li>
          ))}
        </ul>,
      )
      continue
    }

    if (NUMBERED.test(line)) {
      const items: string[] = []
      while (i < lines.length && NUMBERED.test(lines[i])) {
        items.push(lines[i].replace(NUMBERED, ''))
        i++
      }
      const k = key++
      blocks.push(
        <ol key={k} className="list-decimal space-y-0.5 pl-5">
          {items.map((it, j) => (
            <li key={j}>{renderInline(it, `ol-${k}-${j}`)}</li>
          ))}
        </ol>,
      )
      continue
    }

    if (line.trim() === '') {
      i++
      continue
    }

    const para: string[] = []
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !BULLET.test(lines[i]) &&
      !NUMBERED.test(lines[i]) &&
      !FENCE.test(lines[i])
    ) {
      para.push(lines[i])
      i++
    }
    const k = key++
    blocks.push(
      <p key={k}>
        {para.map((p, j) => (
          <span key={j}>
            {j > 0 && <br />}
            {renderInline(p, `p-${k}-${j}`)}
          </span>
        ))}
      </p>,
    )
  }

  return <div className="space-y-2">{blocks}</div>
}
