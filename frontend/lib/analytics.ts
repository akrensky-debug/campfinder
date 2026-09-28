/**
 * Product analytics. Named events only; the API rejects anything that looks
 * like an email, phone number or name, and so should every call site here.
 */

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

function getSessionId(): string {
  if (typeof window === 'undefined') return ''
  try {
    let sid = sessionStorage.getItem('cf_sid')
    if (!sid) {
      sid = Math.random().toString(36).slice(2) + Date.now().toString(36)
      sessionStorage.setItem('cf_sid', sid)
    }
    return sid
  } catch {
    return ''
  }
}

type Props = Record<string, string | number | boolean | null | undefined>

export function track(event: string, properties?: Props): void {
  if (typeof window === 'undefined') return
  fetch(`${API}/api/v1/events`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ event, session_id: getSessionId(), page: window.location.pathname, properties }),
    keepalive: true,
  }).catch(() => {})
}

export const Events = {
  pageView:              (page: string) => track('page_view', { page }),
  searchSubmitted:       (p: Props) => track('search_submitted', p),
  resultsViewed:         (p: Props) => track('results_viewed', p),
  campDetailViewed:      (id: string) => track('camp_detail_viewed', { camp_id: id }),
  outboundSiteClicked:   (id: string, url: string) => track('outbound_site_clicked', { camp_id: id, url }),
  plannerUsed:           () => track('planner_used'),
  compareUsed:           () => track('compare_used'),
  alertCreated:          (id: string) => track('alert_created', { camp_id: id }),
  campSubmissionStarted: () => track('camp_submission_started'),
  claimFlowStarted:      (id: string) => track('claim_flow_started', { camp_id: id }),
}
