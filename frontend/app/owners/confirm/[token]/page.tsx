'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface Snapshot {
  camp: Record<string, string | number | null>
  sessions: Array<{ name: string | null; start_date: string; end_date: string; price: number | null; availability: string | null }>
}

interface View {
  camp_name: string
  city: string | null
  snapshot: Snapshot
  changed_since_sent: boolean
}

const LABELS: Record<string, string> = {
  name: 'Name', city: 'Town', state: 'State', camp_type: 'Type', age_min: 'Youngest age', age_max: 'Oldest age',
  grade_min: 'Lowest grade', grade_max: 'Highest grade', price_per_week: 'Price per week',
  website_url: 'Website', registration_url: 'Registration page',
}

function fmt(field: string, value: string | number): string {
  if (field === 'price_per_week') return `$${value}`
  if (field === 'camp_type') return ({ day: 'Day camp', sleepaway: 'Sleepaway camp', specialty: 'Specialty program' } as Record<string, string>)[String(value)] ?? String(value)
  return String(value)
}

function fmtDate(d: string) {
  return new Date(d + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

/** The camp owner's page behind the listing email. Opening it changes nothing; the buttons do. */
export default function ConfirmListingPage() {
  const { token } = useParams<{ token: string }>()
  const [view, setView] = useState<View | null>(null)
  const [error, setError] = useState('')
  const [done, setDone] = useState<'confirmed' | 'removed' | 'changed' | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirmRemove, setConfirmRemove] = useState(false)

  useEffect(() => {
    fetch(`${API}/api/v1/owners/confirm/${token}`, { cache: 'no-store' })
      .then(async r => (r.ok ? setView(await r.json()) : setError((await r.json().catch(() => ({}))).detail || 'This link has expired or was already used.')))
      .catch(() => setError('We could not load this page. Please try again.'))
  }, [token])

  async function answer(a: 'confirm' | 'remove') {
    setBusy(true)
    setError('')
    try {
      const r = await fetch(`${API}/api/v1/owners/confirm/${token}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ answer: a }),
      })
      const body = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(body.detail || 'Something went wrong.')
      setDone(body.outcome)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-12 space-y-6">
      {done === 'confirmed' && (
        <Message title="Thank you. Your listing is confirmed.">
          Parents now see &ldquo;confirmed by the camp&rdquo; with today&rsquo;s date. If anything changes, reply to any
          email from us and a person will update it.
        </Message>
      )}
      {done === 'removed' && (
        <Message title={`${view?.camp_name ?? 'Your camp'} is off CampFinder.`}>
          Parents won&rsquo;t see it in search or on our pages. If that was a mistake, reply to the email and a person
          will put it back.
        </Message>
      )}
      {done === 'changed' && (
        <Message title="The listing changed after we emailed you.">
          So we can&rsquo;t mark it confirmed from this link. We&rsquo;ll send you the updated version to check.
        </Message>
      )}

      {!done && !view && (
        <Message title={error ? 'This link no longer works' : 'Loading…'}>{error}</Message>
      )}

      {!done && view && (
        <>
          <header>
            <p className="text-sm text-gray-500">Your listing on CampFinder</p>
            <h1 className="text-2xl font-bold text-gray-900">{view.camp_name}</h1>
            <p className="text-gray-600 mt-1">
              This is what parents see. Is it right? No login, no fee to be listed, nothing to install.
            </p>
          </header>

          {view.changed_since_sent && (
            <p className="text-sm bg-amber-50 border border-amber-200 text-amber-800 rounded-xl px-4 py-3">
              We changed this listing after emailing you, so this link can&rsquo;t confirm it. Reply to the email and
              we&rsquo;ll send the current version.
            </p>
          )}

          <section className="border border-gray-200 rounded-2xl p-5">
            <dl className="divide-y divide-gray-100">
              {Object.entries(view.snapshot.camp).filter(([, v]) => v !== null && v !== '').map(([k, v]) => (
                <div key={k} className="grid grid-cols-3 gap-2 py-2 text-sm">
                  <dt className="text-gray-500">{LABELS[k] ?? k}</dt>
                  <dd className="col-span-2 text-gray-900 break-words">{fmt(k, v as string | number)}</dd>
                </div>
              ))}
            </dl>
            {view.snapshot.sessions.length > 0 && (
              <div className="mt-4">
                <p className="text-sm font-medium text-gray-700 mb-2">Sessions</p>
                <ul className="text-sm text-gray-700 space-y-1">
                  {view.snapshot.sessions.map((s, i) => (
                    <li key={i}>
                      {s.name ? `${s.name} · ` : ''}{fmtDate(s.start_date)} – {fmtDate(s.end_date)}
                      {s.price !== null ? ` · $${s.price}` : ''}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          {!view.changed_since_sent && (
            <div className="space-y-3">
              <button onClick={() => answer('confirm')} disabled={busy}
                className="w-full bg-brand-600 hover:bg-brand-700 text-white font-semibold rounded-xl py-3 disabled:opacity-50">
                {busy ? 'Saving…' : 'Looks right'}
              </button>
              <p className="text-sm text-gray-600 text-center">
                Something wrong? Reply to the email with the fix and a person will change it.
              </p>
            </div>
          )}

          <div className="pt-4 border-t border-gray-100 text-sm">
            {confirmRemove ? (
              <div className="flex flex-wrap items-center gap-3">
                <span className="text-gray-700">Take {view.camp_name} off CampFinder?</span>
                <button onClick={() => answer('remove')} disabled={busy} className="text-red-600 font-medium">Yes, take it down</button>
                <button onClick={() => setConfirmRemove(false)} className="text-gray-500">Keep it</button>
              </div>
            ) : (
              <button onClick={() => setConfirmRemove(true)} className="text-gray-500 hover:text-red-600">
                I&rsquo;d rather not be listed
              </button>
            )}
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </>
      )}
    </div>
  )
}

function Message({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
      {children && <p className="text-gray-600">{children}</p>}
    </div>
  )
}
