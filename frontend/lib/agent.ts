import type { CampSearchResult } from '@/lib/api'
import type { ActivityCard, ActivityProgram, FamilyWeek, ScheduleFitResult } from '@/lib/activities'
import { authHeaders } from '@/lib/auth'
import type { BookingUIData } from '@/components/booking/BookingBlocks'
import { Events } from '@/lib/analytics'
import type { Role, Task } from '@/lib/household'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const FAMILY_KEY = 'cf_family_id'

export interface Kid {
  name?: string | null
  age?: number | null
  interests?: string[]
  notes?: string | null
}

export interface FamilyProfile {
  home_location?: string | null
  kids?: Kid[]
  summer_start?: string | null
  summer_end?: string | null
  weekly_budget?: number | null
  needs?: string[]
  notes?: string | null
}

export interface FamilyEvent {
  id: string
  title: string
  start_date: string
  end_date: string
  child_name?: string | null
  camp_id?: string | null
  notes?: string | null
  // Year-round entries: weekly classes, practices, pickups, enrollment reminders.
  kind?: 'camp' | 'activity' | 'commitment' | 'reminder' | null
  start_time?: string | null
  end_time?: string | null
  rrule?: string | null
  location?: string | null
  offering_id?: string | null
}

export interface Family {
  id: string
  profile: FamilyProfile
  events: FamilyEvent[]
  calendar_url: string | null
  signed_in: boolean
  role: Role
  my_calendar_url: string | null
  can_open_kit: boolean
}

export interface Comparison {
  camps: Array<{
    camp_id: string
    name: string
    city: string
    state: string
    age_min: number | null
    age_max: number | null
    price_per_week: number | null
    session_count: number
    transportation: boolean
    extended_care: boolean
    meals_included: boolean
    verification_status: string
    distance_miles: number | null
  }>
  differences: string[]
}

export interface Plan {
  weeks: Array<{
    week_of: string
    week_end: string
    status: 'covered' | 'gap' | 'overlap'
    camps: Array<{ camp_id: string; name: string; session_dates: string; cost: number | null }>
  }>
  total_estimated_cost: number
  weeks_covered: number
  weeks_total: number
}

export type UIData =
  | { type: 'camps'; camps: CampSearchResult[] }
  | { type: 'camp_detail'; camp: CampSearchResult & { sessions?: Array<{ id: string; name: string | null; start_date: string; end_date: string; price: number | null }> } }
  | ({ type: 'comparison' } & Comparison)
  | ({ type: 'plan' } & Plan)
  | { type: 'calendar'; events: FamilyEvent[] }
  | { type: 'profile'; profile: FamilyProfile }
  | BookingUIData
  | { type: 'activities'; activities: ActivityCard[] }
  | { type: 'activity_detail'; activity: ActivityProgram }
  | { type: 'schedule_fit'; checked_against: string; results: ScheduleFitResult[] }
  | { type: 'week'; week: FamilyWeek; events: FamilyEvent[] }
  | { type: 'tasks'; title?: string | null; tasks: Task[] }
  | { type: 'household'; members: Array<{ id: string; name: string; role: Role; status: string }> }
  | { type: 'assign_proposal'; summary: string; member: { id: string; name: string; status: string } | null; task_ids: string[]; tasks: Task[] }
  | { type: 'invite_proposal'; display_name: string; role: Exclude<Role, 'owner'>; email: string }
  | { type: 'message_draft'; subject: string; body: string; recipients: Array<{ name: string; email: string | null }> }

export type AgentEvent =
  | { type: 'conversation'; id: string }
  | { type: 'text'; text: string }
  | { type: 'tool_start'; name: string; label: string }
  | { type: 'ui'; data: UIData }
  | { type: 'done' }
  | { type: 'error'; message: string }

function readFamilyId(): string | null {
  try { return localStorage.getItem(FAMILY_KEY) } catch { return null }
}

export function rememberFamily(id: string) {
  writeFamilyId(id)
}

function writeFamilyId(id: string) {
  try { localStorage.setItem(FAMILY_KEY, id) } catch {}
}

async function createGuestFamily(): Promise<Family> {
  const res = await fetch(`${API}/api/v1/families`, { method: 'POST' })
  if (!res.ok) throw new Error('Could not start a session')
  const family: Family = await res.json()
  writeFamilyId(family.id)
  return family
}

/**
 * Load this browser's family. Signed in: the account's family, saving the current
 * guest family to the account the first time. Signed out: the guest family, created
 * on first visit.
 */
export async function loadFamily(): Promise<Family> {
  const auth = await authHeaders()
  const existing = readFamilyId()

  if (auth.Authorization) {
    const pick = existing ? `?family_id=${encodeURIComponent(existing)}` : ''
    const mine = await fetch(`${API}/api/v1/me/family${pick}`, { headers: auth, cache: 'no-store' })
    if (mine.ok) {
      const family: Family = await mine.json()
      writeFamilyId(family.id)
      return family
    }
    const guestId = existing ?? (await createGuestFamily()).id
    let claimed = await fetch(`${API}/api/v1/families/${guestId}/claim`, { method: 'POST', headers: auth })
    if (!claimed.ok) {
      // The stored guest family is gone or belongs to someone else: start fresh.
      const fresh = await createGuestFamily()
      claimed = await fetch(`${API}/api/v1/families/${fresh.id}/claim`, { method: 'POST', headers: auth })
    }
    if (claimed.ok) {
      const family: Family = await claimed.json()
      writeFamilyId(family.id)
      Events.familySaved()
      return family
    }
  }

  if (existing) {
    const res = await fetch(`${API}/api/v1/families/${existing}`, { headers: auth, cache: 'no-store' })
    if (res.ok) return res.json()
  }
  return createGuestFamily()
}

/** New private calendar link; anyone holding the old one loses access. */
export async function resetCalendarLink(familyId: string): Promise<Family> {
  const res = await fetch(`${API}/api/v1/families/${familyId}/calendar/reset`, {
    method: 'POST', headers: await authHeaders(),
  })
  if (!res.ok) throw new Error('Could not reset the link')
  return res.json()
}

/** Permanently delete the family, its calendar, conversations and info kit. */
export async function deleteFamily(familyId: string): Promise<void> {
  const res = await fetch(`${API}/api/v1/families/${familyId}`, { method: 'DELETE', headers: await authHeaders() })
  if (!res.ok) throw new Error('Could not delete')
  try { localStorage.removeItem(FAMILY_KEY) } catch {}
}

/** Stream one agent turn. Calls onEvent for each server-sent event. */
export async function streamChat(
  body: { family_id: string; conversation_id?: string | null; message: string },
  onEvent: (e: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API}/api/v1/agent/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok || !res.body) throw new Error('Chat request failed')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let split
    while ((split = buffer.indexOf('\n\n')) !== -1) {
      const chunk = buffer.slice(0, split)
      buffer = buffer.slice(split + 2)
      const line = chunk.split('\n').find(l => l.startsWith('data: '))
      if (line) onEvent(JSON.parse(line.slice(6)))
    }
  }
}
