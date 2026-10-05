import { STATUS_LABEL, STATUS_TONE, countdown, type PackagePreview, type RegisterChecklist, type Registration } from '@/lib/booking'

export type BookingUIData =
  | { type: 'registrations'; registrations: Registration[] }
  | { type: 'register_checklist'; checklist: RegisterChecklist }
  | { type: 'registration_package'; package: PackagePreview; registration_id: string | null }

function RegistrationList({ registrations }: { registrations: Registration[] }) {
  const shown = registrations.filter(r => r.status !== 'cancelled')
  if (!shown.length) return null
  return (
    <a href="/registrations" className="block bg-white rounded-2xl border border-gray-200 divide-y divide-gray-100 hover:border-brand-500">
      {shown.map(r => (
        <div key={r.id} className="px-4 py-2.5 text-sm flex justify-between gap-3">
          <div className="min-w-0">
            <p className="font-medium text-gray-900 truncate">{r.camp_name}{r.child_name ? ` · ${r.child_name}` : ''}</p>
            <p className="text-gray-500">{r.status === 'watching' && r.opens_at ? countdown(r.opens_at) : r.next_step}</p>
          </div>
          <span className={`self-start text-xs font-medium px-2 py-0.5 rounded-full ${STATUS_TONE[r.status]}`}>{STATUS_LABEL[r.status]}</span>
        </div>
      ))}
    </a>
  )
}

function ChecklistCard({ c }: { c: RegisterChecklist }) {
  const missing = c.form.fields.filter(f => f.required && f.ready === false).length
  const href = `/register/${c.camp_id}?${new URLSearchParams({
    ...(c.registration ? { registration: c.registration.id } : {}), ...(c.session_id ? { session: c.session_id } : {}),
  })}`
  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-4 space-y-2 text-sm">
      <p className="font-semibold text-gray-900">Register for {c.camp_name}</p>
      <p className="text-gray-600">
        {c.opens_at ? countdown(c.opens_at) : 'Opening date not known'}
        {c.kit_available ? ` · ${missing ? `${missing} answer${missing === 1 ? '' : 's'} missing from your kit` : 'your kit is ready'}` : ''}
      </p>
      <div className="flex gap-3">
        <a href={href} className="bg-brand-600 hover:bg-brand-700 text-white font-semibold px-3 py-1.5 rounded-lg">Open checklist</a>
        {c.registration_url && <a href={c.registration_url} target="_blank" rel="noopener noreferrer" className="text-brand-700 font-medium py-1.5">Camp's registration ↗</a>}
      </div>
    </div>
  )
}

function PackageCard({ p, registrationId }: { p: PackagePreview; registrationId: string | null }) {
  const fields = [...p.household_fields, ...p.child_fields].map(f => p.labels[f] ?? f)
  const q = registrationId ? `?registration=${registrationId}` : ''
  return (
    <div className="bg-white rounded-2xl border border-amber-200 p-4 space-y-2 text-sm">
      <p className="font-semibold text-gray-900">Package for {p.recipient} · not shared yet</p>
      <p className="text-gray-600">{fields.join(', ')}</p>
      {p.missing.length > 0 && <p className="text-amber-700">Missing from your kit: {p.missing.join(', ')}</p>}
      <a href={`/register/${p.camp_id}${q}`} className="inline-block bg-brand-600 hover:bg-brand-700 text-white font-semibold px-3 py-1.5 rounded-lg">
        Review and share
      </a>
    </div>
  )
}

export function BookingBlock({ data }: { data: BookingUIData }) {
  switch (data.type) {
    case 'registrations':        return <RegistrationList registrations={data.registrations} />
    case 'register_checklist':   return <ChecklistCard c={data.checklist} />
    case 'registration_package': return <PackageCard p={data.package} registrationId={data.registration_id} />
  }
}
