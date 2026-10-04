'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { confirmAlert, getAlert, stopAlert, type AlertView } from '@/lib/alerts'
import { fmtWhen } from '@/lib/booking'

/** The page behind every registration alert email: confirm, see the date, or stop. Opening it changes nothing. */
export default function AlertPage() {
  const { token } = useParams<{ token: string }>()
  const [view, setView] = useState<AlertView | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getAlert(token).then(setView).catch(e => setError((e as Error).message))
  }, [token])

  async function act(fn: (t: string) => Promise<AlertView>) {
    setBusy(true)
    setError('')
    try {
      setView(await fn(token))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (!view) {
    return (
      <div className="max-w-xl mx-auto px-4 py-12 space-y-2">
        <h1 className="text-2xl font-bold text-gray-900">{error ? 'This link no longer works' : 'Loading…'}</h1>
        {error && <p className="text-gray-600">{error}</p>}
      </div>
    )
  }

  const what = view.session_name ? `${view.camp_name} (${view.session_name})` : view.camp_name
  const campPage = `/camps/${view.camp_id}`
  const opensFuture = view.opens_at && new Date(view.opens_at).getTime() > Date.now()

  return (
    <div className="max-w-xl mx-auto px-4 py-12 space-y-6">
      <header>
        <p className="text-sm text-gray-500">Registration alerts · {view.email_hint}</p>
        <h1 className="text-2xl font-bold text-gray-900">{what}</h1>
      </header>

      {view.status === 'pending' && (
        <div className="space-y-3">
          <p className="text-gray-600">
            Confirm and we&rsquo;ll email you when the registration date is announced, the day before, and when it opens.
          </p>
          <button onClick={() => act(confirmAlert)} disabled={busy}
            className="w-full bg-brand-600 hover:bg-brand-700 text-white font-semibold rounded-xl py-3 disabled:opacity-50">
            {busy ? 'Saving…' : 'Confirm alerts'}
          </button>
        </div>
      )}

      {view.status === 'on' && (
        <div className="space-y-3">
          <p className="text-sm bg-green-50 border border-green-200 text-green-800 rounded-xl px-4 py-3">
            Alerts are on. {opensFuture
              ? <>Registration opens <strong>{fmtWhen(view.opens_at!)}</strong>.</>
              : view.opens_at ? <>Registration has opened.</> : <>We&rsquo;ll email you as soon as the camp announces the date.</>}
          </p>
          <div className="flex flex-wrap gap-3 text-sm">
            {view.registration_url && (
              <a href={view.registration_url} target="_blank" rel="noopener noreferrer"
                className="text-brand-600 underline">Camp&rsquo;s registration page ↗</a>
            )}
            <a href={`/register/${view.camp_id}`} className="text-brand-600 underline">Get your forms ready</a>
            <a href={campPage} className="text-brand-600 underline">Camp page</a>
          </div>
          <div className="pt-4 border-t border-gray-100">
            <button onClick={() => act(stopAlert)} disabled={busy} className="text-sm text-gray-500 hover:text-red-600">
              Stop alerts for {view.camp_name}
            </button>
          </div>
        </div>
      )}

      {view.status === 'stopped' && (
        <p className="text-gray-600">
          Alerts for {view.camp_name} are stopped. We won&rsquo;t email this address about it again. Changed your
          mind? <a href={campPage} className="text-brand-600 underline">Sign up again on the camp&rsquo;s page</a>.
        </p>
      )}

      {view.status === 'expired' && (
        <p className="text-gray-600">
          This confirm link has expired, so no alerts were set up.{' '}
          <a href={campPage} className="text-brand-600 underline">Sign up again on the camp&rsquo;s page</a>.
        </p>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  )
}
