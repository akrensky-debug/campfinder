'use client'

import { useEffect, useState } from 'react'
import { useSession } from '@/lib/auth'
import { loadFamily, type Family } from '@/lib/agent'
import {
  PAY_LABEL, STATUS_LABEL, STATUS_TONE, countdown, deleteRegistration, fmtDay, fmtWhen, getReminderPrefs,
  listRegistrations, previewReminders, saveReminderPrefs, updateRegistration,
  type Registration, type RegistrationUpdate, type ReminderPreview, type ReminderPrefs,
} from '@/lib/booking'

const input = 'w-full border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-brand-500'

export default function RegistrationsPage() {
  const session = useSession()
  const [family, setFamily] = useState<Family | null>(null)
  const [regs, setRegs] = useState<Registration[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (session === undefined) return
    loadFamily()
      .then(async f => { setFamily(f); setRegs(await listRegistrations(f.id)) })
      .catch(e => setError(e.message))
  }, [session])

  const replace = (r: Registration) => setRegs(rs => (rs ?? []).map(x => (x.id === r.id ? r : x)))

  if (!family || !regs) {
    return <div className="max-w-3xl mx-auto px-4 py-16 text-gray-400">{error || 'Loading…'}</div>
  }

  const active = regs.filter(r => r.status !== 'cancelled')
  const cancelled = regs.filter(r => r.status === 'cancelled')

  return (
    <div className="max-w-3xl mx-auto px-4 py-10 space-y-10">
      <header>
        <h1 className="text-2xl font-bold text-gray-900">Registrations</h1>
        <p className="text-gray-600 mt-1">
          Camps you're watching and the ones you've signed up for. You register and pay on each camp's own
          site; record it here and your calendar and reminders keep up.
        </p>
        {session && <a href="/kit" className="inline-block mt-2 text-sm font-medium text-brand-700">Your info kit ›</a>}
      </header>

      {active.length === 0 ? (
        <div className="border border-dashed border-gray-200 rounded-2xl p-6 text-sm text-gray-500">
          Nothing tracked yet. On a camp's page, press <strong>Get ready to register</strong>, or ask the
          assistant to watch a camp for you.
        </div>
      ) : (
        <ul className="space-y-3">
          {active.map(r => (
            <RegistrationCard key={r.id} familyId={family.id} reg={r} onChange={replace}
              onRemove={() => setRegs(rs => (rs ?? []).filter(x => x.id !== r.id))} />
          ))}
        </ul>
      )}

      {cancelled.length > 0 && (
        <details className="text-sm text-gray-500">
          <summary className="cursor-pointer">{cancelled.length} cancelled</summary>
          <ul className="mt-2 space-y-1">
            {cancelled.map(r => <li key={r.id}>{r.camp_name}{r.child_name ? ` · ${r.child_name}` : ''}</li>)}
          </ul>
        </details>
      )}

      {session ? (
        <ReminderSettings familyId={family.id} />
      ) : (
        <section className="border-t border-gray-100 pt-6 text-sm text-gray-600">
          <h2 className="font-semibold text-gray-900 mb-1">Reminders</h2>
          <a href="/signin" className="text-brand-700 font-medium">Sign in</a> to get an email before registration
          opens and before payments and forms are due.
        </section>
      )}
    </div>
  )
}

function RegistrationCard({ familyId, reg, onChange, onRemove }: {
  familyId: string; reg: Registration; onChange: (r: Registration) => void; onRemove: () => void
}) {
  const [editing, setEditing] = useState(false)
  const opens = reg.status === 'watching' && reg.opens_at
  return (
    <li className="border border-gray-200 rounded-2xl p-4 space-y-3 bg-white">
      <div className="flex flex-wrap justify-between gap-3">
        <div className="min-w-0">
          <a href={`/camps/${reg.camp_id}`} className="font-semibold text-gray-900 hover:text-brand-700">{reg.camp_name}</a>
          <p className="text-sm text-gray-500">
            {[reg.child_name, reg.session_name,
              reg.start_date && reg.end_date ? `${fmtDay(reg.start_date)} – ${fmtDay(reg.end_date)}` : null]
              .filter(Boolean).join(' · ') || 'Any session'}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5 items-start">
          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${STATUS_TONE[reg.status]}`}>{STATUS_LABEL[reg.status]}</span>
          {reg.status !== 'watching' && (
            <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${reg.payment_status === 'paid' ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-600'}`}>
              {PAY_LABEL[reg.payment_status]}{reg.amount_paid ? ` · $${reg.amount_paid.toLocaleString()}` : ''}
            </span>
          )}
        </div>
      </div>

      {opens && (
        <div className="flex flex-wrap items-baseline gap-x-3 text-sm">
          <span className="font-semibold text-brand-700">{countdown(reg.opens_at!)}</span>
          <span className="text-gray-500">
            {fmtWhen(reg.opens_at!)}{reg.opens_at_source === 'family' ? ' (your date)' : ''}
          </span>
        </div>
      )}
      {!opens && <p className="text-sm text-gray-700">{reg.next_step}</p>}

      <div className="flex flex-wrap gap-3 text-sm">
        {reg.status !== 'registered' || reg.payment_status !== 'paid' ? (
          <a href={`/register/${reg.camp_id}?registration=${reg.id}`}
            className="bg-brand-600 hover:bg-brand-700 text-white font-semibold px-4 py-1.5 rounded-lg">
            {reg.status === 'watching' ? 'Register-now checklist' : 'Checklist'}
          </a>
        ) : null}
        <button onClick={() => setEditing(e => !e)} className="font-medium text-brand-700">
          {editing ? 'Close' : reg.status === 'watching' ? 'I registered' : 'Update'}
        </button>
        <button onClick={async () => {
          if (!confirm(`Stop tracking ${reg.camp_name}? Its dates come off your calendar.`)) return
          await deleteRegistration(familyId, reg.id)
          onRemove()
        }} className="text-gray-400 hover:text-red-600">Stop tracking</button>
      </div>

      {editing && <RecordForm familyId={familyId} reg={reg} onSaved={r => { onChange(r); setEditing(false) }} />}
    </li>
  )
}

function RecordForm({ familyId, reg, onSaved }: { familyId: string; reg: Registration; onSaved: (r: Registration) => void }) {
  const [form, setForm] = useState<RegistrationUpdate>({
    status: reg.status === 'watching' ? 'registered' : reg.status,
    payment_status: reg.payment_status,
    amount_paid: reg.amount_paid, paid_on: reg.paid_on, balance_due: reg.balance_due,
    payment_due_date: reg.payment_due_date, forms_due_date: reg.forms_due_date,
    confirmation_number: reg.confirmation_number,
  })
  const [error, setError] = useState('')
  const set = (k: keyof RegistrationUpdate, v: unknown) => setForm(f => ({ ...f, [k]: v === '' ? null : v }))
  const num = (v: string) => (v === '' ? null : Number(v))

  async function save(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    try { onSaved(await updateRegistration(familyId, reg.id, form)) } catch (err) { setError((err as Error).message) }
  }

  return (
    <form onSubmit={save} className="border-t border-gray-100 pt-3 grid sm:grid-cols-2 gap-3 text-sm">
      <label className="space-y-1 text-gray-600">
        <span>Status</span>
        <select className={input} value={form.status} onChange={e => set('status', e.target.value)}>
          <option value="registered">Registered</option>
          <option value="waitlisted">On the waitlist</option>
          <option value="cancelled">Cancelled</option>
          <option value="watching">Not yet</option>
        </select>
      </label>
      <label className="space-y-1 text-gray-600">
        <span>Payment</span>
        <select className={input} value={form.payment_status} onChange={e => set('payment_status', e.target.value)}>
          <option value="unpaid">Not paid</option>
          <option value="deposit">Deposit paid</option>
          <option value="paid">Paid in full</option>
          <option value="refunded">Refunded</option>
        </select>
      </label>
      <label className="space-y-1 text-gray-600">
        <span>Amount paid ($)</span>
        <input type="number" min={0} step="0.01" className={input} value={form.amount_paid ?? ''} onChange={e => set('amount_paid', num(e.target.value))} />
      </label>
      <label className="space-y-1 text-gray-600">
        <span>Paid on</span>
        <input type="date" className={input} value={form.paid_on ?? ''} onChange={e => set('paid_on', e.target.value)} />
      </label>
      {form.payment_status !== 'paid' && (
        <>
          <label className="space-y-1 text-gray-600">
            <span>Still owed ($)</span>
            <input type="number" min={0} step="0.01" className={input} value={form.balance_due ?? ''} onChange={e => set('balance_due', num(e.target.value))} />
          </label>
          <label className="space-y-1 text-gray-600">
            <span>Payment due</span>
            <input type="date" className={input} value={form.payment_due_date ?? ''} onChange={e => set('payment_due_date', e.target.value)} />
          </label>
        </>
      )}
      <label className="space-y-1 text-gray-600">
        <span>Forms due (medical, waiver)</span>
        <input type="date" className={input} value={form.forms_due_date ?? ''} onChange={e => set('forms_due_date', e.target.value)} />
      </label>
      <label className="space-y-1 text-gray-600">
        <span>Confirmation number</span>
        <input className={input} value={form.confirmation_number ?? ''} onChange={e => set('confirmation_number', e.target.value)} />
      </label>
      <div className="sm:col-span-2 flex items-center gap-3">
        <button className="bg-brand-600 hover:bg-brand-700 text-white font-semibold px-4 py-2 rounded-lg">Save</button>
        {error && <span className="text-red-600">{error}</span>}
      </div>
    </form>
  )
}

const OPEN_CHOICES: Array<[number, string]> = [[7, 'A week before'], [3, '3 days before'], [1, 'The day before'], [0, 'The morning of']]
const DEADLINE_CHOICES: Array<[number, string]> = [[7, 'A week before'], [3, '3 days before'], [1, 'The day before'], [0, 'On the day']]

function ReminderSettings({ familyId }: { familyId: string }) {
  const [prefs, setPrefs] = useState<ReminderPrefs | null>(null)
  const [today, setToday] = useState<ReminderPreview[]>([])
  const [status, setStatus] = useState('')

  useEffect(() => {
    getReminderPrefs(familyId).then(setPrefs).catch(() => setPrefs(null))
    previewReminders(familyId).then(setToday).catch(() => setToday([]))
  }, [familyId])

  if (!prefs) return null
  const toggle = (key: 'opens_days' | 'deadline_days', d: number) =>
    setPrefs(p => p && ({ ...p, [key]: p[key].includes(d) ? p[key].filter(x => x !== d) : [...p[key], d] }))

  async function save() {
    if (!prefs) return
    setStatus('Saving…')
    try {
      setPrefs(await saveReminderPrefs(familyId, prefs))
      setToday(await previewReminders(familyId))
      setStatus('Saved.')
    } catch (e) { setStatus((e as Error).message) }
  }

  return (
    <section className="border-t border-gray-100 pt-6 space-y-4">
      <div>
        <h2 className="font-semibold text-gray-900">Reminders</h2>
        <p className="text-sm text-gray-600">One email, only when something is coming up. It names the camp and the date, never anything from your info kit.</p>
      </div>
      <label className="flex items-center gap-2 text-sm text-gray-700">
        <input type="checkbox" checked={prefs.enabled} onChange={e => setPrefs({ ...prefs, enabled: e.target.checked })} />
        Email me registration reminders
      </label>
      {prefs.enabled && (
        <div className="space-y-4 text-sm">
          <label className="block space-y-1 text-gray-600 max-w-sm">
            <span>Send to</span>
            <input type="email" className={input} value={prefs.email ?? ''} onChange={e => setPrefs({ ...prefs, email: e.target.value || null })} />
          </label>
          <DayChoices label="Before registration opens" choices={OPEN_CHOICES} chosen={prefs.opens_days} onToggle={d => toggle('opens_days', d)} />
          <DayChoices label="Before payments and forms are due" choices={DEADLINE_CHOICES} chosen={prefs.deadline_days} onToggle={d => toggle('deadline_days', d)} />
        </div>
      )}
      <div className="flex items-center gap-3">
        <button onClick={save} className="bg-brand-600 hover:bg-brand-700 text-white text-sm font-semibold px-4 py-2 rounded-lg">Save reminders</button>
        {status && <span className="text-sm text-gray-500">{status}</span>}
      </div>
      <div className="text-sm">
        <p className="font-medium text-gray-700">Going out today</p>
        {today.length ? (
          <ul className="mt-1 space-y-1 text-gray-600">{today.map((t, i) => <li key={i}>✉️ {t.text}</li>)}</ul>
        ) : <p className="text-gray-400">Nothing due today.</p>}
      </div>
    </section>
  )
}

function DayChoices({ label, choices, chosen, onToggle }: {
  label: string; choices: Array<[number, string]>; chosen: number[]; onToggle: (d: number) => void
}) {
  return (
    <fieldset>
      <legend className="text-gray-700 font-medium mb-1.5">{label}</legend>
      <div className="flex flex-wrap gap-2">
        {choices.map(([d, text]) => (
          <label key={d} className={`border rounded-full px-3 py-1 cursor-pointer ${chosen.includes(d) ? 'bg-brand-50 border-brand-500 text-brand-700' : 'border-gray-200 text-gray-600'}`}>
            <input type="checkbox" className="sr-only" checked={chosen.includes(d)} onChange={() => onToggle(d)} />
            {text}
          </label>
        ))}
      </div>
    </fieldset>
  )
}
