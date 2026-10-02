import { authHeaders } from '@/lib/auth'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface Contact {
  name: string
  relationship?: string | null
  phone?: string | null
  email?: string | null
}

export interface Household {
  parents: Contact[]
  home_address?: string | null
  emergency_contacts: Contact[]
  authorized_pickups: Contact[]
  insurance_provider?: string | null
  insurance_member_id?: string | null
  insurance_group_number?: string | null
  pediatrician_name?: string | null
  pediatrician_phone?: string | null
}

export interface Child {
  name: string
  date_of_birth?: string | null
  grade?: string | null
  allergies?: string | null
  medications?: string | null
  medical_conditions?: string | null
  dietary_needs?: string | null
  swim_ability?: string | null
  tshirt_size?: string | null
  notes?: string | null
}

export interface InfoKit {
  household: Household
  children: Child[]
}

export interface ShareSummary {
  id: string
  recipient: string
  children: string[]
  household_fields: string[]
  child_fields: string[]
  fields_shared: number
  fields_total: number
  expires_at: string
  revoked_at: string | null
  open_count: number
  last_opened_at: string | null
  created_at: string
  active: boolean
}

export interface SharedPackage {
  recipient: string
  expires_at: string
  household: Record<string, unknown>
  children: Array<Record<string, unknown> & { name: string }>
}

export const HOUSEHOLD_LABELS: Record<string, string> = {
  parents: 'Parents / guardians',
  home_address: 'Home address',
  emergency_contacts: 'Emergency contacts',
  authorized_pickups: 'Authorized pickups',
  insurance_provider: 'Insurance provider',
  insurance_member_id: 'Insurance member ID',
  insurance_group_number: 'Insurance group number',
  pediatrician_name: 'Pediatrician',
  pediatrician_phone: 'Pediatrician phone',
}

export const CHILD_LABELS: Record<string, string> = {
  date_of_birth: 'Date of birth',
  grade: 'Grade',
  allergies: 'Allergies',
  medications: 'Medications',
  medical_conditions: 'Medical conditions',
  dietary_needs: 'Dietary needs',
  swim_ability: 'Swim ability',
  tshirt_size: 'T-shirt size',
  notes: 'Notes for staff',
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

export const getKit = (familyId: string) => call<InfoKit>(`/families/${familyId}/kit`)
export const saveKit = (familyId: string, kit: InfoKit) =>
  call<InfoKit>(`/families/${familyId}/kit`, { method: 'PUT', body: JSON.stringify(kit) })
export const listShares = (familyId: string) => call<ShareSummary[]>(`/families/${familyId}/kit/shares`)
export const createShare = (familyId: string, body: {
  recipient: string; children: string[]; household_fields: string[]; child_fields: string[]; expires_in_days: number
}) => call<{ share: ShareSummary; url: string }>(`/families/${familyId}/kit/shares`, { method: 'POST', body: JSON.stringify(body) })
export const revokeShare = (familyId: string, shareId: string) =>
  call<ShareSummary>(`/families/${familyId}/kit/shares/${shareId}/revoke`, { method: 'POST' })

export async function openShare(token: string): Promise<SharedPackage> {
  const res = await fetch(`${API}/api/v1/shares/${token}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('This link has expired or was withdrawn by the family.')
  return res.json()
}
