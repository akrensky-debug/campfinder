'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { getCamp, type CampDetail } from '@/lib/api'
import { Events } from '@/lib/analytics'
import TrustBadge from '@/components/TrustBadge'
import RequestInfoModal from '@/components/RequestInfoModal'

export default function CampDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [camp, setCamp]         = useState<CampDetail | null>(null)
  const [loading, setLoading]   = useState(true)
  const [showModal, setModal]   = useState(false)

  useEffect(() => {
    if (!id) return
    getCamp(id)
      .then(data => { setCamp(data); Events.campDetailViewed(id) })
      .catch(() => setCamp(null))
      .finally(() => setLoading(false))
  }, [id])

  if (loading) return (
    <div className="max-w-4xl mx-auto px-4 py-16">
      <div className="space-y-4">
        {[1,2,3].map(i => <div key={i} className="bg-gray-100 rounded-2xl h-24 animate-pulse" />)}
      </div>
    </div>
  )

  if (!camp) return (
    <div className="max-w-4xl mx-auto px-4 py-16 text-center text-gray-500">Camp not found.</div>
  )

  const typeLabel: Record<string, string> = { day: 'Day Camp', sleepaway: 'Sleepaway', specialty: 'Specialty' }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      {showModal && <RequestInfoModal campId={camp.id} campName={camp.name} onClose={() => setModal(false)} />}

      {/* Breadcrumb */}
      <nav className="text-sm text-gray-400 mb-6">
        <a href="/search" className="hover:text-brand-600">← Back to results</a>
      </nav>

      {/* Header */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6 mb-4">
        <div className="flex flex-col md:flex-row md:items-start gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1 text-sm text-gray-500">
              <span>{typeLabel[camp.camp_type] ?? camp.camp_type}</span>
              <span>·</span>
              <span>{camp.city}, {camp.state}</span>
            </div>
            <h1 className="text-2xl md:text-3xl font-extrabold text-gray-900 mb-3">{camp.name}</h1>
            <TrustBadge status={camp.verification_status} aca={camp.aca_accredited} />
            {camp.last_updated_date && (
              <p className="text-xs text-gray-400 mt-2">
                Last updated {new Date(camp.last_updated_date).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })}
              </p>
            )}
          </div>

          {/* Primary CTAs */}
          <div className="flex flex-col gap-2 md:min-w-[200px]">
            <button
              onClick={() => setModal(true)}
              className="bg-brand-600 hover:bg-brand-700 text-white font-bold px-5 py-3 rounded-xl transition-colors text-center"
            >
              Request info →
            </button>
            {camp.website_url && (
              <a
                href={camp.website_url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => Events.outboundSiteClicked(camp.id, camp.website_url!)}
                className="border border-gray-200 text-gray-700 font-medium px-5 py-2.5 rounded-xl text-center hover:border-brand-400 hover:text-brand-700 transition-colors text-sm"
              >
                Visit camp website ↗
              </a>
            )}
            {camp.registration_url && (
              <a
                href={camp.registration_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-center text-sm text-brand-600 underline hover:text-brand-700"
              >
                Register directly
              </a>
            )}
          </div>
        </div>
      </div>

      <div className="grid md:grid-cols-3 gap-4">
        {/* Main content */}
        <div className="md:col-span-2 space-y-4">
          {/* Description */}
          {(camp.description_full || camp.description_short) && (
            <section className="bg-white rounded-2xl border border-gray-200 p-6">
              <h2 className="font-bold text-gray-900 mb-3">About this camp</h2>
              <p className="text-gray-600 text-sm leading-relaxed">
                {camp.description_full || camp.description_short}
              </p>
            </section>
          )}

          {/* Sessions */}
          {camp.sessions && camp.sessions.length > 0 && (
            <section className="bg-white rounded-2xl border border-gray-200 p-6">
              <h2 className="font-bold text-gray-900 mb-4">2027 Sessions</h2>
              <div className="space-y-3">
                {camp.sessions.map(s => {
                  const avail: Record<string, string> = {
                    open: 'text-green-600 bg-green-50',
                    waitlist: 'text-yellow-700 bg-yellow-50',
                    full: 'text-red-600 bg-red-50',
                    unknown: 'text-gray-500 bg-gray-50',
                  }
                  return (
                    <div key={s.id} className="flex items-center justify-between py-3 border-b border-gray-100 last:border-0">
                      <div>
                        <p className="font-medium text-sm text-gray-900">{s.name || 'Session'}</p>
                        <p className="text-xs text-gray-500">
                          {new Date(s.start_date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                          {' - '}
                          {new Date(s.end_date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                        </p>
                      </div>
                      <div className="flex items-center gap-3">
                        {s.price && <span className="font-semibold text-gray-900">${Math.round(s.price).toLocaleString()}</span>}
                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full capitalize ${avail[s.availability] ?? avail.unknown}`}>
                          {s.availability}
                        </span>
                      </div>
                    </div>
                  )
                })}
              </div>
            </section>
          )}

          {/* Activities */}
          {camp.activities && camp.activities.length > 0 && (
            <section className="bg-white rounded-2xl border border-gray-200 p-6">
              <h2 className="font-bold text-gray-900 mb-3">Activities</h2>
              <div className="flex flex-wrap gap-2">
                {camp.activities.map(a => (
                  <span key={a} className="text-sm bg-gray-100 text-gray-700 px-3 py-1 rounded-full capitalize">{a}</span>
                ))}
              </div>
            </section>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          {/* Quick facts */}
          <section className="bg-white rounded-2xl border border-gray-200 p-5">
            <h2 className="font-bold text-gray-900 mb-4 text-sm uppercase tracking-wide">Quick facts</h2>
            <dl className="space-y-3 text-sm">
              {camp.age_min != null && camp.age_max != null && (
                <div className="flex justify-between">
                  <dt className="text-gray-500">Ages</dt>
                  <dd className="font-medium">{camp.age_min}-{camp.age_max}</dd>
                </div>
              )}
              {camp.price_per_week && (
                <div className="flex justify-between">
                  <dt className="text-gray-500">Price</dt>
                  <dd className="font-medium">${Math.round(camp.price_per_week)}/week</dd>
                </div>
              )}
              {camp.indoor_outdoor && (
                <div className="flex justify-between">
                  <dt className="text-gray-500">Setting</dt>
                  <dd className="font-medium capitalize">{camp.indoor_outdoor}</dd>
                </div>
              )}
              {camp.gender_policy && (
                <div className="flex justify-between">
                  <dt className="text-gray-500">Gender</dt>
                  <dd className="font-medium capitalize">{camp.gender_policy}</dd>
                </div>
              )}
              <div className="flex justify-between">
                <dt className="text-gray-500">Transport</dt>
                <dd className="font-medium">{camp.transportation ? '✓ Yes' : 'No'}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Extended care</dt>
                <dd className="font-medium">{camp.extended_care ? '✓ Yes' : 'No'}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Meals</dt>
                <dd className="font-medium">{camp.meals_included ? '✓ Included' : 'No'}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Financial aid</dt>
                <dd className="font-medium">{camp.financial_aid ? '✓ Available' : 'No'}</dd>
              </div>
            </dl>
          </section>

          {/* Contact */}
          {(camp.email || camp.phone) && (
            <section className="bg-white rounded-2xl border border-gray-200 p-5">
              <h2 className="font-bold text-gray-900 mb-3 text-sm uppercase tracking-wide">Contact</h2>
              <div className="space-y-2 text-sm">
                {camp.email && <p className="text-gray-600 break-all">{camp.email}</p>}
                {camp.phone && <p className="text-gray-600">{camp.phone}</p>}
              </div>
            </section>
          )}

          {/* Trust summary */}
          {camp.trust_summary && (
            <section className="bg-gray-50 rounded-2xl border border-gray-200 p-5">
              <h2 className="font-bold text-gray-900 mb-3 text-sm uppercase tracking-wide">Data quality</h2>
              <div className="space-y-2 text-xs text-gray-500">
                <p>Verification: <span className="font-medium text-gray-700 capitalize">{camp.trust_summary.verification_status.replace('_', ' ')}</span></p>
                {camp.trust_summary.fields_verified.length > 0 && (
                  <p>Verified fields: {camp.trust_summary.fields_verified.length}</p>
                )}
                {camp.trust_summary.fields_missing.length > 0 && (
                  <p className="text-amber-600">Missing: {camp.trust_summary.fields_missing.join(', ')}</p>
                )}
                {camp.trust_summary.accreditation.status === 'confirmed' && (
                  <p className="text-green-600 font-medium">ACA Accredited ✓</p>
                )}
              </div>
              {camp.verification_status === 'unverified' && (
                <a
                  href={`/operators/claim?camp_id=${camp.id}`}
                  className="block mt-3 text-xs text-brand-600 underline"
                  onClick={() => Events.claimFlowStarted(camp.id)}
                >
                  Own this camp? Claim your listing →
                </a>
              )}
            </section>
          )}
        </div>
      </div>
    </div>
  )
}
