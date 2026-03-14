import { useRef, useCallback, useEffect, useState, useMemo } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import { forceCollide } from 'd3-force-3d'
import { nodeRadius, nodeColor, linkWidth, linkColor, linkLineDash, clubInitials, LINK_COLORS } from './constellation-utils'

// Persistent image cache (survives re-renders, shared across instances)
const logoCache = new Map() // url -> { img, status: 'loading'|'ready'|'error' }

function getLogoImage(url, onLoad) {
    if (!url) return null
    const cached = logoCache.get(url)
    if (cached) return cached.status === 'ready' ? cached.img : null

    const img = new Image()
    img.crossOrigin = 'anonymous'
    logoCache.set(url, { img, status: 'loading' })
    img.onload = () => {
        logoCache.set(url, { img, status: 'ready' })
        onLoad()
    }
    img.onerror = () => {
        logoCache.set(url, { img, status: 'error' })
    }
    img.src = url
    return null
}

export function ConstellationGraph({ data, onNodeClick, selectedNode }) {
    const graphRef = useRef()
    const containerRef = useRef()
    const hasZoomedRef = useRef(false)
    const [dimensions, setDimensions] = useState({ width: 800, height: 500 })
    const [hoveredNode, setHoveredNode] = useState(null)
    const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 })
    const [, setLogoTick] = useState(0) // bump to re-render when logos load

    // Responsive sizing
    useEffect(() => {
        const el = containerRef.current
        if (!el) return
        const observer = new ResizeObserver((entries) => {
            const { width } = entries[0].contentRect
            const height = width < 640 ? 300 : 500
            setDimensions({ width, height })
        })
        observer.observe(el)
        return () => observer.disconnect()
    }, [])

    // Build graph data — parent node floats naturally (no fixed position)
    const graphData = useMemo(() => {
        if (!data?.nodes?.length) return { nodes: [], links: [] }

        const nodes = data.nodes.map(n => ({ ...n }))
        const links = data.links.map(l => ({ ...l }))
        return { nodes, links }
    }, [data])

    // Reset zoom flag when graph data changes so zoomToFit fires once per dataset
    useEffect(() => { hasZoomedRef.current = false }, [graphData])

    // Add collision force to prevent node overlap
    useEffect(() => {
        const fg = graphRef.current
        if (!fg) return
        fg.d3Force('collision', forceCollide(node => nodeRadius(node) + 4))
    }, [graphData])

    // Trigger re-render when a logo finishes loading
    const bumpLogo = useCallback(() => setLogoTick(t => t + 1), [])

    // Custom node rendering
    const paintNode = useCallback((node, ctx) => {
        const r = nodeRadius(node)
        const color = nodeColor(node)
        const isSelected = selectedNode?.club_api_id === node.club_api_id

        // Selection ring
        if (isSelected) {
            ctx.beginPath()
            ctx.arc(node.x, node.y, r + 5, 0, 2 * Math.PI)
            ctx.strokeStyle = '#d97706' // amber-600 (selection ring)
            ctx.lineWidth = 2.5
            ctx.stroke()
        }

        // Glow for parent node
        if (node.is_parent) {
            ctx.beginPath()
            ctx.arc(node.x, node.y, r + 4, 0, 2 * Math.PI)
            ctx.fillStyle = 'rgba(234, 179, 8, 0.2)'
            ctx.fill()

            ctx.beginPath()
            ctx.arc(node.x, node.y, r + 2, 0, 2 * Math.PI)
            ctx.strokeStyle = '#eab308'
            ctx.lineWidth = 2
            ctx.stroke()
        }

        // Try drawing the club logo clipped to a circle
        const logoImg = getLogoImage(node.club_logo, bumpLogo)

        // Node circle — dark neutral when logo present, status color as fallback
        ctx.beginPath()
        ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
        ctx.fillStyle = logoImg ? '#1e293b' : color
        ctx.fill()

        if (logoImg) {
            ctx.save()
            ctx.beginPath()
            ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
            ctx.clip()

            // Draw logo centered, fitting inside the circle
            const logoSize = r * 2
            ctx.drawImage(
                logoImg,
                node.x - logoSize / 2,
                node.y - logoSize / 2,
                logoSize,
                logoSize,
            )
            ctx.restore()

            // Subtle border ring so logos don't bleed into the dark background
            ctx.beginPath()
            ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
            ctx.strokeStyle = 'rgba(148,163,184,0.5)'
            ctx.lineWidth = 0.75
            ctx.stroke()
        } else {
            // Fallback: initials text when logo isn't loaded yet
            const initials = clubInitials(node.club_name)
            ctx.textAlign = 'center'
            ctx.textBaseline = 'middle'
            ctx.fillStyle = '#ffffff'
            ctx.font = `bold ${Math.max(6, r * 0.6)}px sans-serif`
            ctx.fillText(initials, node.x, node.y)
        }

        // Player count badge
        if (!node.is_parent && node.player_count > 1) {
            const badgeR = Math.max(5, r * 0.35)
            const bx = node.x + r * 0.7
            const by = node.y - r * 0.7
            ctx.beginPath()
            ctx.arc(bx, by, badgeR, 0, 2 * Math.PI)
            ctx.fillStyle = '#1e293b'
            ctx.fill()
            ctx.fillStyle = '#ffffff'
            ctx.font = `bold ${Math.max(5, badgeR * 1.1)}px sans-serif`
            ctx.fillText(String(node.player_count), bx, by)
        }
    }, [selectedNode, bumpLogo])

    // Hover handling
    const handleNodeHover = useCallback((node) => {
        setHoveredNode(node || null)
        if (node) {
            const fg = graphRef.current
            if (fg) {
                const coords = fg.graph2ScreenCoords(node.x, node.y)
                setTooltipPos({ x: coords.x, y: coords.y })
            }
        }
    }, [])

    const handleNodeDragEnd = useCallback((node) => {
        node.fx = node.x
        node.fy = node.y
    }, [])

    const handleNodeClick = useCallback((node) => {
        if (onNodeClick) onNodeClick(node)
    }, [onNodeClick])

    if (!graphData.nodes.length) return null

    return (
        <div ref={containerRef} className="relative w-full bg-slate-900 rounded-lg overflow-hidden">
            <ForceGraph2D
                ref={graphRef}
                graphData={graphData}
                width={dimensions.width}
                height={dimensions.height}
                backgroundColor="transparent"
                nodeCanvasObject={paintNode}
                nodePointerAreaPaint={(node, color, ctx) => {
                    const r = nodeRadius(node)
                    ctx.beginPath()
                    ctx.arc(node.x, node.y, r + 4, 0, 2 * Math.PI)
                    ctx.fillStyle = color
                    ctx.fill()
                }}
                linkWidth={link => linkWidth(link)}
                linkColor={link => linkColor(link)}
                linkLineDash={link => linkLineDash(link)}
                linkLabel={link => link.players?.map(p => p.player_name).join(', ') || ''}
                linkHoverPrecision={8}
                linkCurvature={0.15}
                linkDirectionalParticles={0}
                warmupTicks={100}
                d3AlphaDecay={0.04}
                d3VelocityDecay={0.3}
                d3AlphaMin={0.001}
                cooldownTicks={150}
                onNodeHover={handleNodeHover}
                onNodeClick={handleNodeClick}
                onNodeDragEnd={handleNodeDragEnd}
                enableZoomInteraction={true}
                enablePanInteraction={true}
                enableNodeDrag={true}
                onEngineStop={() => {
                    if (!hasZoomedRef.current) {
                        hasZoomedRef.current = true
                        const fg = graphRef.current
                        if (fg) fg.zoomToFit(400, 60)
                    }
                }}
                d3Force="charge"
                d3ForceConfig={{
                    charge: { strength: -600 },
                    link: {
                        distance: link => {
                            const count = link.player_count || 1
                            return Math.max(80, 250 / Math.sqrt(count))
                        },
                    },
                }}
            />

            {/* Tooltip */}
            {hoveredNode && (
                <div
                    className="absolute pointer-events-none z-20 bg-slate-800 text-white text-xs rounded-lg px-3 py-2 shadow-lg border border-slate-700"
                    style={{
                        left: tooltipPos.x,
                        top: tooltipPos.y - 50,
                        transform: 'translateX(-50%)',
                    }}
                >
                    <div className="font-semibold">{hoveredNode.club_name}</div>
                    <div className="text-slate-300">
                        {hoveredNode.player_count} player{hoveredNode.player_count !== 1 ? 's' : ''}
                        {' · '}
                        {hoveredNode.total_appearances} apps
                    </div>
                </div>
            )}

            {/* Legend */}
            <div className="absolute bottom-2 right-2 flex gap-3 text-[10px] text-slate-400 bg-slate-900/80 rounded px-2 py-1">
                <span className="flex items-center gap-1">
                    <svg width="18" height="6"><line x1="0" y1="3" x2="18" y2="3" stroke={LINK_COLORS.loan} strokeWidth="2" strokeDasharray="4 2" /></svg>
                    Loan
                </span>
                <span className="flex items-center gap-1">
                    <svg width="18" height="6"><line x1="0" y1="3" x2="18" y2="3" stroke={LINK_COLORS.permanent} strokeWidth="2" /></svg>
                    Permanent
                </span>
                <span className="flex items-center gap-1">
                    <svg width="18" height="6"><line x1="0" y1="3" x2="18" y2="3" stroke={LINK_COLORS.return} strokeWidth="1.5" /></svg>
                    Return
                </span>
            </div>
        </div>
    )
}

export default ConstellationGraph
