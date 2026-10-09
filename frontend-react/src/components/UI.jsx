/*
Small shared UI primitives used across the logged-in pages:
- Skeleton: shimmer placeholder shown while data is loading
- EmptyState: friendly blank-slate with an inline SVG, copy, and a CTA
- ConfirmModal: styled replacement for the native confirm() dialog
- Card: the established bg-navy-light rounded-2xl p-6 shadow-lg container
*/

import { useEffect } from 'react'

export function Skeleton({ className = '' }) {
  return <div className={`animate-pulse rounded-lg bg-navy/80 ${className}`} />
}

/* A ready-made skeleton card so "Loading..." text disappears everywhere. */
export function SkeletonCard({ lines = 3, className = '' }) {
  return (
    <div className={`bg-navy-light rounded-2xl p-6 shadow-lg ${className}`}>
      <Skeleton className="h-4 w-1/3 mb-4" />
      <div className="space-y-3">
        {Array.from({ length: lines }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    </div>
  )
}

/* Skeleton row for stat-card grids. */
export function StatSkeleton() {
  return (
    <div className="bg-navy-light rounded-2xl p-6 shadow-lg">
      <Skeleton className="h-3 w-1/2 mb-3" />
      <Skeleton className="h-6 w-3/4" />
    </div>
  )
}

export function EmptyState({ icon, title, description, action }) {
  return (
    <div className="flex flex-col items-center text-center py-12 px-6">
      {icon}
      <h3 className="text-white font-semibold mt-4">{title}</h3>
      <p className="text-gray-400 text-sm mt-1.5 max-w-sm leading-relaxed">{description}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

/*
Styled replacement for the native confirm() dialog. Renders inside a
full-screen overlay; Escape and overlay-click both cancel.
*/
export function ConfirmModal({ open, title, message, confirmLabel = 'Confirm', cancelLabel = 'Cancel', danger = false, onConfirm, onCancel }) {
  useEffect(() => {
    if (!open) return undefined
    function onKey(e) {
      if (e.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onCancel])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-[90] flex items-center justify-center bg-black/60 px-4"
      onClick={onCancel}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div
        className="bg-navy-light border border-gray-700 rounded-2xl p-6 shadow-2xl w-full max-w-md"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-white font-semibold text-lg">{title}</h3>
        <p className="text-gray-400 text-sm mt-2 leading-relaxed">{message}</p>
        <div className="flex justify-end gap-3 mt-6">
          <button
            type="button"
            onClick={onCancel}
            className="bg-navy border border-gray-700 hover:border-gray-500 text-gray-300 rounded-xl px-4 py-2 text-sm transition-colors"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={`rounded-xl px-4 py-2 text-sm font-semibold transition-colors ${
              danger
                ? 'bg-coral-dark hover:bg-coral text-navy'
                : 'bg-mint hover:bg-mint-dark text-navy'
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

/* The established card container, shared so the pattern stays consistent. */
export function Card({ title, children, className = '' }) {
  return (
    <div className={`bg-navy-light rounded-2xl p-6 shadow-lg ${className}`}>
      {title && <h2 className="text-white font-semibold text-lg mb-4">{title}</h2>}
      {children}
    </div>
  )
}
