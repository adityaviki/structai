import type {
  DocumentWire,
  ImportRunWire,
  ProjectWire,
  ProjectWithStats,
  RowsPage,
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
  // Projects
  listProjects: () => request<ProjectWithStats[]>('GET', '/api/projects'),
  getProject: (id: string) => request<ProjectWire>('GET', `/api/projects/${id}`),
  createProject: (body: { name: string; description?: string; emoji?: string; color?: string }) =>
    request<ProjectWire>('POST', '/api/projects', body),

  // Documents
  listDocuments: (projectId: string) =>
    request<DocumentWire[]>('GET', `/api/projects/${projectId}/documents`),
  uploadDocument: (projectId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<DocumentWire>('POST', `/api/projects/${projectId}/documents`, form)
  },

  // Imports
  listImports: (projectId: string) =>
    request<ImportRunWire[]>('GET', `/api/projects/${projectId}/imports`),
  createImport: (
    projectId: string,
    body: { document_id: string; instructions?: string; auto_mode?: boolean },
  ) => request<ImportRunWire>('POST', `/api/projects/${projectId}/imports`, body),
  getRun: (runId: string) => request<ImportRunWire>('GET', `/api/runs/${runId}`),

  // Tables
  listTables: (projectId: string) =>
    request<TableSummary[]>('GET', `/api/projects/${projectId}/tables`),
  getTable: (projectId: string, name: string) =>
    request<TableDetail>('GET', `/api/projects/${projectId}/tables/${encodeURIComponent(name)}`),
  getRows: (projectId: string, name: string, opts?: { cursor?: string; limit?: number }) => {
    const params = new URLSearchParams()
    if (opts?.cursor) params.set('cursor', opts.cursor)
    if (opts?.limit) params.set('limit', String(opts.limit))
    const q = params.toString() ? `?${params.toString()}` : ''
    return request<RowsPage>(
      'GET',
      `/api/projects/${projectId}/tables/${encodeURIComponent(name)}/rows${q}`,
    )
  },
}

export function runEventsUrl(runId: string): string {
  return `/api/runs/${runId}/events`
}
