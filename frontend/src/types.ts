export type ImportStatus =
  | 'queued'
  | 'profiling'
  | 'generating'
  | 'executing'
  | 'fixing'
  | 'validating'
  | 'needs_clarification'
  | 'completed'
  | 'failed'
  | 'cancelling'
  | 'cancelled'
  | 'reverted'

export type DocumentStatus = 'uploaded' | 'importing' | 'imported' | 'failed' | 'needs_attention'

export type PipelineStepKey =
  | 'profile'
  | 'generate'
  | 'execute'
  | 'validate'

export type PipelineStepStatus = 'pending' | 'running' | 'success' | 'error' | 'warning'

export interface PipelineStep {
  key: PipelineStepKey
  title: string
  status: PipelineStepStatus
  startedAt?: string
  durationMs?: number
  /** Markdown-ish detail rendered in the step body */
  summary?: string
  /** Optional code preview (e.g. generated import script) */
  code?: string
  language?: 'sql' | 'python' | 'json'
  /** Attempt counter (for fixing loops) */
  attempts?: number
  errors?: string[]
}

export interface Clarification {
  id: string
  question: string
  context: string
  options: { id: string; label: string; description?: string }[]
  /** If the user already answered */
  answer?: string
}

export interface ImportRun {
  id: string
  documentId: string
  projectId: string
  /** Pretty name to show in lists; usually matches the doc */
  title: string
  status: ImportStatus
  startedAt: string
  finishedAt?: string
  /** 0-100 */
  progress: number
  steps: PipelineStep[]
  clarifications?: Clarification[]
  /** Created tables by this run */
  createdTables?: string[]
  rowsImported?: number
  totalRows?: number
  /** Optional natural-language instructions the user gave the agent when starting the run */
  instructions?: string
  /** When true, the agent makes its own decisions instead of pausing to ask the user */
  autoMode?: boolean
  /** Decisions the agent recorded on its own (only meaningful when autoMode is true) */
  autoDecisions?: { question: string; choice: string; reasoning?: string }[]
}

export interface Document {
  id: string
  projectId: string
  name: string
  /** e.g. csv, tsv, xlsx */
  ext: 'csv' | 'tsv' | 'xlsx' | 'json'
  sizeBytes: number
  uploadedAt: string
  status: DocumentStatus
  rowsPreview?: string[][]
  columnsPreview?: string[]
  /** Latest import run id, if any */
  lastImportId?: string
}

export interface Column {
  name: string
  type: string
  nullable?: boolean
  isPK?: boolean
  fk?: { table: string; column: string }
}

export interface TableInfo {
  id: string
  projectId: string
  name: string
  description?: string
  columns: Column[]
  rows: (string | number | boolean | null)[][]
  rowCount: number
  /** Document(s) this table was sourced from */
  sourceDocumentIds: string[]
}

export interface Project {
  id: string
  name: string
  description?: string
  emoji?: string
  color?: string
  createdAt: string
  updatedAt: string
}
