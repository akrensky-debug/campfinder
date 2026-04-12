import type { CampSearchResult } from '@/lib/api'
import TrustBadge from './TrustBadge'
import { Events } from '@/lib/analytics'

interface Props {
  camp: CampSearchResult
  blurred?: boolean
  rank?: number
}

export default function CampCard({ camp, blurred = false, rank }: Props) {
  const typeLabel: Record<string, string> = {
    day: 'Day Camp', sleepaway: 'Sleepaway', specialty: 'Specialty'
  }

  return (
    <a
      href={blurred ? undefined : `/camps/${camp.id}`}
      onClick={() => !blurred && Events.campDetailViewed(camp.id)}
      className={`block bg-white rounded-2xl border border-gray-200 p-5 hover:border-brand-300 hover:shadow-md transition-all relative ${blurred ? 'cursor-default select-none' : ''}`}
    >
      {blurred && (
        <div className="absolute inset-0 rounded-2xl backdrop-blur-sm bg-white/60 z-10" />
      )}

      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            {rank && <span className="text-xs font-bold text-brand-600 bg-brand-50 px-2 py-0.5 rounded-full">#{rank}</span>}
            <span className="text-xs text-gray-500 font-medium">{typeLabel[camp.camp_type] ?? camp.camp_type}</span>
          </div>
          <h3 className="font-bold text-gray-900 text-lg leading-tight truncate">{camp.name}</h3>
          <p className="text-sm text-gray-500 mt-0.5">
            {camp.city}, {camp.state}
            {camp.distance_miles != null && ` · ${camp.distance_miles} mi`}
          </p>
        </div>
        {camp.price_per_week && (
          <div className="text-right shrink-0">
            <span className="text-lg font-bold text-gray-900">${Math.round(camp.price_per_week)}</span>
            <span className="text-xs text-gray-400">/wk</span>
          </div>
        )}
      </div>

      {camp.description_short && (
        <p className="text-sm text-gray-600 mb-3 line-clamp-2">{camp.description_short}</p>
      )}

      <div className="flex flex-wrap gap-2 mb-3">
        {camp.primary_categories?.slice(0, 3).map(cat => (
          <span key={cat} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full capitalize">{cat}</span>
        ))}
        {camp.age_min != null && camp.age_max != null && (
          <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
            Ages {camp.age_min}-{camp.age_max}
          </span>
        )}
      </div>

      <div className="flex items-center justify-between">
        <TrustBadge status={camp.verification_status} aca={camp.aca_accredited} />
        <div className="flex gap-2 text-xs text-gray-400">
          {camp.transportation && <span>🚌 Transport</span>}
          {camp.extended_care && <span>⏰ Extended care</span>}
          {camp.financial_aid && <span>💰 Aid available</span>}
        </div>
      </div>

      {camp.match_reasons && camp.match_reasons.length > 0 && !blurred && (
        <div className="mt-3 pt-3 border-t border-gray-100">
          <p className="text-xs text-brand-600 font-medium">
            {camp.match_reasons.slice(0, 2).join(' · ')}
          </p>
        </div>
      )}
    </a>
  )
}
