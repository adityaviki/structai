import { ArrowRight, Database, FileSpreadsheet, Plus, Sparkles, Workflow } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { Logo } from '../components/ui/Logo'
import { Modal } from '../components/ui/Modal'
import { api } from '../api/client'
import { useAsync } from '../api/hooks'
import { formatRelative } from '../data/mockData'

export function HomePage() {
  const [showNew, setShowNew] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const navigate = useNavigate()

  const { data: projects, loading, error, reload } = useAsync(() => api.listProjects(), [])

  const closeModal = () => {
    setShowNew(false)
    setName('')
    setDescription('')
    setCreateError(null)
  }

  const onCreate = async () => {
    setSubmitting(true)
    setCreateError(null)
    try {
      const proj = await api.createProject({
        name: name.trim(),
        description: description.trim() || undefined,
      })
      closeModal()
      reload()
      navigate(`/projects/${proj.id}`)
    } catch (err) {
      setCreateError((err as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-30 border-b border-zinc-900 bg-zinc-950/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <Logo />
          <div className="flex items-center gap-2">
            <button onClick={() => setShowNew(true)} className="btn-primary">
              <Plus className="h-4 w-4" />
              New project
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-10">
        <section className="relative overflow-hidden rounded-2xl border border-zinc-900 bg-gradient-to-br from-zinc-900 via-zinc-950 to-zinc-950 p-8">
          <div className="absolute inset-0 grid-bg opacity-60" />
          <div className="absolute -top-32 -right-24 h-72 w-72 rounded-full bg-brand-500/20 blur-3xl" />
          <div className="relative max-w-2xl">
            <div className="inline-flex items-center gap-1.5 rounded-full border border-brand-500/20 bg-brand-500/10 px-2.5 py-1 text-xs text-brand-300">
              <Sparkles className="h-3 w-3" />
              Agentic import pipeline
            </div>
            <h1 className="mt-4 text-3xl font-semibold tracking-tight">
              Drop messy spreadsheets in. Get a clean database out.
            </h1>
            <p className="mt-3 text-zinc-400">
              Upload CSV files. An AI agent profiles each file, writes the import script, runs it,
              and surfaces what it did.
            </p>
            <div className="mt-6 flex flex-wrap items-center gap-2 text-xs text-zinc-400">
              <span className="chip"><FileSpreadsheet className="h-3 w-3" />Any structured file</span>
              <span className="chip"><Workflow className="h-3 w-3" />Self-healing scripts</span>
              <span className="chip"><Database className="h-3 w-3" />Normalized output</span>
            </div>
          </div>
        </section>

        <section className="mt-10">
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-sm font-medium text-zinc-300">Your projects</h2>
            <button onClick={() => setShowNew(true)} className="text-xs text-brand-400 hover:text-brand-300">
              + new
            </button>
          </div>
          {loading && <p className="text-sm text-zinc-500">Loading…</p>}
          {error && <p className="text-sm text-rose-400">{error.message}</p>}
          {!loading && !error && (projects?.length ?? 0) === 0 && (
            <div className="card flex flex-col items-center justify-center p-12 text-center">
              <Database className="h-6 w-6 text-zinc-500" />
              <p className="mt-3 text-sm text-zinc-300">No projects yet</p>
              <p className="mt-1 text-xs text-zinc-500">
                Click <span className="text-zinc-300">New project</span> to get started.
              </p>
            </div>
          )}
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {(projects ?? []).map((p) => (
              <Link
                key={p.id}
                to={`/projects/${p.id}`}
                className="card group relative overflow-hidden p-5 hover:border-zinc-700 transition-colors"
              >
                <div className="relative">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{p.emoji ?? '📦'}</span>
                    <div className="min-w-0">
                      <h3 className="truncate font-semibold text-zinc-100">{p.name}</h3>
                      <p className="truncate text-xs text-zinc-500">{p.description ?? ''}</p>
                    </div>
                  </div>
                  <div className="mt-5 grid grid-cols-3 gap-3 text-center">
                    <Stat label="Tables" value={p.stats.tables} />
                    <Stat label="Docs" value={p.stats.documents} />
                    <Stat label="Imports" value={p.stats.imports_completed} />
                  </div>
                  <div className="mt-4 flex items-center justify-between text-xs text-zinc-500">
                    <span>Updated {formatRelative(p.updated_at)}</span>
                    <span className="inline-flex items-center gap-1 text-brand-400 opacity-0 group-hover:opacity-100 transition-opacity">
                      Open <ArrowRight className="h-3 w-3" />
                    </span>
                  </div>
                </div>
              </Link>
            ))}

            <button
              onClick={() => setShowNew(true)}
              className="group flex flex-col items-center justify-center rounded-xl border border-dashed border-zinc-800 bg-zinc-950/50 p-5 text-center text-zinc-400 transition-colors hover:border-brand-500/40 hover:text-brand-300"
            >
              <Plus className="h-6 w-6" />
              <span className="mt-2 text-sm font-medium">New project</span>
              <span className="mt-0.5 text-xs text-zinc-500">Start a fresh database</span>
            </button>
          </div>
        </section>
      </main>

      <Modal
        open={showNew}
        onClose={closeModal}
        title="New project"
        description="Each project is its own database. You can have many imports inside it."
        footer={
          <>
            <button className="btn-ghost" onClick={closeModal}>Cancel</button>
            <button
              className="btn-primary"
              onClick={onCreate}
              disabled={!name.trim() || submitting}
            >
              {submitting ? 'Creating…' : 'Create'}
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-400">Name</label>
            <input
              className="input"
              autoFocus
              placeholder="e.g. Marketing campaigns 2026"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-400">Description (optional)</label>
            <textarea
              className="input"
              rows={3}
              placeholder="What kind of data goes here?"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          {createError && <p className="text-sm text-rose-400">{createError}</p>}
        </div>
      </Modal>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-zinc-800/80 bg-zinc-900/40 p-2">
      <div className="text-lg font-semibold text-zinc-100">{value}</div>
      <div className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</div>
    </div>
  )
}
