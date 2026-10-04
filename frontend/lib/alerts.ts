// Public "tell me when registration opens" alerts. No account: an email and a confirm link.

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface CampRegistration {
  camp_id: string
  registration_url: string | null
  opens_at: string | null
  closes_at: string | null
  verified: boolean
  source_url: string | null
  alerts_waiting: number
}

export type AlertStatus = 'pending' | 'on' | 'stopped' | 'expired'

export interface AlertView {
  status: AlertStatus
  camp_id: string
  camp_name: string
  session_name: string | null
  email_hint: string
  opens_at: string | null
  closes_at: string | null
  registration_url: string | null
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API}/api/v1${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init.headers || {}) },
    cache: 'no-store',
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = Array.isArray(body.detail) ? "That doesn't look like an email address." : body.detail
    throw new Error(typeof detail === 'string' ? detail : 'Something went wrong')
  }
  return body as T
}

export const getCampRegistration = (campId: string) => call<CampRegistration>(`/camps/${campId}/registration`)
export const signUpForAlerts = (campId: string, email: string, sessionId?: string | null) =>
  call<{ status: 'check_email' }>(`/camps/${campId}/registration/alerts`, {
    method: 'POST', body: JSON.stringify({ email, session_id: sessionId || null }),
  })
export const getAlert = (token: string) => call<AlertView>(`/registration-alerts/${encodeURIComponent(token)}`)
export const confirmAlert = (token: string) =>
  call<AlertView>(`/registration-alerts/${encodeURIComponent(token)}/confirm`, { method: 'POST' })
export const stopAlert = (token: string) =>
  call<AlertView>(`/registration-alerts/${encodeURIComponent(token)}/stop`, { method: 'POST' })
