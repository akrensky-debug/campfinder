'use client'

import { supabase, useSession } from '@/lib/auth'

export default function AccountLink() {
  const session = useSession()
  if (!supabase() || session === undefined) return null
  return session ? (
    <>
      <a href="/registrations" className="hidden sm:inline text-sm font-medium text-gray-600 hover:text-brand-700">Registrations</a>
      <a href="/kit" className="whitespace-nowrap text-sm font-medium text-gray-600 hover:text-brand-700">Info kit</a>
    </>
  ) : (
    <a href="/signin" className="text-sm font-medium text-gray-600 hover:text-brand-700">Sign in</a>
  )
}
