/**
 * Lightweight client-side analytics.
 * Fires events to /api/v1/events and persists a session_id in sessionStorage.
 */

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

function getSessionId(): string {
  if (typeof window === 'undefined') return ''
  let sid = sessionStorage.getItem('cf_sid')
  if (!sid) {
    sid = Math.random().toString(36).slice(2) + Date.now().toString(36)
    sessionStorage.setItem('cf_sid', sid)
  }
  return sid
}

// Which assistant (ChatGPT, Claude) first sent this browser, kept for 30 days so a
// family saved after an emailed sign-in link still counts toward that door.
const SOURCE_KEY = 'cf_src'
const SOURCE_TTL_MS = 30 * 24 * 3600 * 1000

function arrivalSource(): string | undefined {
  try {
    const saved = JSON.parse(localStorage.getItem(SOURCE_KEY) || 'null')
    if (saved && Date.now() - saved.at < SOURCE_TTL_MS) return saved.source
  } catch {}
  return undefined
}

/** Record an arrival from an assistant link (utm_source=chatgpt|claude|...). */
export function captureAssistantArrival(params: URLSearchParams, prefilled = false): void {
  const source = params.get('utm_source')
  if (!source) return
  try {
    if (!arrivalSource()) localStorage.setItem(SOURCE_KEY, JSON.stringify({ source, at: Date.now() }))
  } catch {}
  track('assistant_handoff', { source, campaign: params.get('utm_campaign'), prefilled })
}

export function track(event: string, properties?: Record<string, unknown>): void {
  if (typeof window === 'undefined') return
  const source = arrivalSource()
  fetch(`${API}/api/v1/events`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      event,
      session_id: getSessionId(),
      page: window.location.pathname,
      properties: source ? { ...properties, arrival_source: source } : properties,
    }),
    keepalive: true,
  }).catch(() => {}) // fire-and-forget, never throw
}

// Typed event helpers -- keeps call sites clean
export const Events = {
  pageView:               (page: string) => track('page_view', { page }),
  searchSubmitted:        (p: Record<string, unknown>) => track('search_submitted', p),
  resultsViewed:          (p: Record<string, unknown>) => track('results_viewed', p),
  emailGateViewed:        (p: Record<string, unknown>) => track('email_gate_viewed', p),
  emailSubmitted:         (p: Record<string, unknown>) => track('email_submitted', p),
  campDetailViewed:       (id: string) => track('camp_detail_viewed', { camp_id: id }),
  requestInfoClicked:     (id: string) => track('request_info_clicked', { camp_id: id }),
  outboundSiteClicked:    (id: string, url: string) => track('outbound_site_clicked', { camp_id: id, url }),
  plannerUsed:            () => track('planner_used'),
  shortlistSaved:         (id: string) => track('shortlist_saved', { camp_id: id }),
  campSubmissionStarted:  () => track('camp_submission_started'),
  claimFlowStarted:       (id: string) => track('claim_flow_started', { camp_id: id }),
  stripeCheckoutStarted:  (id: string) => track('stripe_checkout_started', { camp_id: id }),
  stripeCheckoutCompleted:(id: string) => track('stripe_checkout_completed', { camp_id: id }),
  familySaved:            () => track('family_saved'),
  calendarSubscribed:     (how: string) => track('calendar_subscribed', { how }),
}
