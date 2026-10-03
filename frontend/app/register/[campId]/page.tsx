'use client'

import { Suspense, useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'next/navigation'
import { useSession } from '@/lib/auth'
import { loadFamily, type Family } from '@/lib/agent'
import { getKit, type Contact, type InfoKit } from '@/lib/kit'
import {
  bookingStatus, confirmBooking, countdown, fmtWhen, getChecklist, getQuote, openingCalendarLink, previewPackage,
  sharePackage, watchRegistration, type BookingQuote, type PackagePreview, type RegisterChecklist,
} from '@/lib/booking'

export default function RegisterPage() {
  return (
    <Suspense fallback={<div className="max-w-3xl mx-auto px-4 py-16 text-gray-400">Loading…</div>}>
      <Register />
    </Suspense>
  )
}

function Register() {
  const { campId } = useParams<{ campId: string }>()
  const search = useSearchParams()
  const session = useSession()
  const [family, setFamily] = useState<Family | null>(null)
  const [list, setList] = useState<RegisterChecklist | null>(null)
  const [error, setError] = useState('')
  const [now, setNow] = useState(Date.now())
  const registrationId = search.get('registration')
  const sessionId = search.get('session')
  const child = search.get('child')

  async function refresh(f: Family, regId = registrationId) {
    setList(await getChecklist(f.id, { camp_id: campId, session_id: sessionId, child, registration_id: regId }))
  }

  useEffect(() => {
    if (session === undefined) return
    loadFamily().then(async f => { setFamily(f); await refresh(f) }).catch(e => setError(e.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, campId, registrationId])

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30_000)
    return () => clearInterval(t)
  }, [])

  if (!family || !list) return <div className="max-w-3xl mx-auto px-4 py-16 text-gray-400">{error || 'Loading…'}</div>

  const reg = list.registration
  const opensLater = list.opens_at && new Date(list.opens_at).getTime() > now
  const kidName = reg?.child_name || child || ''

  async function watch() {
    if (!family) return
    const r = await watchRegistration(family.id, { camp_id: campId, session_id: sessionId, child_name: child })
    window.history.replaceState(null, '', `/register/${campId}?registration=${r.id}`)
    await refresh(family, r.id)
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-10 space-y-8">
      <header className="space-y-2">
        <p className="text-sm text-gray-500"><a href="/registrations" className="hover:text-brand-700">Registrations</a> ›</p>
        <h1 className="text-2xl font-bold text-gray-900">Register for {list.camp_name}</h1>
        <p className="text-gray-600">
          {[kidName, list.session_name, list.price ? `$${list.price.toLocaleString()}` : null,
            list.availability && list.availability !== 'unknown' ? list.availability : null].filter(Boolean).join(' · ')}
        </p>
      </header>

      <section className="rounded-2xl border border-brand-100 bg-brand-50 p-5 space-y-3">
        {reg && (reg.status === 'registered' || reg.status === 'waitlisted') ? (
          <div>
            <p className="text-xl font-bold text-green-700">{reg.status === 'registered' ? 'Registered ✓' : 'On the waitlist'}</p>
            <p className="text-sm text-gray-700">{reg.next_step}{reg.confirmation_number ? ` Confirmation ${reg.confirmation_number}.` : ''}</p>
          </div>
        ) : list.opens_at ? (
          <div>
            <p className="text-xl font-bold text-brand-800">{countdown(list.opens_at, now)}</p>
            <p className="text-sm text-gray-700">
              {opensLater ? 'Registration opens' : 'Registration opened'} {fmtWhen(list.opens_at)}
              {list.opens_at_source === 'family' ? ' (the date you entered)' : ' (from the camp)'}
              {list.closes_at ? ` · closes ${fmtWhen(list.closes_at)}` : ''}
            </p>
          </div>
        ) : (
          <p className="text-sm text-gray-700">We don't have this camp's registration date yet. Check its site, or add the date on your Registrations page.</p>
        )}
        <div className="flex flex-wrap gap-3">
          {list.registration_url ? (
            <a href={list.registration_url} target="_blank" rel="noopener noreferrer"
              className="bg-brand-600 hover:bg-brand-700 text-white font-semibold px-5 py-2.5 rounded-xl">
              Open the camp's registration ↗
            </a>
          ) : <span className="text-sm text-gray-500">No registration link on file; use the camp's website.</span>}
          {opensLater && list.opens_at && reg?.status !== 'registered' && reg?.status !== 'waitlisted' && (
            <a href={openingCalendarLink(list.camp_name, list.opens_at, list.registration_url)} target="_blank" rel="noopener noreferrer"
              className="border border-gray-200 bg-white text-gray-700 font-medium px-4 py-2.5 rounded-xl text-sm">
              Add an alarm to Google Calendar
            </a>
          )}
          {!reg && (
            <button onClick={watch} className="border border-gray-200 bg-white text-gray-700 font-medium px-4 py-2.5 rounded-xl text-sm">
              Track this and remind me
            </button>
          )}
        </div>
        <p className="text-xs text-gray-500">You register and pay on the camp's own site. CampFinder never submits forms or payments for you.</p>
      </section>

      <section className="space-y-2">
        <h2 className="font-semibold text-gray-900">Checklist</h2>
        <ol className="space-y-2">
          {list.steps.map(s => (
            <li key={s.key} className="flex gap-3 text-sm">
              <span className={`mt-0.5 h-5 w-5 shrink-0 rounded-full border flex items-center justify-center text-xs ${s.done ? 'bg-green-600 border-green-600 text-white' : 'border-gray-300 text-transparent'}`}>✓</span>
              <span className="text-gray-700">
                {s.text}{' '}
                {s.href && <a href={s.href} target={s.href.startsWith('http') ? '_blank' : undefined} rel="noopener noreferrer" className="text-brand-700 font-medium">Open</a>}
              </span>
            </li>
          ))}
        </ol>
      </section>

      <FormAnswers familyId={family.id} list={list} signedIn={!!session} kidName={kidName} />

      {session && list.kit_available && (
        <PackagePanel familyId={family.id} campId={campId} kidName={kidName} registrationId={reg?.id ?? null}
          onShared={() => refresh(family, reg?.id ?? registrationId)} sharedCount={list.shares.length} />
      )}

      {session && reg && <SandboxBooking familyId={family.id} registrationId={reg.id} onBooked={() => refresh(family, reg.id)} />}
    </div>
  )
}

function fmtContacts(list: Contact[]): string {
  return list.map(c => [c.name, c.relationship && `(${c.relationship})`, c.phone, c.email].filter(Boolean).join(' ')).join('; ')
}

function answerFor(kit: InfoKit, field: string, kidName: string): string | null {
  const [scope, name] = field.split('.')
  if (scope === 'household') {
    const v = (kit.household as unknown as Record<string, unknown>)[name]
    if (Array.isArray(v)) return v.length ? fmtContacts(v as Contact[]) : null
    return (v as string | null) || null
  }
  const kid = kit.children.find(c => c.name.toLowerCase() === kidName.toLowerCase()) ?? (kit.children.length === 1 ? kit.children[0] : undefined)
  if (!kid) return null
  if (name === 'name') return kid.name
  return ((kid as unknown as Record<string, unknown>)[name] as string | null) || null
}

function FormAnswers({ familyId, list, signedIn, kidName }: {
  familyId: string; list: RegisterChecklist; signedIn: boolean; kidName: string
}) {
  const [kit, setKit] = useState<InfoKit | null>(null)
  const [copied, setCopied] = useState('')
  const [error, setError] = useState('')

  async function show() {
    try { setKit(await getKit(familyId)) } catch (e) { setError((e as Error).message) }
  }

  function copy(q: string, text: string) {
    navigator.clipboard?.writeText(text)
    setCopied(q)
    setTimeout(() => setCopied(''), 1500)
  }

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-semibold text-gray-900">What the form asks</h2>
        {signedIn && list.kit_available && (
          kit
            ? <button onClick={() => setKit(null)} className="text-sm text-gray-500">Hide my answers</button>
            : <button onClick={show} className="text-sm font-medium text-brand-700">Show my answers to copy</button>
        )}
      </div>
      <p className="text-sm text-gray-500">
        {list.form.typical
          ? "We haven't mapped this camp's form yet, so this is what most camp forms ask."
          : `From this camp's form${list.form.platform ? ` (${list.form.platform})` : ''}.`}
        {!list.kit_available && ' Sign in and fill in your info kit to have answers ready.'}
      </p>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <ul className="divide-y divide-gray-100 border border-gray-200 rounded-2xl bg-white">
        {list.form.fields.map(f => {
          const answer = kit && f.kit_field ? answerFor(kit, f.kit_field, kidName) : null
          return (
            <li key={f.question} className="px-4 py-2.5 text-sm flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="text-gray-800">{f.question}{!f.required && <span className="text-gray-400"> (optional)</span>}</p>
                {answer && <p className="text-gray-600 break-words">{answer}</p>}
              </div>
              <span className="shrink-0">
                {answer ? (
                  <button onClick={() => copy(f.question, answer)} className="text-brand-700 font-medium">{copied === f.question ? 'Copied' : 'Copy'}</button>
                ) : f.kit_field === null ? (
                  <span className="text-gray-400">On the camp's site</span>
                ) : f.ready === true ? (
                  <span className="text-green-700">In your kit</span>
                ) : f.ready === false ? (
                  <a href="/kit" className="text-amber-700">Missing{f.missing_for.length ? ` for ${f.missing_for.join(', ')}` : ''}: add it</a>
                ) : null}
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function PackagePanel({ familyId, campId, kidName, registrationId, sharedCount, onShared }: {
  familyId: string; campId: string; kidName: string; registrationId: string | null; sharedCount: number; onShared: () => void
}) {
  const [preview, setPreview] = useState<PackagePreview | null>(null)
  const [household, setHousehold] = useState<string[]>([])
  const [childFields, setChildFields] = useState<string[]>([])
  const [link, setLink] = useState('')
  const [error, setError] = useState('')

  async function prepare() {
    setError('')
    try {
      const p = await previewPackage(familyId, { camp_id: campId, children: kidName ? [kidName] : [], registration_id: registrationId })
      setPreview(p)
      setHousehold(p.household_fields)
      setChildFields(p.child_fields)
    } catch (e) { setError((e as Error).message) }
  }

  async function share() {
    if (!preview) return
    setError('')
    try {
      const res = await sharePackage(familyId, {
        camp_id: campId, children: preview.children, household_fields: household,
        child_fields: preview.children.length ? childFields : [], expires_in_days: 30,
      })
      setLink(res.url)
      onShared()
    } catch (e) { setError((e as Error).message) }
  }

  const toggle = (list: string[], set: (v: string[]) => void, v: string) => set(list.includes(v) ? list.filter(x => x !== v) : [...list, v])

  return (
    <section className="space-y-3">
      <h2 className="font-semibold text-gray-900">Info kit package for this camp</h2>
      <p className="text-sm text-gray-600">
        A private link with only what this camp's form asks for. Send it to the camp if they accept it, or keep it to
        copy from. It expires in 30 days, you can withdraw it on your Info kit page, and you'll see when it's opened.
        {sharedCount > 0 && ` You've already shared ${sharedCount} with this camp.`}
      </p>
      {!preview && !link && (
        <button onClick={prepare} className="border border-brand-500 text-brand-700 font-semibold px-4 py-2 rounded-xl text-sm">Prepare a package to review</button>
      )}
      {preview && !link && (
        <div className="border border-gray-200 rounded-2xl p-4 space-y-3 text-sm bg-white">
          <p className="text-gray-700">
            For <strong>{preview.recipient}</strong>{preview.children.length ? `, about ${preview.children.join(', ')}` : ''}. Untick anything you'd rather not send.
          </p>
          <FieldChecks title="Household" fields={preview.household_fields} labels={preview.labels} chosen={household} onToggle={v => toggle(household, setHousehold, v)} />
          {preview.children.length > 0 && (
            <FieldChecks title={`About ${preview.children.join(', ')}`} fields={preview.child_fields} labels={preview.labels} chosen={childFields} onToggle={v => toggle(childFields, setChildFields, v)} />
          )}
          {preview.missing.length > 0 && <p className="text-amber-700">Your kit doesn't have: {preview.missing.join(', ')}. <a href="/kit" className="underline">Add them</a> first, or answer on the form.</p>}
          {preview.not_in_kit.length > 0 && <p className="text-gray-500">Answer on the camp's site yourself: {preview.not_in_kit.join(', ')}.</p>}
          <div className="flex items-center gap-3">
            <button onClick={share} disabled={!household.length && !childFields.length}
              className="bg-brand-600 hover:bg-brand-700 disabled:opacity-40 text-white font-semibold px-4 py-2 rounded-xl">
              Share {household.length + (preview.children.length ? childFields.length : 0)} fields with {preview.recipient}
            </button>
            <button onClick={() => setPreview(null)} className="text-gray-500">Cancel</button>
          </div>
        </div>
      )}
      {link && (
        <div className="bg-brand-50 border border-brand-100 rounded-xl p-3 text-sm space-y-1">
          <p className="text-brand-700 font-medium">Copy this link now; it's shown only once.</p>
          <div className="flex gap-2">
            <input readOnly value={link} className="w-full border border-gray-200 rounded-lg px-3 py-2 bg-white" onFocus={e => e.target.select()} />
            <button onClick={() => navigator.clipboard?.writeText(link)} className="text-brand-700 font-medium px-2">Copy</button>
          </div>
        </div>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
    </section>
  )
}

function FieldChecks({ title, fields, labels, chosen, onToggle }: {
  title: string; fields: string[]; labels: Record<string, string>; chosen: string[]; onToggle: (f: string) => void
}) {
  if (!fields.length) return null
  return (
    <fieldset>
      <legend className="font-medium text-gray-700 mb-1.5">{title}</legend>
      <div className="flex flex-wrap gap-2">
        {fields.map(f => (
          <label key={f} className={`border rounded-full px-3 py-1 cursor-pointer ${chosen.includes(f) ? 'bg-brand-50 border-brand-500 text-brand-700' : 'border-gray-200 text-gray-400 line-through'}`}>
            <input type="checkbox" className="sr-only" checked={chosen.includes(f)} onChange={() => onToggle(f)} />
            {labels[f] ?? f}
          </label>
        ))}
      </div>
    </fieldset>
  )
}

function SandboxBooking({ familyId, registrationId, onBooked }: { familyId: string; registrationId: string; onBooked: () => void }) {
  const [enabled, setEnabled] = useState(false)
  const [quote, setQuote] = useState<BookingQuote | null>(null)
  const [readTerms, setReadTerms] = useState(false)
  const [result, setResult] = useState('')
  const [error, setError] = useState('')

  useEffect(() => { bookingStatus().then(s => setEnabled(s.enabled)).catch(() => setEnabled(false)) }, [])
  if (!enabled) return null

  async function ask() {
    setError('')
    try { setQuote(await getQuote(familyId, registrationId)) } catch (e) { setError((e as Error).message) }
  }

  async function book() {
    if (!quote) return
    setError('')
    try {
      const res = await confirmBooking(familyId, quote.attempt_id, Math.round(quote.price * 100))
      setResult(`${res.status === 'waitlisted' ? 'Added to the waitlist' : 'Booked'} (sandbox ref ${res.provider_ref}). ${res.amount_due ? `$${res.amount_due} is due to the camp.` : ''}`)
      setQuote(null)
      onBooked()
    } catch (e) { setError((e as Error).message) }
  }

  return (
    <section className="space-y-3 border-2 border-dashed border-amber-300 rounded-2xl p-4">
      <p className="text-xs font-bold uppercase tracking-wide text-amber-700">Sandbox prototype · test bookings only</p>
      {!quote && !result && (
        <button onClick={ask} className="border border-gray-300 bg-white font-semibold px-4 py-2 rounded-xl text-sm">Get a quote through CampFinder</button>
      )}
      {quote && (
        <div className="space-y-3 text-sm">
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
            <dt className="text-gray-500">Seller</dt><dd>{quote.seller} (you're buying from the camp)</dd>
            <dt className="text-gray-500">For</dt><dd>{quote.child_name} · {quote.item}</dd>
            <dt className="text-gray-500">Price</dt><dd className="font-semibold">${quote.price.toLocaleString()} {quote.currency.toUpperCase()}{quote.availability === 'waitlist' ? ' (waitlist: nothing due unless a spot opens)' : ''}</dd>
            <dt className="text-gray-500">Held until</dt><dd>{fmtWhen(quote.expires_at)}</dd>
            <dt className="text-gray-500">Payment</dt><dd>Paid to the camp on its own system after booking</dd>
            <dt className="text-gray-500">We'll send</dt><dd>{quote.fields_to_send.join(', ')}</dd>
          </dl>
          {quote.missing.length > 0 && <p className="text-amber-700">Add to your info kit first: {quote.missing.join(', ')}.</p>}
          <label className="flex gap-2 items-start">
            <input type="checkbox" className="mt-1" checked={readTerms} onChange={e => setReadTerms(e.target.checked)} />
            <span>I've read the camp's <a href={quote.terms_url ?? '#'} target="_blank" rel="noopener noreferrer" className="underline">terms</a>. Waivers and medical forms are still mine to sign with the camp.</span>
          </label>
          <button onClick={book} disabled={!readTerms || quote.missing.length > 0}
            className="bg-brand-600 hover:bg-brand-700 disabled:opacity-40 text-white font-semibold px-4 py-2 rounded-xl">
            Confirm booking for ${quote.price.toLocaleString()}
          </button>
        </div>
      )}
      {result && <p className="text-sm text-green-700">{result}</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}
    </section>
  )
}
