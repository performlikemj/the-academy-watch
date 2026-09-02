import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

const SOURCE_DETAILS = {
  api: {
    label: 'API-reported',
    title: 'Stats supplied by API-Football or another verified data feed.',
    variant: 'outline',
    className: 'border-sky-200 bg-sky-50 text-sky-800',
  },
  club: {
    label: 'Club-confirmed',
    title: 'Stats entered and confirmed by an approved club representative.',
    variant: 'outline',
    className: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  },
  self: {
    label: 'Self-reported',
    title: 'Stats entered by the player or their approved profile owner.',
    variant: 'secondary',
    className: '',
  },
}

const SOURCE_ALIASES = {
  api_football: 'api',
  fixtures: 'api',
  journey: 'api',
  apss: 'api',
  shadow: 'api',
  club_confirmed: 'club',
  user: 'self',
  self_reported: 'self',
}

function provenanceSource(provenance) {
  if (!provenance) return null
  const raw = typeof provenance === 'string'
    ? provenance
    : provenance.source_category || provenance.source || provenance.primary_source
  if (!raw) return null
  const normalized = String(raw).trim().toLowerCase().replaceAll('-', '_')
  return SOURCE_DETAILS[normalized] ? normalized : SOURCE_ALIASES[normalized] || null
}

export function ProvenanceChip({ provenance, className }) {
  const source = provenanceSource(provenance)
  if (!source) return null
  const details = SOURCE_DETAILS[source]

  return (
    <Badge
      variant={details.variant}
      className={cn('cursor-help whitespace-nowrap', details.className, className)}
      title={details.title}
      aria-label={`${details.label}. ${details.title}`}
      data-provenance-source={source}
    >
      {details.label}
    </Badge>
  )
}

export default ProvenanceChip
