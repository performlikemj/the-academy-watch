import { SponsorSidebar, SponsorStrip } from '@/components/SponsorSidebar'
import { useIsMobile } from '@/hooks/use-mobile'

/**
 * Layout wrapper for public pages that includes the sponsor sidebar.
 * On desktop: shows sidebar on the right
 * On mobile: shows horizontal sponsor strip at the bottom
 */
export function PublicLayout({ children, showSponsors = true }) {
    const isMobile = useIsMobile()

    if (!showSponsors) {
        return <>{children}</>
    }

    return (
        <div className="max-w-[1400px] mx-auto">
            <div className="flex flex-col lg:flex-row gap-6 px-4 sm:px-6 lg:px-8 py-6">
                {/* Main content */}
                <div className="flex-1 min-w-0">
                    {children}
                </div>

                {/* Sponsor sidebar - hidden on mobile */}
                <SponsorSidebar className="hidden lg:block" />
            </div>

            {/* Mobile sponsor strip - shown below content on smaller screens */}
            {isMobile && (
                <div className="px-4 pb-6">
                    <SponsorStrip />
                </div>
            )}
        </div>
    )
}

export default PublicLayout

