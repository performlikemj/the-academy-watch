import { getStatusLabel } from './constellation-utils'

const STATUS_COLORS = {
    first_team: '#059669',
    on_loan: '#d97706',
    academy: '#ea580c',
    released: '#78716c',
    sold: '#e11d48',
}

const STATUS_ORDER = ['first_team', 'on_loan', 'academy', 'released', 'sold']

function Chip({ label, count, color, isActive, onClick }) {
    return (
        <button
            type="button"
            onClick={onClick}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-sm font-medium whitespace-nowrap transition-colors ${
                isActive
                    ? 'bg-slate-700 text-white border-slate-500'
                    : 'bg-slate-800/50 text-slate-400 border-slate-700 hover:bg-slate-700/50'
            }`}
        >
            {color && (
                <span
                    className="inline-block w-2 h-2 rounded-full shrink-0"
                    style={{ backgroundColor: color }}
                />
            )}
            <span>{label}</span>
            {count != null && (
                <span className="opacity-70">({count})</span>
            )}
        </button>
    )
}

export function NetworkStatusBar({ summary, activeFilter, onFilterChange, parentTeamName }) {
    if (!summary) return null

    const total = STATUS_ORDER.reduce((sum, s) => sum + (summary[s] || 0), 0)

    const handleClick = (status) => {
        onFilterChange(activeFilter === status ? null : status)
    }

    return (
        <div
            className="flex gap-2 overflow-x-auto pb-1 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]"
        >
            <Chip
                label="All"
                count={total}
                color={null}
                isActive={activeFilter == null}
                onClick={() => onFilterChange(null)}
            />
            {STATUS_ORDER.map((status) => {
                const count = summary[status] || 0
                if (count === 0) return null
                return (
                    <Chip
                        key={status}
                        label={getStatusLabel(status, parentTeamName)}
                        count={count}
                        color={STATUS_COLORS[status]}
                        isActive={activeFilter === status}
                        onClick={() => handleClick(status)}
                    />
                )
            })}
        </div>
    )
}

export default NetworkStatusBar
