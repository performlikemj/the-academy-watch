import { useState, useEffect } from 'react'
import { APIService } from '@/lib/api'
import { cn } from '@/lib/utils'

export function SponsorSidebar({ className }) {
    const [sponsors, setSponsors] = useState([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        loadSponsors()
    }, [])

    const loadSponsors = async () => {
        try {
            const data = await APIService.getSponsors()
            setSponsors(data.sponsors || [])
        } catch (error) {
            console.warn('Failed to load sponsors:', error)
            setSponsors([])
        } finally {
            setLoading(false)
        }
    }

    const handleSponsorClick = async (sponsor) => {
        // Track click in background (don't block navigation)
        APIService.trackSponsorClick(sponsor.id).catch(() => {
            // Silently ignore tracking errors
        })
    }

    // Don't render anything if there are no sponsors or still loading
    if (loading || sponsors.length === 0) {
        return null
    }

    return (
        <aside className={cn(
            'w-full lg:w-56 xl:w-64 shrink-0',
            className
        )}>
            <div className="sticky top-24">
                <div className="rounded-xl border bg-card shadow-sm overflow-hidden">
                    {/* Header */}
                    <div className="px-4 py-3 border-b bg-muted/30">
                        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                            Sponsors
                        </h3>
                    </div>

                    {/* Sponsor Cards */}
                    <div className="p-3 space-y-3">
                        {sponsors.map((sponsor) => (
                            <a
                                key={sponsor.id}
                                href={sponsor.link_url}
                                target="_blank"
                                rel="noopener noreferrer sponsored"
                                onClick={() => handleSponsorClick(sponsor)}
                                className="block group"
                                title={sponsor.description || sponsor.name}
                            >
                                <div className="rounded-lg border bg-background p-2 transition-all duration-200 hover:border-primary/50 hover:shadow-md hover:scale-[1.02]">
                                    <div className="aspect-[16/9] w-full overflow-hidden rounded-md bg-muted flex items-center justify-center">
                                        <img
                                            src={sponsor.image_url}
                                            alt={sponsor.name}
                                            className="w-full h-full object-contain transition-transform duration-200 group-hover:scale-105"
                                            loading="lazy"
                                        />
                                    </div>
                                    <p className="mt-2 text-xs text-center text-muted-foreground truncate">
                                        {sponsor.name}
                                    </p>
                                </div>
                            </a>
                        ))}
                    </div>
                </div>
            </div>
        </aside>
    )
}

/**
 * Mobile-friendly horizontal sponsor strip for smaller screens.
 * Use this in mobile layouts instead of the sidebar.
 */
export function SponsorStrip({ className }) {
    const [sponsors, setSponsors] = useState([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        loadSponsors()
    }, [])

    const loadSponsors = async () => {
        try {
            const data = await APIService.getSponsors()
            setSponsors(data.sponsors || [])
        } catch (error) {
            console.warn('Failed to load sponsors:', error)
            setSponsors([])
        } finally {
            setLoading(false)
        }
    }

    const handleSponsorClick = async (sponsor) => {
        APIService.trackSponsorClick(sponsor.id).catch(() => {})
    }

    if (loading || sponsors.length === 0) {
        return null
    }

    return (
        <div className={cn('w-full py-2', className)}>
            <div className="rounded-xl border bg-card shadow-sm overflow-hidden">
                <div className="px-4 py-2 border-b bg-muted/30">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground text-center">
                        Sponsors
                    </h3>
                </div>
                <div className="p-3 overflow-x-auto">
                    <div className="flex gap-3 min-w-min">
                        {sponsors.map((sponsor) => (
                            <a
                                key={sponsor.id}
                                href={sponsor.link_url}
                                target="_blank"
                                rel="noopener noreferrer sponsored"
                                onClick={() => handleSponsorClick(sponsor)}
                                className="block group flex-shrink-0"
                                title={sponsor.description || sponsor.name}
                            >
                                <div className="w-28 rounded-lg border bg-background p-2 transition-all duration-200 hover:border-primary/50 hover:shadow-md">
                                    <div className="aspect-[16/9] w-full overflow-hidden rounded-md bg-muted flex items-center justify-center">
                                        <img
                                            src={sponsor.image_url}
                                            alt={sponsor.name}
                                            className="w-full h-full object-contain"
                                            loading="lazy"
                                        />
                                    </div>
                                    <p className="mt-1 text-[10px] text-center text-muted-foreground truncate">
                                        {sponsor.name}
                                    </p>
                                </div>
                            </a>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    )
}

export default SponsorSidebar

