'use client'

import { useState, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import { searchCamps, type CampSearchResult } from '@/lib/api'
import { Events } from '@/lib/analytics'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

function ClaimFlow() {
  const params = useSearchParams()
  const prefillId = params.get('camp_id')

  const [step, setStep] = useState<'search' | 'confirm' | 'verify' | 'done'>(prefillId ? 'confirm' : 'search')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<CampSearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [selected, setSelected] = useState<CampSearchResult | null>(null)
  const [email, setEmail] = useState('')
  const [contactName, setContactName] = useState('')
  const [role, setRole] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [token, setToken] = useState('')
  const [verifying, setVerifying] = useState(false)
  const [verifyError, setVerifyError] = useState('')
  const [upgrading, setUpgrading] = useState(false)

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    if (!query.trim()) return
    setSearching(true)
    setError('')
    try {
      const data = await searchCamps({ location: query, limit: 10 })
      setResults(data.results)
      if (data.results.length === 0) setError('No camps found. Try a different name or city.')
    } catch {
      setError('Search failed. Please try again.')
    } finally {
      setSearching(false)
    }
  }

  function selectCamp(camp: CampSearchResult) {
    setSelected(camp)
    Events.claimFlowStarted(camp.id)
    setStep('confirm')
  }

  async function handleClaim(e: React.FormEvent) {
    e.preventDefault()
    if (!selected) return
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`${API_URL}/api/v1/claims`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          camp_id: selected.id,
          email,
          contact_name: contactName || undefined,
          role: role || undefined,
        }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || 'Claim failed')
      }
      setStep('verify')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Something went wrong.')
    } finally {
      setLoading(false)
    }
  }

  async function handleVerify(e: React.FormEvent) {
    e.preventDefault()
    if (!token.trim()) return
    setVerifying(true)
    setVerifyError('')
    try {
      const res = await fetch(`${API_URL}/api/v1/claims/verify?token=${encodeURIComponent(token)}`)
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || 'Invalid or expired token')
      }
      setStep('done')
    } catch (err: unknown) {
      setVerifyError(err instanceof Error ? err.message : 'Verification failed.')
    } finally {
      setVerifying(false)
    }
  }

  return (
    <div className="max-w-xl mx-auto px-4 py-12">
      <nav className="text-sm text-gray-400 mb-8">
        <a href="/operators" className="hover:text-brand-600">← For camps</a>
      </nav>

      {/* Step: Search */}
      {step === 'search' && (
        <>
          <div className="mb-8">
            <h1 className="text-3xl font-extrabold text-gray-900 mb-2">Claim your listing</h1>
            <p className="text-gray-500 text-sm">
              Search for your camp below. Claiming your listing lets you update sessions,
              pricing, and contact info -- and earns a verified badge that builds trust with parents.
            </p>
          </div>

          <form onSubmit={handleSearch} className="flex gap-2 mb-6">
            <input
              type="text"
              placeholder="Camp name or city"
              value={query}
              onChange={e => setQuery(e.target.value)}
              className="flex-1 px-4 py-3 border border-gray-200 rounded-xl text-sm outline-none focus:border-brand-400"
            />
            <button
              type="submit"
              disabled={searching}
              className="bg-brand-600 hover:bg-brand-700 text-white font-semibold px-5 py-3 rounded-xl text-sm transition-colors disabled:opacity-60"
            >
              {searching ? '...' : 'Search'}
            </button>
          </form>

          {error && <p className="text-red-500 text-sm mb-4">{error}</p>}

          {results.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs text-gray-400 mb-3">Select your camp:</p>
              {results.map(camp => (
                <button
                  key={camp.id}
                  onClick={() => selectCamp(camp)}
                  className="w-full text-left bg-white border border-gray-200 rounded-xl p-4 hover:border-brand-300 hover:shadow-sm transition-all"
                >
                  <p className="font-semibold text-gray-900 text-sm">{camp.name}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{camp.city}, {camp.state}</p>
                </button>
              ))}
              <p className="text-xs text-gray-400 pt-2">
                Don't see your camp?{' '}
                <a href="/operators/submit" className="text-brand-600 underline">Submit it here →</a>
              </p>
            </div>
          )}
        </>
      )}

      {/* Step: Confirm & submit claim */}
      {step === 'confirm' && selected && (
        <>
          <div className="mb-6">
            <h1 className="text-3xl font-extrabold text-gray-900 mb-1">Claim this listing</h1>
            <div className="bg-brand-50 border border-brand-200 rounded-xl px-4 py-3 mt-3">
              <p className="font-semibold text-gray-900 text-sm">{selected.name}</p>
              <p className="text-xs text-gray-500">{selected.city}, {selected.state}</p>
            </div>
          </div>

          <form onSubmit={handleClaim} className="space-y-4">
            <div>
              <label className="block text-sm text-gray-600 mb-1">Your email *</label>
              <input
                type="email"
                required
                value={email}
                onChange={e => setEmail(e.target.value)}
                className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm outline-none focus:border-brand-400"
                placeholder="director@yourcamp.com"
              />
              <p className="text-xs text-gray-400 mt-1">We'll send a verification link to this address.</p>
            </div>

            <div>
              <label className="block text-sm text-gray-600 mb-1">Your name</label>
              <input
                type="text"
                value={contactName}
                onChange={e => setContactName(e.target.value)}
                className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm outline-none focus:border-brand-400"
                placeholder="Jane Smith"
              />
            </div>

            <div>
              <label className="block text-sm text-gray-600 mb-1">Your role</label>
              <input
                type="text"
                value={role}
                onChange={e => setRole(e.target.value)}
                className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm outline-none focus:border-brand-400"
                placeholder="Camp Director, Owner, Marketing..."
              />
            </div>

            {error && <p className="text-red-500 text-sm">{error}</p>}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-brand-600 hover:bg-brand-700 text-white font-bold py-3.5 rounded-xl transition-colors disabled:opacity-60"
            >
              {loading ? 'Sending verification...' : 'Send verification email →'}
            </button>

            <button
              type="button"
              onClick={() => { setStep('search'); setSelected(null) }}
              className="w-full text-sm text-gray-400 hover:text-gray-600 py-1"
            >
              ← Search again
            </button>
          </form>
        </>
      )}

      {/* Step: Enter token */}
      {step === 'verify' && (
        <>
          <div className="mb-8">
            <div className="text-4xl mb-4">📬</div>
            <h1 className="text-2xl font-extrabold text-gray-900 mb-2">Check your email</h1>
            <p className="text-gray-500 text-sm">
              We've sent a verification code to <strong>{email}</strong>.
              Enter it below to complete your claim.
            </p>
          </div>

          <form onSubmit={handleVerify} className="space-y-4">
            <input
              type="text"
              placeholder="Paste verification code"
              value={token}
              onChange={e => setToken(e.target.value)}
              required
              className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm outline-none focus:border-brand-400 font-mono"
            />

            {verifyError && <p className="text-red-500 text-sm">{verifyError}</p>}

            <button
              type="submit"
              disabled={verifying}
              className="w-full bg-brand-600 hover:bg-brand-700 text-white font-bold py-3.5 rounded-xl transition-colors disabled:opacity-60"
            >
              {verifying ? 'Verifying...' : 'Verify and claim listing →'}
            </button>
          </form>
        </>
      )}

      {/* Step: Done */}
      {step === 'done' && (
        <div className="text-center py-8">
          <div className="text-5xl mb-4">✅</div>
          <h1 className="text-2xl font-extrabold text-gray-900 mb-3">Listing claimed!</h1>
          <p className="text-gray-500 text-sm mb-6">
            Your ownership has been verified. You can now update your listing, add sessions,
            and manage your camp's data on CampFinder.
          </p>
          <div className="bg-brand-50 border border-brand-200 rounded-2xl p-6 text-left mb-6">
            <h2 className="font-bold text-gray-900 mb-3 text-sm">What's next</h2>
            <ul className="text-sm text-gray-600 space-y-2">
              <li>✓ Your listing now shows a <strong>claimed</strong> status badge</li>
              <li>✓ Parents see that your data is managed by a verified owner</li>
              <li>→ Add your 2025 sessions and pricing to rank higher in search</li>
              <li>→ Upgrade to Pro for priority placement and AI discoverability boost</li>
            </ul>
          </div>
          <div className="bg-white border border-gray-200 rounded-2xl p-6 text-left">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="font-bold text-gray-900 text-sm mb-1">Pro listing -- $149/yr</p>
                <p className="text-xs text-gray-500">
                  Priority ranking · Verified badge · Session management · AI discoverability signals
                </p>
              </div>
              <button
                disabled={upgrading}
                onClick={async () => {
                  if (!selected) return
                  setUpgrading(true)
                  Events.stripeCheckoutStarted(selected.id)
                  try {
                    const res = await fetch(`${API_URL}/api/v1/stripe/checkout`, {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ camp_id: selected.id, email }),
                    })
                    const data = await res.json()
                    if (data.checkout_url) {
                      window.location.href = data.checkout_url
                    }
                  } catch {
                    setUpgrading(false)
                  }
                }}
                className="shrink-0 bg-brand-600 hover:bg-brand-700 text-white font-bold px-4 py-2 rounded-xl text-sm transition-colors disabled:opacity-60"
              >
                {upgrading ? 'Redirecting...' : 'Upgrade →'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function ClaimPage() {
  return (
    <Suspense fallback={<div className="max-w-xl mx-auto px-4 py-24 text-center text-gray-400">Loading...</div>}>
      <ClaimFlow />
    </Suspense>
  )
}
