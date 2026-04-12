const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface CampSearchResult {
  id: string
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
  description_short: string | null
  hero_image_url: string | null
  distance_miles: number | null
  match_score: number | null
  match_reasons: string[]
  detail_url: string | null
}

export interface SearchResponse {
  results: CampSearchResult[]
  total: number
  location: string
  radius_miles: number
}

export interface SessionSummary {
  id: string
  name: string | null
  start_date: string
  end_date: string
  price: number | null
  availability: string
  full_season: boolean
}

export interface TrustSummary {
  verification_status: string
  last_updated: string | null
  fields_verified: string[]
  fields_unverified: string[]
  fields_missing: string[]
  accreditation: { status: string; source: string | null }
}

export interface CampDetail extends CampSearchResult {
  operator_name: string | null
  website_url: string | null
  registration_url: string | null
  email: string | null
  phone: string | null
  street_address: string | null
  zip: string
  region: string | null
  description_full: string | null
  activities: string[]
  indoor_outdoor: string | null
  gender_policy: string | null
  refund_policy_summary: string | null
  special_needs_notes: string | null
  swim_waterfront_notes: string | null
  aca_source_url: string | null
  last_updated_date: string | null
  sessions: SessionSummary[]
  trust_summary: TrustSummary
}

export async function searchCamps(params: {
  location: string
  age?: number
  camp_type?: string
  categories?: string[]
  max_price_per_week?: number
  limit?: number
}): Promise<SearchResponse> {
  const res = await fetch(`${API}/api/v1/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...params, limit: params.limit ?? 20 }),
    cache: 'no-store',
  })
  if (!res.ok) throw new Error('Search failed')
  return res.json()
}

export async function getCamp(id: string): Promise<CampDetail> {
  const res = await fetch(`${API}/api/v1/camps/${id}`, { cache: 'no-store' })
  if (!res.ok) throw new Error('Camp not found')
  return res.json()
}

export async function captureLead(data: {
  parent_email: string
  first_name?: string
  parent_zip?: string
  child_age_band?: string
  weeks_needed?: number
  interests?: string[]
  target_camp_id?: string
  search_context?: Record<string, unknown>
  message?: string
  consent_flag?: boolean
  source?: string
  matched_camp_ids?: string[]
}): Promise<{ id: string }> {
  const res = await fetch(`${API}/api/v1/leads`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('Failed to save')
  return res.json()
}

export async function submitCamp(data: {
  name: string
  city: string
  state: string
  camp_type?: string
  contact_email: string
  contact_name?: string
  phone?: string
  website_url?: string
  description_short?: string
  age_min?: number
  age_max?: number
  price_per_week?: number
  primary_categories?: string[]
}): Promise<{ id: string; name: string }> {
  const res = await fetch(`${API}/api/v1/submissions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('Failed to submit')
  return res.json()
}
