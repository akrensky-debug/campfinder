'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { signOut, useSession } from '@/lib/auth'
import { deleteFamily, loadFamily, type Family } from '@/lib/agent'
import {
  CHILD_LABELS, HOUSEHOLD_LABELS, createShare, getKit, listShares, revokeShare, saveKit,
  type Child, type Contact, type InfoKit, type ShareSummary,
} from '@/lib/kit'

const EMPTY_KIT: InfoKit = {
  household: { parents: [], emergency_contacts: [], authorized_pickups: [] },
  children: [],
}
const CONTACT_LISTS = ['parents', 'emergency_contacts', 'authorized_pickups'] as const
const HOUSEHOLD_TEXT = [
  'home_address', 'insurance_provider', 'insurance_member_id', 'insurance_group_number',
  'pediatrician_name', 'pediatrician_phone',
] as const
const LONG_CHILD = new Set(['allergies', 'medications', 'medical_conditions', 'notes'])

const input = 'w-full border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-brand-400'

export default function KitPage() {
  const session = useSession()
  const router = useRouter()
  const [family, setFamily] = useState<Family | null>(null)
  const [kit, setKit] = useState<InfoKit>(EMPTY_KIT)
  const [shares, setShares] = useState<ShareSummary[]>([])
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    if (session === null) router.replace('/signin')
    if (!session) return
    loadFamily()
      .then(async f => {
        if (!f.can_open_kit) {
          // Caregivers, viewers and co-parents without access: no form to fill in and lose.
          setError('private')
          return
        }
        setFamily(f)
        const [k, s] = await Promise.all([getKit(f.id), listShares(f.id)])
        // First visit: start a card for each kid the agent already knows about.
        if (!k.children.length && f.profile.kids?.length) {
          k.children = f.profile.kids.filter(kid => kid.name).map(kid => ({ name: kid.name as string }))
        }
        setKit(k)
        setShares(s)
      })
      .catch(e => setError(e.message))
  }, [session, router])

  async function save() {
    if (!family) return
    setStatus('Saving…')
    setError('')
    try {
      await saveKit(family.id, {
        ...kit,
        children: kit.children.filter(c => c.name.trim()),
      })
      setStatus('Saved and encrypted.')
    } catch (e) {
      setStatus('')
      setError((e as Error).message)
    }
  }

  function setHousehold(field: string, value: unknown) {
    setKit(k => ({ ...k, household: { ...k.household, [field]: value } }))
    setStatus('')
  }

  function setChild(i: number, field: keyof Child, value: string) {
    setKit(k => ({ ...k, children: k.children.map((c, j) => (j === i ? { ...c, [field]: value || null } : c)) }))
    setStatus('')
  }

  async function eraseEverything() {
    if (!family) return
    if (!confirm('Delete your family, calendar, conversations and info kit permanently? This cannot be undone.')) return
    await deleteFamily(family.id)
    await signOut()
    router.replace('/')
  }

  if (error === 'private') {
    return (
      <div className="max-w-3xl mx-auto px-4 py-16 space-y-2">
        <h1 className="text-2xl font-bold text-gray-900">Info kit</h1>
        <p className="text-gray-600">
          The info kit (medical details, emergency contacts, insurance) is private to the family's owner.
          They can give a co-parent access from the Household page.
        </p>
        <a href="/household" className="text-sm font-medium text-brand-700 hover:underline">Go to Household →</a>
      </div>
    )
  }

  if (!session || !family) {
    return <div className="max-w-3xl mx-auto px-4 py-16 text-gray-400">{error || 'Loading…'}</div>
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-10 space-y-10">
      <header>
        <h1 className="text-2xl font-bold text-gray-900">Info kit</h1>
        <p className="text-gray-600 mt-1">
          What camps ask for at registration, filled in once. It's encrypted, never shown to the
          assistant, and shared only as a package you choose.
        </p>
        <a href="/registrations" className="inline-block mt-2 text-sm font-medium text-brand-700">Registrations and reminders ›</a>
      </header>

      <section className="space-y-5">
        <h2 className="font-semibold text-gray-900">Household</h2>
        {CONTACT_LISTS.map(list => (
          <ContactList
            key={list}
            label={HOUSEHOLD_LABELS[list]}
            contacts={kit.household[list]}
            onChange={v => setHousehold(list, v)}
          />
        ))}
        <div className="grid sm:grid-cols-2 gap-3">
          {HOUSEHOLD_TEXT.map(f => (
            <label key={f} className="text-sm text-gray-600 space-y-1">
              <span>{HOUSEHOLD_LABELS[f]}</span>
              <input
                className={input}
                value={(kit.household[f] as string | null) ?? ''}
                onChange={e => setHousehold(f, e.target.value || null)}
              />
            </label>
          ))}
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">Kids</h2>
          <button
            onClick={() => setKit(k => ({ ...k, children: [...k.children, { name: '' }] }))}
            className="text-sm font-medium text-brand-700"
          >
            + Add a child
          </button>
        </div>
        {kit.children.map((c, i) => (
          <div key={i} className="border border-gray-200 rounded-2xl p-4 space-y-3">
            <div className="flex gap-3 items-end">
              <label className="flex-1 text-sm text-gray-600 space-y-1">
                <span>Name on forms</span>
                <input className={input} value={c.name} onChange={e => setChild(i, 'name', e.target.value)} />
              </label>
              <button
                onClick={() => setKit(k => ({ ...k, children: k.children.filter((_, j) => j !== i) }))}
                className="text-sm text-gray-400 hover:text-red-600 pb-2"
              >
                Remove
              </button>
            </div>
            <div className="grid sm:grid-cols-2 gap-3">
              {Object.keys(CHILD_LABELS).map(f => (
                <label key={f} className={`text-sm text-gray-600 space-y-1 ${LONG_CHILD.has(f) ? 'sm:col-span-2' : ''}`}>
                  <span>{CHILD_LABELS[f]}</span>
                  {LONG_CHILD.has(f) ? (
                    <textarea
                      rows={2}
                      className={input}
                      value={(c[f as keyof Child] as string | null) ?? ''}
                      onChange={e => setChild(i, f as keyof Child, e.target.value)}
                    />
                  ) : (
                    <input
                      type={f === 'date_of_birth' ? 'date' : 'text'}
                      className={input}
                      value={(c[f as keyof Child] as string | null) ?? ''}
                      onChange={e => setChild(i, f as keyof Child, e.target.value)}
                    />
                  )}
                </label>
              ))}
            </div>
          </div>
        ))}
      </section>

      <div className="flex items-center gap-4 sticky bottom-0 bg-white py-3 border-t border-gray-100">
        <button onClick={save} className="bg-brand-600 hover:bg-brand-700 text-white font-semibold px-5 py-2.5 rounded-xl">
          Save
        </button>
        {status && <span className="text-sm text-gray-500">{status}</span>}
        {error && <span className="text-sm text-red-600">{error}</span>}
      </div>

      <SharePanel familyId={family.id} kit={kit} shares={shares} onShares={setShares} />

      <section className="border-t border-gray-100 pt-6 space-y-2">
        <h2 className="font-semibold text-gray-900">Your data</h2>
        <p className="text-sm text-gray-600">
          Deleting removes your family profile, calendar, conversations, info kit and every share link, permanently.
        </p>
        <div className="flex gap-4 text-sm">
          <button onClick={() => signOut().then(() => router.replace('/'))} className="text-gray-600 hover:text-gray-900">
            Sign out
          </button>
          <button onClick={eraseEverything} className="text-red-600 hover:text-red-700">Delete everything</button>
        </div>
      </section>
    </div>
  )
}

function ContactList({ label, contacts, onChange }: { label: string; contacts: Contact[]; onChange: (c: Contact[]) => void }) {
  const update = (i: number, field: keyof Contact, value: string) =>
    onChange(contacts.map((c, j) => (j === i ? { ...c, [field]: value || null } : c)))
  return (
    <div className="space-y-2">
      <div className="flex justify-between text-sm">
        <span className="text-gray-700 font-medium">{label}</span>
        <button onClick={() => onChange([...contacts, { name: '' }])} className="text-brand-700 font-medium">+ Add</button>
      </div>
      {contacts.map((c, i) => (
        <div key={i} className="grid grid-cols-2 sm:grid-cols-[1fr_1fr_1fr_auto] gap-2">
          <input className={input} placeholder="Name" value={c.name} onChange={e => update(i, 'name', e.target.value)} />
          <input className={input} placeholder="Relationship" value={c.relationship ?? ''} onChange={e => update(i, 'relationship', e.target.value)} />
          <input className={input} placeholder="Phone" value={c.phone ?? ''} onChange={e => update(i, 'phone', e.target.value)} />
          <button onClick={() => onChange(contacts.filter((_, j) => j !== i))} className="text-sm text-gray-400 hover:text-red-600">
            Remove
          </button>
        </div>
      ))}
    </div>
  )
}

function SharePanel({ familyId, kit, shares, onShares }: {
  familyId: string; kit: InfoKit; shares: ShareSummary[]; onShares: (s: ShareSummary[]) => void
}) {
  const [recipient, setRecipient] = useState('')
  const [kids, setKids] = useState<string[]>([])
  const [household, setHousehold] = useState<string[]>(['parents', 'emergency_contacts', 'authorized_pickups'])
  const [childFields, setChildFields] = useState<string[]>(['date_of_birth', 'allergies', 'medications'])
  const [days, setDays] = useState(30)
  const [link, setLink] = useState('')
  const [error, setError] = useState('')

  const toggle = (list: string[], set: (v: string[]) => void, v: string) =>
    set(list.includes(v) ? list.filter(x => x !== v) : [...list, v])

  async function share(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    try {
      const res = await createShare(familyId, {
        recipient, children: kids, household_fields: household, child_fields: kids.length ? childFields : [],
        expires_in_days: days,
      })
      setLink(res.url)
      setRecipient('')
      onShares([res.share, ...shares])
    } catch (err) {
      setError((err as Error).message)
    }
  }

  async function revoke(id: string) {
    const updated = await revokeShare(familyId, id)
    onShares(shares.map(s => (s.id === id ? updated : s)))
  }

  const savedKids = kit.children.filter(c => c.name.trim())

  return (
    <section className="space-y-4">
      <h2 className="font-semibold text-gray-900">Share with a camp</h2>
      <p className="text-sm text-gray-600">
        Pick the kids and only the fields this camp asks for. They get a private link that expires; you can
        withdraw it any time and see when it was opened. Save your kit first.
      </p>
      <form onSubmit={share} className="border border-gray-200 rounded-2xl p-4 space-y-4">
        <input required className={input} placeholder="Who is it for? e.g. Riverside STEM Camp" value={recipient} onChange={e => setRecipient(e.target.value)} />
        <Checks label="Kids" options={savedKids.map(c => [c.name, c.name])} chosen={kids} onToggle={v => toggle(kids, setKids, v)} />
        <Checks label="Household" options={Object.entries(HOUSEHOLD_LABELS)} chosen={household} onToggle={v => toggle(household, setHousehold, v)} />
        {kids.length > 0 && (
          <Checks label="For each kid" options={Object.entries(CHILD_LABELS)} chosen={childFields} onToggle={v => toggle(childFields, setChildFields, v)} />
        )}
        <div className="flex flex-wrap items-center gap-3">
          <select value={days} onChange={e => setDays(Number(e.target.value))} className={`${input} w-auto`}>
            <option value={7}>Expires in 7 days</option>
            <option value={30}>Expires in 30 days</option>
            <option value={90}>Expires in 90 days</option>
          </select>
          <button className="bg-brand-600 hover:bg-brand-700 text-white font-semibold px-4 py-2 rounded-xl text-sm">
            Create private link
          </button>
          {error && <span className="text-sm text-red-600">{error}</span>}
        </div>
        {link && (
          <div className="bg-brand-50 border border-brand-200 rounded-xl p-3 text-sm space-y-1">
            <p className="text-brand-700 font-medium">Copy this link now; it's shown only once.</p>
            <div className="flex gap-2">
              <input readOnly value={link} className={`${input} bg-white`} onFocus={e => e.target.select()} />
              <button type="button" onClick={() => navigator.clipboard?.writeText(link)} className="text-brand-700 font-medium px-2">
                Copy
              </button>
            </div>
          </div>
        )}
      </form>

      {shares.length > 0 && (
        <ul className="space-y-2">
          {shares.map(s => (
            <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 border border-gray-200 rounded-xl px-4 py-3 text-sm">
              <div>
                <p className="font-medium text-gray-900">{s.recipient}</p>
                <p className="text-gray-500">
                  {s.fields_shared} of {s.fields_total} fields{s.children.length ? ` · ${s.children.join(', ')}` : ''} ·{' '}
                  {s.open_count ? `opened ${s.open_count} time${s.open_count === 1 ? '' : 's'}` : 'not opened yet'} ·{' '}
                  {s.active ? `expires ${new Date(s.expires_at).toLocaleDateString()}` : s.revoked_at ? 'withdrawn' : 'expired'}
                </p>
              </div>
              {s.active && <button onClick={() => revoke(s.id)} className="text-red-600 hover:text-red-700">Withdraw</button>}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function Checks({ label, options, chosen, onToggle }: {
  label: string; options: Array<[string, string]>; chosen: string[]; onToggle: (v: string) => void
}) {
  if (!options.length) return null
  return (
    <fieldset>
      <legend className="text-sm font-medium text-gray-700 mb-1.5">{label}</legend>
      <div className="flex flex-wrap gap-2">
        {options.map(([value, text]) => (
          <label key={value} className={`text-sm border rounded-full px-3 py-1 cursor-pointer ${chosen.includes(value) ? 'bg-brand-50 border-brand-300 text-brand-700' : 'border-gray-200 text-gray-600'}`}>
            <input type="checkbox" className="sr-only" checked={chosen.includes(value)} onChange={() => onToggle(value)} />
            {text}
          </label>
        ))}
      </div>
    </fieldset>
  )
}
