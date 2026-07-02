import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Database,
  Filter,
  Inbox,
  Sparkles,
  Table2,
  X,
} from 'lucide-react'
import clsx from 'clsx'
import { api } from '../../api/client'
import { useAsync } from '../../api/hooks'
import type { RowsPage, SchemaColumn, TableDetail } from '../../api/types'
import { AIChangesPanel } from '../AIChangesPanel'

const NUMERIC_TYPES = new Set([
  'integer',
  'bigint',
  'smallint',
  'double precision',
  'real',
  'numeric',
])

const DATE_TYPES = new Set([
  'date',
  'timestamp without time zone',
  'timestamp with time zone',
])

export function DataTab({ projectId }: { projectId: string }) {
  const { tableName } = useParams()
  const navigate = useNavigate()

  const { data: tables, loading: tablesLoading, error: tablesError } = useAsync(
    () => api.listTables(projectId),
    [projectId],
  )

  const [showAgent, setShowAgent] = useState(false)
  const [reloadToken, setReloadToken] = useState(0)

  const activeName = tableName ?? tables?.[0]?.name ?? ''

  if (tablesLoading) return <p className="text-sm text-zinc-500">Loading tables…</p>
  if (tablesError) return <p className="text-sm text-rose-400">{tablesError.message}</p>

  if ((tables?.length ?? 0) === 0) {
    return (
      <div className="card flex flex-col items-center justify-center p-16 text-center">
        <div className="rounded-full border border-zinc-800 bg-zinc-900 p-3">
          <Database className="h-6 w-6 text-zinc-500" />
        </div>
        <h3 className="mt-4 text-base font-medium">No tables yet</h3>
        <p className="mt-1 max-w-sm text-sm text-zinc-400">
          Upload a CSV/TSV/XLSX/JSON from the Documents tab and run an import — tables the agent
          creates will appear here.
        </p>
      </div>
    )
  }

  return (
    <div className="flex h-[calc(100vh-9.5rem)] gap-4">
      <aside className="card flex w-72 shrink-0 flex-col overflow-hidden">
        <div className="flex items-center justify-between border-b border-zinc-800 px-3 py-2">
          <span className="text-[10px] uppercase tracking-wider text-zinc-500">Tables</span>
          <button
            onClick={() => setShowAgent((v) => !v)}
            title="AI agent"
            className={clsx(
              'inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-[11px] transition-colors',
              showAgent
                ? 'bg-brand-500/15 text-brand-200'
                : 'text-brand-300/80 hover:bg-zinc-800 hover:text-brand-200',
            )}
          >
            <Sparkles className="h-3.5 w-3.5" />
            Agent
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {(tables ?? []).map((t) => (
            <button
              key={t.name}
              onClick={() => navigate(`/projects/${projectId}/data/${encodeURIComponent(t.name)}`)}
              className={clsx(
                'group flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors',
                t.name === activeName
                  ? 'bg-zinc-800/80 text-zinc-100'
                  : 'text-zinc-300 hover:bg-zinc-900',
              )}
            >
              <span className="flex min-w-0 items-center gap-2">
                <Table2
                  className={clsx('h-3.5 w-3.5', t.name === activeName ? 'text-brand-400' : 'text-zinc-500')}
                />
                <span className="truncate font-mono text-[13px]">{t.name}</span>
              </span>
              <span className="rounded-full bg-zinc-900 px-1.5 text-[10px] text-zinc-500">
                {t.row_count.toLocaleString()}
              </span>
            </button>
          ))}
        </div>
      </aside>

      <section className="card flex min-w-0 flex-1 flex-col overflow-hidden">
        {activeName ? (
          <TableView projectId={projectId} tableName={activeName} reloadToken={reloadToken} />
        ) : (
          <div className="flex flex-1 items-center justify-center text-zinc-500">
            <Inbox className="mr-2 h-4 w-4" /> Select a table
          </div>
        )}
      </section>

      {showAgent && (
        <AIChangesPanel
          projectId={projectId}
          tableName={activeName || undefined}
          onClose={() => setShowAgent(false)}
          onDataChanged={() => setReloadToken((t) => t + 1)}
        />
      )}
    </div>
  )
}

type SortState = { col: string; dir: 'asc' | 'desc' } | null

function TableView({
  projectId,
  tableName,
  reloadToken,
}: {
  projectId: string
  tableName: string
  reloadToken: number
}) {
  const { data: detail, loading: detailLoading, error: detailError } = useAsync(
    () => api.getTable(projectId, tableName),
    [projectId, tableName, reloadToken],
  )

  const [pages, setPages] = useState<RowsPage[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sort, setSort] = useState<SortState>(null)
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [showFilters, setShowFilters] = useState(false)

  const activeFilters = useMemo(
    () =>
      Object.entries(filters)
        .filter(([, v]) => v.trim().length > 0)
        .map(([col, v]) => ({ col, op: defaultOpForColumn(detail?.columns.find((c) => c.name === col)), value: v.trim() })),
    [filters, detail],
  )

  useEffect(() => {
    setPages([])
    setError(null)
    setSort(null)
    setFilters({})
    setShowFilters(false)
  }, [projectId, tableName])

  useEffect(() => {
    if (!detail) return
    let cancelled = false
    setLoading(true)
    api
      .getRows(projectId, tableName, {
        limit: 100,
        sort: sort?.col,
        dir: sort?.dir,
        filters: activeFilters,
      })
      .then(
        (page) => {
          if (!cancelled) {
            setPages([page])
            setLoading(false)
          }
        },
        (err: Error) => {
          if (!cancelled) {
            setError(err.message)
            setLoading(false)
          }
        },
      )
    return () => {
      cancelled = true
    }
  }, [projectId, tableName, detail, sort?.col, sort?.dir, activeFilters])

  const loadMore = async () => {
    const last = pages[pages.length - 1]
    if (!last?.next_cursor) return
    setLoading(true)
    try {
      const page = await api.getRows(projectId, tableName, {
        cursor: last.next_cursor,
        limit: 100,
        sort: sort?.col,
        dir: sort?.dir,
        filters: activeFilters,
      })
      setPages((p) => [...p, page])
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const cycleSort = (col: string) => {
    setSort((prev) => {
      if (!prev || prev.col !== col) return { col, dir: 'asc' }
      if (prev.dir === 'asc') return { col, dir: 'desc' }
      return null
    })
  }

  const clearAll = () => {
    setSort(null)
    setFilters({})
  }

  if (detailLoading) return <div className="p-6 text-sm text-zinc-500">Loading table…</div>
  if (detailError || !detail)
    return <div className="p-6 text-sm text-rose-400">{detailError?.message ?? 'Failed to load table'}</div>

  const rows = pages.flatMap((p) => p.rows)
  const cols = pages[0]?.columns ?? detail.columns.map((c) => c.name)
  const hasMore = !!pages[pages.length - 1]?.next_cursor
  const hasAnyFilter = sort !== null || activeFilters.length > 0

  return (
    <>
      <div className="border-b border-zinc-800 p-4">
        <div className="flex items-center gap-2">
          <Table2 className="h-4 w-4 text-brand-400" />
          <h2 className="font-mono text-base font-medium text-zinc-100">{detail.name}</h2>
          <span className="chip">{detail.row_count.toLocaleString()} rows</span>
          <span className="chip">{detail.columns.length} columns</span>
        </div>
      </div>

      <div className="flex items-center gap-2 border-b border-zinc-800 bg-zinc-900/30 p-3">
        <button
          onClick={() => setShowFilters((v) => !v)}
          className={clsx(
            'btn',
            showFilters || activeFilters.length > 0
              ? 'bg-brand-500/15 text-brand-200 hover:bg-brand-500/25'
              : 'btn-secondary',
          )}
        >
          <Filter className="h-3.5 w-3.5" />
          Filters
          {activeFilters.length > 0 && (
            <span className="ml-0.5 rounded-full bg-brand-500/30 px-1.5 text-[10px] text-brand-100">
              {activeFilters.length}
            </span>
          )}
        </button>
        {hasAnyFilter && (
          <button onClick={clearAll} className="btn-ghost text-xs">
            Clear all
          </button>
        )}
        <div className="ml-auto text-xs text-zinc-500">
          {loading
            ? 'Loading…'
            : `Showing ${rows.length.toLocaleString()} of ${detail.row_count.toLocaleString()}`}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full border-separate border-spacing-0 font-mono text-[13px]">
          <thead className="sticky top-0 z-10 bg-zinc-950">
            <tr>
              <th className="border-b border-zinc-800 px-3 py-2 text-right text-[11px] font-normal text-zinc-600 w-12">
                #
              </th>
              {cols.map((name) => {
                const isSorted = sort?.col === name
                return (
                  <th
                    key={name}
                    className="border-b border-zinc-800 px-3 py-2 text-left text-[11px] font-medium text-zinc-400"
                  >
                    <button
                      onClick={() => cycleSort(name)}
                      className="group flex w-full items-center gap-1.5"
                    >
                      <span className="text-zinc-200">{name}</span>
                      <span
                        className={clsx(
                          'ml-auto inline-flex h-4 w-4 items-center justify-center transition-opacity',
                          isSorted
                            ? 'opacity-100 text-brand-300'
                            : 'opacity-0 group-hover:opacity-60 text-zinc-500',
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
                <th className="border-b border-zinc-800 bg-zinc-950 px-2 py-1.5" />
                {cols.map((name) => {
                  const col = detail.columns.find((c) => c.name === name)
                  const placeholder = filterPlaceholder(col)
                  return (
                    <th
                      key={name}
                      className="border-b border-zinc-800 bg-zinc-950 px-2 py-1.5"
                    >
                      <div className="flex items-center gap-1">
                        <input
                          className="w-full rounded-sm border border-zinc-800 bg-zinc-900 px-2 py-1 font-sans text-[11px] text-zinc-200 placeholder-zinc-600 outline-none focus:border-brand-500/60 focus:ring-1 focus:ring-brand-500/20"
                          placeholder={placeholder}
                          value={filters[name] ?? ''}
                          onChange={(e) =>
                            setFilters((f) => ({ ...f, [name]: e.target.value }))
                          }
                        />
                        {filters[name] && (
                          <button
                            className="rounded-sm p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"
                            onClick={() =>
                              setFilters((f) => {
                                const { [name]: _omit, ...rest } = f
                                return rest
                              })
                            }
                            aria-label={`Clear ${name} filter`}
                          >
                            <X className="h-3 w-3" />
                          </button>
                        )}
                      </div>
                    </th>
                  )
                })}
              </tr>
            )}
          </thead>
          <tbody>
            {rows.length === 0 && !loading && (
              <tr>
                <td
                  colSpan={cols.length + 1}
                  className="border-b border-zinc-900 py-10 text-center text-sm text-zinc-500"
                >
                  No rows match
                </td>
              </tr>
            )}
            {rows.map((row, i) => (
              <tr key={i} className="group">
                <td className="border-b border-zinc-900 px-3 py-1.5 text-right text-[11px] text-zinc-600 group-hover:bg-zinc-900/50">
                  {i + 1}
                </td>
                {row.map((cell, j) => (
                  <td
                    key={j}
                    className="border-b border-zinc-900 px-3 py-1.5 text-zinc-200 group-hover:bg-zinc-900/50"
                  >
                    <Cell value={cell} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between border-t border-zinc-800 bg-zinc-950 px-4 py-2 text-xs text-zinc-500">
        <span>
          {rows.length.toLocaleString()} of {detail.row_count.toLocaleString()}
          {hasAnyFilter && ' (filtered/sorted)'}
        </span>
        <div className="flex items-center gap-2">
          {error && <span className="text-rose-400">{error}</span>}
          {hasMore && (
            <button className="btn-ghost px-2 py-1 text-xs" onClick={() => void loadMore()} disabled={loading}>
              {loading ? 'Loading…' : 'Load more'}
            </button>
          )}
        </div>
      </div>
    </>
  )
}

function defaultOpForColumn(col: SchemaColumn | undefined): string {
  if (!col) return 'contains'
  if (NUMERIC_TYPES.has(col.type) || DATE_TYPES.has(col.type)) return 'eq'
  if (col.type === 'boolean') return 'eq'
  return 'contains'
}

function filterPlaceholder(col: SchemaColumn | TableDetail['columns'][number] | undefined): string {
  if (!col) return 'Filter…'
  if (NUMERIC_TYPES.has(col.type)) return `= number`
  if (DATE_TYPES.has(col.type)) return `= YYYY-MM-DD`
  if (col.type === 'boolean') return `= true/false`
  return 'contains…'
}

function Cell({ value }: { value: string | number | boolean | null }) {
  if (value === null) return <span className="text-zinc-700 italic">NULL</span>
  if (typeof value === 'boolean')
    return <span className={value ? 'text-emerald-400' : 'text-zinc-500'}>{String(value)}</span>
  if (typeof value === 'number')
    return <span className="text-amber-300">{value.toLocaleString()}</span>
  return <span>{String(value)}</span>
}
