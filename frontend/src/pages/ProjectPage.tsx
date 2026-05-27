import {
  ChevronRight,
  Database,
  FileSpreadsheet,
  GitBranch,
  Plus,
  Settings as SettingsIcon,
  Trash2,
  Upload,
} from 'lucide-react'
import { useState } from 'react'
import { NavLink, Navigate, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import clsx from 'clsx'
import { Logo } from '../components/ui/Logo'
import { DataTab } from '../components/tabs/DataTab'
import { ImportsTab } from '../components/tabs/ImportsTab'
import { ImportDetail } from '../components/tabs/ImportDetail'
import { SchemaTab } from '../components/tabs/SchemaTab'
import { DocumentsTab } from '../components/tabs/DocumentsTab'
import { ProjectSettingsTab } from '../components/tabs/ProjectSettingsTab'
import { NewImportModal } from '../components/NewImportModal'
import { Modal } from '../components/ui/Modal'
import { api } from '../api/client'
import { useAsync } from '../api/hooks'

export function ProjectPage() {
  const { projectId = '' } = useParams()
  const navigate = useNavigate()
  const [showNewImport, setShowNewImport] = useState(false)
  const [importsRefresh, setImportsRefresh] = useState(0)
  const [showDelete, setShowDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const { data: project, loading, error } = useAsync(() => api.getProject(projectId), [projectId])

  if (loading) return <p className="p-10 text-sm text-zinc-500">Loading project…</p>
  if (error || !project) return <Navigate to="/" replace />

  const onDelete = async () => {
    setDeleting(true)
    setDeleteError(null)
    try {
      await api.deleteProject(projectId)
      navigate('/', { replace: true })
    } catch (err) {
      setDeleteError((err as Error).message)
    } finally {
      setDeleting(false)
    }
  }

  const tabs = [
    { to: 'imports', label: 'Imports', icon: FileSpreadsheet },
    { to: 'data', label: 'Data', icon: Database },
    { to: 'schema', label: 'Schema', icon: GitBranch },
    { to: 'documents', label: 'Documents', icon: Upload },
    { to: 'settings', label: 'Settings', icon: SettingsIcon },
  ]

  const onImportStarted = () => setImportsRefresh((n) => n + 1)

  return (
    <div className="flex h-full min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-zinc-900 bg-zinc-950/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-6 py-3">
          <div className="flex min-w-0 items-center gap-2">
            <Logo />
            <ChevronRight className="h-4 w-4 text-zinc-700" />
            <div className="flex min-w-0 items-center gap-2">
              <span className="text-base">{project.emoji ?? '📦'}</span>
              <h1 className="truncate text-sm font-medium text-zinc-100">{project.name}</h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowDelete(true)}
              className="btn-ghost text-rose-300/80 hover:bg-rose-500/10 hover:text-rose-200"
              title="Delete project"
            >
              <Trash2 className="h-4 w-4" />
            </button>
            <button onClick={() => setShowNewImport(true)} className="btn-primary">
              <Plus className="h-4 w-4" />
              New import
            </button>
          </div>
        </div>
        <nav className="mx-auto flex max-w-7xl items-center gap-1 px-4">
          {tabs.map((t) => (
            <NavLink
              key={t.to}
              to={t.to}
              className={({ isActive }) =>
                clsx(
                  'relative inline-flex items-center gap-2 border-b-2 px-3 py-2.5 text-sm transition-colors',
                  isActive
                    ? 'border-brand-400 text-zinc-100'
                    : 'border-transparent text-zinc-400 hover:text-zinc-200',
                )
              }
            >
              <t.icon className="h-3.5 w-3.5" />
              {t.label}
            </NavLink>
          ))}
        </nav>
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-6 py-6">
        <Routes>
          <Route index element={<Navigate to="imports" replace />} />
          <Route path="data" element={<DataTab projectId={projectId} />} />
          <Route path="data/:tableName" element={<DataTab projectId={projectId} />} />
          <Route
            path="imports"
            element={<ImportsTab projectId={projectId} refreshKey={importsRefresh} />}
          />
          <Route path="imports/:importId" element={<ImportDetail />} />
          <Route path="schema" element={<SchemaTab projectId={projectId} />} />
          <Route
            path="documents"
            element={<DocumentsTab projectId={projectId} onNewImport={() => setShowNewImport(true)} />}
          />
          <Route
            path="settings"
            element={<ProjectSettingsTab project={project} />}
          />
          <Route path="*" element={<Navigate to="imports" replace />} />
        </Routes>
      </main>

      <NewImportModal
        open={showNewImport}
        onClose={() => setShowNewImport(false)}
        projectId={projectId}
        onStarted={onImportStarted}
      />

      <Modal
        open={showDelete}
        onClose={() => setShowDelete(false)}
        title="Delete project"
        description="This drops the project's Postgres database, every snapshot, and all uploaded files. It cannot be undone."
        footer={
          <>
            <button className="btn-ghost" onClick={() => setShowDelete(false)} disabled={deleting}>
              Cancel
            </button>
            <button
              className="btn-primary !bg-rose-500 hover:!bg-rose-400"
              onClick={() => void onDelete()}
              disabled={deleting}
            >
              {deleting ? 'Deleting…' : `Delete ${project.name}`}
            </button>
          </>
        }
      >
        {deleteError && <p className="text-sm text-rose-400">{deleteError}</p>}
      </Modal>
    </div>
  )
}
