import { X } from 'lucide-react'
import { useEffect } from 'react'
import clsx from 'clsx'

interface ModalProps {
  open: boolean
  onClose: () => void
  title?: string
  description?: string
  children: React.ReactNode
  footer?: React.ReactNode
  size?: 'sm' | 'md' | 'lg' | 'xl'
}

export function Modal({ open, onClose, title, description, children, footer, size = 'md' }: ModalProps) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 animate-fade-in"
      onClick={onClose}
    >
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        onClick={(e) => e.stopPropagation()}
        className={clsx(
          'relative w-full overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950 shadow-2xl animate-slide-up flex flex-col max-h-[90vh]',
          size === 'sm' && 'max-w-md',
          size === 'md' && 'max-w-lg',
          size === 'lg' && 'max-w-2xl',
          size === 'xl' && 'max-w-4xl',
        )}
      >
        {(title || description) && (
          <div className="flex items-start justify-between gap-4 border-b border-zinc-800 p-5">
            <div>
              {title && <h2 className="text-base font-semibold text-zinc-100">{title}</h2>}
              {description && (
                <p className="mt-1 text-sm text-zinc-400">{description}</p>
              )}
            </div>
            <button
              onClick={onClose}
              className="rounded-md p-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )}
        <div className="overflow-y-auto p-5">{children}</div>
        {footer && (
          <div className="border-t border-zinc-800 bg-zinc-900/30 p-4 flex justify-end gap-2">
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}
