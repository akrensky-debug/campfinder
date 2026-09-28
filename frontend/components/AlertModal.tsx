'use client'

import { useState } from 'react'
import { createAlert } from '@/lib/api'
import { Events } from '@/lib/analytics'

interface Props {
  campId: string
  campName: string
  onClose: () => void
}

export default function AlertModal({ campId, campName, onClose }: Props) {
  const [email, setEmail] = useState('')
  const [done, setDone] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      await createAlert({ email, camp_id: campId })
      Events.alertCreated(campId)
      setDone(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6" onClick={e => e.stopPropagation()}>
        {done ? (
          <div className="text-center py-4">
            <h3 className="text-lg font-bold mb-1">You're on the list</h3>
            <p className="text-sm text-gray-500">
              We'll email you when registration for <strong>{campName}</strong> is about to open.
              One email per camp, and a link to stop it in every message.
            </p>
            <button onClick={onClose} className="mt-4 text-sm text-brand-600 underline">Close</button>
          </div>
        ) : (
          <>
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="text-lg font-bold">Tell me when registration opens</h3>
                <p className="text-sm text-gray-500">{campName}</p>
              </div>
              <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none" aria-label="Close">&times;</button>
            </div>
            <form onSubmit={handleSubmit} className="space-y-3">
              <input
                type="email"
                placeholder="Email address"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm outline-none focus:border-brand-400"
              />
              {error && <p className="text-sm text-red-600">{error}</p>}
              <button
                type="submit"
                disabled={loading}
                className="w-full bg-brand-600 hover:bg-brand-700 text-white font-bold py-3 rounded-xl transition-colors disabled:opacity-60"
              >
                {loading ? 'Saving...' : 'Alert me'}
              </button>
              <p className="text-xs text-gray-400">We use your email for this alert and nothing else.</p>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
