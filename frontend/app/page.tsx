'use client'

import { useEffect, useRef, useState } from 'react'
import { track } from '@/lib/analytics'
import {
  loadFamily, resetCalendarLink, streamChat,
  type AgentEvent, type Family, type UIData,
} from '@/lib/agent'
import { AgentBlock, AgentText, CalendarList } from '@/components/agent/AgentBlocks'
import { WeekView } from '@/components/agent/ActivityBlocks'
import { getFamilyWeek, type FamilyWeek } from '@/lib/activities'

type Part =
  | { kind: 'text'; text: string }
  | { kind: 'ui'; data: UIData }

interface Message {
  role: 'user' | 'assistant'
  parts: Part[]
  status?: string   // current tool label while the turn is running
  error?: string
}

const STARTERS = [
  'Find a STEM day camp near Providence for my 8-year-old',
  'I need full-day coverage for two kids for all of July',
  'Swim lessons after 3:30 on weekdays for my 5-year-old near Providence',
  'Help me plan our whole summer',
]

export default function AgentHome() {
  const [family, setFamily] = useState<Family | null>(null)
  const [familyError, setFamilyError] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [panelOpen, setPanelOpen] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    loadFamily().then(setFamily).catch(() => setFamilyError(true))
    // Arriving from ChatGPT or another assistant: pre-fill what the parent was asking for.
    const params = new URLSearchParams(window.location.search)
    const q = params.get('q')
    if (q) setInput(q.slice(0, 1000))
    const source = params.get('utm_source')
    if (source) track('assistant_handoff', { source, campaign: params.get('utm_campaign'), prefilled: !!q })
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages])

  function updateLast(fn: (m: Message) => Message) {
    setMessages(prev => [...prev.slice(0, -1), fn(prev[prev.length - 1])])
  }

  function handleEvent(e: AgentEvent) {
    switch (e.type) {
      case 'conversation':
        setConversationId(e.id)
        break
      case 'text':
        updateLast(m => {
          const parts = [...m.parts]
          const last = parts[parts.length - 1]
          if (last?.kind === 'text') parts[parts.length - 1] = { kind: 'text', text: last.text + e.text }
          else parts.push({ kind: 'text', text: e.text })
          return { ...m, parts, status: undefined }
        })
        break
      case 'tool_start':
        updateLast(m => ({ ...m, status: e.label }))
        break
      case 'ui':
        if (e.data.type === 'profile') {
          const profile = e.data.profile
          setFamily(f => (f ? { ...f, profile } : f))
        } else if (e.data.type === 'calendar' || e.data.type === 'week') {
          const events = e.data.events
          setFamily(f => (f ? { ...f, events } : f))
        }
        updateLast(m => ({ ...m, parts: [...m.parts, { kind: 'ui', data: e.data }] }))
        break
      case 'error':
        updateLast(m => ({ ...m, error: e.message, status: undefined }))
        break
      case 'done':
        updateLast(m => ({ ...m, status: undefined }))
        break
    }
  }

  async function send(text: string) {
    const message = text.trim()
    if (!message || busy || !family) return
    setInput('')
    setBusy(true)
    setMessages(prev => [
      ...prev,
      { role: 'user', parts: [{ kind: 'text', text: message }] },
      { role: 'assistant', parts: [], status: 'Thinking' },
    ])
    track('agent_message_sent', { conversation_id: conversationId, first: !conversationId })
    try {
      await streamChat({ family_id: family.id, conversation_id: conversationId, message }, handleEvent)
    } catch {
      updateLast(m => ({ ...m, error: 'Connection lost. Please try again.', status: undefined }))
    } finally {
      setBusy(false)
    }
  }

  function newConversation() {
    setMessages([])
    setConversationId(null)
  }

  const empty = messages.length === 0

  return (
    <div className="max-w-6xl mx-auto px-4 flex gap-6">
      {/* Conversation */}
      <section className="flex-1 min-w-0 flex flex-col min-h-[calc(100vh-65px)]">
        <div className="flex items-center justify-between py-3 lg:hidden">
          <button onClick={() => setPanelOpen(o => !o)} className="text-sm font-medium text-brand-700">
            {panelOpen ? 'Hide your family' : 'Your family & calendar'}
          </button>
          {!empty && <button onClick={newConversation} className="text-sm text-gray-500">New chat</button>}
        </div>
        {panelOpen && family && <div className="lg:hidden mb-4"><FamilyPanel family={family} onChange={setFamily} /></div>}

        {empty ? (
          <div className="flex-1 flex flex-col justify-center py-12">
            <h1 className="text-3xl md:text-4xl font-extrabold text-gray-900 mb-3 leading-tight">
              Summer, handled.
            </h1>
            <p className="text-gray-600 text-lg mb-8 max-w-xl">
              Tell me about your kids and your summer. I'll find verified camps, work out the weeks,
              and put it all on one calendar you can share. Weekly classes and lessons too, checked
              against everyone's schedule.
            </p>
            <div className="grid sm:grid-cols-2 gap-2 max-w-2xl">
              {STARTERS.map(s => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  disabled={!family}
                  className="text-left text-sm bg-gray-50 hover:bg-brand-50 border border-gray-200 hover:border-brand-300 rounded-xl px-4 py-3 text-gray-700 transition-colors disabled:opacity-50"
                >
                  {s}
                </button>
              ))}
            </div>
            {familyError && (
              <p className="text-sm text-red-600 mt-6">We couldn't connect right now. Please refresh to try again.</p>
            )}
          </div>
        ) : (
          <div className="flex-1 py-6 space-y-6">
            {messages.map((m, i) => <MessageView key={i} message={m} />)}
            <div ref={bottomRef} />
          </div>
        )}

        <form
          onSubmit={e => { e.preventDefault(); send(input) }}
          className="sticky bottom-0 bg-white pt-2 pb-4"
        >
          <div className="flex gap-2 items-end border border-gray-200 rounded-2xl p-2 shadow-sm focus-within:border-brand-400">
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) }
              }}
              rows={1}
              placeholder={empty ? 'Ages, town, interests, weeks you need covered…' : 'Reply…'}
              className="flex-1 resize-none outline-none px-2 py-2 text-base max-h-40"
            />
            <button
              type="submit"
              disabled={busy || !input.trim() || !family}
              className="bg-brand-600 hover:bg-brand-700 text-white font-semibold px-4 py-2 rounded-xl transition-colors disabled:opacity-40"
            >
              {busy ? '…' : 'Send'}
            </button>
          </div>
        </form>
      </section>

      {/* Family panel (desktop) */}
      <aside className="hidden lg:block w-80 shrink-0 py-6">
        <div className="sticky top-20 space-y-4">
          {!empty && (
            <button onClick={newConversation} className="text-sm text-gray-500 hover:text-gray-800">+ New chat</button>
          )}
          {family && <FamilyPanel family={family} onChange={setFamily} />}
        </div>
      </aside>
    </div>
  )
}

function MessageView({ message }: { message: Message }) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="bg-brand-600 text-white rounded-2xl rounded-br-md px-4 py-2.5 max-w-[85%] whitespace-pre-wrap">
          {message.parts.map(p => (p.kind === 'text' ? p.text : '')).join('')}
        </div>
      </div>
    )
  }
  return (
    <div className="space-y-3 text-gray-800">
      {message.parts.map((p, i) =>
        p.kind === 'text' ? <AgentText key={i} text={p.text} /> : <AgentBlock key={i} data={p.data} />,
      )}
      {message.status && (
        <p className="text-sm text-gray-400 flex items-center gap-2">
          <span className="inline-block w-2 h-2 rounded-full bg-brand-500 animate-pulse" />
          {message.status}…
        </p>
      )}
      {message.error && <p className="text-sm text-red-600">{message.error}</p>}
    </div>
  )
}

function FamilyPanel({ family, onChange }: { family: Family; onChange: (f: Family) => void }) {
  const { profile, events } = family
  const feed = family.calendar_url
  const webcal = feed?.replace(/^https?:/, 'webcal:')
  const [copied, setCopied] = useState(false)

  async function resetLink() {
    if (!confirm('Anyone using the current calendar link will lose access. Make a new link?')) return
    onChange(await resetCalendarLink(family.id))
    setCopied(false)
  }

  return (
    <div className="space-y-4">
      <div className="bg-gray-50 rounded-2xl p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">Your family</p>
        {profile.kids?.length || profile.home_location ? (
          <div className="space-y-1.5 text-sm text-gray-700">
            {profile.home_location && <p>📍 {profile.home_location}</p>}
            {profile.kids?.map((k, i) => (
              <p key={i}>
                👧 {k.name || 'Child'}{k.age != null ? `, ${k.age}` : ''}
                {k.interests?.length ? <span className="text-gray-500"> · {k.interests.join(', ')}</span> : null}
              </p>
            ))}
            {profile.summer_start && profile.summer_end && (
              <p>☀️ {profile.summer_start} → {profile.summer_end}</p>
            )}
            {profile.weekly_budget != null && <p>💵 Up to ${profile.weekly_budget}/week</p>}
            {profile.needs?.map((n, i) => <p key={i} className="text-gray-500">• {n}</p>)}
          </div>
        ) : (
          <p className="text-sm text-gray-400">I'll remember your kids, town and summer plans as we talk.</p>
        )}
      </div>

      <ThisWeek familyId={family.id} events={events} />

      <div className="bg-gray-50 rounded-2xl p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">Family calendar</p>
        <CalendarList events={events} compact />
        {events.length > 0 && feed && webcal && (
          <div className="mt-3 pt-3 border-t border-gray-200 flex flex-wrap gap-x-3 gap-y-1 text-xs font-medium">
            <a href={`https://calendar.google.com/calendar/r?cid=${encodeURIComponent(webcal)}`} target="_blank" rel="noreferrer" className="text-brand-700 hover:underline">
              Add to Google Calendar
            </a>
            <a href={webcal} className="text-brand-700 hover:underline">Apple / Outlook</a>
            <button
              onClick={() => { navigator.clipboard?.writeText(feed); setCopied(true) }}
              className="text-gray-500 hover:text-gray-800"
            >
              {copied ? 'Link copied' : 'Copy private link'}
            </button>
            <button onClick={resetLink} className="text-gray-500 hover:text-gray-800">Reset link</button>
          </div>
        )}
      </div>

      <div className="bg-gray-50 rounded-2xl p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">Info kit</p>
        {family.signed_in ? (
          <>
            <p className="text-sm text-gray-600 mb-2">
              Allergies, emergency contacts, insurance: fill them in once, share only what each camp asks for.
            </p>
            <a href="/kit" className="text-sm font-medium text-brand-700 hover:underline">Open your info kit →</a>
          </>
        ) : (
          <>
            <p className="text-sm text-gray-600 mb-2">
              Save your family to an account to keep it safe and fill in camp forms once.
            </p>
            <a href="/signin" className="text-sm font-medium text-brand-700 hover:underline">Save to an account →</a>
          </>
        )}
      </div>
    </div>
  )
}

/** Everyone's week at a glance. Shown once something with a weekly time is on the calendar. */
function ThisWeek({ familyId, events }: { familyId: string; events: Family['events'] }) {
  const [week, setWeek] = useState<FamilyWeek | null>(null)
  const [offset, setOffset] = useState(0)
  const hasWeekly = events.some(e => e.start_time || e.rrule)

  useEffect(() => {
    if (!hasWeekly) return
    const d = new Date()
    d.setDate(d.getDate() + offset * 7)
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    getFamilyWeek(familyId, iso).then(setWeek).catch(() => setWeek(null))
  }, [familyId, events, offset, hasWeekly])

  if (!hasWeekly || !week) return null
  return (
    <div className="bg-gray-50 rounded-2xl p-4">
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
          {offset === 0 ? 'This week' : `Week of ${new Date(week.week_of + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`}
        </p>
        <div className="flex gap-2 text-sm text-gray-500">
          <button onClick={() => setOffset(o => o - 1)} aria-label="Previous week" className="hover:text-gray-800">‹</button>
          {offset !== 0 && <button onClick={() => setOffset(0)} className="text-xs hover:text-gray-800">Today</button>}
          <button onClick={() => setOffset(o => o + 1)} aria-label="Next week" className="hover:text-gray-800">›</button>
        </div>
      </div>
      <WeekView week={week} compact />
    </div>
  )
}
