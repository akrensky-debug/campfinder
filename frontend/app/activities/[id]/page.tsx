'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import TrustBadge from '@/components/TrustBadge'
import {
  getActivity, getActivitySources, KIND_LABEL, money, PRICE_LABEL,
  type ActivityProgram, type ActivitySession, type FieldSource, type PriceOption,
} from '@/lib/activities'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

function fmtDay(d: string) {
  return new Date(d + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function PriceList({ prices }: { prices: PriceOption[] }) {
  if (!prices.length) return null
  return (
    <ul className="text-sm text-gray-700 space-y-0.5">
      {prices.map((p, i) => (
        <li key={i}>
          <span className="font-semibold">{money(p.amount)}</span>{' '}
          {PRICE_LABEL[p.type] ?? p.type}
          {p.audience ? ` · ${p.audience}` : ''}
          {p.covers ? ` · ${p.covers}` : ''}
          {p.notes ? <span className="text-gray-500"> ({p.notes})</span> : null}
        </li>
      ))}
    </ul>
  )
}

function SessionRow({ s }: { s: ActivitySession }) {
  const enrollment = s.enrollment
  return (
    <div className="border-t border-gray-100 first:border-t-0 py-4 grid md:grid-cols-[1fr_auto] gap-3">
      <div className="min-w-0">
        <p className="font-semibold text-gray-900">{s.schedule?.summary || s.name || 'Day and time not published'}</p>
        <p className="text-sm text-gray-500">
          {[s.skill_level, s.term, s.ages && (s.ages.min != null || s.ages.max != null) ? `Ages ${s.ages.min ?? '?'}–${s.ages.max ?? '?'}` : null]
            .filter(Boolean).join(' · ')}
        </p>
        {s.start_date && s.end_date && (
          <p className="text-sm text-gray-600 mt-1">
            {fmtDay(s.start_date)} – {fmtDay(s.end_date)}
            {s.schedule?.meeting_count ? ` · ${s.schedule.meeting_count} classes` : ''}
          </p>
        )}
        {s.schedule?.exdates?.length ? (
          <p className="text-xs text-gray-500">No class: {s.schedule.exdates.map(fmtDay).join(', ')}</p>
        ) : null}
        {s.location && <p className="text-xs text-gray-500">At {[s.location.address, s.location.city].filter(Boolean).join(', ')}</p>}
        {enrollment && (enrollment.opens || enrollment.closes) && (
          <p className="text-xs text-gray-600 mt-1">
            Registration {enrollment.opens ? `opens ${fmtDay(enrollment.opens)}` : ''}
            {enrollment.opens && enrollment.closes ? ', ' : ''}
            {enrollment.closes ? `closes ${fmtDay(enrollment.closes)}` : ''}
          </p>
        )}
      </div>
      <div className="md:text-right space-y-2">
        <PriceList prices={s.prices} />
        {s.schedule && s.start_date && (
          <a href={`${API}${s.calendar_url}`} className="inline-block text-sm font-medium text-brand-700 hover:underline">
            Add to my calendar
          </a>
        )}
      </div>
    </div>
  )
}

export default function ActivityPage() {
  const { id } = useParams<{ id: string }>()
  const [a, setA] = useState<ActivityProgram | null>(null)
  const [sources, setSources] = useState<FieldSource[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!id) return
    getActivity(id).then(setA).catch(() => setA(null)).finally(() => setLoading(false))
    getActivitySources(id).then(setSources)
  }, [id])

  if (loading) return (
    <div className="max-w-4xl mx-auto px-4 py-16 space-y-4">
      {[1, 2, 3].map(i => <div key={i} className="bg-gray-100 rounded-2xl h-24 animate-pulse" />)}
    </div>
  )
  if (!a) return <div className="max-w-4xl mx-auto px-4 py-16 text-center text-gray-500">Activity not found.</div>

  const sessions = a.sessions ?? []
  const ask = `Does ${a.name}${a.provider.name ? ` at ${a.provider.name}` : ''} fit our week? Check it against our calendar.`
  const urls = Array.from(new Map(sources.filter(s => s.source_url).map(s => [s.source_url!, s])).values())

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-4">
      <nav className="text-sm text-gray-400">
        <a href="/" className="hover:text-brand-600">← Back to CampFinder</a>
      </nav>

      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <div className="flex flex-col md:flex-row md:items-start gap-4">
          <div className="flex-1">
            <p className="text-sm text-gray-500 mb-1">
              {KIND_LABEL[a.kind] ?? a.kind} · {a.location.city}, {a.location.state}
            </p>
            <h1 className="text-2xl md:text-3xl font-extrabold text-gray-900 mb-1">{a.name}</h1>
            {a.provider.name && <p className="text-gray-600 mb-3">{a.provider.name}</p>}
            <TrustBadge status={a.verification.status} />
          </div>
          <div className="flex flex-col gap-2 md:min-w-[220px]">
            <a href={`/?q=${encodeURIComponent(ask)}`} className="bg-brand-600 hover:bg-brand-700 text-white font-bold px-5 py-3 rounded-xl text-center transition-colors">
              Check it fits our week →
            </a>
            {(a.registration_url || a.provider.website) && (
              <a href={a.registration_url || a.provider.website!} target="_blank" rel="noopener noreferrer"
                 className="border border-gray-200 text-gray-700 font-medium px-5 py-2.5 rounded-xl text-center hover:border-brand-400 hover:text-brand-700 transition-colors text-sm">
                {a.registration_url ? 'Register with the provider ↗' : 'Provider website ↗'}
              </a>
            )}
          </div>
        </div>
        {a.description && <p className="text-gray-700 mt-4">{a.description}</p>}
        <div className="flex flex-wrap gap-2 mt-4">
          {a.ages.min != null && a.ages.max != null && <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">Ages {a.ages.min}–{a.ages.max}</span>}
          {a.skill_levels.map(l => <span key={l} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">{l}</span>)}
          {a.trial_available && <span className="text-xs bg-purple-50 text-purple-700 px-2 py-0.5 rounded-full">Trial class{a.trial_notes ? `: ${a.trial_notes}` : ''}</span>}
          {a.membership_required && <span className="text-xs bg-amber-50 text-amber-800 px-2 py-0.5 rounded-full">Membership required</span>}
        </div>
      </div>

      {a.verification.status === 'unverified' && (
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4 text-sm text-amber-900">
          We gathered these details from the provider's own website and haven't confirmed them with the
          provider yet. Schedules and prices change by term, so check with them before you register.
          {a.verification.fields_missing.length > 0 && (
            <> Not published: {a.verification.fields_missing.map(f => f.replace('schedule.', '').replace(/_/g, ' ')).join(', ')}.</>
          )}
        </div>
      )}

      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <h2 className="font-bold text-gray-900 mb-1">Times and prices</h2>
        {a.price.options.length > 0 && <div className="mb-2"><PriceList prices={a.price.options} /></div>}
        {sessions.length ? sessions.map(s => <SessionRow key={s.id} s={s} />) : (
          <p className="text-sm text-gray-500">No schedule published that we could read. Check the provider's site for days and times.</p>
        )}
      </div>

      <div className="bg-white rounded-2xl border border-gray-200 p-6 text-sm">
        <h2 className="font-bold text-gray-900 mb-2">Contact</h2>
        <div className="text-gray-700 space-y-0.5">
          {a.location.address && <p>{a.location.address}, {a.location.city}, {a.location.state}</p>}
          {a.provider.phone && <p>{a.provider.phone}</p>}
          {a.provider.email && <p>{a.provider.email}</p>}
          {a.provider.website && <p><a className="text-brand-700 hover:underline" href={a.provider.website} target="_blank" rel="noopener noreferrer">{a.provider.website}</a></p>}
        </div>
      </div>

      {urls.length > 0 && (
        <div className="bg-gray-50 rounded-2xl p-6 text-sm">
          <h2 className="font-bold text-gray-900 mb-2">Where this came from</h2>
          <ul className="space-y-1 text-gray-600">
            {urls.slice(0, 5).map(s => (
              <li key={s.source_url} className="break-all">
                <a href={s.source_url!} target="_blank" rel="noopener noreferrer" className="text-brand-700 hover:underline">{s.source_url}</a>
                {s.retrieved_on && <span className="text-gray-400"> · read {fmtDay(s.retrieved_on)}</span>}
                <span className="text-gray-400"> · {sources.filter(x => x.source_url === s.source_url).length} facts</span>
              </li>
            ))}
          </ul>
          {urls.length > 5 && (
            <details className="mt-2 text-gray-600">
              <summary className="cursor-pointer text-brand-700">All {urls.length} source pages</summary>
              <ul className="space-y-1 mt-2">
                {urls.slice(5).map(s => (
                  <li key={s.source_url} className="break-all">
                    <a href={s.source_url!} target="_blank" rel="noopener noreferrer" className="text-brand-700 hover:underline">{s.source_url}</a>
                    {s.retrieved_on && <span className="text-gray-400"> · read {fmtDay(s.retrieved_on)}</span>}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  )
}
