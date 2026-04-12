'use client'

import { useEffect, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import { Events } from '@/lib/analytics'

function SuccessContent() {
  const params = useSearchParams()
  const campId = params.get('camp_id') || ''

  useEffect(() => {
    if (campId) Events.stripeCheckoutCompleted(campId)
  }, [campId])

  return (
    <div className="max-w-lg mx-auto px-4 py-24 text-center">
      <div className="text-5xl mb-4">🎉</div>
      <h1 className="text-2xl font-extrabold text-gray-900 mb-3">You're on Pro!</h1>
      <p className="text-gray-500 text-sm mb-8">
        Your listing is now verified and will rank higher in search results.
        Parents searching in your area will see your camp first.
      </p>
      <div className="bg-brand-50 border border-brand-200 rounded-2xl p-6 text-left mb-6">
        <h2 className="font-bold text-gray-900 mb-3 text-sm">Your Pro benefits are active</h2>
        <ul className="text-sm text-gray-600 space-y-2">
          <li>✓ Verified badge shown to all parents</li>
          <li>✓ Priority placement in search results</li>
          <li>✓ AI discoverability signals updated</li>
          <li>✓ Session management unlocked</li>
        </ul>
      </div>
      <a
        href={campId ? `/camps/${campId}` : '/search'}
        className="inline-block bg-brand-600 hover:bg-brand-700 text-white font-bold px-6 py-3 rounded-xl transition-colors"
      >
        View your listing →
      </a>
    </div>
  )
}

export default function ClaimSuccessPage() {
  return (
    <Suspense fallback={<div className="max-w-lg mx-auto px-4 py-24 text-center text-gray-400">Loading...</div>}>
      <SuccessContent />
    </Suspense>
  )
}
