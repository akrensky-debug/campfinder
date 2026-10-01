'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { CHILD_LABELS, HOUSEHOLD_LABELS, openShare, type Contact, type SharedPackage } from '@/lib/kit'

function Value({ value }: { value: unknown }) {
  if (Array.isArray(value)) {
    return (
      <ul className="space-y-0.5">
        {(value as Contact[]).map((c, i) => (
          <li key={i}>
            {c.name}{c.relationship ? ` (${c.relationship})` : ''}{c.phone ? ` · ${c.phone}` : ''}{c.email ? ` · ${c.email}` : ''}
          </li>
        ))}
      </ul>
    )
  }
  return <span className="whitespace-pre-wrap">{String(value)}</span>
}

function Rows({ entries, labels }: { entries: Array<[string, unknown]>; labels: Record<string, string> }) {
  return (
    <dl className="divide-y divide-gray-100">
      {entries.map(([k, v]) => (
        <div key={k} className="grid sm:grid-cols-3 gap-1 py-2 text-sm">
          <dt className="text-gray-500">{labels[k] ?? k}</dt>
          <dd className="sm:col-span-2 text-gray-900"><Value value={v} /></dd>
        </div>
      ))}
    </dl>
  )
}

export default function SharedPackagePage() {
  const { token } = useParams<{ token: string }>()
  const [pkg, setPkg] = useState<SharedPackage | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    openShare(token).then(setPkg).catch(e => setError(e.message))
  }, [token])

  if (error) return <div className="max-w-2xl mx-auto px-4 py-16 text-gray-600">{error}</div>
  if (!pkg) return <div className="max-w-2xl mx-auto px-4 py-16 text-gray-400">Loading…</div>

  const household = Object.entries(pkg.household)
  return (
    <div className="max-w-2xl mx-auto px-4 py-10 space-y-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Registration information</p>
        <h1 className="text-2xl font-bold text-gray-900 mt-1">For {pkg.recipient}</h1>
        <p className="text-sm text-gray-500 mt-1">
          Shared by the family through CampFinder. This link expires on {new Date(pkg.expires_at).toLocaleDateString()}
          {' '}and the family can withdraw it at any time. Please copy what you need into your records.
        </p>
      </header>
      {household.length > 0 && (
        <section className="border border-gray-200 rounded-2xl p-4">
          <h2 className="font-semibold text-gray-900 mb-1">Household</h2>
          <Rows entries={household} labels={HOUSEHOLD_LABELS} />
        </section>
      )}
      {pkg.children.map(child => {
        const { name, ...rest } = child
        return (
          <section key={name} className="border border-gray-200 rounded-2xl p-4">
            <h2 className="font-semibold text-gray-900 mb-1">{name}</h2>
            <Rows entries={Object.entries(rest)} labels={CHILD_LABELS} />
          </section>
        )
      })}
    </div>
  )
}
