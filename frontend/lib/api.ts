const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface SessionSummary {
  id: string
  name: string | null
  start_date: string
  end_date: string
  age_min: number | null
  age_max: number | null
  price: number | null
  full_season: boolean
  availability: string
  spots_total: number | null
  spots_available: number | null
  registration_opens_at: string | null
}

export interface CampSearchResult {
  id: string
  slug: string
  name: string
  city: string
  state: string
  camp_type: string
  primary_categories: string[]
  age_min: number | null
  age_max: number | null
  price_per_week: number | null
  price_min: number | null
  price_max: number | null
  transportation: boolean
  extended_care: boolean
  meals_included: boolean
  financial_aid: boolean
  aca_accredited: boolean | null
  verification_status: string
  updated_at: string | null
  description_short: string | null
  hero_image_url: string | null
  detail_url: string | null
  distance_miles: number | null
  match_score: number | null
  match_reasons: string[]
  next_session: SessionSummary | null
}

export interface SearchResponse {
  results: CampSearchResult[]
  total: number
  location: string
  radius_miles: number
  location_recognised: boolean
}

export interface TrustSummary {
  verification_status: string
  last_updated: string | null
  fields_verified: string[]
  fields_unverified: string[]
  fields_missing: string[]
  accreditation: { status: string; source: string | null }
}

export interface CampDetail extends Omit<CampSearchResult, 'distance_miles' | 'match_score' | 'match_reasons' | 'next_session'> {
  operator_name: string | null
  website_url: string | null
  registration_url: string | null
  email: string | null
  phone: string | null
  street_address: string | null
  zip: string
  lat: number
  lng: number
  region: string | null
  description_full: string | null
  activities: string[]
  indoor_outdoor: string | null
  gender_policy: string | null
  refund_policy_summary: string | null
  special_needs_notes: string | null
  swim_waterfront_notes: string | null
  aca_source_url: string | null
  sessions: SessionSummary[]
  trust_summary: TrustSummary | null
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = 'Request failed'
    try { detail = (await res.json()).detail ?? detail } catch { /* keep default */ }
    throw new Error(typeof detail === 'string' ? detail : 'Request failed')
  }
  return res.json()
}

export function searchCamps(params: {
  location: string
  age?: number
  camp_type?: string
  categories?: string[]
  max_price_per_week?: number
  radius_miles?: number
  limit?: number
}): Promise<SearchResponse> {
  return post('/api/v1/search', params)
}

export async function getCamp(idOrSlug: string): Promise<CampDetail> {
  const res = await fetch(`${API}/api/v1/camps/${encodeURIComponent(idOrSlug)}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('Camp not found')
  return res.json()
}

export function createAlert(data: { email: string; camp_id: string }): Promise<{ id: string; status: string }> {
  return post('/api/v1/alerts', data)
}

export function startClaim(data: { camp_id: string; email: string; contact_name?: string; role?: string }): Promise<{ message: string; camp_name: string }> {
  return post('/api/v1/claims', data)
}

export async function verifyClaim(token: string): Promise<{ message: string; camp_name: string }> {
  const res = await fetch(`${API}/api/v1/claims/verify?token=${encodeURIComponent(token)}`)
  if (!res.ok) throw new Error('This link has expired or was already used')
  return res.json()
}

export function submitCamp(data: {
  name: string
  city: string
  state: string
  zip?: string
  camp_type?: string
  email: string
  contact_name?: string
  phone?: string
  website_url?: string
  description?: string
  age_min?: number
  age_max?: number
  primary_categories?: string[]
  notes?: string
}): Promise<{ id: string; name: string; status: string }> {
  return post('/api/v1/submissions', data)
}
