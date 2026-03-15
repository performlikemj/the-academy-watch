import { useMemo, useCallback } from 'react'
import { motion } from 'framer-motion' // eslint-disable-line no-unused-vars

const CX = 250
const CY = 250
const ORBIT_RADIUS = 180
const CENTER_R = 40
const MIN_NODE_R = 14
const MAX_NODE_R = 30
const BADGE_R = 8
const MAX_LABEL_LEN = 20

function truncate(str, max) {
    if (!str) return ''
    return str.length > max ? str.slice(0, max - 1) + '\u2026' : str
}

function computeNodeRadius(count) {
    return Math.min(MAX_NODE_R, Math.max(MIN_NODE_R, Math.sqrt(count) * 8))
}

function computeLineWidth(count) {
    return Math.max(1, Math.min(4, count * 0.8))
}

/**
 * Radial/orbital visualization of squad player origins.
 * Parent club sits at center; feeder academies orbit around it.
 */
export function RadialOriginsChart({
    origins,
    parentClub,
    onAcademyClick,
    selectedAcademyId,
}) {
    const groups = origins?.academy_breakdown

    // Sort: homegrown first, then by count descending
    const sortedGroups = useMemo(() => {
        if (!groups?.length) return []
        return [...groups].sort((a, b) => {
            if (a.is_homegrown !== b.is_homegrown) {
                return a.is_homegrown ? -1 : 1
            }
            return b.count - a.count
        })
    }, [groups])

    // Compute x, y, angle, radius for each node
    const nodePositions = useMemo(() => {
        if (!sortedGroups.length) return []
        const total = sortedGroups.length
        return sortedGroups.map((group, index) => {
            const angle = (index / total) * 2 * Math.PI - Math.PI / 2
            const x = CX + Math.cos(angle) * ORBIT_RADIUS
            const y = CY + Math.sin(angle) * ORBIT_RADIUS
            const r = computeNodeRadius(group.count)

            // Label positioning: push outward from orbit
            const labelOffset = r + 10
            const lx = CX + Math.cos(angle) * (ORBIT_RADIUS + labelOffset)
            const ly = CY + Math.sin(angle) * (ORBIT_RADIUS + labelOffset)
            // Left half: textAnchor end; right half: start
            const isLeftHalf = lx < CX
            const textAnchor = isLeftHalf ? 'end' : 'start'

            return { group, x, y, r, lx, ly, textAnchor, angle }
        })
    }, [sortedGroups])

    const handleClick = useCallback(
        (group) => {
            if (onAcademyClick) onAcademyClick(group)
        },
        [onAcademyClick],
    )

    // Animation timing
    const lineStagger = 0.05
    const lineDuration = 0.6
    const totalLineTime = nodePositions.length * lineStagger + lineDuration
    const nodeStagger = 0.05

    if (!groups?.length) {
        return (
            <div className="w-full aspect-square max-w-[360px] sm:max-w-[500px] mx-auto flex items-center justify-center">
                <p className="text-sm text-slate-500">
                    No feeder academy data available.
                </p>
            </div>
        )
    }

    return (
        <div className="w-full aspect-square max-w-[360px] sm:max-w-[500px] mx-auto">
            <svg
                viewBox="-50 0 600 500"
                className="w-full h-full"
                role="img"
                aria-label="Radial chart of squad player origins"
            >
                <defs>
                    {/* Center clip path */}
                    <clipPath id="clip-radial-center">
                        <circle cx={CX} cy={CY} r={CENTER_R} />
                    </clipPath>

                    {/* Node clip paths */}
                    {nodePositions.map(({ group, x, y, r }) => (
                        <clipPath
                            key={`clip-node-${group.academy.api_id}`}
                            id={`clip-radial-node-${group.academy.api_id}`}
                        >
                            <circle cx={x} cy={y} r={r} />
                        </clipPath>
                    ))}
                </defs>

                {/* Connection lines (rendered first, behind nodes) */}
                {nodePositions.map(({ group, x, y }, i) => {
                    const isHomegrown = group.is_homegrown
                    const strokeColor = isHomegrown
                        ? 'rgba(234,179,8,0.25)'
                        : 'rgba(148,163,184,0.2)'
                    const sw = computeLineWidth(group.count)

                    return (
                        <motion.line
                            key={`line-${group.academy.api_id}`}
                            x1={CX}
                            y1={CY}
                            x2={x}
                            y2={y}
                            stroke={strokeColor}
                            strokeWidth={sw}
                            initial={{ pathLength: 0 }}
                            animate={{ pathLength: 1 }}
                            transition={{
                                duration: lineDuration,
                                delay: i * lineStagger,
                                ease: 'easeOut',
                            }}
                        />
                    )
                })}

                {/* Center glow ring */}
                <circle
                    cx={CX}
                    cy={CY}
                    r={CENTER_R + 4}
                    fill="none"
                    stroke="rgba(234,179,8,0.3)"
                    strokeWidth={2}
                />

                {/* Center circle */}
                <circle
                    cx={CX}
                    cy={CY}
                    r={CENTER_R}
                    fill="#1e293b"
                    stroke="#eab308"
                    strokeWidth={2}
                />

                {/* Center logo */}
                {parentClub?.logo && (
                    <image
                        href={parentClub.logo}
                        x={CX - CENTER_R}
                        y={CY - CENTER_R}
                        width={CENTER_R * 2}
                        height={CENTER_R * 2}
                        clipPath="url(#clip-radial-center)"
                        preserveAspectRatio="xMidYMid slice"
                    />
                )}

                {/* Feeder academy nodes */}
                {nodePositions.map(({ group, x, y, r, lx, ly, textAnchor }, i) => {
                    const isHomegrown = group.is_homegrown
                    const isSelected = selectedAcademyId != null && group.academy.api_id === selectedAcademyId
                    const clipId = `clip-radial-node-${group.academy.api_id}`
                    const badgeX = x + r * 0.7
                    const badgeY = y - r * 0.7

                    return (
                        <motion.g
                            key={`node-${group.academy.api_id}`}
                            initial={{ opacity: 0, scale: 0 }}
                            animate={{ opacity: 1, scale: 1 }}
                            transition={{
                                duration: 0.4,
                                delay: totalLineTime + i * nodeStagger,
                                ease: 'easeOut',
                            }}
                            style={{
                                cursor: 'pointer',
                                transformOrigin: `${x}px ${y}px`,
                            }}
                            onClick={() => handleClick(group)}
                        >
                            {/* Selected amber ring */}
                            {isSelected && (
                                <circle
                                    cx={x}
                                    cy={y}
                                    r={r + 5}
                                    fill="none"
                                    stroke="#f59e0b"
                                    strokeWidth={2.5}
                                />
                            )}

                            {/* Node border */}
                            <circle
                                cx={x}
                                cy={y}
                                r={r}
                                fill="#1e293b"
                                stroke={isHomegrown ? '#eab308' : '#334155'}
                                strokeWidth={1.5}
                            />

                            {/* Node logo */}
                            {group.academy.logo && (
                                <image
                                    href={group.academy.logo}
                                    x={x - r}
                                    y={y - r}
                                    width={r * 2}
                                    height={r * 2}
                                    clipPath={`url(#${clipId})`}
                                    preserveAspectRatio="xMidYMid slice"
                                />
                            )}

                            {/* Player count badge */}
                            <circle
                                cx={badgeX}
                                cy={badgeY}
                                r={BADGE_R}
                                fill="#334155"
                            />
                            <text
                                x={badgeX}
                                y={badgeY}
                                textAnchor="middle"
                                dominantBaseline="central"
                                fill="#ffffff"
                                fontSize={9}
                                fontWeight="bold"
                            >
                                {group.count}
                            </text>

                            {/* Name label */}
                            <text
                                x={lx}
                                y={ly}
                                textAnchor={textAnchor}
                                dominantBaseline="central"
                                fill="#94a3b8"
                                fontSize={9}
                            >
                                {truncate(group.academy.name, MAX_LABEL_LEN)}
                            </text>

                            {/* Hover hit area (invisible, slightly larger) */}
                            <circle
                                cx={x}
                                cy={y}
                                r={r + 4}
                                fill="transparent"
                                className="hover:scale-110"
                                style={{ transformOrigin: `${x}px ${y}px` }}
                            />
                        </motion.g>
                    )
                })}
            </svg>
        </div>
    )
}

export default RadialOriginsChart
