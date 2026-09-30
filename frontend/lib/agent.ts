import type { CampSearchResult } from '@/lib/api'

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
}

export interface Family {
  id: string
  profile: FamilyProfile
  events: FamilyEvent[]
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

function writeFamilyId(id: string) {
  try { localStorage.setItem(FAMILY_KEY, id) } catch {}
}

/** Load this browser's family, creating one on first visit. */
export async function loadFamily(): Promise<Family> {
  const existing = readFamilyId()
  if (existing) {
    const res = await fetch(`${API}/api/v1/families/${existing}`, { cache: 'no-store' })
    if (res.ok) return res.json()
  }
  const res = await fetch(`${API}/api/v1/families`, { method: 'POST' })
  if (!res.ok) throw new Error('Could not start a session')
  const family: Family = await res.json()
  writeFamilyId(family.id)
  return { ...family, events: family.events ?? [] }
}

export function calendarFeedUrl(familyId: string): string {
  return `${API}/api/v1/families/${familyId}/calendar.ics`
}

/** Stream one agent turn. Calls onEvent for each server-sent event. */
export async function streamChat(
  body: { family_id: string; conversation_id?: string | null; message: string },
  onEvent: (e: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API}/api/v1/agent/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
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
