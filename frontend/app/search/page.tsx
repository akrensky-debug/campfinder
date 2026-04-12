'use client'

import { useEffect, useState, Suspense } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { searchCamps, type CampSearchResult } from '@/lib/api'
import { Events } from '@/lib/analytics'
import CampCard from '@/components/CampCard'
import EmailGate from '@/components/EmailGate'

const TEASER_COUNT = 3

function SearchResults() {
  const params = useSearchParams()
  const router = useRouter()

  const location   = params.get('location') || ''
  const age        = params.get('age') ? Number(params.get('age')) : undefined
  const camp_type  = params.get('camp_type') || undefined
  const category   = params.get('category') || undefined

  const [results, setResults]     = useState<CampSearchResult[]>([])
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState('')
  const [unlocked, setUnlocked]   = useState(false)

  // Search form state (for inline re-search)
  const [loc, setLoc]       = useState(location)
  const [ageVal, setAgeVal] = useState(age?.toString() ?? '')

  useEffect(() => {
    // Check persisted unlock
    if (typeof window !== 'undefined' && localStorage.getItem('cf_unlocked')) {
      setUnlocked(true)
    }
  }, [])

  useEffect(() => {
    if (!location) return
    setLoading(true)
    setError('')
    Events.searchSubmitted({ location, age, camp_type, category })

    searchCamps({
      location,
      age,
      camp_type,
      categories: category ? [category] : undefined,
      limit: 20,
    })
      .then(data => {
        setResults(data.results)
        Events.resultsViewed({ count: data.total, location })
        if (data.total > TEASER_COUNT && !unlocked) {
          Events.emailGateViewed({ hidden: data.total - TEASER_COUNT, location })
        }
      })
      .catch(() => setError('Search failed. Please try again.'))
      .finally(() => setLoading(false))
  }, [location, age, camp_type, category])

  function handleReSearch(e: React.FormEvent) {
    e.preventDefault()
    const p = new URLSearchParams({ location: loc })
    if (ageVal) p.set('age', ageVal)
    router.push(`/search?${p.toString()}`)
  }

  const visible = unlocked ? results : results.slice(0, TEASER_COUNT)
  const hidden  = unlocked ? [] : results.slice(TEASER_COUNT)
  const matchedIds = results.map(r => r.id)

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      {/* Compact re-search bar */}
      <form onSubmit={handleReSearch} className="flex gap-2 mb-8 flex-wrap">
        <input
          value={loc}
          onChange={e => setLoc(e.target.value)}
          placeholder="Location"
          className="flex-1 min-w-[180px] px-4 py-2.5 border border-gray-200 rounded-xl text-sm outline-none focus:border-brand-400"
        />
        <input
          type="number"
          value={ageVal}
          onChange={e => setAgeVal(e.target.value)}
          placeholder="Age"
          min={3} max={18}
          className="w-24 px-4 py-2.5 border border-gray-200 rounded-xl text-sm outline-none focus:border-brand-400"
        />
        <button
          type="submit"
          className="bg-brand-600 text-white font-semibold px-5 py-2.5 rounded-xl text-sm hover:bg-brand-700 transition-colors"
        >
          Search
        </button>
      </form>

      {/* Loading */}
      {loading && (
        <div className="space-y-4">
          {[1,2,3].map(i => (
            <div key={i} className="bg-gray-100 rounded-2xl h-40 animate-pulse" />
          ))}
        </div>
      )}

      {/* Error */}
      {!loading && error && (
        <div className="text-center py-16 text-gray-500">{error}</div>
      )}

      {/* No results */}
      {!loading && !error && results.length === 0 && (
        <div className="text-center py-16">
          <p className="text-gray-500 mb-2">No camps found near <strong>{location}</strong>.</p>
          <p className="text-sm text-gray-400">Try a nearby city or expand your search radius.</p>
        </div>
      )}

      {/* Results */}
      {!loading && results.length > 0 && (
        <>
          <p className="text-sm text-gray-500 mb-4">
            {results.length} camp{results.length !== 1 ? 's' : ''} near <strong>{location}</strong>
            {age ? ` for age ${age}` : ''}
          </p>

          <div className="space-y-4">
            {visible.map((camp, i) => (
              <CampCard key={camp.id} camp={camp} rank={i + 1} />
            ))}
          </div>

          {/* Email gate */}
          {!unlocked && hidden.length > 0 && (
            <div className="mt-6">
              {/* Blurred previews */}
              <div className="space-y-4 mb-6 pointer-events-none">
                {hidden.slice(0, 2).map(camp => (
                  <CampCard key={camp.id} camp={camp} blurred />
                ))}
              </div>
              <EmailGate
                hiddenCount={hidden.length}
                searchContext={{ location, age, camp_type }}
                matchedCampIds={matchedIds}
                onUnlock={() => setUnlocked(true)}
              />
            </div>
          )}

          {unlocked && (
            <div className="mt-8 p-4 bg-brand-50 border border-brand-200 rounded-2xl text-center">
              <p className="text-sm text-brand-700 font-medium">
                ✉️ Results sent to your email ·
                <a href="/camps" className="underline ml-1">Save your shortlist</a>
              </p>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default function SearchPage() {
  return (
    <Suspense fallback={<div className="max-w-6xl mx-auto px-4 py-16 text-center text-gray-400">Loading...</div>}>
      <SearchResults />
    </Suspense>
  )
}
