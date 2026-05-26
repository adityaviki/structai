import { useLayoutEffect, useRef, useState } from 'react'
import { Hash, KeyRound, Link2, Network } from 'lucide-react'
import { getTables } from '../../data/mockData'
import type { TableInfo } from '../../types'

const layouts: Record<string, Record<string, { x: number; y: number }>> = {
  p_sales: {
    t_customers: { x: 60, y: 60 },
    t_categories: { x: 720, y: 60 },
    t_orders: { x: 60, y: 360 },
    t_products: { x: 720, y: 360 },
    t_order_items: { x: 380, y: 620 },
  },
  p_hr: {
    t_departments: { x: 60, y: 60 },
    t_employees: { x: 460, y: 60 },
    t_payroll: { x: 460, y: 380 },
  },
}

const CARD_W = 280

export function SchemaTab({ projectId }: { projectId: string }) {
  const tables = getTables(projectId)
  const layout = layouts[projectId] ?? {}
  const containerRef = useRef<HTMLDivElement>(null)
  const [tick, setTick] = useState(0)

  useLayoutEffect(() => {
    const onResize = () => setTick((t) => t + 1)
    window.addEventListener('resize', onResize)
    setTick((t) => t + 1)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  if (tables.length === 0) {
    return (
      <div className="card flex flex-col items-center justify-center p-16 text-center">
        <div className="rounded-full border border-zinc-800 bg-zinc-900 p-3">
          <Network className="h-6 w-6 text-zinc-500" />
        </div>
        <h3 className="mt-4 text-base font-medium">No schema yet</h3>
        <p className="mt-1 max-w-sm text-sm text-zinc-400">
          Run an import to populate the schema. Relationships are inferred from FK constraints
          the agent creates.
        </p>
      </div>
    )
  }

  const placed = tables.map((t) => ({
    ...t,
    pos: layout[t.id] ?? { x: 60 + Math.random() * 600, y: 60 + Math.random() * 400 },
  }))
  const heightOf = (t: TableInfo) => 56 + t.columns.length * 26

  // Build FK edges
  type Edge = { from: TableInfo & { pos: { x: number; y: number } }; to: TableInfo & { pos: { x: number; y: number } }; col: string }
  const edges: Edge[] = []
  placed.forEach((from) => {
    from.columns.forEach((c) => {
      if (c.fk) {
        const to = placed.find((p) => p.name === c.fk!.table)
        if (to) edges.push({ from, to, col: c.name })
      }
    })
  })

  const maxX = Math.max(...placed.map((p) => p.pos.x + CARD_W)) + 60
  const maxY = Math.max(...placed.map((p) => p.pos.y + heightOf(p))) + 60

  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between border-b border-zinc-800 p-4">
        <div>
          <h2 className="text-sm font-medium text-zinc-100">Schema diagram</h2>
          <p className="text-xs text-zinc-500">
            Inferred from imports — drag is a placeholder, real version will auto-layout.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-zinc-400">
          <span className="chip"><KeyRound className="h-3 w-3 text-amber-400" /> primary key</span>
          <span className="chip"><Link2 className="h-3 w-3 text-sky-400" /> foreign key</span>
        </div>
      </div>
      <div
        ref={containerRef}
        className="relative overflow-auto bg-[radial-gradient(circle_at_1px_1px,rgba(255,255,255,0.04)_1px,transparent_0)] [background-size:24px_24px]"
        style={{ height: 'calc(100vh - 14rem)' }}
      >
        <div className="relative" style={{ width: maxX, height: maxY }}>
          {/* Edges */}
          <svg
            className="pointer-events-none absolute inset-0"
            width={maxX}
            height={maxY}
            style={{ overflow: 'visible' }}
            key={tick}
          >
            <defs>
              <marker
                id="arrow"
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#38bdf8" />
              </marker>
            </defs>
            {edges.map((e, i) => {
              const fromX = e.from.pos.x + CARD_W
              const fromY = e.from.pos.y + 56 + (e.from.columns.findIndex((c) => c.name === e.col)) * 26 + 13
              const toX = e.to.pos.x
              const toY = e.to.pos.y + 30
              const midX = (fromX + toX) / 2
              const d = `M ${fromX} ${fromY} C ${midX} ${fromY}, ${midX} ${toY}, ${toX} ${toY}`
              const reverseDirection = fromX > toX
              const d2 = reverseDirection
                ? `M ${e.from.pos.x} ${fromY} C ${e.from.pos.x - 80} ${fromY}, ${e.to.pos.x + CARD_W + 80} ${toY}, ${e.to.pos.x + CARD_W} ${toY}`
                : d
              return (
                <g key={i}>
                  <path
                    d={d2}
                    fill="none"
                    stroke="#38bdf8"
                    strokeOpacity="0.6"
                    strokeWidth={1.5}
                    markerEnd="url(#arrow)"
                  />
                </g>
              )
            })}
          </svg>

          {/* Cards */}
          {placed.map((t) => (
            <div
              key={t.id}
              className="absolute rounded-lg border border-zinc-800 bg-zinc-950/95 shadow-xl"
              style={{ left: t.pos.x, top: t.pos.y, width: CARD_W }}
            >
              <div className="flex items-center justify-between gap-2 border-b border-zinc-800 px-3 py-2">
                <div className="flex items-center gap-2">
                  <Hash className="h-3.5 w-3.5 text-brand-400" />
                  <span className="font-mono text-sm font-medium text-zinc-100">{t.name}</span>
                </div>
                <span className="text-[10px] text-zinc-500">{t.rowCount.toLocaleString()} rows</span>
              </div>
              <ul className="divide-y divide-zinc-900 text-[12px]">
                {t.columns.map((c) => (
                  <li
                    key={c.name}
                    className="flex items-center justify-between gap-2 px-3 py-1"
                  >
                    <span className="flex items-center gap-1.5 font-mono">
                      {c.isPK && <KeyRound className="h-3 w-3 text-amber-400" />}
                      {c.fk && <Link2 className="h-3 w-3 text-sky-400" />}
                      <span className={c.isPK ? 'text-amber-100' : 'text-zinc-200'}>
                        {c.name}
                      </span>
                      {c.nullable && <span className="text-zinc-600">?</span>}
                    </span>
                    <span className="text-zinc-500">{c.type}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
