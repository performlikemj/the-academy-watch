import React from 'react'
import { MapPin } from 'lucide-react'
import { useJourney } from '@/contexts/JourneyContext'
import { JourneyStrip } from './JourneyStrip'
import { JourneyTimeline } from './JourneyTimeline'

/**
 * Pure presentation component that renders the journey map + timeline.
 * Reads journey data from the parent JourneyProvider (in PlayerPage).
 * No data fetching — PlayerPage loads journeyData and passes it via context.
 */
export default function PlayerJourneyView() {
    const { journeyData } = useJourney()

    if (!journeyData?.stops?.length) {
        return (
            <div className="flex flex-col items-center justify-center py-12">
                <MapPin className="h-12 w-12 text-muted-foreground/70 mb-2" />
                <p className="text-muted-foreground">No journey data available</p>
            </div>
        )
    }

    return (
        <div className="space-y-4">
            <JourneyStrip />
            <JourneyTimeline journeyData={journeyData} loading={false} error={null} />
        </div>
    )
}
