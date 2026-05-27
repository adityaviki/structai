import clsx from 'clsx'

const colors: Record<string, string> = {
  csv: 'from-emerald-500/30 to-emerald-700/20 text-emerald-300',
  tsv: 'from-cyan-500/30 to-cyan-700/20 text-cyan-300',
  xlsx: 'from-green-500/30 to-emerald-700/20 text-green-300',
  json: 'from-amber-500/30 to-amber-700/20 text-amber-300',
}

export function FileIcon({ ext, className }: { ext: string; className?: string }) {
  const tone = colors[ext] ?? 'from-zinc-700 to-zinc-800 text-zinc-300'
  return (
    <span
      className={clsx(
        'inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-zinc-800 bg-gradient-to-br font-mono text-[10px] font-semibold uppercase tracking-wide',
        tone,
        className,
      )}
    >
      {ext}
    </span>
  )
}
