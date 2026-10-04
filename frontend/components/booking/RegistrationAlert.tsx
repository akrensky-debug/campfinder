'use client'

import { useEffect, useState } from 'react'
import { getCampRegistration, signUpForAlerts, type CampRegistration } from '@/lib/alerts'
import { fmtWhen } from '@/lib/booking'

/** "Email me when registration opens", on a camp's page. No account needed. */
export default function RegistrationAlert({ campId, campName }: { campId: string; campName: string }) {
  const [reg, setReg] = useState<CampRegistration | null>(null)
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    getCampRegistration(campId).then(setReg).catch(() => setReg(null))
  }, [campId])

  const now = Date.now()
  const opens = reg?.verified && reg.opens_at ? new Date(reg.opens_at).getTime() : null
  const closes = reg?.closes_at ? new Date(reg.closes_at).getTime() : null
  const isOpen = opens !== null && opens <= now && (closes === null || closes > now)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await signUpForAlerts(campId, email)
      setSent(true)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="bg-white rounded-2xl border border-gray-200 p-6 mb-4">
      <h2 className="font-bold text-gray-900 mb-1">Registration</h2>
      <p className="text-sm text-gray-600 mb-3">
        {isOpen
          ? <>Registration is open now.{closes ? ` It closes ${fmtWhen(reg!.closes_at!)}.` : ''}</>
          : opens && opens > now
            ? <>Registration opens <strong>{fmtWhen(reg!.opens_at!)}</strong>. Checked against the camp&rsquo;s own site.</>
            : <>We don&rsquo;t have {campName}&rsquo;s next registration date yet.</>}
      </p>

      {!isOpen && (sent ? (
        <p className="text-sm bg-green-50 border border-green-200 text-green-800 rounded-xl px-4 py-3">
          Check your email for a link to confirm. Nothing else comes until you click it.
        </p>
      ) : (
        <form onSubmit={submit} className="space-y-2">
          <label htmlFor="alert-email" className="text-sm font-medium text-gray-700">
            Email me when registration opens
          </label>
          <div className="flex flex-col sm:flex-row gap-2">
            <input id="alert-email" type="email" required value={email} onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com" autoComplete="email"
              className="flex-1 border border-gray-300 rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-brand-500" />
            <button type="submit" disabled={busy}
              className="bg-brand-600 hover:bg-brand-700 text-white font-semibold rounded-xl px-4 py-2 text-sm disabled:opacity-50">
              {busy ? 'Sending…' : 'Tell me'}
            </button>
          </div>
          <p className="text-xs text-gray-500">
            No account. We email when the date is announced, the day before, and when it opens. One click stops it.
          </p>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </form>
      ))}

      {reg && reg.alerts_waiting > 1 && (
        <p className="text-xs text-gray-400 mt-3">
          {reg.alerts_waiting} families are waiting to hear when registration opens.
        </p>
      )}
    </section>
  )
}
