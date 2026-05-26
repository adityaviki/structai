import { useNavigate, useParams } from 'react-router-dom'
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Database,
  Filter,
  Inbox,
  KeyRound,
  Link2,
  Search,
  Sparkles,
  Table2,
  X,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import clsx from 'clsx'
import { getTables } from '../../data/mockData'
import { AIChangesPanel } from '../AIChangesPanel'

type SortDir = 'asc' | 'desc'

export function DataTab({ projectId }: { projectId: string }) {
  const tables = getTables(projectId)
  const navigate = useNavigate()
  const { tableId } = useParams()
  const [tableQuery, setTableQuery] = useState('')
  const [rowQuery, setRowQuery] = useState('')
  const [sort, setSort] = useState<{ col: string; dir: SortDir } | null>(null)
  const [columnFilters, setColumnFilters] = useState<Record<string, string>>({})
  const [showFilters, setShowFilters] = useState(false)
  const [showAI, setShowAI] = useState(false)

  const activeId = tableId ?? tables[0]?.id ?? ''
  const active = tables.find((t) => t.id === activeId)

  const filteredTables = useMemo(
    () => tables.filter((t) => t.name.toLowerCase().includes(tableQuery.toLowerCase())),
    [tables, tableQuery],
  )

  const displayRows = useMemo(() => {
    if (!active) return []
    const q = rowQuery.trim().toLowerCase()
    const activeColFilters = Object.entries(columnFilters).filter(([, v]) => v.trim().length > 0)

    let rows = active.rows.map((row, originalIdx) => ({ row, originalIdx }))

    // Global search across all cells
    if (q) {
      rows = rows.filter(({ row }) =>
        row.some((cell) => (cell ?? '').toString().toLowerCase().includes(q)),
      )
    }

    // Per-column filters
    if (activeColFilters.length > 0) {
      const colIndex: Record<string, number> = {}
      active.columns.forEach((c, i) => (colIndex[c.name] = i))
      rows = rows.filter(({ row }) =>
        activeColFilters.every(([col, val]) => {
          const idx = colIndex[col]
          if (idx === undefined) return true
          return (row[idx] ?? '').toString().toLowerCase().includes(val.toLowerCase())
        }),
      )
    }

    // Sort
    if (sort) {
      const idx = active.columns.findIndex((c) => c.name === sort.col)
      if (idx >= 0) {
        rows = [...rows].sort((a, b) => {
          const av = a.row[idx]
          const bv = b.row[idx]
          if (av === bv) return 0
          if (av === null) return 1
          if (bv === null) return -1
          let cmp: number
          if (typeof av === 'number' && typeof bv === 'number') cmp = av - bv
          else cmp = String(av).localeCompare(String(bv))
          return sort.dir === 'asc' ? cmp : -cmp
        })
      }
    }

    return rows
  }, [active, rowQuery, columnFilters, sort])

  const activeFilterCount = Object.values(columnFilters).filter((v) => v.trim().length > 0).length
  const hasAnyFilter = activeFilterCount > 0 || rowQuery.trim().length > 0 || sort !== null

  const cycleSort = (col: string) => {
    setSort((prev) => {
      if (!prev || prev.col !== col) return { col, dir: 'asc' }
      if (prev.dir === 'asc') return { col, dir: 'desc' }
      return null
    })
  }

  const clearAll = () => {
    setRowQuery('')
    setColumnFilters({})
    setSort(null)
  }

  if (tables.length === 0) {
    return (
      <div className="card flex flex-col items-center justify-center p-16 text-center">
        <div className="rounded-full border border-zinc-800 bg-zinc-900 p-3">
          <Database className="h-6 w-6 text-zinc-500" />
        </div>
        <h3 className="mt-4 text-base font-medium">No tables yet</h3>
        <p className="mt-1 max-w-sm text-sm text-zinc-400">
          Upload a file from the Documents tab and run an import — tables created
          by the agent will appear here.
        </p>
      </div>
    )
  }

  return (
    <div className="flex h-[calc(100vh-9.5rem)] gap-4">
      {/* Left rail */}
      <aside className="card flex w-72 shrink-0 flex-col overflow-hidden">
        <div className="border-b border-zinc-800 p-3">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500" />
            <input
              className="input pl-8 py-1.5 text-sm"
              placeholder="Search tables"
              value={tableQuery}
              onChange={(e) => setTableQuery(e.target.value)}
            />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          <p className="px-2 py-1 text-[10px] uppercase tracking-wider text-zinc-500">
            Tables
          </p>
          {filteredTables.map((t) => (
            <button
              key={t.id}
              onClick={() => {
                navigate(`/projects/${projectId}/data/${t.id}`)
                // Reset per-table state when switching
                setRowQuery('')
                setColumnFilters({})
                setSort(null)
              }}
              className={clsx(
                'group flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors',
                t.id === activeId
                  ? 'bg-zinc-800/80 text-zinc-100'
                  : 'text-zinc-300 hover:bg-zinc-900',
              )}
            >
              <span className="flex min-w-0 items-center gap-2">
                <Table2 className={clsx('h-3.5 w-3.5', t.id === activeId ? 'text-brand-400' : 'text-zinc-500')} />
                <span className="truncate font-mono text-[13px]">{t.name}</span>
              </span>
              <span className="rounded-full bg-zinc-900 px-1.5 text-[10px] text-zinc-500 group-hover:bg-zinc-800">
                {t.rowCount.toLocaleString()}
              </span>
            </button>
          ))}
        </div>
        <div className="border-t border-zinc-800 p-3 text-xs text-zinc-500">
          {tables.length} tables · {tables.reduce((s, t) => s + t.rowCount, 0).toLocaleString()} rows
        </div>
      </aside>

      {/* Table view */}
      <section className="card flex min-w-0 flex-1 flex-col overflow-hidden">
        {active ? (
          <>
            <div className="flex items-start justify-between gap-4 border-b border-zinc-800 p-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <Table2 className="h-4 w-4 text-brand-400" />
                  <h2 className="font-mono text-base font-medium text-zinc-100">{active.name}</h2>
                  <span className="chip">{active.rowCount.toLocaleString()} rows</span>
                  <span className="chip">{active.columns.length} columns</span>
                </div>
                {active.description && (
                  <p className="mt-1 text-sm text-zinc-400">{active.description}</p>
                )}
              </div>
              {!showAI && (
                <button
                  onClick={() => setShowAI(true)}
                  className="btn group inline-flex items-center gap-2 rounded-md border border-brand-500/30 bg-brand-500/10 px-2.5 py-1.5 text-sm font-medium text-brand-200 hover:bg-brand-500/15"
                >
                  <Sparkles className="h-3.5 w-3.5" />
                  Ask AI to change data
                </button>
              )}
            </div>

            {/* Search + filter toolbar */}
            <div className="flex items-center gap-2 border-b border-zinc-800 bg-zinc-900/30 p-3">
              <div className="relative flex-1">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500" />
                <input
                  className="input pl-8 py-1.5 text-sm"
                  placeholder={`Search rows in ${active.name}…`}
                  value={rowQuery}
                  onChange={(e) => setRowQuery(e.target.value)}
                />
                {rowQuery && (
                  <button
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded-sm p-0.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"
                    onClick={() => setRowQuery('')}
                    aria-label="Clear search"
                  >
                    <X className="h-3 w-3" />
                  </button>
                )}
              </div>
              <button
                onClick={() => setShowFilters((v) => !v)}
                className={clsx(
                  'btn',
                  showFilters || activeFilterCount > 0
                    ? 'bg-brand-500/15 text-brand-200 hover:bg-brand-500/25'
                    : 'btn-secondary',
                )}
              >
                <Filter className="h-3.5 w-3.5" />
                Filters
                {activeFilterCount > 0 && (
                  <span className="ml-0.5 rounded-full bg-brand-500/30 px-1.5 text-[10px] text-brand-100">
                    {activeFilterCount}
                  </span>
                )}
              </button>
              {hasAnyFilter && (
                <button onClick={clearAll} className="btn-ghost text-xs">
                  Clear all
                </button>
              )}
            </div>

            {/* Column inspector */}
            <div className="flex flex-wrap gap-2 border-b border-zinc-800 bg-zinc-900/30 px-3 py-2">
              {active.columns.map((c) => (
                <div
                  key={c.name}
                  className="inline-flex items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-950/40 px-2 py-1 text-xs"
                >
                  {c.isPK && <KeyRound className="h-3 w-3 text-amber-400" />}
                  {c.fk && <Link2 className="h-3 w-3 text-sky-400" />}
                  <span className="font-mono text-zinc-200">{c.name}</span>
                  <span className="text-zinc-500">{c.type}</span>
                  {c.nullable && <span className="text-zinc-600">?</span>}
                </div>
              ))}
            </div>

            <div className="min-h-0 flex-1 overflow-auto">
              <table className="w-full border-separate border-spacing-0 font-mono text-[13px]">
                <thead className="sticky top-0 z-10 bg-zinc-950">
                  <tr>
                    <th className="border-b border-zinc-800 px-3 py-2 text-right text-[11px] font-normal text-zinc-600 w-12">
                      #
                    </th>
                    {active.columns.map((c) => {
                      const isSorted = sort?.col === c.name
                      return (
                        <th
                          key={c.name}
                          className="border-b border-zinc-800 px-3 py-2 text-left text-[11px] font-medium text-zinc-400"
                        >
                          <button
                            onClick={() => cycleSort(c.name)}
                            className="group flex w-full items-center gap-1.5"
                          >
                            <span className="text-zinc-200">{c.name}</span>
                            <span className="text-zinc-600">{c.type}</span>
                            <span
                              className={clsx(
                                'ml-auto inline-flex h-4 w-4 items-center justify-center transition-opacity',
                                isSorted ? 'opacity-100 text-brand-300' : 'opacity-0 group-hover:opacity-60 text-zinc-500',
                              )}
                            >
                              {isSorted ? (
                                sort?.dir === 'asc' ? (
                                  <ArrowUp className="h-3 w-3" />
                                ) : (
                                  <ArrowDown className="h-3 w-3" />
                                )
                              ) : (
                                <ArrowUpDown className="h-3 w-3" />
                              )}
                            </span>
                          </button>
                        </th>
                      )
                    })}
                  </tr>
                  {showFilters && (
                    <tr>
                      <th className="border-b border-zinc-800 bg-zinc-950 px-2 py-1.5"></th>
                      {active.columns.map((c) => (
                        <th
                          key={c.name}
                          className="border-b border-zinc-800 bg-zinc-950 px-2 py-1.5"
                        >
                          <input
                            className="w-full rounded-sm border border-zinc-800 bg-zinc-900 px-2 py-1 font-sans text-[11px] text-zinc-200 placeholder-zinc-600 outline-none focus:border-brand-500/60 focus:ring-1 focus:ring-brand-500/20"
                            placeholder={`Filter ${c.name}…`}
                            value={columnFilters[c.name] ?? ''}
                            onChange={(e) =>
                              setColumnFilters((cf) => ({ ...cf, [c.name]: e.target.value }))
                            }
                          />
                        </th>
                      ))}
                    </tr>
                  )}
                </thead>
                <tbody>
                  {displayRows.length === 0 ? (
                    <tr>
                      <td
                        colSpan={active.columns.length + 1}
                        className="border-b border-zinc-900 py-10 text-center text-sm text-zinc-500"
                      >
                        <div className="flex flex-col items-center gap-2">
                          <Filter className="h-4 w-4 text-zinc-600" />
                          No rows match your filters
                          <button onClick={clearAll} className="btn-ghost text-xs">
                            Clear filters
                          </button>
                        </div>
                      </td>
                    </tr>
                  ) : (
                    displayRows.map(({ row, originalIdx }) => (
                      <tr key={originalIdx} className="group">
                        <td className="border-b border-zinc-900 px-3 py-1.5 text-right text-[11px] text-zinc-600 group-hover:bg-zinc-900/50">
                          {originalIdx + 1}
                        </td>
                        {row.map((cell, j) => (
                          <td
                            key={j}
                            className="border-b border-zinc-900 px-3 py-1.5 text-zinc-200 group-hover:bg-zinc-900/50"
                          >
                            <CellValue value={cell} highlight={rowQuery} />
                          </td>
                        ))}
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
              <div className="flex items-center justify-between border-t border-zinc-800 bg-zinc-950 px-4 py-2 text-xs text-zinc-500">
                <span>
                  {hasAnyFilter ? (
                    <>
                      <span className="text-zinc-300">{displayRows.length}</span> of{' '}
                      {active.rows.length} sample rows match
                      <span className="ml-1 text-zinc-600">
                        · table has {active.rowCount.toLocaleString()} total
                      </span>
                    </>
                  ) : (
                    <>
                      Showing 1–{active.rows.length} of {active.rowCount.toLocaleString()}
                    </>
                  )}
                </span>
                <div className="flex items-center gap-1">
                  <button className="btn-ghost px-2 py-1 text-xs" disabled>
                    Prev
                  </button>
                  <button className="btn-ghost px-2 py-1 text-xs">Next</button>
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center text-zinc-500">
            <Inbox className="mr-2 h-4 w-4" /> Select a table
          </div>
        )}
      </section>

      {showAI && <AIChangesPanel onClose={() => setShowAI(false)} />}
    </div>
  )
}

function CellValue({ value, highlight }: { value: string | number | boolean | null; highlight: string }) {
  if (value === null) return <span className="text-zinc-700 italic">NULL</span>
  if (typeof value === 'boolean')
    return <span className={value ? 'text-emerald-400' : 'text-zinc-500'}>{String(value)}</span>
  if (typeof value === 'number')
    return <span className="text-amber-300">{value.toLocaleString()}</span>

  const text = value as string
  const q = highlight.trim()
  if (!q) return <span>{text}</span>

  const idx = text.toLowerCase().indexOf(q.toLowerCase())
  if (idx < 0) return <span>{text}</span>

  return (
    <span>
      {text.slice(0, idx)}
      <mark className="bg-brand-500/30 text-brand-100 rounded-sm px-0.5">
        {text.slice(idx, idx + q.length)}
      </mark>
      {text.slice(idx + q.length)}
    </span>
  )
}
