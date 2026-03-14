import { createContext, useContext, useState, useMemo, useCallback } from 'react'
import { buildProgressionNodes } from '@/lib/journey-utils'

const JourneyContext = createContext(null)

export function JourneyProvider({ journeyData, children }) {
    const [selectedNodeId, setSelectedNodeId] = useState(null)

    const progressionNodes = useMemo(
        () => buildProgressionNodes(journeyData?.stops),
        [journeyData],
    )

    const selectedNode = useMemo(() => {
        if (selectedNodeId == null) return null
        return progressionNodes.find(n => n.id === selectedNodeId) ?? null
    }, [selectedNodeId, progressionNodes])

    const selectNode = useCallback((nodeOrNull) => {
        setSelectedNodeId(nodeOrNull?.id ?? null)
    }, [])

    /** True when node is chronologically at or before the selected node. */
    const isNodeVisited = useCallback((node) => {
        if (selectedNodeId == null) return true // nothing selected → everything is "now"
        return node.id <= selectedNodeId
    }, [selectedNodeId])

    const value = useMemo(() => ({
        progressionNodes,
        selectedNode,
        selectNode,
        isNodeVisited,
        journeyData,
    }), [progressionNodes, selectedNode, selectNode, isNodeVisited, journeyData])

    return (
        <JourneyContext.Provider value={value}>
            {children}
        </JourneyContext.Provider>
    )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useJourney() {
    const ctx = useContext(JourneyContext)
    if (!ctx) {
        // Return a safe fallback so components don't crash outside provider
        return {
            progressionNodes: [],
            selectedNode: null,
            selectNode: () => {},
            isNodeVisited: () => true,
            journeyData: null,
        }
    }
    return ctx
}
