import type {
  ClarificationWire,
  DocumentWire,
  ImportRunWire,
  LayoutPosition,
  ProjectLayout,
  ProjectSchema,
  ProjectWire,
  ProjectWithStats,
  RowsPage,
  SchemaProposalWire,
  SessionWire,
  SettingsPatch,
  SettingsWire,
  SnapshotWire,
  TableDetail,
  TableSummary,
} from './types'

type Json = Record<string, unknown> | unknown[] | string | number | boolean | null

interface ProblemDetails {
  type?: string
  title?: string
  status?: number
  detail?: string
}

export class ApiClientError extends Error {
  status: number
  detail: string
  constructor(status: number, problem: ProblemDetails) {
    super(problem.detail ?? problem.title ?? `HTTP ${status}`)
    this.status = status
    this.detail = problem.detail ?? this.message
  }
}

// Notified when a request comes back 401 after the session has gone (expired or
// signed out in another tab). The AuthProvider registers a handler that drops
// the user back to the login screen. Auth endpoints are excluded so the login
// form can show its own error instead of bouncing.
let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler
}

async function request<T>(
  method: string,
  path: string,
  body?: Json | FormData,
): Promise<T> {
  const init: RequestInit = { method }
  if (body instanceof FormData) {
    init.body = body
  } else if (body !== undefined) {
    init.headers = { 'content-type': 'application/json' }
    init.body = JSON.stringify(body)
  }
  const res = await fetch(path, init)
  if (!res.ok) {
    if (res.status === 401 && !path.startsWith('/api/auth/')) {
      onUnauthorized?.()
    }
    let problem: ProblemDetails = { status: res.status, title: res.statusText }
    try {
      problem = (await res.json()) as ProblemDetails
    } catch {
      /* ignore */
    }
    throw new ApiClientError(res.status, problem)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const api = {
  // Auth
  me: () => request<SessionWire>('GET', '/api/auth/me'),
  login: (username: string, password: string) =>
    request<SessionWire>('POST', '/api/auth/login', { username, password }),
  logout: () => request<SessionWire>('POST', '/api/auth/logout'),

  // Projects
  listProjects: () => request<ProjectWithStats[]>('GET', '/api/projects'),
  getProject: (id: string) => request<ProjectWire>('GET', `/api/projects/${id}`),
  createProject: (body: { name: string; description?: string; emoji?: string; color?: string }) =>
    request<ProjectWire>('POST', '/api/projects', body),
  deleteProject: (id: string) => request<void>('DELETE', `/api/projects/${id}`),

  // Documents
  listDocuments: (projectId: string) =>
    request<DocumentWire[]>('GET', `/api/projects/${projectId}/documents`),
  uploadDocument: (projectId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<DocumentWire>('POST', `/api/projects/${projectId}/documents`, form)
  },
  deleteDocument: (projectId: string, documentId: string) =>
    request<void>('DELETE', `/api/projects/${projectId}/documents/${documentId}`),

  // Imports
  listImports: (projectId: string) =>
    request<ImportRunWire[]>('GET', `/api/projects/${projectId}/imports`),
  createImport: (
    projectId: string,
    body: { document_id: string; instructions?: string; auto_mode?: boolean },
  ) => request<ImportRunWire>('POST', `/api/projects/${projectId}/imports`, body),
  getRun: (runId: string) => request<ImportRunWire>('GET', `/api/runs/${runId}`),
  cancelRun: (runId: string) => request<{ status: string }>('POST', `/api/runs/${runId}/cancel`),
  undoRun: (runId: string) => request<ImportRunWire>('POST', `/api/runs/${runId}/undo`),
  restartRun: (runId: string) => request<ImportRunWire>('POST', `/api/runs/${runId}/restart`),
  answerClarification: (
    runId: string,
    clarId: string,
    body: { choice_id?: string; custom?: string },
  ) =>
    request<ClarificationWire>(
      'POST',
      `/api/runs/${runId}/clarifications/${clarId}/answer`,
      body,
    ),
  acceptSchemaProposal: (runId: string, proposalId: string) =>
    request<SchemaProposalWire>(
      'POST',
      `/api/runs/${runId}/schema-proposals/${proposalId}/accept`,
    ),
  reviseSchemaProposal: (runId: string, proposalId: string, feedback: string) =>
    request<SchemaProposalWire>(
      'POST',
      `/api/runs/${runId}/schema-proposals/${proposalId}/revise`,
      { feedback },
    ),

  // Tables
  listTables: (projectId: string) =>
    request<TableSummary[]>('GET', `/api/projects/${projectId}/tables`),
  getTable: (projectId: string, name: string) =>
    request<TableDetail>('GET', `/api/projects/${projectId}/tables/${encodeURIComponent(name)}`),
  getRows: (
    projectId: string,
    name: string,
    opts?: {
      cursor?: string
      limit?: number
      sort?: string
      dir?: 'asc' | 'desc'
      filters?: { col: string; op: string; value: string }[]
    },
  ) => {
    const params = new URLSearchParams()
    if (opts?.cursor) params.set('cursor', opts.cursor)
    if (opts?.limit) params.set('limit', String(opts.limit))
    if (opts?.sort) params.set('sort', opts.sort)
    if (opts?.dir) params.set('dir', opts.dir)
    for (const f of opts?.filters ?? []) {
      params.append('filter', `${f.col}:${f.op}:${f.value}`)
    }
    const q = params.toString() ? `?${params.toString()}` : ''
    return request<RowsPage>(
      'GET',
      `/api/projects/${projectId}/tables/${encodeURIComponent(name)}/rows${q}`,
    )
  },

  // Schema diagram
  getSchema: (projectId: string) =>
    request<ProjectSchema>('GET', `/api/projects/${projectId}/schema`),
  getLayout: (projectId: string) =>
    request<ProjectLayout>('GET', `/api/projects/${projectId}/schema/layout`),
  saveLayout: (projectId: string, positions: LayoutPosition[]) =>
    request<ProjectLayout>('POST', `/api/projects/${projectId}/schema/layout`, { positions }),

  // Settings
  getSettings: () => request<SettingsWire>('GET', '/api/settings'),
  patchSettings: (patch: SettingsPatch) =>
    request<SettingsWire>('PATCH', '/api/settings', patch as Record<string, unknown>),
  setProjectModel: (projectId: string, model_override: string | null) =>
    request<{ model_override: string | null }>(
      'PUT',
      `/api/projects/${projectId}/model`,
      { model_override },
    ),

  // Snapshots
  listSnapshots: (projectId: string) =>
    request<SnapshotWire[]>('GET', `/api/projects/${projectId}/snapshots`),
  pinSnapshot: (projectId: string, runId: string) =>
    request<SnapshotWire>('POST', `/api/projects/${projectId}/snapshots/${runId}/pin`),
  deleteSnapshot: (projectId: string, runId: string) =>
    request<void>('DELETE', `/api/projects/${projectId}/snapshots/${runId}`),
}

export function runEventsUrl(runId: string): string {
  return `/api/runs/${runId}/events`
}
