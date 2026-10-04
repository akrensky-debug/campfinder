import TrustBadge from '@/components/TrustBadge'
import {
  KIND_LABEL, money,
  type ActivityCard, type ActivityOffering, type ActivityProgram, type FamilyWeek, type ScheduleFitResult,
} from '@/lib/activities'

const SHOWN = 5

const DAY_NAMES: Record<string, string> = { MO: 'Mon', TU: 'Tue', WE: 'Wed', TH: 'Thu', FR: 'Fri', SA: 'Sat', SU: 'Sun' }

function clock(t: string) {
  const [h, m] = t.split(':').map(Number)
  return `${h % 12 || 12}${m ? `:${String(m).padStart(2, '0')}` : ''}${h < 12 ? 'am' : 'pm'}`
}

/** 'FREQ=WEEKLY;BYDAY=TU,TH' + '16:40' -> 'Tue & Thu 4:40pm'. */
export function weeklyLabel(rrule: string, startTime?: string | null) {
  const codes = (rrule.match(/BYDAY=([A-Z,]+)/)?.[1] ?? '').split(',').filter(Boolean)
  const days = codes.length === 5 && !codes.includes('SA') && !codes.includes('SU')
    ? 'Weekdays'
    : codes.map(c => DAY_NAMES[c] ?? c).join(codes.length === 2 ? ' & ' : ', ')
  return [days || 'Weekly', startTime ? clock(startTime.slice(0, 5)) : ''].filter(Boolean).join(' ')
}

function fmtDay(d: string) {
  return new Date(d + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function EnrollmentChip({ o }: { o: ActivityOffering }) {
  if (o.availability === 'full') return <span className="text-xs bg-red-50 text-red-700 px-2 py-0.5 rounded-full">Full</span>
  if (o.availability === 'waitlist') return <span className="text-xs bg-amber-50 text-amber-700 px-2 py-0.5 rounded-full">Waitlist</span>
  if (o.enrollment_status === 'open')
    return <span className="text-xs bg-green-50 text-green-700 px-2 py-0.5 rounded-full">Open{o.enrollment_closes ? ` until ${fmtDay(o.enrollment_closes)}` : ''}</span>
  if (o.enrollment_status === 'upcoming' && o.enrollment_opens)
    return <span className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full">Opens {fmtDay(o.enrollment_opens)}</span>
  if (o.enrollment_status === 'closed') return <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">Registration closed</span>
  return null
}

function OfferingRow({ o }: { o: ActivityOffering }) {
  const label = [o.skill_level, o.term_name].filter(Boolean).join(' · ')
  const price = o.price != null ? `${money(o.price)}/term` : o.per_class != null ? `${money(o.per_class)}/class` : null
  return (
    <li className="flex items-start justify-between gap-3 py-2 border-t border-gray-100 first:border-t-0">
      <div className="min-w-0">
        <p className="text-sm font-medium text-gray-800">{o.schedule || 'Day and time not published'}</p>
        <p className="text-xs text-gray-500">
          {label}{label && (o.start_date || o.location) ? ' · ' : ''}
          {o.start_date && o.end_date ? `${fmtDay(o.start_date)} – ${fmtDay(o.end_date)}` : ''}
          {o.location ? ` · ${o.location}` : ''}
        </p>
      </div>
      <div className="text-right shrink-0 space-y-1">
        {price && <p className="text-sm font-semibold text-gray-900">{price}</p>}
        <EnrollmentChip o={o} />
      </div>
    </li>
  )
}

export function ActivityResultCard({ a, rank }: { a: ActivityCard; rank?: number }) {
  const price = a.per_class != null ? { v: money(a.per_class), u: '/class' } : a.term_price != null ? { v: money(a.term_price), u: '/term' } : null
  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-4 hover:border-brand-300 transition-colors">
      <a href={`/activities/${a.id}`} className="block">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-0.5 text-xs text-gray-500 font-medium">
              {rank && <span className="font-bold text-brand-600 bg-brand-50 px-2 py-0.5 rounded-full">#{rank}</span>}
              <span>{KIND_LABEL[a.kind] ?? a.kind}</span>
            </div>
            <h3 className="font-bold text-gray-900 leading-tight">{a.name}</h3>
            <p className="text-sm text-gray-500">
              {[a.provider_name, a.city && a.state ? `${a.city}, ${a.state}` : null, a.distance_miles != null && a.distance_miles >= 1 ? `~${Math.round(a.distance_miles)} mi` : null]
                .filter(Boolean).join(' · ')}
            </p>
          </div>
          {price && (
            <div className="text-right shrink-0">
              <span className="text-xs text-gray-400">from </span>
              <span className="text-lg font-bold text-gray-900">{price.v}</span>
              <span className="text-xs text-gray-400">{price.u}</span>
            </div>
          )}
        </div>
      </a>
      <div className="flex flex-wrap items-center gap-2 mt-2">
        <TrustBadge status={a.verification_status} />
        {a.age_min != null && a.age_max != null && (
          <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">Ages {a.age_min}–{a.age_max}</span>
        )}
        {a.trial_available && <span className="text-xs bg-purple-50 text-purple-700 px-2 py-0.5 rounded-full">Trial class</span>}
      </div>
      {a.offerings.length > 0 ? (
        <ul className="mt-2">
          {a.offerings.map(o => <OfferingRow key={o.id} o={o} />)}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-gray-500">The provider hasn't published a schedule we could read. Check their site for times.</p>
      )}
      {a.offering_count > a.offerings.length && (
        <p className="text-xs text-gray-400 mt-1">+{a.offering_count - a.offerings.length} more times</p>
      )}
      {a.match_reasons.length > 0 && (
        <p className="mt-2 pt-2 border-t border-gray-100 text-xs text-brand-600 font-medium">
          {a.match_reasons.slice(0, 3).join(' · ')}
        </p>
      )}
    </div>
  )
}

export function ActivityResults({ activities }: { activities: ActivityCard[] }) {
  if (!activities.length) return null
  return (
    <div className="space-y-3">
      {activities.slice(0, SHOWN).map((a, i) => <ActivityResultCard key={a.id} a={a} rank={i + 1} />)}
      {activities.length > SHOWN && (
        <p className="text-xs text-gray-400 pl-1">+{activities.length - SHOWN} more. Ask to see them.</p>
      )}
    </div>
  )
}

export function ActivityDetailCard({ activity }: { activity: ActivityProgram }) {
  const sessions = activity.sessions ?? []
  return (
    <a href={`/activities/${activity.id}`} className="block bg-white rounded-2xl border border-gray-200 p-4 hover:border-brand-300 transition-colors">
      <div className="flex justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold text-gray-900">{activity.name}</p>
          <p className="text-sm text-gray-500">{[activity.provider.name, `${activity.location.city}, ${activity.location.state}`].filter(Boolean).join(' · ')}</p>
        </div>
        <TrustBadge status={activity.verification.status} />
      </div>
      {sessions.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {sessions.slice(0, 8).map(s => (
            <span key={s.id} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
              {s.schedule?.summary || s.name || 'Schedule TBA'}{s.skill_level ? ` · ${s.skill_level}` : ''}
            </span>
          ))}
        </div>
      )}
    </a>
  )
}

const SEVERITY = {
  clash: { label: 'Clash', cls: 'text-red-700' },
  all_day: { label: 'Busy all day', cls: 'text-red-700' },
  logistics: { label: 'Pickup overlap', cls: 'text-amber-700' },
}

export function ScheduleFitView({ results }: { results: ScheduleFitResult[] }) {
  return (
    <div className="space-y-2">
      {results.map(r => (
        <div key={r.offering_id} className={`rounded-2xl border p-4 ${r.fits === false ? 'border-red-200 bg-red-50/50' : r.fits ? 'border-green-200 bg-green-50/50' : 'border-gray-200 bg-white'}`}>
          <div className="flex justify-between gap-3">
            <p className="font-semibold text-gray-900 text-sm">{r.name}</p>
            <span className={`text-sm font-semibold shrink-0 ${r.fits === false ? 'text-red-700' : r.fits ? 'text-green-700' : 'text-gray-500'}`}>
              {r.fits === false ? 'Conflicts' : r.fits ? (r.conflicts.length ? 'Fits, with a catch' : 'Fits') : 'Can’t check'}
            </span>
          </div>
          <p className="text-xs text-gray-500">
            {r.schedule}{r.meetings_left != null ? ` · ${r.no_class_dates?.length ? '' : 'up to '}${r.meetings_left} classes left` : ''}
            {r.no_class_dates?.length ? ` · no class ${r.no_class_dates.map(fmtDay).join(', ')}` : ''}
          </p>
          {r.note && <p className="text-sm text-gray-600 mt-1">{r.note}</p>}
          {r.conflicts.length > 0 && (
            <ul className="mt-2 space-y-1">
              {r.conflicts.map((c, i) => (
                <li key={i} className="text-sm text-gray-700">
                  <span className={`font-medium ${SEVERITY[c.severity].cls}`}>{SEVERITY[c.severity].label}:</span>{' '}
                  {c.detail} ({c.date_count} {c.date_count === 1 ? 'date' : 'dates'}, from {fmtDay(c.dates[0])})
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  )
}

const KID_COLORS = [
  'bg-sky-100 text-sky-900 border-sky-200',
  'bg-rose-100 text-rose-900 border-rose-200',
  'bg-emerald-100 text-emerald-900 border-emerald-200',
  'bg-amber-100 text-amber-900 border-amber-200',
  'bg-violet-100 text-violet-900 border-violet-200',
]

/** A family's week at a glance: one column per day, entries colored by kid. */
export function WeekView({ week, compact = false }: { week: FamilyWeek; compact?: boolean }) {
  const color = (child: string | null) =>
    child && week.kids.includes(child) ? KID_COLORS[week.kids.indexOf(child) % KID_COLORS.length] : 'bg-gray-100 text-gray-800 border-gray-200'
  const today = new Date().toISOString().slice(0, 10)
  const empty = week.days.every(d => d.items.length === 0)
  return (
    <div className={compact ? '' : 'bg-white rounded-2xl border border-gray-200 p-4'}>
      {!compact && (
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <p className="font-semibold text-gray-900 text-sm">Week of {fmtDay(week.week_of)}</p>
          <div className="flex flex-wrap gap-1.5">
            {week.kids.map(k => <span key={k} className={`text-xs px-2 py-0.5 rounded-full border ${color(k)}`}>{k}</span>)}
          </div>
        </div>
      )}
      {empty ? (
        <p className="text-sm text-gray-400">Nothing scheduled this week.</p>
      ) : (
        <div className={compact ? 'space-y-2' : 'grid grid-cols-1 sm:grid-cols-7 gap-2'}>
          {week.days.map(d => (compact && d.items.length === 0 ? null : (
            <div key={d.date} className={compact ? 'flex gap-3' : 'min-w-0'}>
              <p className={`text-xs font-semibold ${compact ? 'w-10 shrink-0 pt-1' : 'mb-1'} ${d.date === today ? 'text-brand-700' : 'text-gray-500'}`}>
                {d.label}{!compact && <span className="font-normal"> {new Date(d.date + 'T00:00:00').getDate()}</span>}
              </p>
              <div className="space-y-1 flex-1 min-w-0">
                {d.items.map((it, i) => (
                  <div key={`${it.event_id}-${i}`} className={`rounded-lg border px-2 py-1 text-xs ${color(it.child_name)}`} title={it.location ?? undefined}>
                    <p className="font-semibold">{it.time_label}</p>
                    <p className="leading-snug break-words">{it.title}</p>
                  </div>
                ))}
              </div>
            </div>
          )))}
        </div>
      )}
    </div>
  )
}
