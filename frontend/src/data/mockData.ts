import type {
  Document,
  ImportRun,
  Project,
  TableInfo,
} from '../types'

// Phase 0: empty data. Pages render their loading/empty states.
// Phase 1 replaces these with real API-backed hooks.

export const projects: Project[] = []
export const salesTables: TableInfo[] = []
export const hrTables: TableInfo[] = []
export const invTables: TableInfo[] = []
export const allTables: TableInfo[] = []
export const documents: Document[] = []
export const importRuns: ImportRun[] = []

export const getProject = (id: string) => projects.find((p) => p.id === id)
export const getTables = (projectId: string) =>
  allTables.filter((t) => t.projectId === projectId)
export const getDocuments = (projectId: string) =>
  documents.filter((d) => d.projectId === projectId)
export const getImports = (projectId: string) =>
  importRuns.filter((r) => r.projectId === projectId)
export const getImport = (id: string) => importRuns.find((r) => r.id === id)
export const getDocument = (id: string) => documents.find((d) => d.id === id)

export const formatBytes = (n: number) => {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

export const formatRelative = (iso: string, now = new Date()) => {
  const then = new Date(iso).getTime()
  const diffSec = Math.round((now.getTime() - then) / 1000)
  if (diffSec < 60) return `${diffSec}s ago`
  if (diffSec < 3600) return `${Math.round(diffSec / 60)}m ago`
  if (diffSec < 86_400) return `${Math.round(diffSec / 3600)}h ago`
  const days = Math.round(diffSec / 86_400)
  if (days < 30) return `${days}d ago`
  const months = Math.round(days / 30)
  if (months < 12) return `${months}mo ago`
  return `${Math.round(months / 12)}y ago`
}

export const formatDuration = (ms: number) => {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  const m = Math.floor(ms / 60_000)
  const s = Math.round((ms % 60_000) / 1000)
  return `${m}m ${s}s`
}
