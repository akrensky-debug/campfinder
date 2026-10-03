import { authHeaders } from '@/lib/auth'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export type Role = 'owner' | 'co_parent' | 'caregiver' | 'viewer'
export type TaskKind = 'dropoff' | 'pickup' | 'form' | 'payment' | 'packing' | 'deadline' | 'other'
export type TaskStatus = 'open' | 'done' | 'skipped'

export const ROLE_LABELS: Record<Role, string> = {
  owner: 'Owner',
  co_parent: 'Co-parent',
  caregiver: 'Caregiver',
  viewer: 'Viewer',
}

export const ROLE_HELP: Record<Exclude<Role, 'owner'>, string> = {
  co_parent: 'The full plan: chat, calendar and every job',
  caregiver: 'Only the jobs you give them, plus the calendar',
  viewer: 'The calendar only',
}

export const KIND_LABELS: Record<TaskKind, string> = {
  dropoff: 'Drop-off',
  pickup: 'Pickup',
  form: 'Form',
  payment: 'Payment',
  packing: 'Packing',
  deadline: 'Deadline',
  other: 'To do',
}

export const KIND_ICONS: Record<TaskKind, string> = {
  dropoff: '🚗', pickup: '🚗', form: '📝', payment: '💳', packing: '🎒', deadline: '⏰', other: '•',
}

export interface Member {
  id: string
  display_name: string
  role: Role
  status: 'invited' | 'active'
  email: string | null
  kit_access: boolean
  invite_expires_at: string | null
  reminder_pref: 'daily' | 'day_before' | 'off' | null
  weekly_summary: boolean | null
  is_you: boolean
}

export interface Household {
  role: Role
  you: Member | null
  members: Member[]
  can_manage: boolean
  my_calendar_url: string | null
}

export interface Task {
  id: string
  kind: TaskKind
  title: string
  due_date: string
  due_time: string | null
  status: TaskStatus
  notes: string | null
  child_name: string | null
  assignee_id: string | null
  assignee_name: string | null
  event_id: string | null
  camp_id: string | null
  checklist: Array<{ item: string; done: boolean }>
  completed_at: string | null
  completed_by_name: string | null
}

export interface AuditEntry {
  actor_name: string
  via: string
  action: string
  target_type: string | null
  detail: Record<string, unknown>
  created_at: string
}

export interface InvitePreview {
  invited_by: string
  display_name: string
  role: Role
  role_help: string
  email_hint: string
  expires_at: string
  expired: boolean
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API}/api/v1${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(await authHeaders()), ...(init.headers || {}) },
    cache: 'no-store',
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : 'Something went wrong')
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

const json = (method: string, body?: unknown): RequestInit => ({ method, body: body === undefined ? undefined : JSON.stringify(body) })

export const getHousehold = (fid: string) => call<Household>(`/families/${fid}/household`)
export const inviteMember = (fid: string, body: { display_name: string; email: string; role: Exclude<Role, 'owner'> }) =>
  call<{ member: Member; url: string; emailed: boolean }>(`/families/${fid}/members/invite`, json('POST', body))
export const updateMember = (fid: string, mid: string, body: { display_name?: string; role?: Role; kit_access?: boolean }) =>
  call<Member>(`/families/${fid}/members/${mid}`, json('PATCH', body))
export const removeMember = (fid: string, mid: string) => call<void>(`/families/${fid}/members/${mid}`, json('DELETE'))
export const leaveFamily = (fid: string) => call<void>(`/families/${fid}/leave`, json('POST'))
export const updateMyPrefs = (fid: string, body: { reminder_pref?: string; weekly_summary?: boolean }) =>
  call<Member>(`/families/${fid}/me`, json('PATCH', body))
export const resetMyCalendar = (fid: string) => call<Household>(`/families/${fid}/me/calendar/reset`, json('POST'))

export const listTasks = (fid: string) => call<Task[]>(`/families/${fid}/tasks`)
export const createTasks = (fid: string, tasks: Array<Partial<Task> & { title: string; due_date: string }>) =>
  call<Task[]>(`/families/${fid}/tasks`, json('POST', tasks))
export const updateTask = (fid: string, tid: string, body: Partial<Pick<Task, 'status' | 'title' | 'due_date' | 'due_time' | 'notes' | 'checklist'>>) =>
  call<Task>(`/families/${fid}/tasks/${tid}`, json('PATCH', body))
export const deleteTask = (fid: string, tid: string) => call<void>(`/families/${fid}/tasks/${tid}`, json('DELETE'))
export const assignTasks = (fid: string, taskIds: string[], memberId: string | null) =>
  call<Task[]>(`/families/${fid}/tasks/assign`, json('POST', { task_ids: taskIds, member_id: memberId }))
export const generateTasks = (fid: string, body: { event_ids?: string[]; dropoff_time?: string | null; pickup_time?: string | null }) =>
  call<Task[]>(`/families/${fid}/tasks/generate`, json('POST', body))
export const getAudit = (fid: string) => call<AuditEntry[]>(`/families/${fid}/audit?limit=50`)

export const previewInvite = (token: string) => call<InvitePreview>(`/invites/${token}`)
export const acceptInvite = (token: string) => call<{ family_id: string; role: Role }>(`/invites/${token}/accept`, json('POST'))

/** Monday of the week containing an ISO date. */
export function weekOf(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7))
  // Local date parts: toISOString() would shift to UTC and land on Sunday east of Greenwich.
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function fmtDay(iso: string): string {
  return new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
}

export function fmtTime(t: string | null): string {
  if (!t) return ''
  const [h, m] = t.split(':').map(Number)
  return new Date(2000, 0, 1, h, m).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}

const AUDIT_TEXT: Record<string, string> = {
  invited: 'invited', invite_renewed: 'sent a new invite to', joined: 'joined the household', member_updated: 'changed access for',
  member_removed: 'removed', left: 'left the household', tasks_created: 'added', tasks_assigned: 'assigned',
  tasks_unassigned: 'unassigned', tasks_deleted: 'deleted', task_completed: 'completed', task_skipped: 'skipped',
  task_reopened: 'reopened', task_updated: 'edited', kit_viewed: 'opened the info kit', kit_saved: 'updated the info kit',
  kit_shared: 'shared the info kit with', kit_share_withdrawn: 'withdrew an info kit share',
}

export function describeAudit(e: AuditEntry): string {
  const d = e.detail as Record<string, unknown>
  const verb = AUDIT_TEXT[e.action] ?? e.action.replace(/_/g, ' ')
  let what = ''
  if (typeof d.name === 'string') what = d.name
  else if (typeof d.title === 'string') what = d.title
  else if (typeof d.recipient === 'string') what = d.recipient
  else if (typeof d.count === 'number') what = `${d.count} job${d.count === 1 ? '' : 's'}`
  const to = typeof d.to === 'string' ? ` to ${d.to}` : ''
  const via = e.via === 'assistant' ? ' (with the assistant)' : ''
  return `${e.actor_name} ${verb}${what ? ' ' + what : ''}${to}${via}`
}
