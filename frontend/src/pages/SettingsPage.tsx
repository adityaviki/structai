import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, KeyRound, Save, ShieldCheck } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../api/client'
import { useAsync } from '../api/hooks'
import { Logo } from '../components/ui/Logo'
import { ThemeToggle } from '../components/ui/ThemeToggle'
import { LogoutButton } from '../components/ui/LogoutButton'

const MODEL_OPTIONS = [
  { id: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6 (default)' },
  { id: 'claude-opus-4-7', label: 'Claude Opus 4.7' },
]

export function SettingsPage() {
  const { data, loading, error, reload } = useAsync(() => api.getSettings(), [])
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState('')
  const [keepN, setKeepN] = useState(10)
  const [maxAge, setMaxAge] = useState(30)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (!data) return
    setModel(data.default_model)
    setKeepN(data.snapshot_keep_last_n)
    setMaxAge(data.snapshot_max_age_days)
  }, [data])

  const save = async () => {
    setSaving(true)
    setSaveError(null)
    setSaved(false)
    try {
      const patch: Parameters<typeof api.patchSettings>[0] = {
        default_model: model,
        snapshot_keep_last_n: keepN,
        snapshot_max_age_days: maxAge,
      }
      if (apiKey.trim()) patch.anthropic_api_key = apiKey.trim()
      await api.patchSettings(patch)
      setApiKey('')
      setSaved(true)
      reload()
    } catch (err) {
      setSaveError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-30 border-b border-zinc-900 bg-zinc-950/80 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center gap-3 px-6 py-3">
          <Logo />
          <div className="ml-auto" />
          <ThemeToggle />
          <LogoutButton />
          <Link
            to="/"
            className="inline-flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-200"
          >
            <ArrowLeft className="h-3 w-3" /> Back to projects
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-zinc-400">Single-user app — these apply to your local install.</p>

        {loading && <p className="mt-6 text-sm text-zinc-500">Loading…</p>}
        {error && <p className="mt-6 text-sm text-rose-400">{error.message}</p>}

        {data && (
          <div className="mt-8 space-y-6">
            {/* API key */}
            <section className="card p-5">
              <h2 className="flex items-center gap-2 text-sm font-medium text-zinc-100">
                <KeyRound className="h-4 w-4 text-brand-400" />
                Anthropic API key
              </h2>
              <p className="mt-1 text-xs text-zinc-500">
                Required for any LLM-driven stage. Env var <code>STRUCTAI_ANTHROPIC_API_KEY</code>{' '}
                takes precedence over what you save here.
              </p>
              <div className="mt-3 flex items-center gap-2 text-xs">
                <span
                  className={clsx(
                    'inline-flex items-center gap-1 rounded-full border px-2 py-0.5',
                    data.anthropic_key_present
                      ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                      : 'border-rose-500/30 bg-rose-500/10 text-rose-300',
                  )}
                >
                  <ShieldCheck className="h-3 w-3" />
                  {data.anthropic_key_present ? 'configured' : 'missing'} · source:{' '}
                  {data.anthropic_key_source}
                </span>
              </div>
              <input
                className="input mt-3"
                type="password"
                placeholder={
                  data.anthropic_key_source === 'env'
                    ? 'Set via env; UI value is ignored'
                    : 'sk-ant-…'
                }
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                disabled={data.anthropic_key_source === 'env'}
              />
            </section>

            {/* Default model */}
            <section className="card p-5">
              <h2 className="text-sm font-medium text-zinc-100">Default model</h2>
              <p className="mt-1 text-xs text-zinc-500">
                Used by all stages unless a project overrides it. Source: {data.default_model_source}.
              </p>
              <select
                className="input mt-3"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                disabled={data.default_model_source === 'env'}
              >
                {MODEL_OPTIONS.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.label}
                  </option>
                ))}
              </select>
            </section>

            {/* Retention */}
            <section className="card p-5">
              <h2 className="text-sm font-medium text-zinc-100">Snapshot retention</h2>
              <p className="mt-1 text-xs text-zinc-500">
                The hourly sweeper drops snapshots beyond these limits. Pinned snapshots are
                always kept.
              </p>
              <div className="mt-3 grid grid-cols-2 gap-3">
                <label className="text-xs">
                  <span className="text-zinc-400">Keep last</span>
                  <input
                    type="number"
                    min={0}
                    max={1000}
                    value={keepN}
                    onChange={(e) => setKeepN(Number(e.target.value) || 0)}
                    className="input mt-1"
                  />
                </label>
                <label className="text-xs">
                  <span className="text-zinc-400">Max age (days, 0 = no limit)</span>
                  <input
                    type="number"
                    min={0}
                    max={3650}
                    value={maxAge}
                    onChange={(e) => setMaxAge(Number(e.target.value) || 0)}
                    className="input mt-1"
                  />
                </label>
              </div>
            </section>

            {saveError && <p className="text-sm text-rose-400">{saveError}</p>}
            {saved && <p className="text-sm text-emerald-400">Saved.</p>}

            <div className="flex items-center justify-end">
              <button className="btn-primary" disabled={saving} onClick={() => void save()}>
                <Save className="h-3.5 w-3.5" />
                {saving ? 'Saving…' : 'Save settings'}
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
