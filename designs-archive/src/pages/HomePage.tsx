import { ArrowRight, Database, FileSpreadsheet, Plus, Sparkles, Workflow } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useMemo, useState } from 'react'
import { Logo } from '../components/ui/Logo'
import { Modal } from '../components/ui/Modal'
import {
  documents,
  formatRelative,
  getDocuments,
  getImports,
  getTables,
  importRuns,
  projects,
} from '../data/mockData'
import { StatusBadge } from '../components/ui/StatusBadge'

export function HomePage() {
  const [showNew, setShowNew] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')

  const activeImports = useMemo(
    () =>
      importRuns.filter((r) =>
        ['executing', 'fixing', 'profiling', 'generating', 'validating', 'needs_clarification', 'queued'].includes(
          r.status,
        ),
      ),
    [],
  )

  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-30 border-b border-zinc-900 bg-zinc-950/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <Logo />
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowNew(true)}
              className="btn-primary"
            >
              <Plus className="h-4 w-4" />
              New project
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-10">
        {/* Hero */}
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
              Upload CSV, TSV, XLSX or JSON files. An AI agent profiles each file, writes the
              import script, runs it, fixes its own errors, and asks for clarification when it
              has to make a judgment call.
            </p>
            <div className="mt-6 flex flex-wrap items-center gap-2 text-xs text-zinc-400">
              <span className="chip"><FileSpreadsheet className="h-3 w-3" />Any structured file</span>
              <span className="chip"><Workflow className="h-3 w-3" />Self-healing scripts</span>
              <span className="chip"><Database className="h-3 w-3" />Normalized output</span>
            </div>
          </div>
        </section>

        {/* Active imports strip */}
        {activeImports.length > 0 && (
          <section className="mt-8">
            <div className="mb-3 flex items-baseline justify-between">
              <h2 className="text-sm font-medium text-zinc-300">In-flight imports</h2>
              <span className="text-xs text-zinc-500">
                {activeImports.length} in the queue · 1 running at a time
              </span>
            </div>
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              {activeImports.map((run) => {
                const project = projects.find((p) => p.id === run.projectId)!
                return (
                  <Link
                    key={run.id}
                    to={`/projects/${run.projectId}/imports/${run.id}`}
                    className="card group p-4 hover:border-brand-500/40 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-zinc-100">{run.title}</p>
                        <p className="mt-0.5 truncate text-xs text-zinc-500">{project.emoji} {project.name}</p>
                      </div>
                      <StatusBadge status={run.status} />
                    </div>
                    <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-zinc-800">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-brand-500 to-emerald-400 transition-all"
                        style={{ width: `${run.progress}%` }}
                      />
                    </div>
                    <div className="mt-2 flex items-center justify-between text-[11px] text-zinc-500">
                      <span>{run.status === 'queued' ? 'Waiting' : `${run.progress}%`}</span>
                      <span>{run.status === 'queued' ? 'Queued' : 'Started'} {formatRelative(run.startedAt)}</span>
                    </div>
                  </Link>
                )
              })}
            </div>
          </section>
        )}

        {/* Projects */}
        <section className="mt-10">
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-sm font-medium text-zinc-300">Your projects</h2>
            <button
              onClick={() => setShowNew(true)}
              className="text-xs text-brand-400 hover:text-brand-300"
            >
              + new
            </button>
          </div>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {projects.map((p) => {
              const tables = getTables(p.id)
              const docs = getDocuments(p.id)
              const imports = getImports(p.id)
              const completedImports = imports.filter((r) => r.status === 'completed').length
              return (
                <Link
                  key={p.id}
                  to={`/projects/${p.id}`}
                  className="card group relative overflow-hidden p-5 hover:border-zinc-700 transition-colors"
                >
                  <div className={`pointer-events-none absolute -top-12 -right-12 h-32 w-32 rounded-full bg-gradient-to-br ${p.color} blur-2xl opacity-60 group-hover:opacity-100 transition-opacity`} />
                  <div className="relative">
                    <div className="flex items-center gap-3">
                      <span className="text-2xl">{p.emoji}</span>
                      <div className="min-w-0">
                        <h3 className="truncate font-semibold text-zinc-100">{p.name}</h3>
                        <p className="truncate text-xs text-zinc-500">{p.description}</p>
                      </div>
                    </div>
                    <div className="mt-5 grid grid-cols-3 gap-3 text-center">
                      <div className="rounded-md border border-zinc-800/80 bg-zinc-900/40 p-2">
                        <div className="text-lg font-semibold text-zinc-100">{tables.length}</div>
                        <div className="text-[10px] uppercase tracking-wider text-zinc-500">Tables</div>
                      </div>
                      <div className="rounded-md border border-zinc-800/80 bg-zinc-900/40 p-2">
                        <div className="text-lg font-semibold text-zinc-100">{docs.length}</div>
                        <div className="text-[10px] uppercase tracking-wider text-zinc-500">Docs</div>
                      </div>
                      <div className="rounded-md border border-zinc-800/80 bg-zinc-900/40 p-2">
                        <div className="text-lg font-semibold text-zinc-100">{completedImports}</div>
                        <div className="text-[10px] uppercase tracking-wider text-zinc-500">Imports</div>
                      </div>
                    </div>
                    <div className="mt-4 flex items-center justify-between text-xs text-zinc-500">
                      <span>Updated {formatRelative(p.updatedAt)}</span>
                      <span className="inline-flex items-center gap-1 text-brand-400 opacity-0 group-hover:opacity-100 transition-opacity">
                        Open <ArrowRight className="h-3 w-3" />
                      </span>
                    </div>
                  </div>
                </Link>
              )
            })}

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

        <footer className="mt-16 border-t border-zinc-900 pt-4 text-center text-xs text-zinc-600">
          {documents.length} documents · {importRuns.length} import runs across {projects.length} projects
        </footer>
      </main>

      <Modal
        open={showNew}
        onClose={() => setShowNew(false)}
        title="New project"
        description="Each project is its own database. You can have many imports inside it."
        footer={
          <>
            <button className="btn-ghost" onClick={() => setShowNew(false)}>
              Cancel
            </button>
            <button
              className="btn-primary"
              onClick={() => {
                setShowNew(false)
                setName('')
                setDescription('')
              }}
              disabled={!name}
            >
              Create
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
          <div className="rounded-md border border-zinc-800 bg-zinc-900/40 p-3 text-xs text-zinc-400">
            <span className="text-zinc-300">Prototype:</span> creating a project doesn't persist
            yet — use the existing demo projects to explore the UI.
          </div>
        </div>
      </Modal>
    </div>
  )
}
