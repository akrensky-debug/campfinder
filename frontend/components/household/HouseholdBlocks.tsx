'use client'

import { useState } from 'react'
import type { UIData } from '@/lib/agent'
import {
  KIND_ICONS, ROLE_HELP, ROLE_LABELS, assignTasks, fmtDay, fmtTime, inviteMember, type Role, type Task,
} from '@/lib/household'

type Of<T extends UIData['type']> = Extract<UIData, { type: T }>

const SHOWN = 8
const box = 'bg-white rounded-2xl border border-gray-200 p-4'
const primary = 'bg-brand-600 hover:bg-brand-700 text-white font-semibold px-4 py-2 rounded-xl text-sm disabled:opacity-50'

function TaskLines({ tasks }: { tasks: Task[] }) {
  return (
    <ul className="space-y-1">
      {tasks.slice(0, SHOWN).map(t => (
        <li key={t.id} className="text-sm text-gray-700 flex gap-2">
          <span>{KIND_ICONS[t.kind]}</span>
          <span className={`flex-1 ${t.status !== 'open' ? 'line-through text-gray-400' : ''}`}>{t.title}</span>
          <span className="text-gray-400 shrink-0">{fmtDay(t.due_date)}{t.due_time ? ` ${fmtTime(t.due_time)}` : ''}</span>
        </li>
      ))}
      {tasks.length > SHOWN && <li className="text-xs text-gray-400">+{tasks.length - SHOWN} more</li>}
    </ul>
  )
}

export function TasksCard({ data }: { data: Of<'tasks'> }) {
  if (!data.tasks.length) return null
  const people = Array.from(new Set(data.tasks.map(t => t.assignee_name ?? 'Nobody yet')))
  return (
    <div className={box}>
      <div className="flex justify-between items-baseline mb-2">
        <p className="text-sm font-semibold text-gray-900">{data.title ?? 'Jobs'} · {data.tasks.length}</p>
        <a href="/household" className="text-xs font-medium text-brand-700 hover:underline">Open the job list →</a>
      </div>
      <TaskLines tasks={data.tasks} />
      {people.length > 0 && <p className="text-xs text-gray-400 mt-2">Owners: {people.join(', ')}</p>}
    </div>
  )
}

export function HouseholdCard({ data }: { data: Of<'household'> }) {
  if (!data.members.length) return null
  return (
    <div className={`${box} flex flex-wrap gap-2`}>
      {data.members.map(m => (
        <span key={m.id} className="text-sm bg-gray-50 border border-gray-200 rounded-full px-3 py-1">
          {m.name} <span className="text-gray-400">· {ROLE_LABELS[m.role]}{m.status === 'invited' ? ', invited' : ''}</span>
        </span>
      ))}
    </div>
  )
}

export function AssignProposal({ data, familyId }: { data: Of<'assign_proposal'>; familyId?: string }) {
  const [state, setState] = useState<'idle' | 'busy' | 'done' | 'dismissed'>('idle')
  const [error, setError] = useState('')
  async function confirm() {
    if (!familyId) return
    setState('busy')
    setError('')
    try {
      await assignTasks(familyId, data.task_ids, data.member?.id ?? null)
      setState('done')
    } catch (e) {
      setError((e as Error).message)
      setState('idle')
    }
  }
  if (state === 'dismissed') return <p className="text-sm text-gray-400">Left as it was.</p>
  return (
    <div className={`${box} border-brand-200`}>
      <p className="text-sm font-semibold text-gray-900 mb-2">{data.summary}?</p>
      <TaskLines tasks={data.tasks} />
      {data.member?.status === 'invited' && (
        <p className="text-xs text-amber-700 mt-2">{data.member.name} hasn't accepted the invite yet; reminders start once they do.</p>
      )}
      <div className="flex items-center gap-3 mt-3">
        {state === 'done' ? (
          <p className="text-sm font-medium text-green-700">✓ Done. {data.member ? `${data.member.name} will get a reminder before each one.` : ''}</p>
        ) : (
          <>
            <button onClick={confirm} disabled={state === 'busy' || !familyId} className={primary}>
              {state === 'busy' ? 'Assigning…' : 'Confirm'}
            </button>
            <button onClick={() => setState('dismissed')} className="text-sm text-gray-500">Not now</button>
          </>
        )}
        {error && <span className="text-sm text-red-600">{error}</span>}
      </div>
    </div>
  )
}

export function InviteProposal({ data, familyId }: { data: Of<'invite_proposal'>; familyId?: string }) {
  const [email, setEmail] = useState(data.email)
  const [name, setName] = useState(data.display_name)
  const [role, setRole] = useState<Exclude<Role, 'owner'>>(data.role)
  const [state, setState] = useState<'idle' | 'busy' | 'done' | 'dismissed'>('idle')
  const [error, setError] = useState('')
  async function send(e: React.FormEvent) {
    e.preventDefault()
    if (!familyId) return
    setState('busy')
    setError('')
    try {
      await inviteMember(familyId, { display_name: name, email, role })
      setState('done')
    } catch (err) {
      setError((err as Error).message)
      setState('idle')
    }
  }
  if (state === 'dismissed') return <p className="text-sm text-gray-400">No invite sent.</p>
  if (state === 'done') return <p className="text-sm font-medium text-green-700">✓ Invite sent to {name} ({email}).</p>
  return (
    <form onSubmit={send} className={`${box} border-brand-200 space-y-3`}>
      <p className="text-sm font-semibold text-gray-900">Invite {name} to your household?</p>
      <div className="grid sm:grid-cols-2 gap-2">
        <input required value={name} onChange={e => setName(e.target.value)} className="border border-gray-200 rounded-lg px-3 py-2 text-sm" aria-label="Name" />
        <input required type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="Their email" className="border border-gray-200 rounded-lg px-3 py-2 text-sm" aria-label="Email" />
      </div>
      <select value={role} onChange={e => setRole(e.target.value as Exclude<Role, 'owner'>)} className="border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white">
        {(['co_parent', 'caregiver', 'viewer'] as const).map(r => <option key={r} value={r}>{ROLE_LABELS[r]}: {ROLE_HELP[r].toLowerCase()}</option>)}
      </select>
      <div className="flex items-center gap-3">
        <button disabled={state === 'busy' || !familyId} className={primary}>{state === 'busy' ? 'Sending…' : 'Send invite'}</button>
        <button type="button" onClick={() => setState('dismissed')} className="text-sm text-gray-500">Not now</button>
        {error && <span className="text-sm text-red-600">{error}</span>}
      </div>
    </form>
  )
}

export function MessageDraft({ data }: { data: Of<'message_draft'> }) {
  const [copied, setCopied] = useState(false)
  const emails = data.recipients.map(r => r.email).filter(Boolean) as string[]
  const mailto = emails.length
    ? `mailto:${emails.join(',')}?subject=${encodeURIComponent(data.subject)}&body=${encodeURIComponent(data.body)}`
    : null
  return (
    <div className={box}>
      <p className="text-xs uppercase tracking-wide text-gray-400 mb-1">Draft · to {data.recipients.map(r => r.name).join(', ')}</p>
      <p className="text-sm font-semibold text-gray-900 mb-1">{data.subject}</p>
      <p className="text-sm text-gray-700 whitespace-pre-wrap">{data.body}</p>
      <div className="flex gap-4 mt-3 text-sm font-medium">
        {mailto && <a href={mailto} className="text-brand-700 hover:underline">Open in email</a>}
        <button onClick={() => { navigator.clipboard?.writeText(`${data.subject}\n\n${data.body}`); setCopied(true) }} className="text-gray-600">
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
    </div>
  )
}
