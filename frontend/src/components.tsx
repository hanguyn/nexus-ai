import { AlertCircle, Inbox, LoaderCircle, X } from 'lucide-react'
import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { humanize } from './api'

export function Badge({ value }: { value: string }) {
  return <span className={`badge badge-${value.toLowerCase()}`}><i />{humanize(value)}</span>
}

export function PageHeader({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <div className="page-header"><div><h1>{title}</h1><p>{description}</p></div>{action}</div>
}

export function Notice({ message, error = false }: { message: string; error?: boolean }) {
  return <div className={`notice ${error ? 'notice-error' : ''}`} role={error ? 'alert' : 'status'}><AlertCircle size={17} />{message}</div>
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty"><Inbox size={22} />{children}</div>
}

export function Loading() {
  return <div className="empty" role="status"><LoaderCircle className="animate-spin" size={21} />Loading…</div>
}

export function Modal({ title, close, children }: { title: string; close: () => void; children: ReactNode }) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const element = dialog.current
    element?.showModal()
    return () => element?.close()
  }, [])
  return <dialog ref={dialog} onCancel={event => { event.preventDefault(); close() }} aria-labelledby="dialog-title">
    <div className="card-heading"><h2 id="dialog-title">{title}</h2><button className="icon-button" onClick={close} aria-label="Close dialog"><X size={20} /></button></div>
    {children}
  </dialog>
}
