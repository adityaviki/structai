import { GitBranch } from 'lucide-react'

export function SchemaTab() {
  return (
    <div className="card flex flex-col items-center justify-center p-16 text-center">
      <div className="rounded-full border border-zinc-800 bg-zinc-900 p-3">
        <GitBranch className="h-6 w-6 text-zinc-500" />
      </div>
      <h3 className="mt-4 text-base font-medium">Schema diagram</h3>
      <p className="mt-1 max-w-sm text-sm text-zinc-400">
        ER diagram with tables and foreign-key links lands in Phase 5.
      </p>
    </div>
  )
}
