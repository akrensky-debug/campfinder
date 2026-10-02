import CampCard from '@/components/CampCard'
import TrustBadge from '@/components/TrustBadge'
import type { Comparison, FamilyEvent, Plan, UIData } from '@/lib/agent'
import { ActivityDetailCard, ActivityResults, ScheduleFitView, WeekView, weeklyLabel } from '@/components/agent/ActivityBlocks'

const SHOWN_CAMPS = 5

function fmtDate(d: string) {
  return new Date(d + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export function fmtRange(start: string, end: string) {
  return start === end ? fmtDate(start) : `${fmtDate(start)} – ${fmtDate(end)}`
}

/** Minimal formatting for agent text: paragraphs, bullet lists and **bold**. */
export function AgentText({ text }: { text: string }) {
  const blocks = text.trim().split(/\n{2,}/)
  const inline = (s: string) =>
    s.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
      part.startsWith('**') && part.endsWith('**')
        ? <strong key={i}>{part.slice(2, -2)}</strong>
        : <span key={i}>{part}</span>,
    )
  return (
    <div className="space-y-3 leading-relaxed">
      {blocks.map((block, i) => {
        const lines = block.split('\n')
        if (lines.every(l => /^\s*([-*•]|\d+\.)\s/.test(l))) {
          return (
            <ul key={i} className="list-disc pl-5 space-y-1">
              {lines.map((l, j) => <li key={j}>{inline(l.replace(/^\s*([-*•]|\d+\.)\s/, ''))}</li>)}
            </ul>
          )
        }
        return <p key={i} className="whitespace-pre-wrap">{inline(block)}</p>
      })}
    </div>
  )
}

function CampResults({ camps }: { camps: Extract<UIData, { type: 'camps' }>['camps'] }) {
  if (!camps.length) return null
  return (
    <div className="space-y-3">
      {camps.slice(0, SHOWN_CAMPS).map((c, i) => <CampCard key={c.id} camp={c} rank={i + 1} />)}
      {camps.length > SHOWN_CAMPS && (
        <p className="text-xs text-gray-400 pl-1">+{camps.length - SHOWN_CAMPS} more. Ask to see them.</p>
      )}
    </div>
  )
}

function CampDetailCard({ camp }: { camp: Extract<UIData, { type: 'camp_detail' }>['camp'] }) {
  return (
    <a href={`/camps/${camp.id}`} className="block bg-white rounded-2xl border border-gray-200 p-4 hover:border-brand-300 transition-colors">
      <div className="flex justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold text-gray-900 truncate">{camp.name}</p>
          <p className="text-sm text-gray-500">{camp.city}, {camp.state}</p>
        </div>
        <TrustBadge status={camp.verification_status} aca={camp.aca_accredited} />
      </div>
      {camp.sessions && camp.sessions.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {camp.sessions.slice(0, 8).map(s => (
            <span key={s.id} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
              {fmtRange(s.start_date, s.end_date)}{s.price ? ` · $${Math.round(s.price)}` : ''}
            </span>
          ))}
        </div>
      )}
    </a>
  )
}

function ComparisonView({ data }: { data: Comparison }) {
  const rows: Array<[string, (c: Comparison['camps'][number]) => string]> = [
    ['Location', c => `${c.city}, ${c.state}${c.distance_miles != null ? ` · ${c.distance_miles} mi` : ''}`],
    ['Ages', c => (c.age_min != null && c.age_max != null ? `${c.age_min}–${c.age_max}` : '—')],
    ['Per week', c => (c.price_per_week ? `$${Math.round(c.price_per_week)}` : '—')],
    ['Sessions', c => String(c.session_count)],
    ['Extended care', c => (c.extended_care ? 'Yes' : 'No')],
    ['Transport', c => (c.transportation ? 'Yes' : 'No')],
    ['Meals', c => (c.meals_included ? 'Yes' : 'No')],
  ]
  return (
    <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="text-left p-3 font-medium text-gray-500" />
              {data.camps.map(c => (
                <th key={c.camp_id} className="text-left p-3 font-semibold text-gray-900 min-w-[140px]">
                  <a href={`/camps/${c.camp_id}`} className="hover:text-brand-700">{c.name}</a>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(([label, get]) => (
              <tr key={label} className="border-t border-gray-100">
                <td className="p-3 text-gray-500 whitespace-nowrap">{label}</td>
                {data.camps.map(c => <td key={c.camp_id} className="p-3 text-gray-800">{get(c)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.differences.length > 0 && (
        <ul className="border-t border-gray-100 p-3 text-sm text-gray-700 list-disc pl-8 space-y-1">
          {data.differences.map((d, i) => <li key={i}>{d}</li>)}
        </ul>
      )}
    </div>
  )
}

function PlanView({ plan }: { plan: Plan }) {
  const tone = { covered: 'bg-green-50 border-green-200', gap: 'bg-amber-50 border-amber-200', overlap: 'bg-red-50 border-red-200' }
  const label = { covered: 'Covered', gap: 'Gap', overlap: 'Overlap' }
  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-4">
      <div className="flex justify-between text-sm mb-3">
        <span className="font-semibold text-gray-900">{plan.weeks_covered} of {plan.weeks_total} weeks covered</span>
        <span className="text-gray-500">≈ ${Math.round(plan.total_estimated_cost).toLocaleString()}</span>
      </div>
      <div className="space-y-1.5">
        {plan.weeks.map(w => (
          <div key={w.week_of} className={`flex items-center justify-between gap-3 border rounded-lg px-3 py-1.5 text-sm ${tone[w.status]}`}>
            <span className="text-gray-600 whitespace-nowrap">{fmtRange(w.week_of, w.week_end)}</span>
            <span className="text-gray-800 truncate text-right">
              {w.camps.length ? w.camps.map(c => c.name).join(' + ') : label[w.status]}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function CalendarList({ events, compact = false }: { events: FamilyEvent[]; compact?: boolean }) {
  if (!events.length) return <p className="text-sm text-gray-400">Nothing on the calendar yet.</p>
  return (
    <ul className="space-y-1.5">
      {events.map(e => (
        <li key={e.id} className={`flex gap-3 text-sm ${compact ? '' : 'bg-white border border-gray-200 rounded-lg px-3 py-2'}`}>
          <span className="text-gray-500 w-28 shrink-0">
            {e.rrule ? weeklyLabel(e.rrule, e.start_time) : fmtRange(e.start_date, e.end_date)}
          </span>
          <span className="text-gray-800 min-w-0">{e.title}</span>
        </li>
      ))}
    </ul>
  )
}

export function AgentBlock({ data }: { data: UIData }) {
  switch (data.type) {
    case 'camps':       return <CampResults camps={data.camps} />
    case 'camp_detail': return <CampDetailCard camp={data.camp} />
    case 'comparison':  return <ComparisonView data={data} />
    case 'plan':        return <PlanView plan={data} />
    case 'calendar':    return <CalendarList events={data.events} />
    case 'profile':     return null // reflected in the family panel
    // Year-round activities
    case 'activities':      return <ActivityResults activities={data.activities} />
    case 'activity_detail': return <ActivityDetailCard activity={data.activity} />
    case 'schedule_fit':    return <ScheduleFitView results={data.results} />
    case 'week':            return <WeekView week={data.week} />
  }
}
