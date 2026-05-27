import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Database, Inbox, KeyRound, Link2, Table2 } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../../api/client'
import { useAsync } from '../../api/hooks'
import type { RowsPage, TableDetail } from '../../api/types'

export function DataTab({ projectId }: { projectId: string }) {
  const { tableName } = useParams()
  const navigate = useNavigate()

  const { data: tables, loading: tablesLoading, error: tablesError } = useAsync(
    () => api.listTables(projectId),
    [projectId],
  )

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
          Upload a CSV from the Documents tab and run an import — tables the agent creates will
          appear here.
        </p>
      </div>
    )
  }

  return (
    <div className="flex h-[calc(100vh-9.5rem)] gap-4">
      <aside className="card flex w-72 shrink-0 flex-col overflow-hidden">
        <div className="border-b border-zinc-800 px-3 py-2 text-[10px] uppercase tracking-wider text-zinc-500">
          Tables
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
          <TableView projectId={projectId} tableName={activeName} />
        ) : (
          <div className="flex flex-1 items-center justify-center text-zinc-500">
            <Inbox className="mr-2 h-4 w-4" /> Select a table
          </div>
        )}
      </section>
    </div>
  )
}

function TableView({ projectId, tableName }: { projectId: string; tableName: string }) {
  const { data: detail, loading: detailLoading, error: detailError } = useAsync(
    () => api.getTable(projectId, tableName),
    [projectId, tableName],
  )

  const [pages, setPages] = useState<RowsPage[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setPages([])
    setError(null)
    let cancelled = false
    setLoading(true)
    api.getRows(projectId, tableName, { limit: 100 }).then(
      (page) => {
        if (!cancelled) setPages([page])
        if (!cancelled) setLoading(false)
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
  }, [projectId, tableName])

  const loadMore = async () => {
    const last = pages[pages.length - 1]
    if (!last?.next_cursor) return
    setLoading(true)
    try {
      const page = await api.getRows(projectId, tableName, { cursor: last.next_cursor, limit: 100 })
      setPages((p) => [...p, page])
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  if (detailLoading) return <div className="p-6 text-sm text-zinc-500">Loading table…</div>
  if (detailError || !detail)
    return <div className="p-6 text-sm text-rose-400">{detailError?.message ?? 'Failed to load table'}</div>

  const rows = pages.flatMap((p) => p.rows)
  const cols = pages[0]?.columns ?? detail.columns.map((c) => c.name)
  const hasMore = !!pages[pages.length - 1]?.next_cursor

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

      <div className="flex flex-wrap gap-2 border-b border-zinc-800 bg-zinc-900/30 px-3 py-2">
        {detail.columns.map((c) => (
          <div
            key={c.name}
            className="inline-flex items-center gap-1.5 rounded-md border border-zinc-800 bg-zinc-950/40 px-2 py-1 text-xs"
          >
            {c.is_pk && <KeyRound className="h-3 w-3 text-amber-400" />}
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
              {cols.map((name) => (
                <th
                  key={name}
                  className="border-b border-zinc-800 px-3 py-2 text-left text-[11px] font-medium text-zinc-400"
                >
                  <span className="text-zinc-200">{name}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && !loading && (
              <tr>
                <td
                  colSpan={cols.length + 1}
                  className="border-b border-zinc-900 py-10 text-center text-sm text-zinc-500"
                >
                  No rows
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
          Showing {rows.length.toLocaleString()} of {detail.row_count.toLocaleString()}
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

function Cell({ value }: { value: string | number | boolean | null }) {
  if (value === null) return <span className="text-zinc-700 italic">NULL</span>
  if (typeof value === 'boolean')
    return <span className={value ? 'text-emerald-400' : 'text-zinc-500'}>{String(value)}</span>
  if (typeof value === 'number')
    return <span className="text-amber-300">{value.toLocaleString()}</span>
  return <span>{String(value)}</span>
}
