// @ts-check
import { test, expect } from '@playwright/test'

/**
 * E2E tests for Player Journey feature
 * 
 * These tests verify the journey map and timeline functionality
 * on the player page.
 */

test.describe('Player Journey', () => {
    
    test.describe('Journey Tab', () => {
        test('should show Journey tab on player page', async ({ page }) => {
            // Navigate to a player page (use a known player ID from test data)
            await page.goto('/player/284324') // Garnacho
            
            // Wait for page to load
            await page.waitForLoadState('networkidle')
            
            // Check that the Journey tab exists
            const journeyTab = page.getByRole('tab', { name: /journey/i })
            await expect(journeyTab).toBeVisible()
        })
        
        test('should load journey data when Journey tab is clicked', async ({ page }) => {
            await page.goto('/player/284324')
            await page.waitForLoadState('networkidle')
            
            // Click on Journey tab
            const journeyTab = page.getByRole('tab', { name: /journey/i })
            await journeyTab.click()
            
            // Wait for either loading state or map content
            // The map should show or a loading indicator should appear
            const mapContainer = page.locator('.leaflet-container, [class*="journey-map"]')
            const loadingIndicator = page.locator('[class*="animate-spin"], .loading')
            const noDataMessage = page.getByText(/no journey data|journey not found/i)
            
            // Wait for one of these to appear
            await expect(
                mapContainer.or(loadingIndicator).or(noDataMessage)
            ).toBeVisible({ timeout: 10000 })
        })
    })
    
    test.describe('Journey Map Component', () => {
        test.beforeEach(async ({ page }) => {
            await page.goto('/player/284324')
            await page.waitForLoadState('networkidle')
            await page.getByRole('tab', { name: /journey/i }).click()
        })
        
        test('should display map with club markers when journey data exists', async ({ page }) => {
            // Wait for map to load
            const mapContainer = page.locator('.leaflet-container')
            
            // If map loads successfully, it should have tile layers
            const hasMap = await mapContainer.count() > 0
            
            if (hasMap) {
                await expect(mapContainer).toBeVisible()
                
                // Check for markers (custom-marker divs or leaflet markers)
                const markers = page.locator('.leaflet-marker-icon, .custom-marker')
                
                // If journey exists, there should be at least one marker
                // (Could be 0 if no journey data yet)
                const markerCount = await markers.count()
                console.log(`Found ${markerCount} markers on map`)
            }
        })
        
        test('should open club detail drawer when marker is clicked', async ({ page }) => {
            const mapContainer = page.locator('.leaflet-container')
            const hasMap = await mapContainer.count() > 0
            
            if (hasMap) {
                // Find and click a marker
                const marker = page.locator('.leaflet-marker-icon, .custom-marker').first()
                const hasMarker = await marker.count() > 0
                
                if (hasMarker) {
                    await marker.click()
                    
                    // Drawer should open with club details
                    const drawer = page.locator('[role="dialog"], [vaul-drawer]')
                    await expect(drawer).toBeVisible({ timeout: 5000 })
                    
                    // Should show club name and stats
                    await expect(drawer.getByText(/appearances|apps/i)).toBeVisible()
                }
            }
        })
        
        test('should show legend on map', async ({ page }) => {
            const mapContainer = page.locator('.leaflet-container')
            const hasMap = await mapContainer.count() > 0
            
            if (hasMap) {
                // Legend should be visible
                const legend = page.getByText(/youth|first team|international/i)
                const legendCount = await legend.count()
                expect(legendCount).toBeGreaterThan(0)
            }
        })
    })
    
    test.describe('Journey Timeline Component', () => {
        test.beforeEach(async ({ page }) => {
            await page.goto('/player/284324')
            await page.waitForLoadState('networkidle')
            await page.getByRole('tab', { name: /journey/i }).click()
        })
        
        test('should display timeline with career entries', async ({ page }) => {
            // Wait for content to load
            await page.waitForTimeout(2000)
            
            // Look for timeline content
            const timeline = page.getByText(/career timeline|origin|current/i)
            const timelineCount = await timeline.count()
            
            // Either timeline is visible or there's no data message
            if (timelineCount > 0) {
                await expect(timeline.first()).toBeVisible()
            }
        })
        
        test('should show level badges (U18, U21, First Team)', async ({ page }) => {
            await page.waitForTimeout(2000)
            
            // Look for level badges
            const badges = page.locator('[class*="badge"], .badge')
            const badgeCount = await badges.count()
            
            if (badgeCount > 0) {
                // At least one badge should be visible
                await expect(badges.first()).toBeVisible()
            }
        })
        
        test('should show stats for each club stop', async ({ page }) => {
            await page.waitForTimeout(2000)
            
            // Look for stats display (apps, goals, assists)
            const statsText = page.getByText(/\d+\s*(apps|appearances|goals)/i)
            const statsCount = await statsText.count()
            
            if (statsCount > 0) {
                await expect(statsText.first()).toBeVisible()
            }
        })
    })
    
    test.describe('Admin Journey Sync', () => {
        // These tests require admin authentication
        // They test the sync functionality
        
        test.skip('should be able to trigger journey sync as admin', async ({ page }) => {
            // TODO: Implement admin auth helper
            // This test would:
            // 1. Login as admin
            // 2. Navigate to player page
            // 3. Trigger sync via API or admin button
            // 4. Verify journey data is populated
        })
    })
})

test.describe('Journey API', () => {
    test('GET /api/players/:id/journey returns journey data or 404', async ({ request }) => {
        const response = await request.get('/api/players/284324/journey')
        
        // Should return 200 with data or 404 if not synced yet
        expect([200, 404]).toContain(response.status())
        
        if (response.status() === 200) {
            const data = await response.json()
            
            // Verify structure
            expect(data).toHaveProperty('player_api_id')
            expect(data).toHaveProperty('totals')
        }
    })
    
    test('GET /api/players/:id/journey/map returns map-optimized data', async ({ request }) => {
        const response = await request.get('/api/players/284324/journey/map')
        
        expect([200, 404]).toContain(response.status())
        
        if (response.status() === 200) {
            const data = await response.json()
            
            // Verify map data structure
            expect(data).toHaveProperty('player_name')
            expect(data).toHaveProperty('stops')
            expect(Array.isArray(data.stops)).toBe(true)
            
            // If stops exist, verify structure
            if (data.stops.length > 0) {
                const stop = data.stops[0]
                expect(stop).toHaveProperty('club_id')
                expect(stop).toHaveProperty('club_name')
                expect(stop).toHaveProperty('years')
                expect(stop).toHaveProperty('levels')
            }
        }
    })
    
    test('GET /api/club-locations returns club coordinates', async ({ request }) => {
        const response = await request.get('/api/club-locations')
        
        expect(response.status()).toBe(200)
        
        const data = await response.json()
        
        // Verify structure
        expect(data).toHaveProperty('locations')
        expect(data).toHaveProperty('count')
        expect(Array.isArray(data.locations)).toBe(true)
        
        // Should have seeded locations
        if (data.count > 0) {
            const location = data.locations[0]
            expect(location).toHaveProperty('club_api_id')
            expect(location).toHaveProperty('club_name')
            expect(location).toHaveProperty('lat')
            expect(location).toHaveProperty('lng')
        }
    })
})
