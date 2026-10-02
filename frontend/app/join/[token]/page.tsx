'use client'

import { useEffect, useRef, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { sendSignInLink, signOut, supabase, useSession } from '@/lib/auth'
import { rememberFamily } from '@/lib/agent'
import { ROLE_LABELS, acceptInvite, previewInvite, type InvitePreview } from '@/lib/household'

export default function JoinPage() {
  const { token } = useParams<{ token: string }>()
  const session = useSession()
  const router = useRouter()
  const [invite, setInvite] = useState<InvitePreview | null>(null)
  const [error, setError] = useState('')
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [busy, setBusy] = useState(false)
  const tried = useRef(false)

  useEffect(() => {
    previewInvite(token).then(setInvite).catch(e => setError(e.message))
  }, [token])

  async function accept() {
    setBusy(true)
    setError('')
    try {
      const res = await acceptInvite(token)
      rememberFamily(res.family_id)
      router.replace('/household')
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }

  // Back from the sign-in email: accept straight away.
  useEffect(() => {
    if (session && invite && !invite.expired && !tried.current) {
      tried.current = true
      accept()
    }
  }, [session, invite]) // eslint-disable-line react-hooks/exhaustive-deps

  async function sendLink(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    const err = await sendSignInLink(email.trim(), `/join/${token}`)
    setBusy(false)
    if (err) setError(err)
    else setSent(true)
  }

  return (
    <div className="max-w-md mx-auto px-4 py-16 space-y-5">
      {!invite ? (
        <>
          <h1 className="text-2xl font-bold text-gray-900">Join a family</h1>
          <p className="text-gray-600">{error || 'Checking your invite…'}</p>
        </>
      ) : (
        <>
          <div>
            <p className="text-sm text-gray-500 mb-1">Hi {invite.display_name},</p>
            <h1 className="text-2xl font-bold text-gray-900">{invite.invited_by} invited you to help with their family's summer plan</h1>
          </div>
          <div className="bg-gray-50 rounded-2xl p-4 text-sm text-gray-700 space-y-1">
            <p><span className="font-medium">{ROLE_LABELS[invite.role]}:</span> you'll see {invite.role_help}.</p>
            <p className="text-gray-500">You'll get a short email before each job, and can turn that off any time.</p>
          </div>

          {invite.expired ? (
            <p className="text-amber-700">This invite has expired. Ask {invite.invited_by} to send a new one.</p>
          ) : !supabase() ? (
            <p className="text-gray-600">Sign-in isn't set up on this site yet.</p>
          ) : session ? (
            <div className="space-y-3">
              <p className="text-sm text-gray-600">Signed in as {session.user.email}.</p>
              <button onClick={accept} disabled={busy} className="w-full bg-brand-600 hover:bg-brand-700 text-white font-semibold rounded-xl py-3 disabled:opacity-50">
                {busy ? 'Joining…' : 'Accept and join'}
              </button>
              {error && (
                <div className="text-sm text-red-600 space-y-1">
                  <p>{error}</p>
                  <button onClick={() => signOut().then(() => { tried.current = true; setError('') })} className="text-gray-600 underline">
                    Use a different email
                  </button>
                </div>
              )}
            </div>
          ) : sent ? (
            <div>
              <p className="text-gray-800 font-medium mb-1">Check your email.</p>
              <p className="text-gray-600 text-sm">We sent a sign-in link to {email}. Open it to finish joining.</p>
            </div>
          ) : (
            <form onSubmit={sendLink} className="space-y-3">
              <p className="text-sm text-gray-600">
                Sign in with the address the invite went to ({invite.email_hint}). No password; we'll email you a link.
              </p>
              <input
                type="email" required value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com"
                className="w-full border border-gray-200 rounded-xl px-4 py-3 outline-none focus:border-brand-400"
              />
              <button disabled={busy} className="w-full bg-brand-600 hover:bg-brand-700 text-white font-semibold rounded-xl py-3 disabled:opacity-50">
                {busy ? 'Sending…' : 'Email me a sign-in link'}
              </button>
              {error && <p className="text-sm text-red-600">{error}</p>}
            </form>
          )}
        </>
      )}
    </div>
  )
}
