import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  type Node,
  type Edge,
  type NodeChange,
  type NodeProps,
  type NodeTypes,
  Position,
  ReactFlow,
  applyNodeChanges,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import dagre from '@dagrejs/dagre'
import { KeyRound, Link2, Table2 } from 'lucide-react'
import { api } from '../../api/client'
import type { LayoutPosition, ProjectSchema, SchemaTable } from '../../api/types'

const NODE_WIDTH = 260
const ROW_HEIGHT = 26
const HEADER_HEIGHT = 44

type TableNodeData = { table: SchemaTable }
type TableNodeType = Node<TableNodeData, 'table'>

function autoLayout(tables: SchemaTable[]): Record<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', nodesep: 60, ranksep: 120 })

  for (const t of tables) {
    g.setNode(t.name, {
      width: NODE_WIDTH,
      height: HEADER_HEIGHT + ROW_HEIGHT * Math.max(1, t.columns.length) + 16,
    })
  }
  for (const t of tables) {
    for (const c of t.columns) {
      if (c.fk) g.setEdge(t.name, c.fk.table)
    }
  }
  dagre.layout(g)

  const out: Record<string, { x: number; y: number }> = {}
  for (const t of tables) {
    const node = g.node(t.name)
    out[t.name] = { x: node.x - NODE_WIDTH / 2, y: node.y - (HEADER_HEIGHT + ROW_HEIGHT * t.columns.length) / 2 }
  }
  return out
}

function TableNode({ data }: NodeProps<TableNodeType>) {
  const t = data.table
  return (
    <div className="overflow-hidden rounded-md border border-zinc-800 bg-zinc-950 shadow-lg" style={{ width: NODE_WIDTH }}>
      <div className="flex items-center justify-between gap-2 border-b border-zinc-800 bg-zinc-900/60 px-3 py-2">
        <div className="flex items-center gap-2 min-w-0">
          <Table2 className="h-3.5 w-3.5 shrink-0 text-brand-400" />
          <span className="truncate font-mono text-[13px] text-zinc-100">{t.name}</span>
        </div>
        <span className="text-[10px] text-zinc-500">{t.row_count.toLocaleString()} rows</span>
      </div>
      <ul className="divide-y divide-zinc-900 font-mono text-[12px]">
        {t.columns.map((c) => (
          <li key={c.name} className="relative flex items-center gap-1.5 px-3 py-1 text-zinc-300">
            <Handle
              id={`l-${c.name}`}
              type="target"
              position={Position.Left}
              className="!h-2 !w-2 !border-0 !bg-zinc-600"
            />
            {c.is_pk && <KeyRound className="h-3 w-3 shrink-0 text-amber-400" />}
            {c.fk && !c.is_pk && <Link2 className="h-3 w-3 shrink-0 text-sky-400" />}
            <span className="truncate text-zinc-200">{c.name}</span>
            <span className="ml-auto truncate text-zinc-500">{c.type}</span>
            <Handle
              id={`r-${c.name}`}
              type="source"
              position={Position.Right}
              className="!h-2 !w-2 !border-0 !bg-zinc-600"
            />
          </li>
        ))}
      </ul>
    </div>
  )
}

const nodeTypes: NodeTypes = { table: TableNode as unknown as NodeTypes[string] }

export function SchemaTab({ projectId }: { projectId: string }) {
  const [schema, setSchema] = useState<ProjectSchema | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [nodes, setNodes] = useState<TableNodeType[]>([])
  const [edges, setEdges] = useState<Edge[]>([])
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([api.getSchema(projectId), api.getLayout(projectId)]).then(
      ([s, l]) => {
        if (cancelled) return
        setSchema(s)
        const saved: Record<string, { x: number; y: number }> = {}
        for (const p of l.positions) saved[p.table_name] = { x: p.x, y: p.y }
        const auto = autoLayout(s.tables)
        const computed = s.tables.map<TableNodeType>((t) => ({
          id: t.name,
          type: 'table',
          position: saved[t.name] ?? auto[t.name] ?? { x: 0, y: 0 },
          data: { table: t },
        }))
        setNodes(computed)

        const e: Edge[] = []
        for (const t of s.tables) {
          for (const c of t.columns) {
            if (!c.fk) continue
            e.push({
              id: `${t.name}.${c.name}->${c.fk.table}.${c.fk.column}`,
              source: t.name,
              sourceHandle: `r-${c.name}`,
              target: c.fk.table,
              targetHandle: `l-${c.fk.column}`,
              markerEnd: { type: MarkerType.ArrowClosed, color: '#71717a' },
              style: { stroke: '#71717a', strokeWidth: 1.5 },
            })
          }
        }
        setEdges(e)
      },
      (err: Error) => {
        if (!cancelled) setError(err.message)
      },
    )
    return () => {
      cancelled = true
    }
  }, [projectId])

  const persistPositions = useCallback(
    (next: TableNodeType[]) => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => {
        const positions: LayoutPosition[] = next.map((n) => ({
          table_name: n.id,
          x: n.position.x,
          y: n.position.y,
        }))
        void api.saveLayout(projectId, positions).catch(() => {})
      }, 500)
    },
    [projectId],
  )

  const onNodesChange = useCallback(
    (changes: NodeChange<TableNodeType>[]) => {
      setNodes((curr) => {
        const next = applyNodeChanges(changes, curr)
        if (changes.some((c) => c.type === 'position' && !c.dragging)) {
          persistPositions(next)
        }
        return next
      })
    },
    [persistPositions],
  )

  const showEmpty = useMemo(
    () => schema !== null && schema.tables.length === 0,
    [schema],
  )

  if (error) return <p className="text-sm text-rose-400">{error}</p>
  if (!schema) return <p className="text-sm text-zinc-500">Loading schema…</p>

  if (showEmpty) {
    return (
      <div className="card flex flex-col items-center justify-center p-16 text-center">
        <Table2 className="h-6 w-6 text-zinc-500" />
        <h3 className="mt-4 text-base font-medium">No tables yet</h3>
        <p className="mt-1 text-sm text-zinc-400">
          Run an import — once tables exist, this tab shows them as an ER diagram.
        </p>
      </div>
    )
  }

  return (
    <div className="card h-[calc(100vh-9.5rem)] overflow-hidden">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        nodeTypes={nodeTypes}
        fitView
        proOptions={{ hideAttribution: true }}
        colorMode="dark"
      >
        <Background gap={20} color="#27272a" />
        <Controls position="bottom-right" showInteractive={false} />
      </ReactFlow>
    </div>
  )
}
