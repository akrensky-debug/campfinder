'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useSession } from '@/lib/auth'
import { loadFamily, type Family, type FamilyEvent } from '@/lib/agent'
import {
  KIND_ICONS, KIND_LABELS, ROLE_HELP, ROLE_LABELS, assignTasks, createTasks, describeAudit, fmtDay, fmtTime,
  generateTasks, getAudit, getHousehold, inviteMember, leaveFamily, listTasks, removeMember, resetMyCalendar,
  updateMember, updateMyPrefs, updateTask, weekOf,
  type AuditEntry, type Household, type Member, type Role, type Task, type TaskKind,
} from '@/lib/household'

const input = 'border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-brand-400 bg-white'
const card = 'bg-white border border-gray-200 rounded-2xl p-4'

export default function HouseholdPage() {
  const session = useSession()
  const router = useRouter()
  const [family, setFamily] = useState<Family | null>(null)
  const [household, setHousehold] = useState<Household | null>(null)
  const [tasks, setTasks] = useState<Task[]>([])
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [error, setError] = useState('')

  const refresh = useCallback(async (f: Family) => {
    const fullPlan = f.role === 'owner' || f.role === 'co_parent'
    const [h, t, a] = await Promise.all([
      getHousehold(f.id), listTasks(f.id), fullPlan && f.signed_in ? getAudit(f.id) : Promise.resolve([]),
    ])
    setHousehold(h)
    setTasks(t)
    setAudit(a)
  }, [])

  useEffect(() => {
    if (session === undefined) return
    loadFamily()
      .then(async f => { setFamily(f); await refresh(f) })
      .catch(e => setError(e.message))
  }, [session, refresh])

  /** Run a change, refresh, and report whether it worked (errors show at the top of the page). */
  async function act(fn: () => Promise<unknown>): Promise<boolean> {
    if (!family) return false
    setError('')
    try {
      await fn()
      await refresh(family)
      return true
    } catch (e) {
      setError((e as Error).message)
      return false
    }
  }

  if (!family || !household) {
    return <div className="max-w-4xl mx-auto px-4 py-16 text-gray-400">{error || 'Loading…'}</div>
  }

  const fullPlan = household.role === 'owner' || household.role === 'co_parent'
  const assignable = household.members.filter(m => m.role !== 'viewer')
  const you = household.you

  return (
    <div className="max-w-4xl mx-auto px-4 py-10 space-y-10">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{fullPlan ? 'Household & jobs' : 'Your jobs'}</h1>
          <p className="text-gray-600 mt-1">
            {fullPlan
              ? 'Who is helping this summer, and who has each drop-off, pickup, form and payment.'
              : `You're helping as ${ROLE_LABELS[household.role].toLowerCase()}. ${household.role === 'viewer' ? 'Here is the family calendar.' : 'Here is what is yours, and the family calendar.'}`}
          </p>
        </div>
        {fullPlan && <a href="/" className="text-sm font-medium text-brand-700 hover:underline">Plan with the assistant →</a>}
      </header>

      {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}

      {!family.signed_in && (
        <div className={`${card} bg-brand-50 border-brand-200`}>
          <p className="text-sm text-gray-700">
            To invite a partner, grandparent or nanny, first <a href="/signin" className="font-medium text-brand-700 underline">save your family to an account</a>.
            You can already keep a job list here.
          </p>
        </div>
      )}

      {household.role !== 'viewer' && (
        <TaskBoard
          tasks={tasks}
          members={assignable}
          fullPlan={fullPlan}
          youId={you?.id ?? null}
          onToggle={t => act(() => updateTask(family.id, t.id, { status: t.status === 'open' ? 'done' : 'open' }))}
          onChecklist={(t, i) => act(() => updateTask(family.id, t.id, {
            checklist: t.checklist.map((c, j) => (j === i ? { ...c, done: !c.done } : c)),
          }))}
          onAssign={(ids, mid) => act(() => assignTasks(family.id, ids, mid))}
          onAdd={t => act(() => createTasks(family.id, [t]))}
        />
      )}

      <CalendarSection
        events={family.events}
        tasks={tasks}
        members={assignable}
        fullPlan={fullPlan}
        onGenerate={(eventIds, dropoff, pickup) => act(() => generateTasks(family.id, { event_ids: eventIds, dropoff_time: dropoff || null, pickup_time: pickup || null }))}
        onAssign={(ids, mid) => act(() => assignTasks(family.id, ids, mid))}
      />

      {family.signed_in && (
        <PeopleSection
          household={household}
          familyId={family.id}
          act={act}
          onLeft={() => { router.replace('/') }}
        />
      )}

      {you && <MySettings familyId={family.id} you={you} role={household.role} feed={household.my_calendar_url} act={act} />}

      {fullPlan && audit.length > 0 && (
        <section className="space-y-3">
          <h2 className="font-semibold text-gray-900">Recent activity</h2>
          <ul className="text-sm text-gray-600 space-y-1.5">
            {audit.slice(0, 20).map((e, i) => (
              <li key={i} className="flex gap-3">
                <span className="text-gray-400 shrink-0 w-28">{new Date(e.created_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</span>
                <span>{describeAudit(e)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tasks, grouped by person and week
// ---------------------------------------------------------------------------

function TaskBoard({ tasks, members, fullPlan, youId, onToggle, onChecklist, onAssign, onAdd }: {
  tasks: Task[]
  members: Member[]
  fullPlan: boolean
  youId: string | null
  onToggle: (t: Task) => void
  onChecklist: (t: Task, i: number) => void
  onAssign: (ids: string[], memberId: string | null) => void
  onAdd: (t: { kind: TaskKind; title: string; due_date: string; due_time: string | null }) => void
}) {
  const [showDone, setShowDone] = useState(false)
  const [selected, setSelected] = useState<string[]>([])
  const [adding, setAdding] = useState(false)

  const visible = tasks.filter(t => showDone || t.status === 'open')
  const groups = useMemo(() => {
    const byPerson = new Map<string, { key: string; label: string; tasks: Task[] }>()
    const order = [youId, ...members.map(m => m.id), null]
    for (const key of order) {
      const label = key === null ? 'Nobody yet' : key === youId ? 'You' : members.find(m => m.id === key)?.display_name ?? ''
      byPerson.set(String(key), { key: String(key), label, tasks: [] })
    }
    for (const t of visible) {
      const k = String(t.assignee_id)
      if (!byPerson.has(k)) byPerson.set(k, { key: k, label: t.assignee_name ?? 'Someone', tasks: [] })
      byPerson.get(k)!.tasks.push(t)
    }
    return Array.from(byPerson.values()).filter(g => g.tasks.length)
  }, [visible, members, youId])

  const toggleSel = (id: string) => setSelected(s => (s.includes(id) ? s.filter(x => x !== id) : [...s, id]))
  const openCount = tasks.filter(t => t.status === 'open').length

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold text-gray-900">
          {fullPlan ? 'Jobs' : 'Your jobs'} <span className="text-gray-400 font-normal">· {openCount} open</span>
        </h2>
        <div className="flex items-center gap-4 text-sm">
          <label className="flex items-center gap-1.5 text-gray-600">
            <input type="checkbox" checked={showDone} onChange={e => setShowDone(e.target.checked)} /> Show done
          </label>
          {fullPlan && <button onClick={() => setAdding(a => !a)} className="font-medium text-brand-700">+ Add a job</button>}
        </div>
      </div>

      {adding && <AddTask onAdd={t => { onAdd(t); setAdding(false) }} />}

      {fullPlan && selected.length > 0 && (
        <div className="sticky top-16 z-10 flex flex-wrap items-center gap-3 bg-brand-50 border border-brand-200 rounded-xl px-4 py-2 text-sm">
          <span className="font-medium text-brand-800">{selected.length} selected</span>
          <span className="text-gray-600">Give to</span>
          <AssignSelect members={members} value={null} onChange={mid => { onAssign(selected, mid); setSelected([]) }} placeholder="Choose…" />
          <button onClick={() => setSelected([])} className="text-gray-500 ml-auto">Clear</button>
        </div>
      )}

      {groups.length === 0 ? (
        <p className="text-sm text-gray-400">
          {fullPlan ? 'No jobs yet. Ask the assistant to "set up the drop-offs and pickups", or make them from a camp below.' : 'Nothing assigned to you right now.'}
        </p>
      ) : (
        <div className="space-y-6">
          {groups.map(g => (
            <div key={g.key} className="space-y-2">
              <h3 className="text-sm font-semibold text-gray-700">{g.label} <span className="text-gray-400 font-normal">· {g.tasks.filter(t => t.status === 'open').length} open</span></h3>
              {weeks(g.tasks).map(([week, ts]) => (
                <div key={week} className={card + ' !p-0 overflow-hidden'}>
                  <div className="flex items-center justify-between px-4 py-2 bg-gray-50 text-xs font-semibold uppercase tracking-wide text-gray-500">
                    <span>Week of {fmtDay(week)}</span>
                    {fullPlan && (
                      <button
                        onClick={() => setSelected(s => Array.from(new Set([...s, ...ts.filter(t => t.status === 'open').map(t => t.id)])))}
                        className="normal-case tracking-normal font-medium text-brand-700"
                      >
                        Select week
                      </button>
                    )}
                  </div>
                  <ul className="divide-y divide-gray-100">
                    {ts.map(t => (
                      <TaskRow
                        key={t.id} task={t} members={members} fullPlan={fullPlan}
                        selected={selected.includes(t.id)} onSelect={() => toggleSel(t.id)}
                        onToggle={() => onToggle(t)} onChecklist={i => onChecklist(t, i)}
                        onAssign={mid => onAssign([t.id], mid)}
                      />
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

function weeks(tasks: Task[]): Array<[string, Task[]]> {
  const m = new Map<string, Task[]>()
  for (const t of tasks) {
    const w = weekOf(t.due_date)
    m.set(w, [...(m.get(w) ?? []), t])
  }
  return Array.from(m.entries()).sort(([a], [b]) => a.localeCompare(b))
}

function TaskRow({ task: t, members, fullPlan, selected, onSelect, onToggle, onChecklist, onAssign }: {
  task: Task; members: Member[]; fullPlan: boolean; selected: boolean
  onSelect: () => void; onToggle: () => void; onChecklist: (i: number) => void; onAssign: (mid: string | null) => void
}) {
  const [open, setOpen] = useState(false)
  const done = t.status !== 'open'
  return (
    <li className="px-4 py-2.5">
      <div className="flex items-center gap-3">
        {fullPlan && !done && (
          <input type="checkbox" aria-label="Select" checked={selected} onChange={onSelect} className="accent-brand-600" />
        )}
        <button
          onClick={onToggle}
          aria-label={done ? 'Mark not done' : 'Mark done'}
          className={`w-5 h-5 rounded-full border-2 shrink-0 flex items-center justify-center text-[10px] ${done ? 'bg-green-500 border-green-500 text-white' : 'border-gray-300 hover:border-green-500'}`}
        >
          {done ? '✓' : ''}
        </button>
        <div className="flex-1 min-w-0">
          <p className={`text-sm ${done ? 'line-through text-gray-400' : 'text-gray-900'}`}>
            <span className="mr-1">{KIND_ICONS[t.kind]}</span>{t.title}
          </p>
          <p className="text-xs text-gray-500">
            {fmtDay(t.due_date)}{t.due_time ? ` · ${fmtTime(t.due_time)}` : ''} · {KIND_LABELS[t.kind]}
            {t.checklist.length > 0 && (
              <button onClick={() => setOpen(o => !o)} className="ml-2 text-brand-700">
                {t.checklist.filter(c => c.done).length}/{t.checklist.length} packed
              </button>
            )}
            {done && t.completed_by_name && <span> · done by {t.completed_by_name}</span>}
          </p>
          {t.notes && <p className="text-xs text-gray-500 mt-0.5">{t.notes}</p>}
        </div>
        {fullPlan && !done && <AssignSelect members={members} value={t.assignee_id} onChange={onAssign} />}
      </div>
      {open && (
        <ul className="mt-2 ml-8 grid sm:grid-cols-2 gap-1">
          {t.checklist.map((c, i) => (
            <li key={i}>
              <label className="flex items-center gap-2 text-sm text-gray-700">
                <input type="checkbox" checked={c.done} onChange={() => onChecklist(i)} className="accent-brand-600" />
                <span className={c.done ? 'line-through text-gray-400' : ''}>{c.item}</span>
              </label>
            </li>
          ))}
        </ul>
      )}
    </li>
  )
}

function AssignSelect({ members, value, onChange, placeholder = 'Nobody yet' }: {
  members: Member[]; value: string | null; onChange: (mid: string | null) => void; placeholder?: string
}) {
  return (
    <select
      value={value ?? ''}
      onChange={e => onChange(e.target.value || null)}
      className="text-sm border border-gray-200 rounded-lg px-2 py-1 bg-white max-w-[9rem]"
      aria-label="Assign to"
    >
      <option value="">{placeholder}</option>
      {members.map(m => (
        <option key={m.id} value={m.id}>{m.is_you ? 'Me' : m.display_name}{m.status === 'invited' ? ' (invited)' : ''}</option>
      ))}
    </select>
  )
}

function AddTask({ onAdd }: { onAdd: (t: { kind: TaskKind; title: string; due_date: string; due_time: string | null }) => void }) {
  const [title, setTitle] = useState('')
  const [kind, setKind] = useState<TaskKind>('form')
  const [day, setDay] = useState('')
  const [time, setTime] = useState('')
  return (
    <form
      onSubmit={e => { e.preventDefault(); onAdd({ kind, title, due_date: day, due_time: time || null }) }}
      className={`${card} flex flex-wrap gap-2 items-center`}
    >
      <input required className={`${input} flex-1 min-w-[12rem]`} placeholder="e.g. Pay Riverside deposit" value={title} onChange={e => setTitle(e.target.value)} />
      <select className={input} value={kind} onChange={e => setKind(e.target.value as TaskKind)}>
        {(Object.keys(KIND_LABELS) as TaskKind[]).map(k => <option key={k} value={k}>{KIND_LABELS[k]}</option>)}
      </select>
      <input required type="date" className={input} value={day} onChange={e => setDay(e.target.value)} />
      <input type="time" className={input} value={time} onChange={e => setTime(e.target.value)} />
      <button className="bg-brand-600 hover:bg-brand-700 text-white font-semibold px-4 py-2 rounded-xl text-sm">Add</button>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Calendar: make jobs from a camp, and hand them out
// ---------------------------------------------------------------------------

function CalendarSection({ events, tasks, members, fullPlan, onGenerate, onAssign }: {
  events: FamilyEvent[]; tasks: Task[]; members: Member[]; fullPlan: boolean
  onGenerate: (eventIds: string[], dropoff: string, pickup: string) => void
  onAssign: (ids: string[], memberId: string | null) => void
}) {
  const [dropoff, setDropoff] = useState('08:30')
  const [pickup, setPickup] = useState('15:00')
  if (!events.length) {
    return (
      <section className="space-y-2">
        <h2 className="font-semibold text-gray-900">Family calendar</h2>
        <p className="text-sm text-gray-400">Nothing on the calendar yet.</p>
      </section>
    )
  }
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold text-gray-900">Family calendar</h2>
        {fullPlan && (
          <div className="flex items-center gap-2 text-xs text-gray-600">
            Drop-off <input type="time" value={dropoff} onChange={e => setDropoff(e.target.value)} className={`${input} !py-1`} />
            Pickup <input type="time" value={pickup} onChange={e => setPickup(e.target.value)} className={`${input} !py-1`} />
          </div>
        )}
      </div>
      <ul className="space-y-2">
        {events.map(e => {
          const rides = tasks.filter(t => t.event_id === e.id && (t.kind === 'dropoff' || t.kind === 'pickup') && t.status === 'open')
          const holders = Array.from(new Set(tasks.filter(t => t.event_id === e.id).map(t => t.assignee_name ?? 'nobody yet')))
          return (
            <li key={e.id} className={`${card} flex flex-wrap items-center gap-3`}>
              <div className="flex-1 min-w-[12rem]">
                <p className="text-sm font-medium text-gray-900">{e.title}</p>
                <p className="text-xs text-gray-500">
                  {fmtDay(e.start_date)} – {fmtDay(e.end_date)}
                  {holders.length > 0 && fullPlan && <> · jobs: {holders.join(', ')}</>}
                </p>
              </div>
              {fullPlan && (rides.length === 0 ? (
                <button onClick={() => onGenerate([e.id], dropoff, pickup)} className="text-sm font-medium text-brand-700 hover:underline">
                  Make ride & packing jobs
                </button>
              ) : (
                <label className="flex items-center gap-2 text-sm text-gray-600">
                  All {rides.length} rides to
                  <AssignSelect members={members} value={null} placeholder="Choose…" onChange={mid => onAssign(rides.map(r => r.id), mid)} />
                </label>
              ))}
            </li>
          )
        })}
      </ul>
    </section>
  )
}

// ---------------------------------------------------------------------------
// People
// ---------------------------------------------------------------------------

function PeopleSection({ household, familyId, act, onLeft }: {
  household: Household; familyId: string; act: (fn: () => Promise<unknown>) => Promise<boolean>; onLeft: () => void
}) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<Exclude<Role, 'owner'>>('caregiver')
  const [link, setLink] = useState<{ url: string; emailed: boolean } | null>(null)
  const manage = household.can_manage

  function rename(m: Member) {
    const next = prompt(m.is_you ? 'What should your household call you?' : `Rename ${m.display_name}`, m.display_name)?.trim()
    if (next && next !== m.display_name) act(() => updateMember(familyId, m.id, { display_name: next }))
  }

  async function invite(e: React.FormEvent) {
    e.preventDefault()
    await act(async () => {
      const res = await inviteMember(familyId, { display_name: name, email, role })
      setLink({ url: res.url, emailed: res.emailed })
      setName('')
      setEmail('')
    })
  }

  async function leave() {
    if (!confirm('Leave this family? You will lose access to its plan and calendar.')) return
    if (await act(() => leaveFamily(familyId))) onLeft()
  }

  if (household.role === 'caregiver' || household.role === 'viewer') {
    return (
      <section className="space-y-2">
        <h2 className="font-semibold text-gray-900">Your access</h2>
        <p className="text-sm text-gray-600">{household.role === 'viewer' ? 'You can see the family calendar.' : 'You can see the jobs assigned to you and the family calendar.'} The family's medical and contact details stay private to the parents.</p>
        <button onClick={leave} className="text-sm text-red-600 hover:text-red-700">Leave this family</button>
      </section>
    )
  }

  return (
    <section className="space-y-4">
      <h2 className="font-semibold text-gray-900">People</h2>
      <ul className="space-y-2">
        {household.members.map(m => (
          <li key={m.id} className={`${card} flex flex-wrap items-center gap-3`}>
            <div className="flex-1 min-w-[10rem]">
              <p className="text-sm font-medium text-gray-900">
                {m.display_name}{m.is_you && <span className="text-gray-400 font-normal"> (you)</span>}
                {manage && <button onClick={() => rename(m)} className="ml-2 text-xs font-normal text-brand-700">Rename</button>}
              </p>
              <p className="text-xs text-gray-500">
                {m.email ?? ROLE_LABELS[m.role]}
                {m.status === 'invited' && <span className="ml-1 text-amber-700">· invited{m.invite_expires_at ? `, link expires ${new Date(m.invite_expires_at).toLocaleDateString()}` : ''}</span>}
              </p>
            </div>
            {manage && m.role !== 'owner' ? (
              <>
                <select
                  value={m.role}
                  onChange={e => act(() => updateMember(familyId, m.id, { role: e.target.value as Role }))}
                  className="text-sm border border-gray-200 rounded-lg px-2 py-1 bg-white"
                  aria-label={`Role for ${m.display_name}`}
                >
                  {(['co_parent', 'caregiver', 'viewer'] as const).map(r => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
                </select>
                {m.role === 'co_parent' && (
                  <label className="flex items-center gap-1.5 text-xs text-gray-600" title="Medical, emergency contacts, insurance">
                    <input
                      type="checkbox"
                      checked={m.kit_access}
                      onChange={e => {
                        if (e.target.checked && !confirm(`Let ${m.display_name} see and share the info kit (medical, insurance, contacts)?`)) return
                        act(() => updateMember(familyId, m.id, { kit_access: e.target.checked }))
                      }}
                    />
                    Info kit
                  </label>
                )}
                {m.status === 'invited' && (
                  <button onClick={() => act(async () => {
                    const res = await inviteMember(familyId, { display_name: m.display_name, email: m.email ?? '', role: m.role as Exclude<Role, 'owner'> })
                    setLink({ url: res.url, emailed: res.emailed })
                  })} className="text-xs text-brand-700">
                    Resend
                  </button>
                )}
                <button
                  onClick={() => confirm(`Remove ${m.display_name}? Their open jobs go back to "nobody yet".`) && act(() => removeMember(familyId, m.id))}
                  className="text-xs text-gray-400 hover:text-red-600"
                >
                  Remove
                </button>
              </>
            ) : (
              <span className="text-xs text-gray-500">{ROLE_LABELS[m.role]}{m.kit_access && m.role !== 'owner' ? ' · info kit' : ''}</span>
            )}
          </li>
        ))}
      </ul>

      {manage ? (
        <form onSubmit={invite} className={`${card} space-y-3`}>
          <p className="text-sm font-medium text-gray-800">Invite someone</p>
          <div className="grid sm:grid-cols-2 gap-2">
            <input required className={input} placeholder="What you call them, e.g. Grandma" value={name} onChange={e => setName(e.target.value)} />
            <input required type="email" className={input} placeholder="Their email" value={email} onChange={e => setEmail(e.target.value)} />
          </div>
          <div className="flex flex-wrap gap-2">
            {(['co_parent', 'caregiver', 'viewer'] as const).map(r => (
              <label key={r} className={`text-sm border rounded-xl px-3 py-2 cursor-pointer ${role === r ? 'bg-brand-50 border-brand-300' : 'border-gray-200'}`}>
                <input type="radio" name="role" className="sr-only" checked={role === r} onChange={() => setRole(r)} />
                <span className="font-medium text-gray-900">{ROLE_LABELS[r]}</span>
                <span className="block text-xs text-gray-500">{ROLE_HELP[r]}</span>
              </label>
            ))}
          </div>
          <button className="bg-brand-600 hover:bg-brand-700 text-white font-semibold px-4 py-2 rounded-xl text-sm">Send invite</button>
          <p className="text-xs text-gray-500">They sign in with that email to accept. The link works for 7 days. The info kit stays with you unless you turn it on for a co-parent.</p>
          {link && (
            <CopyLink
              label={link.emailed ? 'Invite emailed. You can also share this link yourself:' : "Email isn't set up yet, so send them this link yourself:"}
              url={link.url}
            />
          )}
        </form>
      ) : (
        <button onClick={leave} className="text-sm text-red-600 hover:text-red-700">Leave this family</button>
      )}
    </section>
  )
}

function CopyLink({ label, url }: { label: string; url: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="bg-brand-50 border border-brand-200 rounded-xl p-3 text-sm space-y-1">
      <p className="text-brand-700 font-medium">{label}</p>
      <div className="flex gap-2">
        <input readOnly value={url} className={`${input} flex-1`} onFocus={e => e.target.select()} />
        <button type="button" onClick={() => { navigator.clipboard?.writeText(url); setCopied(true) }} className="text-brand-700 font-medium px-2">
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
    </div>
  )
}

function MySettings({ familyId, you, role, feed, act }: {
  familyId: string; you: Member; role: Role; feed: string | null; act: (fn: () => Promise<unknown>) => Promise<boolean>
}) {
  const webcal = feed?.replace(/^https?:/, 'webcal:')
  const [copied, setCopied] = useState(false)
  return (
    <section className="space-y-3">
      <h2 className="font-semibold text-gray-900">Your reminders and calendar</h2>
      <div className={`${card} space-y-3 text-sm`}>
        {role !== 'viewer' && (
          <label className="flex flex-wrap items-center gap-2 text-gray-700">
            Email me my jobs
            <select
              value={you.reminder_pref ?? 'day_before'}
              onChange={e => act(() => updateMyPrefs(familyId, { reminder_pref: e.target.value }))}
              className="border border-gray-200 rounded-lg px-2 py-1 bg-white"
            >
              <option value="day_before">the evening before</option>
              <option value="daily">the morning of</option>
              <option value="off">never</option>
            </select>
          </label>
        )}
        {(role === 'owner' || role === 'co_parent') && (
          <label className="flex items-center gap-2 text-gray-700">
            <input type="checkbox" checked={!!you.weekly_summary} onChange={e => act(() => updateMyPrefs(familyId, { weekly_summary: e.target.checked }))} />
            Sunday summary of the week ahead: who has what, and what nobody has yet
          </label>
        )}
        {feed && webcal && (
          <div className="pt-3 border-t border-gray-100">
            <p className="text-gray-600 mb-1.5">Your own calendar: the family plan plus your jobs.</p>
            <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs font-medium">
              <a href={`https://calendar.google.com/calendar/r?cid=${encodeURIComponent(webcal)}`} target="_blank" rel="noreferrer" className="text-brand-700 hover:underline">Add to Google Calendar</a>
              <a href={webcal} className="text-brand-700 hover:underline">Apple / Outlook</a>
              <button onClick={() => { navigator.clipboard?.writeText(feed); setCopied(true) }} className="text-gray-500 hover:text-gray-800">{copied ? 'Link copied' : 'Copy private link'}</button>
              <button onClick={() => confirm('Make a new link? The old one stops working.') && act(() => resetMyCalendar(familyId))} className="text-gray-500 hover:text-gray-800">Reset link</button>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
