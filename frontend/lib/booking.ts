import { authHeaders } from '@/lib/auth'
import type { ShareSummary } from '@/lib/kit'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export type RegStatus = 'watching' | 'registered' | 'waitlisted' | 'cancelled'
export type PaymentStatus = 'unpaid' | 'deposit' | 'paid' | 'refunded'

export interface Registration {
  id: string
  camp_id: string
  camp_name: string
  session_id: string | null
  session_name: string | null
  start_date: string | null
  end_date: string | null
  child_name: string | null
  status: RegStatus
  payment_status: PaymentStatus
  amount_paid: number | null
  paid_on: string | null
  balance_due: number | null
  payment_due_date: string | null
  forms_due_date: string | null
  opens_at: string | null
  opens_at_source: 'camp' | 'family' | null
  closes_at: string | null
  registration_url: string | null
  confirmation_number: string | null
  notes: string | null
  remind: boolean
  next_step: string
  created_at: string
}

export type RegistrationUpdate = Partial<Pick<Registration,
  'status' | 'payment_status' | 'amount_paid' | 'paid_on' | 'balance_due' | 'payment_due_date' |
  'forms_due_date' | 'opens_at' | 'confirmation_number' | 'notes' | 'remind' | 'child_name' | 'session_id'>>

export interface FormFieldStatus {
  question: string
  kit_field: string | null
  required: boolean
  label: string | null
  ready: boolean | null
  missing_for: string[]
}

export interface RegistrationForm {
  camp_id: string
  typical: boolean
  platform: string | null
  form_url: string | null
  verified_at: string | null
  fields: FormFieldStatus[]
}

export interface ChecklistStep { key: string; text: string; done: boolean | null; href: string | null }

export interface RegisterChecklist {
  camp_id: string
  camp_name: string
  session_id: string | null
  session_name: string | null
  registration_url: string | null
  opens_at: string | null
  opens_at_source: 'camp' | 'family' | null
  closes_at: string | null
  price: number | null
  availability: string | null
  refund_policy: string | null
  form: RegistrationForm
  kit_available: boolean
  shares: ShareSummary[]
  steps: ChecklistStep[]
  registration: Registration | null
}

export interface PackagePreview {
  recipient: string
  camp_id: string
  children: string[]
  household_fields: string[]
  child_fields: string[]
  labels: Record<string, string>
  missing: string[]
  not_in_kit: string[]
  expires_in_days: number
  typical: boolean
}

export interface ReminderPrefs {
  email: string | null
  enabled: boolean
  opens_days: number[]
  deadline_days: number[]
}

export interface ReminderPreview {
  kind: 'opens' | 'payment_due' | 'forms_due'
  registration_id: string
  due_on: string
  days_before: number
  subject: string
  text: string
}

export interface BookingQuote {
  attempt_id: string
  provider: string
  environment: string
  seller: string
  item: string
  child_name: string | null
  price: number
  currency: string
  availability: string
  expires_at: string
  terms_url: string | null
  payment: string
  fields_to_send: string[]
  missing: string[]
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

const fam = (id: string) => `/families/${id}`

export const listRegistrations = (familyId: string) => call<Registration[]>(`${fam(familyId)}/registrations`)
export const watchRegistration = (familyId: string, body: {
  camp_id: string; session_id?: string | null; child_name?: string | null; opens_at?: string | null
}) => call<Registration>(`${fam(familyId)}/registrations`, { method: 'POST', body: JSON.stringify(body) })
export const updateRegistration = (familyId: string, id: string, body: RegistrationUpdate) =>
  call<Registration>(`${fam(familyId)}/registrations/${id}`, { method: 'PATCH', body: JSON.stringify(body) })
export const deleteRegistration = (familyId: string, id: string) =>
  call<void>(`${fam(familyId)}/registrations/${id}`, { method: 'DELETE' })

export function getChecklist(familyId: string, q: {
  camp_id?: string; session_id?: string | null; child?: string | null; registration_id?: string | null
}) {
  const params = new URLSearchParams()
  Object.entries(q).forEach(([k, v]) => { if (v) params.set(k, v) })
  return call<RegisterChecklist>(`${fam(familyId)}/register-checklist?${params}`)
}

export const previewPackage = (familyId: string, body: { camp_id: string; children: string[]; registration_id?: string | null }) =>
  call<PackagePreview>(`${fam(familyId)}/registration-package/preview`, { method: 'POST', body: JSON.stringify(body) })
export const sharePackage = (familyId: string, body: {
  camp_id: string; children: string[]; household_fields: string[]; child_fields: string[]; expires_in_days: number
}) => call<{ share: ShareSummary; url: string }>(`${fam(familyId)}/registration-package`, {
  method: 'POST', body: JSON.stringify({ ...body, confirm: true }),
})

export const getReminderPrefs = (familyId: string) => call<ReminderPrefs>(`${fam(familyId)}/registration-reminders`)
export const saveReminderPrefs = (familyId: string, prefs: ReminderPrefs) =>
  call<ReminderPrefs>(`${fam(familyId)}/registration-reminders`, { method: 'PUT', body: JSON.stringify(prefs) })
export const previewReminders = (familyId: string, on?: string) =>
  call<ReminderPreview[]>(`${fam(familyId)}/registration-reminders/preview${on ? `?on=${on}` : ''}`)

export const bookingStatus = () => call<{ enabled: boolean; environment: string }>('/booking/status')
export const getQuote = (familyId: string, registrationId: string) =>
  call<BookingQuote>(`${fam(familyId)}/bookings/quote`, { method: 'POST', body: JSON.stringify({ registration_id: registrationId }) })
export const confirmBooking = (familyId: string, attemptId: string, priceShownCents: number) =>
  call<{ status: string; provider_ref: string; payment_url: string | null; amount_due: number; registration: Registration }>(
    `${fam(familyId)}/bookings/${attemptId}/confirm`,
    { method: 'POST', body: JSON.stringify({ confirm: true, price_shown_cents: priceShownCents, read_camp_terms: true }) },
  )

// ---------------------------------------------------------------------------
// Display helpers
// ---------------------------------------------------------------------------

export const STATUS_LABEL: Record<RegStatus, string> = {
  watching: 'Watching', registered: 'Registered', waitlisted: 'Waitlist', cancelled: 'Cancelled',
}
export const STATUS_TONE: Record<RegStatus, string> = {
  watching: 'bg-gray-100 text-gray-700',
  registered: 'bg-green-50 text-green-700',
  waitlisted: 'bg-amber-50 text-amber-700',
  cancelled: 'bg-gray-50 text-gray-400',
}
export const PAY_LABEL: Record<PaymentStatus, string> = {
  unpaid: 'Not paid', deposit: 'Deposit paid', paid: 'Paid', refunded: 'Refunded',
}

export function fmtDay(d: string) {
  return new Date(d.length === 10 ? d + 'T00:00:00' : d).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
}

export function fmtWhen(ts: string) {
  return new Date(ts).toLocaleString(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

export function countdown(ts: string, now = Date.now()): string {
  const ms = new Date(ts).getTime() - now
  if (ms <= 0) return 'Open now'
  const days = Math.floor(ms / 86_400_000)
  const hours = Math.floor((ms % 86_400_000) / 3_600_000)
  if (days >= 2) return `Opens in ${days} days`
  if (days === 1) return `Opens in 1 day ${hours} h`
  const mins = Math.floor((ms % 3_600_000) / 60_000)
  return hours ? `Opens in ${hours} h ${mins} min` : `Opens in ${mins} min`
}

/** A Google Calendar link for registration opening, so a parent can set her own alarm. */
export function openingCalendarLink(camp: string, opensAt: string, url: string | null) {
  const start = new Date(opensAt)
  const end = new Date(start.getTime() + 30 * 60_000)
  const f = (d: Date) => d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '')
  const p = new URLSearchParams({
    action: 'TEMPLATE', text: `Registration opens: ${camp}`, dates: `${f(start)}/${f(end)}`,
    details: url ? `Register: ${url}` : '',
  })
  return `https://calendar.google.com/calendar/render?${p}`
}
