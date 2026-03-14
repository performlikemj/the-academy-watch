/**
 * Shared map utilities for geographic visualizations.
 * Used by JourneyMap, NetworkMap, and other map components.
 */

/**
 * Calculate zoom center and level from an array of coordinate objects.
 * react-simple-maps coordinates are [lng, lat].
 * @param {Array<{lat: number, lng: number}>} points - Objects with lat/lng
 * @returns {{ center: [number, number], zoom: number }}
 */
export function calculateView(points) {
    const valid = points.filter(s => s.lat && s.lng)
    if (valid.length === 0) return { center: [0, 30], zoom: 1 }

    const lats = valid.map(s => s.lat)
    const lngs = valid.map(s => s.lng)

    const centerLat = (Math.min(...lats) + Math.max(...lats)) / 2
    const centerLng = (Math.min(...lngs) + Math.max(...lngs)) / 2

    const span = Math.max(
        Math.max(...lats) - Math.min(...lats),
        Math.max(...lngs) - Math.min(...lngs),
        5,
    )

    let zoom = 1
    if (span < 5) zoom = 6
    else if (span < 15) zoom = 4
    else if (span < 30) zoom = 3
    else if (span < 60) zoom = 2

    return { center: [centerLng, centerLat], zoom }
}

/**
 * Compute the midpoint of a great-circle arc with vertical offset for curved paths.
 * @param {[number, number]} from - [lng, lat]
 * @param {[number, number]} to - [lng, lat]
 * @param {number} curvature - offset factor (positive = curve upward)
 * @returns {[number, number]} - [lng, lat] of the control point
 */
export function arcControlPoint(from, to, curvature = 0.3) {
    const midLng = (from[0] + to[0]) / 2
    const midLat = (from[1] + to[1]) / 2

    // Perpendicular offset (rotate 90 degrees from the line direction)
    const dx = to[0] - from[0]
    const dy = to[1] - from[1]

    const offsetLng = midLng - dy * curvature
    const offsetLat = midLat + dx * curvature

    return [offsetLng, offsetLat]
}
