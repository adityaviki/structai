// Wire types matching backend Pydantic schemas. Kept in lockstep with the
// schemas/ directory in the backend. Field names are snake_case where the
// backend sends snake_case to keep this contract one-to-one.

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

export type PipelineStepKey = 'profile' | 'generate' | 'execute' | 'fix' | 'validate'
export type PipelineStepStatus = 'pending' | 'running' | 'success' | 'error' | 'warning'

export interface PipelineStepWire {
  key: PipelineStepKey
  title: string
  status: PipelineStepStatus
  summary: string | null
  code: string | null
  language: string | null
  attempts: number
  errors: string[] | null
  started_at: string | null
  duration_ms: number | null
}

export interface ClarificationOption {
  id: string
  label: string
  description?: string | null
}

export interface ClarificationWire {
  id: string
  run_id: string
  question: string
  context: string | null
  options: ClarificationOption[]
  answer_choice_id: string | null
  answer_custom: string | null
  auto_decision: boolean
  auto_reasoning: string | null
  created_at: string
  answered_at: string | null
}

export interface ImportRunWire {
  id: string
  project_id: string
  document_id: string
  title: string
  status: ImportStatus
  progress: number
  started_at: string
  finished_at: string | null
  rows_imported: number | null
  total_rows: number | null
  created_tables: string[] | null
  instructions: string | null
  auto_mode: boolean
  error_message: string | null
  undo_available: boolean
  reverted_at: string | null
  reverted_by_run_id: string | null
  steps: PipelineStepWire[]
  clarifications: ClarificationWire[]
}

export interface ProjectWire {
  id: string
  name: string
  description: string | null
  emoji: string | null
  color: string | null
  db_name: string
  created_at: string
  updated_at: string
}

export interface ProjectWithStats extends ProjectWire {
  stats: { tables: number; documents: number; imports_completed: number }
}

export interface DocumentWire {
  id: string
  project_id: string
  name: string
  ext: 'csv' | 'tsv' | 'xlsx' | 'json'
  size_bytes: number
  status: 'uploaded' | 'importing' | 'imported' | 'failed' | 'needs_attention'
  last_import_id: string | null
  uploaded_at: string
}

export interface TableSummary {
  name: string
  row_count: number
  column_count: number
}

export interface FkRef {
  table: string
  column: string
}

export interface ColumnWire {
  name: string
  type: string
  nullable: boolean
  is_pk: boolean
  fk: FkRef | null
}

export interface TableDetail {
  name: string
  columns: ColumnWire[]
  row_count: number
  editable: boolean
}

export interface RowsPage {
  columns: string[]
  rows: (string | number | boolean | null)[][]
  next_cursor: string | null
}
