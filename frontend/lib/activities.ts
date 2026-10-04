import { authHeaders } from '@/lib/auth'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

/** One scheduled run of a class: a term, a level, a weekly time. */
export interface ActivityOffering {
  id: string
  name: string | null
  term_name: string | null
  skill_level: string | null
  schedule: string | null          // 'Tuesdays 4–4:30pm'
  start_date: string | null
  end_date: string | null
  meetings_left: number | null
  price: number | null             // lowest full-term price
  per_class: number | null
  availability: 'open' | 'limited' | 'waitlist' | 'full' | 'unknown'
  enrollment_status: 'upcoming' | 'open' | 'closed' | 'unknown'
  enrollment_opens: string | null
  enrollment_closes: string | null
  location: string | null
}

/** A class, lesson, league or after-school program, as search results show it. */
export interface ActivityCard {
  id: string
  kind: 'class' | 'lesson' | 'league' | 'after_school' | 'event'
  name: string
  provider_name: string | null
  city: string | null
  state: string | null
  distance_miles: number | null
  age_min: number | null
  age_max: number | null
  per_class: number | null
  term_price: number | null
  trial_available: boolean | null
  verification_status: string
  registration_url: string | null
  match_reasons: string[]
  offerings: ActivityOffering[]
  offering_count: number
}

export interface ScheduleConflict {
  severity: 'clash' | 'logistics' | 'all_day'
  with: string
  with_child: string | null
  dates: string[]
  date_count: number
  detail: string
}

export interface ScheduleFitResult {
  offering_id: string
  program_id: string
  name: string
  schedule: string | null
  fits: boolean | null
  meetings_left?: number
  first_meeting?: string
  last_meeting?: string
  no_class_dates?: string[]
  conflicts: ScheduleConflict[]
  note?: string
}

export interface WeekItem {
  event_id: string | null
  title: string
  child_name: string | null
  kind: string | null
  all_day: boolean
  start_time: string | null
  end_time: string | null
  time_label: string
  location: string | null
}

export interface FamilyWeek {
  week_of: string
  week_end: string
  kids: string[]
  days: Array<{ date: string; label: string; items: WeekItem[] }>
}

/** The Family Activity schema's Program, for an activity's own page. */
export interface ActivityProgram {
  id: string
  kind: string
  name: string
  description: string | null
  categories: string[]
  ages: { min: number | null; max: number | null }
  location: { address: string | null; city: string; state: string }
  provider: { name: string | null; website: string | null; email: string | null; phone: string | null }
  price: { per_class: number | null; min: number | null; max: number | null; options: PriceOption[] }
  verification: {
    status: string
    last_updated: string | null
    fields_verified: string[]
    fields_unverified: string[]
    fields_missing: string[]
  }
  registration_url: string | null
  skill_levels: string[]
  trial_available: boolean | null
  trial_notes: string | null
  membership_required: boolean | null
  sessions: ActivitySession[] | null
}

export interface PriceOption {
  type: string
  amount: number
  audience: string | null
  covers: string | null
  notes: string | null
}

export interface ActivitySession {
  id: string
  name: string | null
  start_date: string | null
  end_date: string | null
  price: number | null
  availability: string
  calendar_url: string
  term: string | null
  skill_level: string | null
  ages: { min: number | null; max: number | null } | null
  location: { address: string | null; city: string; state: string } | null
  schedule: {
    days_of_week: string[]
    start_time: string | null
    end_time: string | null
    exdates: string[]
    meeting_count: number | null
    next_meeting: string | null
    summary: string | null
  } | null
  prices: PriceOption[]
  enrollment: { opens: string | null; closes: string | null; status: string } | null
}

export interface FieldSource {
  field_name: string
  offering_id: string | null
  source_type: string
  source_url: string | null
  retrieved_on: string | null
}

export const KIND_LABEL: Record<string, string> = {
  class: 'Class', lesson: 'Lessons', league: 'League', after_school: 'After school', event: 'Event',
}

export const PRICE_LABEL: Record<string, string> = {
  full_term: 'Full term', per_class: 'Per class', drop_in: 'Drop-in', trial: 'Trial',
  registration_fee: 'Registration fee', membership: 'Membership', monthly: 'Monthly',
}

export function money(n: number | null | undefined) {
  if (n == null) return null
  return n === 0 ? 'Free' : `$${n % 1 ? n.toFixed(2) : Math.round(n)}`
}

export async function getActivity(id: string): Promise<ActivityProgram> {
  const res = await fetch(`${API}/api/v1/activities/${id}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('Activity not found')
  return res.json()
}

export async function getActivitySources(id: string): Promise<FieldSource[]> {
  const res = await fetch(`${API}/api/v1/activities/${id}/sources`, { cache: 'no-store' })
  return res.ok ? res.json() : []
}

export async function getFamilyWeek(familyId: string, weekOf?: string): Promise<FamilyWeek> {
  const q = weekOf ? `?week_of=${weekOf}` : ''
  const res = await fetch(`${API}/api/v1/families/${familyId}/week${q}`, { headers: await authHeaders(), cache: 'no-store' })
  if (!res.ok) throw new Error('Could not load the week')
  return res.json()
}
