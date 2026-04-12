export default function TrustBadge({ status, aca }: { status: string; aca?: boolean | null }) {
  const map: Record<string, { label: string; cls: string }> = {
    team_verified: { label: '✓ Team Verified',  cls: 'bg-green-100 text-green-800' },
    camp_verified: { label: '✓ Camp Verified',  cls: 'bg-blue-100 text-blue-800' },
    claimed:       { label: '⚑ Claimed',        cls: 'bg-yellow-100 text-yellow-800' },
    unverified:    { label: 'Unverified',        cls: 'bg-gray-100 text-gray-500' },
  }
  const badge = map[status] ?? map.unverified
  return (
    <span className="inline-flex items-center gap-2 flex-wrap">
      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${badge.cls}`}>
        {badge.label}
      </span>
      {aca && (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800">
          ACA Accredited
        </span>
      )}
    </span>
  )
}
