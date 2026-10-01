'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { sendSignInLink, supabase, useSession } from '@/lib/auth'
import { loadFamily } from '@/lib/agent'

export default function SignInPage() {
  const session = useSession()
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  // Arriving back from the email link: save the guest family to the account, then go on.
  useEffect(() => {
    if (!session) return
    loadFamily().then(() => router.replace('/kit')).catch(() => router.replace('/'))
  }, [session, router])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    const err = await sendSignInLink(email.trim())
    setBusy(false)
    if (err) setError(err)
    else setSent(true)
  }

  if (!supabase()) {
    return <Shell><p className="text-gray-600">Sign-in isn't set up on this site yet.</p></Shell>
  }

  if (session) {
    return <Shell><p className="text-gray-600">Signing you in…</p></Shell>
  }

  return (
    <Shell>
      {sent ? (
        <div>
          <p className="text-gray-800 font-medium mb-1">Check your email.</p>
          <p className="text-gray-600 text-sm">We sent a sign-in link to {email}. Open it on this device to continue.</p>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-3">
          <p className="text-gray-600 text-sm">
            No password. We'll email you a link. Your kids, plans and calendar are saved to your account,
            and your info kit stays locked to it.
          </p>
          <input
            type="email"
            required
            value={email}
            onChange={e => setEmail(e.target.value)}
            placeholder="you@example.com"
            className="w-full border border-gray-200 rounded-xl px-4 py-3 outline-none focus:border-brand-400"
          />
          <button
            disabled={busy}
            className="w-full bg-brand-600 hover:bg-brand-700 text-white font-semibold rounded-xl py-3 disabled:opacity-50"
          >
            {busy ? 'Sending…' : 'Email me a sign-in link'}
          </button>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </form>
      )}
    </Shell>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="max-w-md mx-auto px-4 py-16">
      <h1 className="text-2xl font-bold text-gray-900 mb-4">Save your family</h1>
      {children}
    </div>
  )
}
