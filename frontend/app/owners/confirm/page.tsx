'use client'

// The page an owner reaches from "here is your listing". Opening it changes
// nothing; only the buttons do, so a mail scanner following the link is harmless.

import { useEffect, useState, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import { answerListingConfirmation, getListingConfirmation, type ListingConfirmation } from '@/lib/api'

function ages(c: ListingConfirmation['snapshot']['camp']): string {
  if (c.age_min !== null || c.age_max !== null) return `${c.age_min ?? '?'} to ${c.age_max ?? '?'}`
  if (c.grade_min !== null || c.grade_max !== null) return `Grades ${c.grade_min ?? '?'} to ${c.grade_max ?? '?'}`
  return 'Not listed'
}

function Confirm() {
  const token = useSearchParams().get('token') ?? ''
  const [data, setData] = useState<ListingConfirmation | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [outcome, setOutcome] = useState<'confirmed' | 'removed' | 'changed' | null>(null)
  const [askRemove, setAskRemove] = useState(false)

  useEffect(() => {
    if (!token) { setError('This link is missing its code. Reply to the email and a person will help.'); return }
    getListingConfirmation(token).then(setData).catch((e: Error) => setError(e.message))
  }, [token])

  async function answer(a: 'confirm' | 'remove') {
    setBusy(true)
    setError('')
    try {
      setOutcome((await answerListingConfirmation(token, a)).outcome)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Something went wrong. Reply to the email instead.')
    } finally {
      setBusy(false)
    }
  }

  if (outcome === 'confirmed') {
    return <Done title="Thank you. Your listing is confirmed.">
      It now shows "confirmed by the camp" with today's date. When something changes, reply to any
      email from us, for example "Week 3 is full", and we'll update it.
    </Done>
  }
  if (outcome === 'removed') {
    return <Done title="Your camp is off the site.">
      Parents can no longer find it through us. If that was a mistake, reply to the email and a person
      will put it back.
    </Done>
  }
  if (outcome === 'changed') {
    return <Done title="The listing changed after we emailed you.">
      So we haven't marked it confirmed. We'll send you the current version to check.
    </Done>
  }
  if (error) return <Done title="We couldn't open this link.">{error}</Done>
  if (!data) return <p className="text-sm text-gray-500">Loading your listing...</p>

  const c = data.snapshot.camp
  const rows: [string, string][] = [
    ['Name', c.name],
    ['Town', `${c.city}, ${c.state}`],
    ['Ages', ages(c)],
    ['Price per week', c.price_per_week ? `$${c.price_per_week}` : 'Not listed'],
    ['Website', c.website_url ?? 'Not listed'],
  ]

  return (
    <>
      <h1 className="text-3xl font-extrabold text-gray-900 mb-2">Is this right?</h1>
      <p className="text-gray-500 text-sm mb-6">
        This is what parents see for {data.camp_name}. If anything is wrong, reply to the email with
        the fix and we'll change it the same day.
      </p>

      {data.changed_since_sent && (
        <p className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 text-sm text-amber-800 mb-6">
          The listing has changed since we emailed you, so this version can no longer be confirmed. We'll
          send you the current one.
        </p>
      )}

      <dl className="bg-white border border-gray-200 rounded-xl divide-y divide-gray-100 mb-6">
        {rows.map(([k, v]) => (
          <div key={k} className="flex px-4 py-3 text-sm">
            <dt className="w-36 text-gray-500">{k}</dt>
            <dd className="flex-1 text-gray-900">{v}</dd>
          </div>
        ))}
      </dl>

      <h2 className="font-semibold text-gray-900 mb-2">Sessions</h2>
      {data.snapshot.sessions.length === 0
        ? <p className="text-sm text-gray-500 mb-6">None listed yet. Reply with your dates and we'll add them.</p>
        : (
          <ul className="text-sm text-gray-700 space-y-1 mb-6">
            {data.snapshot.sessions.map((s, i) => (
              <li key={i}>
                {s.name ?? 'Session'}: {s.start_date} to {s.end_date}
                {s.price ? `, $${s.price}` : ''}
                {s.registration_opens_at ? `, registration opens ${s.registration_opens_at.slice(0, 10)}` : ''}
              </li>
            ))}
          </ul>
        )}

      {!data.changed_since_sent && (
        <button
          onClick={() => answer('confirm')}
          disabled={busy}
          className="w-full bg-brand-600 hover:bg-brand-700 text-white font-bold py-3.5 rounded-xl transition-colors disabled:opacity-60 mb-3"
        >
          It looks right
        </button>
      )}

      {!askRemove
        ? (
          <button onClick={() => setAskRemove(true)} disabled={busy} className="w-full text-sm text-gray-500 py-2 hover:text-gray-700">
            Take my camp off the site
          </button>
        )
        : (
          <div className="border border-gray-200 rounded-xl p-4 text-sm">
            <p className="text-gray-700 mb-3">Remove {data.camp_name}? Parents won't find it through us any more.</p>
            <button onClick={() => answer('remove')} disabled={busy} className="bg-gray-900 text-white font-semibold px-4 py-2 rounded-lg mr-2 disabled:opacity-60">
              Yes, remove it
            </button>
            <button onClick={() => setAskRemove(false)} className="text-gray-500 px-4 py-2">Keep it</button>
          </div>
        )}
    </>
  )
}

function Done({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <>
      <h1 className="text-2xl font-extrabold text-gray-900 mb-3">{title}</h1>
      <p className="text-gray-600 text-sm">{children}</p>
    </>
  )
}

export default function OwnerConfirmPage() {
  return (
    <div className="max-w-xl mx-auto px-4 py-12">
      <Suspense fallback={<p className="text-sm text-gray-500">Loading...</p>}>
        <Confirm />
      </Suspense>
    </div>
  )
}
