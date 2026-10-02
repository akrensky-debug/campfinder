'use client'

import { createClient, type Session, type SupabaseClient } from '@supabase/supabase-js'
import { useEffect, useState } from 'react'

const URL = process.env.NEXT_PUBLIC_SUPABASE_URL
const ANON = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

let client: SupabaseClient | null = null

/** Browser Supabase client for sign-in only. Null when sign-in isn't configured. */
export function supabase(): SupabaseClient | null {
  if (!URL || !ANON) return null
  if (!client) client = createClient(URL, ANON, { auth: { persistSession: true, detectSessionInUrl: true } })
  return client
}

export async function authHeaders(): Promise<Record<string, string>> {
  const sb = supabase()
  if (!sb) return {}
  const { data } = await sb.auth.getSession()
  return data.session ? { Authorization: `Bearer ${data.session.access_token}` } : {}
}

/** Email sign-in link. Returns an error message, or null on success. */
export async function sendSignInLink(email: string): Promise<string | null> {
  const sb = supabase()
  if (!sb) return 'Sign-in is not set up yet.'
  const { error } = await sb.auth.signInWithOtp({
    email,
    options: { emailRedirectTo: `${window.location.origin}/signin` },
  })
  return error ? error.message : null
}

export async function signOut() {
  await supabase()?.auth.signOut()
}

/** Current session; undefined while loading. */
export function useSession(): Session | null | undefined {
  const [session, setSession] = useState<Session | null | undefined>(undefined)
  useEffect(() => {
    const sb = supabase()
    if (!sb) { setSession(null); return }
    sb.auth.getSession().then(({ data }) => setSession(data.session))
    const { data } = sb.auth.onAuthStateChange((_e, s) => setSession(s))
    return () => data.subscription.unsubscribe()
  }, [])
  return session
}
