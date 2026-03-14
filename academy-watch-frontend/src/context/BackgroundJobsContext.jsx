import { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react'
import { APIService } from '@/lib/api'

const BLOCKING_JOB_TYPES = ['full_rebuild', 'seed_big6']
const POLL_ACTIVE = 3000
const POLL_IDLE = 30000

const BackgroundJobsContext = createContext({
    activeJobs: [],
    isBlocking: false,
    bannerJobs: [],
    dismiss: () => {},
    refresh: () => {},
})

export function useBackgroundJobs() {
    return useContext(BackgroundJobsContext)
}

export function BackgroundJobsProvider({ children }) {
    const [activeJobs, setActiveJobs] = useState([])
    const [dismissed, setDismissed] = useState(new Set())
    const intervalRef = useRef(null)

    const hasRunning = activeJobs.some(j => j.status === 'running')

    const fetchJobs = useCallback(async () => {
        try {
            const data = await APIService.adminGetActiveJobs()
            setActiveJobs(data?.jobs || [])
        } catch {
            // Silently fail - admin may not be authed yet
        }
    }, [])

    useEffect(() => {
        fetchJobs()
    }, [fetchJobs])

    useEffect(() => {
        if (intervalRef.current) clearInterval(intervalRef.current)
        const delay = hasRunning ? POLL_ACTIVE : POLL_IDLE
        intervalRef.current = setInterval(fetchJobs, delay)
        return () => clearInterval(intervalRef.current)
    }, [hasRunning, fetchJobs])

    const isBlocking = activeJobs.some(
        j => j.status === 'running' && BLOCKING_JOB_TYPES.includes(j.type)
    )

    const bannerJobs = activeJobs.filter(
        j => j.status === 'running' && !BLOCKING_JOB_TYPES.includes(j.type) && !dismissed.has(j.id)
    )

    const dismiss = useCallback((jobId) => {
        setDismissed(prev => new Set([...prev, jobId]))
    }, [])

    return (
        <BackgroundJobsContext.Provider value={{ activeJobs, isBlocking, bannerJobs, dismiss, refresh: fetchJobs }}>
            {children}
        </BackgroundJobsContext.Provider>
    )
}
