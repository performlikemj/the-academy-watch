import { GOL_MAINTENANCE_MESSAGE } from '@/lib/gol-maintenance'

export function GolMaintenance() {
  return (
    <div className="flex items-start gap-4 py-4 text-chalk">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-gold font-serif text-lg text-gold" aria-hidden="true">G</span>
      <p className="min-w-0 pt-2 text-[15px] leading-relaxed">{GOL_MAINTENANCE_MESSAGE}</p>
    </div>
  )
}
