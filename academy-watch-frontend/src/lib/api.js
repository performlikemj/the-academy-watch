import {
    normalizeNewsletterIds,
    parseNewsletterId,
} from './newsletter-admin.js'

// API configuration
const API_BASE_URL = (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_API_BASE) || '/api'

export class APIService {
    static adminKey = (typeof localStorage !== 'undefined' && localStorage.getItem('academy_watch_admin_key')) || null
    static userToken = (typeof localStorage !== 'undefined' && localStorage.getItem('academy_watch_user_token')) || null
    static isAdminFlag = (typeof localStorage !== 'undefined' && localStorage.getItem('academy_watch_is_admin') === 'true') || false
    static isJournalistFlag = (typeof localStorage !== 'undefined' && localStorage.getItem('academy_watch_is_journalist') === 'true') || false
    static isCuratorFlag = (typeof localStorage !== 'undefined' && localStorage.getItem('academy_watch_is_curator') === 'true') || false
    static curatorKey = (typeof localStorage !== 'undefined' && localStorage.getItem('academy_watch_curator_key')) || null
    static displayName = (typeof localStorage !== 'undefined' && localStorage.getItem('academy_watch_display_name')) || null
    static displayNameConfirmedFlag = (typeof localStorage !== 'undefined' && localStorage.getItem('academy_watch_display_name_confirmed') === 'true') || false
    static authEventName = 'loan_auth_changed'

    static _emitAuthChanged(extra = {}) {
        if (typeof window === 'undefined' || typeof window.dispatchEvent !== 'function') return
        const detail = {
            token: this.userToken,
            isAdmin: this.isAdmin(),
            isJournalist: this.isJournalist(),
            isCurator: this.isCurator(),
            hasApiKey: !!this.adminKey,
            hasCuratorKey: !!this.curatorKey,
            displayName: this.displayName,
            displayNameConfirmed: this.displayNameConfirmed(),
            ...extra,
        }
        try {
            window.dispatchEvent(new CustomEvent(this.authEventName, { detail }))
        } catch (err) {
            console.warn('Failed to dispatch auth event', err)
        }
    }

    static displayNameConfirmed() {
        if (typeof window === 'undefined') return !!this.displayNameConfirmedFlag
        if (!this.displayNameConfirmedFlag && typeof localStorage !== 'undefined') {
            try {
                this.displayNameConfirmedFlag = localStorage.getItem('academy_watch_display_name_confirmed') === 'true'
            } catch (err) {
                console.warn('Failed to read display name confirmation flag', err)
            }
        }
        return !!this.displayNameConfirmedFlag
    }

    static setDisplayNameConfirmed(value, { silent = false } = {}) {
        this.displayNameConfirmedFlag = !!value
        try {
            if (this.displayNameConfirmedFlag) {
                localStorage.setItem('academy_watch_display_name_confirmed', 'true')
            } else {
                localStorage.removeItem('academy_watch_display_name_confirmed')
            }
        } catch (err) {
            console.warn('Failed to persist display name confirmation flag', err)
        }
        if (!silent) {
            this._emitAuthChanged({ displayNameConfirmed: this.displayNameConfirmedFlag })
        }
    }

    static setAdminKey(key) {
        const trimmed = (key || '').trim()
        this.adminKey = trimmed || null
        try {
            if (trimmed) {
                localStorage.setItem('academy_watch_admin_key', trimmed)
            } else {
                localStorage.removeItem('academy_watch_admin_key')
            }
        } catch (err) {
            console.warn('Failed to persist admin key', err)
        }
        this._emitAuthChanged()
    }

    static setUserToken(token) {
        this.userToken = token || null
        try {
            if (token) {
                localStorage.setItem('academy_watch_user_token', token)
            } else {
                localStorage.removeItem('academy_watch_user_token')
            }
        } catch (err) {
            console.warn('Failed to persist user token', err)
        }
        if (!token) {
            this.setDisplayName(null)
            this.setIsAdmin(false)
            this.setIsJournalist(false)
            this.setIsCurator(false)
        } else {
            this._emitAuthChanged()
        }
    }

    static setIsAdmin(isAdmin) {
        this.isAdminFlag = !!isAdmin
        try {
            localStorage.setItem('academy_watch_is_admin', this.isAdminFlag ? 'true' : 'false')
        } catch (err) {
            console.warn('Failed to persist admin flag', err)
        }
        this._emitAuthChanged()
    }

    static isAdmin() {
        if (this.isAdminFlag) return true
        if (typeof localStorage === 'undefined') return false
        try {
            return localStorage.getItem('academy_watch_is_admin') === 'true'
        } catch (err) {
            console.warn('Failed to read admin flag', err)
            return false
        }
    }

    static setIsJournalist(isJournalist) {
        this.isJournalistFlag = !!isJournalist
        try {
            localStorage.setItem('academy_watch_is_journalist', this.isJournalistFlag ? 'true' : 'false')
        } catch (err) {
            console.warn('Failed to persist journalist flag', err)
        }
        this._emitAuthChanged()
    }

    static isJournalist() {
        if (this.isJournalistFlag) return true
        if (typeof localStorage === 'undefined') return false
        try {
            return localStorage.getItem('academy_watch_is_journalist') === 'true'
        } catch (err) {
            console.warn('Failed to read journalist flag', err)
            return false
        }
    }

    static setIsCurator(isCurator) {
        this.isCuratorFlag = !!isCurator
        try {
            localStorage.setItem('academy_watch_is_curator', this.isCuratorFlag ? 'true' : 'false')
        } catch (err) {
            console.warn('Failed to persist curator flag', err)
        }
        this._emitAuthChanged()
    }

    static isCurator() {
        if (this.isCuratorFlag) return true
        if (typeof localStorage === 'undefined') return false
        try {
            return localStorage.getItem('academy_watch_is_curator') === 'true'
        } catch (err) {
            console.warn('Failed to read curator flag', err)
            return false
        }
    }

    static setCuratorKey(key) {
        const trimmed = (key || '').trim()
        this.curatorKey = trimmed || null
        try {
            if (trimmed) {
                localStorage.setItem('academy_watch_curator_key', trimmed)
            } else {
                localStorage.removeItem('academy_watch_curator_key')
            }
        } catch (err) {
            console.warn('Failed to persist curator key', err)
        }
        this._emitAuthChanged()
    }

    static setDisplayName(name) {
        this.displayName = name || null
        try {
            if (name) {
                localStorage.setItem('academy_watch_display_name', name)
            } else {
                localStorage.removeItem('academy_watch_display_name')
            }
        } catch (err) {
            console.warn('Failed to persist display name', err)
        }
        if (!name) {
            this.setDisplayNameConfirmed(false, { silent: true })
        }
        this._emitAuthChanged()
    }

    static clearDisplayNameCache() {
        this.displayName = null
        try {
            localStorage.removeItem('academy_watch_display_name')
        } catch (err) {
            console.warn('Failed to clear display name cache', err)
        }
        this.setDisplayNameConfirmed(false, { silent: true })
    }

    static async getProfile() {
        const res = await this.request('/auth/me')
        if (typeof res?.display_name_confirmed !== 'undefined') {
            this.setDisplayNameConfirmed(res.display_name_confirmed, { silent: true })
        }
        if (res?.display_name) {
            this.setDisplayName(res.display_name)
        }
        if (typeof res?.role !== 'undefined') {
            this.setIsAdmin(res.role === 'admin')
        }
        if (typeof res?.is_journalist !== 'undefined') {
            this.setIsJournalist(res.is_journalist)
        }
        if (typeof res?.is_curator !== 'undefined') {
            this.setIsCurator(res.is_curator)
        }
        return res
    }

    static async updateDisplayName(displayName) {
        const res = await this.request('/auth/display-name', {
            method: 'POST',
            body: JSON.stringify({ display_name: displayName })
        })
        if (res?.display_name) {
            this.setDisplayName(res.display_name)
        }
        if (typeof res?.display_name_confirmed !== 'undefined') {
            this.setDisplayNameConfirmed(res.display_name_confirmed, { silent: true })
        }
        return res
    }

    static async request(endpoint, options = {}, extra = {}) {
        try {
            const admin = extra && extra.admin
            const curator = extra && extra.curator
            const headers = {
                'Content-Type': 'application/json',
                ...options.headers,
            }
            if (admin) {
                if (!this.userToken) {
                    const err = new Error('Admin login required. Please sign in with an admin email.')
                    err.status = 401
                    throw err
                }
                if (!this.adminKey) {
                    const err = new Error('Admin API key required. Save your key under API Credentials.')
                    err.status = 401
                    throw err
                }
                headers['Authorization'] = `Bearer ${this.userToken}`
                headers['X-API-Key'] = this.adminKey
                headers['X-Admin-Key'] = this.adminKey
            } else if (curator) {
                if (!this.userToken) {
                    const err = new Error('Login required. Please sign in.')
                    err.status = 401
                    throw err
                }
                if (!this.curatorKey) {
                    const err = new Error('Curator key required. Save your key under Curator Settings.')
                    err.status = 401
                    throw err
                }
                headers['Authorization'] = `Bearer ${this.userToken}`
                headers['X-Curator-Key'] = this.curatorKey
            } else if (this.userToken) {
                headers['Authorization'] = `Bearer ${this.userToken}`
            }
            const response = await fetch(`${API_BASE_URL}${endpoint}`, { ...options, headers })


            if (!response.ok) {
                const contentType = response.headers.get('content-type') || ''
                let parsed = null
                let errorText = ''
                try {
                    if (contentType.includes('application/json')) {
                        parsed = await response.json()
                        errorText = parsed?.error || JSON.stringify(parsed)
                    } else {
                        errorText = await response.text()
                    }
                } catch {
                    try {
                        errorText = await response.text()
                    } catch {
                        errorText = ''
                    }
                }
                console.error(`❌ HTTP error response body:`, parsed || errorText)
                const err = new Error(parsed?.error || errorText || `HTTP ${response.status}`)
                err.status = response.status
                err.body = parsed || errorText
                throw err
            }

            if (response.status === 204) return null

            const data = await response.json()
            return data
        } catch (error) {
            console.error('❌ API request failed:', error)
            throw error
        }
    }

    static async getLeagues() {
        return this.request('/leagues')
    }

    static async getGameweeks(season) {
        const query = season ? `?season=${season}` : ''
        return this.request(`/gameweeks${query}`)
    }

    static async getTeams(filters = {}) {
        const params = new URLSearchParams(filters)
        return this.request(`/teams?${params}`)
    }

    static async getTeamLoans(teamId, params = {}) {
        const merged = { active_only: 'true', dedupe: 'true', ...params }
        const search = new URLSearchParams()
        for (const [key, value] of Object.entries(merged)) {
            if (value === undefined || value === null) continue
            search.append(key, String(value))
        }
        const query = search.toString()
        const suffix = query ? `?${query}` : ''
        return this.request(`/teams/${teamId}/loans${suffix}`)
    }

    static async getTeamPlayers(teamId) {
        return this.request(`/teams/${teamId}/players`)
    }

    static async adminTrackedPlayersList(params = {}) {
        const search = new URLSearchParams()
        for (const [key, value] of Object.entries(params)) {
            if (value === undefined || value === null || value === '') continue
            search.append(key, String(value))
        }
        const query = search.toString()
        const suffix = query ? `?${query}` : ''
        return this.request(`/admin/tracked-players${suffix}`, {}, { admin: true })
    }

    static async adminTrackedPlayerCreate(data) {
        return this.request('/admin/tracked-players', {
            method: 'POST',
            body: JSON.stringify(data),
        }, { admin: true })
    }

    static async adminTrackedPlayerUpdate(id, data) {
        return this.request(`/admin/tracked-players/${id}`, {
            method: 'PUT',
            body: JSON.stringify(data),
        }, { admin: true })
    }

    static async adminTrackedPlayerDelete(id) {
        return this.request(`/admin/tracked-players/${id}`, {
            method: 'DELETE',
        }, { admin: true })
    }

    static async adminSeedTeamPlayers(data) {
        return this.request('/admin/tracked-players/seed-team', {
            method: 'POST',
            body: JSON.stringify(data),
        }, { admin: true })
    }

    static async adminRefreshTrackedPlayerStatuses(data = {}) {
        return this.request('/admin/tracked-players/refresh-statuses', {
            method: 'POST',
            body: JSON.stringify(data),
        }, { admin: true })
    }

    static async getTeam(teamId) {
        return this.request(`/teams/${teamId}`)
    }

    static async getNewsletters(filters = {}) {
        const params = new URLSearchParams(filters)
        return this.request(`/newsletters?${params}`)
    }

    static async getNewsletter(id, params = {}) {
        const numericId = parseNewsletterId(id)
        if (!numericId) {
            throw new Error('newsletter id is required')
        }
        const q = new URLSearchParams(params)
        const query = q.toString()
        const url = query ? `/newsletters/${encodeURIComponent(numericId)}?${query}` : `/newsletters/${encodeURIComponent(numericId)}`
        return this.request(url)
    }

    static async refreshNewsletterFixtures(id) {
        const numericId = parseNewsletterId(id)
        if (!numericId) {
            throw new Error('newsletter id is required')
        }
        return this.request(`/newsletters/${encodeURIComponent(numericId)}/refresh-fixtures`, {
            method: 'POST',
        })
    }

    static async getPublicPlayerStats(playerId) {
        return this.request(`/players/${playerId}/stats`)
    }

    static async getPublicPlayerProfile(playerId) {
        return this.request(`/players/${playerId}/profile`)
    }

    static async getPublicPlayerSeasonStats(playerId) {
        return this.request(`/players/${playerId}/season-stats`)
    }

    static async getPlayerCommentaries(playerId) {
        return this.request(`/players/${playerId}/commentaries`)
    }

    static async getUserEmailPreferences() {
        return this.request('/user/email-preferences')
    }

    static async updateUserEmailPreferences(preference) {
        return this.request('/user/email-preferences', {
            method: 'PATCH',
            body: JSON.stringify({ email_delivery_preference: preference })
        })
    }

    static async getAllSubscriptions() {
        return this.request('/user/all-subscriptions')
    }

    static async createSubscriptions(data) {
        return this.request('/subscriptions/bulk_create', {
            method: 'POST',
            body: JSON.stringify(data),
        })
    }

    static async unsubscribeEmail(data = {}) {
        return this.request('/subscriptions/unsubscribe', {
            method: 'POST',
            body: JSON.stringify(data),
        })
    }


    static async updateMySubscriptions(data = {}) {
        return this.request('/subscriptions/me', {
            method: 'POST',
            body: JSON.stringify(data),
        })
    }

    static async getJournalists() {
        return this.request('/journalists')
    }

    static async searchPlayers(query) {
        if (!query || query.length < 2) return []
        const params = new URLSearchParams({ q: query })
        return this.request(`/players/search?${params}`)
    }

    static async searchCommentaries(query) {
        if (!query || query.length < 2) return []
        const params = new URLSearchParams({ q: query })
        return this.request(`/journalists/commentaries/search?${params}`)
    }

    static async getCommentary(commentaryId) {
        if (!commentaryId) throw new Error('commentaryId is required')
        return this.request(`/journalists/commentaries/${encodeURIComponent(commentaryId)}`)
    }

    static async getChartData(params = {}) {
        // params: player_id, chart_type, stat_keys, date_range, week_start, week_end
        const queryParams = new URLSearchParams()
        if (params.player_id) queryParams.set('player_id', params.player_id)
        if (params.chart_type) queryParams.set('chart_type', params.chart_type)
        if (params.stat_keys) queryParams.set('stat_keys', params.stat_keys)
        if (params.date_range) queryParams.set('date_range', params.date_range)
        if (params.week_start) queryParams.set('week_start', params.week_start)
        if (params.week_end) queryParams.set('week_end', params.week_end)
        return this.request(`/journalists/chart-data?${queryParams.toString()}`)
    }

    static async subscribeToJournalist(journalistId) {
        return this.request(`/journalists/${journalistId}/subscribe`, { method: 'POST' })
    }

    static async unsubscribeFromJournalist(journalistId) {
        return this.request(`/journalists/${journalistId}/unsubscribe`, { method: 'POST' })
    }

    static async getJournalistArticles(journalistId) {
        return this.request(`/journalists/${journalistId}/articles`)
    }

    static async getLoanDestinations() {
        return this.request('/writer/loan-destinations')
    }

    static async getNewsletterJournalistView(newsletterId, journalistIds = []) {
        if (!newsletterId) throw new Error('newsletterId is required')
        const params = new URLSearchParams()
        if (journalistIds && journalistIds.length > 0) {
            params.set('journalist_ids', journalistIds.join(','))
        }
        const query = params.toString()
        const url = query
            ? `/newsletters/${encodeURIComponent(newsletterId)}/journalist-view?${query}`
            : `/newsletters/${encodeURIComponent(newsletterId)}/journalist-view`
        return this.request(url)
    }

    static async getMySubscriptions() {
        return this.request('/subscriptions/me')
    }

    static async getSubscriberStats(params = {}, debugOptions = {}) {
        const query = new URLSearchParams()
        if (params.search) query.set('search', params.search)
        if (params.min_subscribers) query.set('min_subscribers', params.min_subscribers)
        if (params.sort) query.set('sort', params.sort)
        const queryString = query.toString()
        const url = `/admin/subscriber-stats${queryString ? '?' + queryString : ''}`
        const requestOptions = {}
        if (debugOptions?.requestId) {
            requestOptions.headers = {
                'X-Debug-Request-ID': debugOptions.requestId,
            }
        }
        return this.request(url, requestOptions, { admin: true })
    }

    static async toggleNewsletterStatus(teamId, newslettersActive) {
        return this.request(`/admin/teams/${teamId}/newsletter-status`, {
            method: 'PATCH',
            body: JSON.stringify({ newsletters_active: newslettersActive }),
        }, { admin: true })
    }

    static async getManageState(token) {
        return this.request(`/subscriptions/manage/${encodeURIComponent(token)}`)
    }

    static async updateManageState(token, data) {
        return this.request(`/subscriptions/manage/${encodeURIComponent(token)}`, {
            method: 'POST',
            body: JSON.stringify(data),
        })
    }

    static async tokenUnsubscribe(token) {
        return this.request(`/subscriptions/unsubscribe/${encodeURIComponent(token)}`, {
            method: 'POST',
        })
    }

    static async verifyToken(token) {
        return this.request(`/verify/${encodeURIComponent(token)}`, {
            method: 'POST',
        })
    }

    static async getStats() {
        return this.request('/stats/overview')
    }

    static async initializeData() {
        return this.request('/init-data', {
            method: 'POST',
        })
    }

    static async debugDatabase() {
        return this.request('/debug/database', {}, { admin: true })
    }

    static async generateNewsletter(data) {
        return this.request('/newsletters/generate', {
            method: 'POST',
            body: JSON.stringify(data),
        })
    }

    static async requestLoginCode(email) {
        const trimmed = (email || '').trim().toLowerCase()
        if (!trimmed) {
            const err = new Error('Email is required')
            err.status = 400
            throw err
        }
        return this.request('/auth/request-code', {
            method: 'POST',
            body: JSON.stringify({ email: trimmed })
        })
    }

    static async requestAuthCode(email) {
        return this.requestLoginCode(email)
    }

    static _recordLoginResult(payload = {}) {
        const role = payload.role || 'user'
        const token = payload.token || payload.access_token
        if (token) {
            this.setUserToken(token)
        }
        this.setIsAdmin(role === 'admin')
        const journalistFlag = payload.is_journalist ?? payload.isJournalist ?? false
        this.setIsJournalist(!!journalistFlag)
        if (typeof payload.display_name_confirmed !== 'undefined') {
            this.setDisplayNameConfirmed(payload.display_name_confirmed, { silent: true })
        }
        if (typeof payload.display_name !== 'undefined' && payload.display_name !== null) {
            this.setDisplayName(payload.display_name)
        } else if (!payload.display_name && !token) {
            this.clearDisplayNameCache()
        }
        this._emitAuthChanged({
            role,
            isJournalist: this.isJournalist(),
            displayNameConfirmed: payload.display_name_confirmed,
            expiresIn: payload.expires_in,
        })
        return payload
    }

    static async verifyLoginCode(email, code) {
        const trimmedEmail = (email || '').trim().toLowerCase()
        const trimmedCode = (code || '').trim()
        if (!trimmedEmail || !trimmedCode) {
            const err = new Error('Email and code are required')
            err.status = 400
            throw err
        }
        const res = await this.request('/auth/verify-code', {
            method: 'POST',
            body: JSON.stringify({ email: trimmedEmail, code: trimmedCode })
        })
        this._recordLoginResult(res || {})
        return res
    }

    static async verifyAuthCode(email, code) {
        return this.verifyLoginCode(email, code)
    }

    static async refreshProfile() {
        try {
            return await this.getProfile()
        } catch (err) {
            if (err?.status === 401) {
                this.logout()
            }
            throw err
        }
    }

    static logout({ clearAdminKey = false } = {}) {
        this.setUserToken('')
        this.clearDisplayNameCache()
        if (clearAdminKey) {
            this.setAdminKey('')
        }
        this.setIsAdmin(false)
        this.setIsJournalist(false)
        this._emitAuthChanged({ role: 'user', token: null })
    }

    // Admin endpoints
    static async validateAdminCredentials() {
        return this.request('/admin/auth-check', {}, { admin: true })
    }
    static async adminGetConfig() { return this.request('/admin/config', {}, { admin: true }) }
    static async adminUpdateConfig(settings) {
        return this.request('/admin/config', { method: 'POST', body: JSON.stringify({ settings }) }, { admin: true })
    }
    static async adminGetRunStatus() { return this.request('/admin/run-status', {}, { admin: true }) }
    static async adminSetRunStatus(paused) {
        return this.request('/admin/run-status', { method: 'POST', body: JSON.stringify({ runs_paused: !!paused }) }, { admin: true })
    }
    static async adminGenerateAll(dateStr) {
        return this.request('/newsletters/generate-weekly-all', { method: 'POST', body: JSON.stringify({ target_date: dateStr }) }, { admin: true })
    }
    static async adminCheckPendingGames(teamId, targetDate) {
        const query = targetDate ? `?target_date=${encodeURIComponent(targetDate)}` : ''
        return this.request(`/newsletters/pending-games/${teamId}${query}`, {}, { admin: true })
    }
    static async adminListPendingFlags() { return this.request('/loans/flags/pending', {}, { admin: true }) }
    static async adminResolveFlag(flagId, { deactivateLoan = false, note = '' } = {}) {
        return this.request(`/loans/flags/${flagId}/resolve`, { method: 'POST', body: JSON.stringify({ action: deactivateLoan ? 'deactivate_loan' : 'none', note }) }, { admin: true })
    }
    static async adminLoansList(params = {}) {
        const q = new URLSearchParams(params)
        return this.request(`/admin/loans?${q}`, {}, { admin: true })
    }
    static async adminLoanCreate(payload) {
        return this.request('/admin/loans', { method: 'POST', body: JSON.stringify(payload) }, { admin: true })
    }
    static async adminLoanUpdate(loanId, payload) {
        return this.request(`/admin/loans/${loanId}`, { method: 'PUT', body: JSON.stringify(payload) }, { admin: true })
    }
    static async adminLoanDeactivate(loanId) {
        return this.request(`/admin/loans/${loanId}/deactivate`, { method: 'POST' }, { admin: true })
    }
    static async adminLoanTransition(loanId, payload) {
        return this.request(`/admin/loans/${loanId}/transition`, { method: 'POST', body: JSON.stringify(payload) }, { admin: true })
    }
    static async adminLoansBulkDeactivate(loanIds, note = null) {
        return this.request('/admin/loans/bulk-deactivate', { method: 'POST', body: JSON.stringify({ loan_ids: loanIds, note }) }, { admin: true })
    }
    static async adminLoansBulkTransition(transitions) {
        return this.request('/admin/loans/bulk-transition', { method: 'POST', body: JSON.stringify({ transitions }) }, { admin: true })
    }
    static async adminLoansPreviewSync(params) {
        return this.request('/admin/loans/preview-sync', { method: 'POST', body: JSON.stringify(params) }, { admin: true })
    }
    static async adminSeedTeam(params) {
        return this.request('/admin/loans/seed-team', { method: 'POST', body: JSON.stringify(params) }, { admin: true })
    }
    static async adminFlags(params = {}) {
        const q = new URLSearchParams(params)
        return this.request(`/admin/flags?${q}`, {}, { admin: true })
    }
    static async adminFlagUpdate(flagId, payload) {
        return this.request(`/admin/flags/${flagId}`, { method: 'POST', body: JSON.stringify(payload) }, { admin: true })
    }
    static async adminBackfillTeamLeagues(season) {
        return this.request(`/admin/backfill-team-leagues/${season}`, { method: 'POST' }, { admin: true })
    }
    static async adminBackfillTeamLeaguesAll(seasons) {
        const body = seasons && seasons.length ? { seasons } : {}
        return this.request(`/admin/backfill-team-leagues`, { method: 'POST', body: JSON.stringify(body) }, { admin: true })
    }
    static async adminMissingNames(params = {}) {
        const q = new URLSearchParams(params)
        return this.request(`/admin/loans/missing-names?${q}`, {}, { admin: true })
    }
    static async adminBackfillNames(payload = {}) {
        return this.request(`/admin/loans/backfill-names`, { method: 'POST', body: JSON.stringify(payload) }, { admin: true })
    }
    static async adminSandboxTasks() {
        return this.request('/admin/sandbox?format=json', { headers: { Accept: 'application/json' } }, { admin: true })
    }
    static async adminSandboxRun(taskId, payload = {}) {
        if (!taskId) {
            throw new Error('taskId is required')
        }
        return this.request(`/admin/sandbox/run/${encodeURIComponent(taskId)}`, {
            method: 'POST',
            body: JSON.stringify(payload || {}),
        }, { admin: true })
    }
    static async adminSupplementalLoansList(params = {}) {
        const q = new URLSearchParams(params)
        return this.request(`/admin/supplemental-loans?${q}`, {}, { admin: true })
    }
    static async adminSupplementalLoanCreate(payload) {
        return this.request('/admin/supplemental-loans', { method: 'POST', body: JSON.stringify(payload) }, { admin: true })
    }
    static async adminSupplementalLoanUpdate(loanId, payload) {
        return this.request(`/admin/supplemental-loans/${loanId}`, { method: 'PUT', body: JSON.stringify(payload) }, { admin: true })
    }
    static async adminSupplementalLoanDelete(loanId) {
        return this.request(`/admin/supplemental-loans/${loanId}`, { method: 'DELETE' }, { admin: true })
    }
    static async adminNewslettersList(params = {}) {
        const q = new URLSearchParams(params)
        const query = q.toString()
        const url = query ? `/admin/newsletters?${query}` : '/admin/newsletters'
        const data = await this.request(url, {}, { admin: true })
        if (!data) {
            return { items: [], total: 0, page: 1, page_size: 0, total_pages: 1, meta: {} }
        }
        if (Array.isArray(data)) {
            return { items: data, total: data.length, page: 1, page_size: data.length, total_pages: 1, meta: {} }
        }
        const items = Array.isArray(data.items)
            ? data.items
            : Array.isArray(data.results)
                ? data.results
                : []
        const total = Number(data.total) || items.length
        const meta = (data.meta && typeof data.meta === 'object') ? data.meta : {}
        return {
            items,
            total,
            page: Number(data.page) || 1,
            page_size: Number(data.page_size) || items.length,
            total_pages: Number(data.total_pages) || 1,
            meta,
        }
    }
    static async adminNewsletterGet(id) {
        return this.request(`/admin/newsletters/${id}`, {}, { admin: true })
    }
    static async adminNewsletterUpdate(id, payload) {
        return this.request(`/admin/newsletters/${id}`, { method: 'PUT', body: JSON.stringify(payload) }, { admin: true })
    }
    static async adminNewsletterBulkPublish(selection, publish = true, options = {}) {
        const payload = { publish: !!publish }

        if (selection && typeof selection === 'object' && !Array.isArray(selection)) {
            const filterParams = selection.filter_params || selection.filterParams
            if (filterParams) payload.filter_params = filterParams
            if (selection.exclude_ids || selection.excludeIds) {
                const ids = normalizeNewsletterIds(selection.exclude_ids || selection.excludeIds)
                if (ids.length > 0) payload.exclude_ids = ids
            }
            if (typeof selection.expected_total !== 'undefined') {
                payload.expected_total = Number(selection.expected_total)
            }
            if (Array.isArray(selection.ids)) {
                const ids = normalizeNewsletterIds(selection.ids)
                if (ids.length > 0) payload.ids = ids
            }
        } else {
            const ids = normalizeNewsletterIds(selection)
            if (ids.length === 0) {
                throw new Error('No newsletter ids provided')
            }
            payload.ids = ids
        }
        const body = JSON.stringify(payload)
        return this.request('/admin/newsletters/bulk-publish', { method: 'POST', body }, { admin: true })
    }

    static async adminNewsletterYoutubeLinksList(newsletterId) {
        return this.request(`/admin/newsletters/${newsletterId}/youtube-links`, {}, { admin: true })
    }
    static async adminNewsletterYoutubeLinkCreate(newsletterId, payload) {
        return this.request(`/admin/newsletters/${newsletterId}/youtube-links`, { method: 'POST', body: JSON.stringify(payload) }, { admin: true })
    }
    static async adminNewsletterYoutubeLinkUpdate(newsletterId, linkId, payload) {
        return this.request(`/admin/newsletters/${newsletterId}/youtube-links/${linkId}`, { method: 'PUT', body: JSON.stringify(payload) }, { admin: true })
    }
    static async adminNewsletterYoutubeLinkDelete(newsletterId, linkId) {
        return this.request(`/admin/newsletters/${newsletterId}/youtube-links/${linkId}`, { method: 'DELETE' }, { admin: true })
    }

    // Newsletter Commentary API methods
    static async adminNewsletterCommentaryList(newsletterId) {
        return this.request(`/admin/newsletters/${newsletterId}/commentary`, {}, { admin: true })
    }
    static async adminNewsletterCommentaryCreate(newsletterId, payload) {
        return this.request(`/admin/newsletters/${newsletterId}/commentary`, { method: 'POST', body: JSON.stringify(payload) }, { admin: true })
    }
    static async adminNewsletterCommentaryUpdate(commentaryId, payload) {
        return this.request(`/admin/commentary/${commentaryId}`, { method: 'PUT', body: JSON.stringify(payload) }, { admin: true })
    }
    static async adminNewsletterCommentaryDelete(commentaryId) {
        return this.request(`/admin/commentary/${commentaryId}`, { method: 'DELETE' }, { admin: true })
    }

    // Player Management API methods
    static async adminPlayersList(params = {}) {
        const q = new URLSearchParams(params)
        const query = q.toString()
        const url = query ? `/admin/players?${query}` : '/admin/players'
        const data = await this.request(url, {}, { admin: true })
        if (!data) {
            return { items: [], total: 0, page: 1, page_size: 50, total_pages: 1 }
        }
        return {
            items: Array.isArray(data.items) ? data.items : [],
            total: Number(data.total) || 0,
            page: Number(data.page) || 1,
            page_size: Number(data.page_size) || 50,
            total_pages: Number(data.total_pages) || 1,
        }
    }
    static async adminPlayerGet(playerId) {
        return this.request(`/admin/players/${playerId}`, {}, { admin: true })
    }
    static async adminPlayerUpdate(playerId, payload) {
        return this.request(`/admin/players/${playerId}`, { method: 'PUT', body: JSON.stringify(payload) }, { admin: true })
    }
    static async adminPlayerBulkUpdateSofascore(updates) {
        return this.request('/admin/players/bulk-update-sofascore', {
            method: 'POST',
            body: JSON.stringify({ updates })
        }, { admin: true })
    }
    static async adminPlayerCreate(payload) {
        return this.request('/admin/players', {
            method: 'POST',
            body: JSON.stringify(payload)
        }, { admin: true })
    }
    static async adminPlayerDelete(playerId) {
        return this.request(`/admin/players/${playerId}`, { method: 'DELETE' }, { admin: true })
    }
    static async adminPlayerFieldOptions() {
        return this.request('/admin/players/field-options', {}, { admin: true })
    }

    static async adminNewsletterBulkDelete(selection = {}) {
        const payload = {}
        if (selection && typeof selection === 'object' && !Array.isArray(selection)) {
            if (selection.filter_params || selection.filterParams) {
                payload.filter_params = selection.filter_params || selection.filterParams
            }
            if (selection.exclude_ids || selection.excludeIds) {
                const ids = normalizeNewsletterIds(selection.exclude_ids || selection.excludeIds)
                if (ids.length > 0) payload.exclude_ids = ids
            }
            if (typeof selection.expected_total !== 'undefined') {
                payload.expected_total = Number(selection.expected_total)
            }
            if (Array.isArray(selection.ids)) {
                const ids = normalizeNewsletterIds(selection.ids)
                if (ids.length > 0) payload.ids = ids
            }
        } else if (Array.isArray(selection)) {
            const ids = normalizeNewsletterIds(selection)
            if (ids.length > 0) payload.ids = ids
        }

        if (!payload.filter_params && (!payload.ids || payload.ids.length === 0)) {
            throw new Error('Provide ids or filter_params for bulk delete')
        }

        const body = JSON.stringify(payload)
        return this.request('/admin/newsletters/bulk', { method: 'DELETE', body }, { admin: true })
    }
    static async adminNewsletterSendPreview(id, overrides = {}) {
        const normalized = parseNewsletterId(id)
        if (!normalized) {
            throw new Error('Newsletter id must be a positive integer')
        }
        const payload = { test_to: '__admins__' }
        if (overrides && typeof overrides === 'object') {
            for (const [key, value] of Object.entries(overrides)) {
                if (typeof value === 'undefined') continue
                payload[key] = value
            }
        }
        return this.request(`/newsletters/${normalized}/send`, { method: 'POST', body: JSON.stringify(payload) }, { admin: true })
    }
    static async adminNewsletterDelete(id) {
        const normalized = parseNewsletterId(id)
        if (!normalized) {
            throw new Error('Newsletter id must be a positive integer')
        }
        return this.request(`/newsletters/${normalized}`, { method: 'DELETE' }, { admin: true })
    }
    static async adminNewsletterRender(id, fmt = 'web') {
        const headers = { 'Accept': 'text/html' }
        const key = this.adminKey || (typeof localStorage !== 'undefined' && localStorage.getItem('academy_watch_admin_key'))
        if (key) headers['X-API-Key'] = key
        const token = this.userToken || (typeof localStorage !== 'undefined' && localStorage.getItem('academy_watch_user_token'))
        if (token) headers['Authorization'] = `Bearer ${token}`
        const numericId = parseNewsletterId(id)
        if (!numericId) {
            throw new Error('Newsletter id must be a positive integer')
        }
        const res = await fetch(`${API_BASE_URL}/newsletters/${numericId}/render.${fmt}`, { headers, method: 'GET' })
        const text = await res.text()
        if (!res.ok) {
            const err = new Error(text || `HTTP ${res.status}`)
            err.status = res.status
            err.body = text
            throw err
        }
        return text
    }

    static async listNewsletterComments(newsletterId) {
        const numericId = parseNewsletterId(newsletterId)
        if (!numericId) {
            throw new Error('Newsletter id must be a positive integer')
        }
        return this.request(`/newsletters/${numericId}/comments`)
    }

    static async createNewsletterComment(newsletterId, body) {
        const numericId = parseNewsletterId(newsletterId)
        if (!numericId) {
            throw new Error('Newsletter id must be a positive integer')
        }
        return this.request(`/newsletters/${numericId}/comments`, {
            method: 'POST',
            body: JSON.stringify({ body }),
        })
    }

    static async applaudCommentary(commentaryId) {
        if (!commentaryId) throw new Error('commentaryId is required')
        return this.request(`/commentaries/${encodeURIComponent(commentaryId)}/applaud`, {
            method: 'POST',
        })
    }

    static async listPlayerComments(playerId) {
        if (!playerId) throw new Error('playerId is required')
        return this.request(`/players/${encodeURIComponent(playerId)}/comments`)
    }

    static async createPlayerComment(playerId, body) {
        if (!playerId) throw new Error('playerId is required')
        return this.request(`/players/${encodeURIComponent(playerId)}/comments`, {
            method: 'POST',
            body: JSON.stringify({ body }),
        })
    }

    static async getPlayerLinks(playerId) {
        if (!playerId) throw new Error('playerId is required')
        return this.request(`/players/${encodeURIComponent(playerId)}/links`)
    }

    static async submitPlayerLink(playerId, { url, title, link_type }) {
        if (!playerId) throw new Error('playerId is required')
        return this.request(`/players/${encodeURIComponent(playerId)}/links`, {
            method: 'POST',
            body: JSON.stringify({ url, title, link_type }),
        })
    }

    static async adminGetPendingPlayerLinks(params = {}) {
        const query = new URLSearchParams(params).toString()
        return this.request(`/admin/player-links/pending${query ? '?' + query : ''}`, {}, { admin: true })
    }

    static async adminUpdatePlayerLink(linkId, payload) {
        return this.request(`/admin/player-links/${linkId}`, {
            method: 'PUT',
            body: JSON.stringify(payload),
        }, { admin: true })
    }

    // Writer Portal API methods
    static async getWriterTeams() {
        return this.request('/writer/teams')
    }

    static async getWriterCommentaries() {
        return this.request('/writer/commentaries')
    }

    static async saveWriterCommentary(payload) {
        return this.request('/writer/commentaries', {
            method: 'POST',
            body: JSON.stringify(payload)
        })
    }

    static async deleteWriterCommentary(commentaryId) {
        return this.request(`/writer/commentaries/${commentaryId}`, {
            method: 'DELETE'
        })
    }

    static async getWriterAvailablePlayers() {
        return this.request('/writer/available-players')
    }

    static async getPlayerStats(playerId) {
        return this.request(`/journalists/players/${playerId}/stats`)
    }

    // Curator API methods
    static async getCuratorTeams() {
        return this.request('/curator/teams', {}, { curator: true })
    }

    static async getCuratorNewsletters(params = {}) {
        const search = new URLSearchParams()
        for (const [key, value] of Object.entries(params)) {
            if (value === undefined || value === null || value === '') continue
            search.append(key, String(value))
        }
        const query = search.toString()
        return this.request(`/curator/newsletters${query ? `?${query}` : ''}`, {}, { curator: true })
    }

    static async generateCuratorNewsletter(data) {
        return this.request('/curator/newsletters/generate', {
            method: 'POST',
            body: JSON.stringify(data),
        }, { curator: true })
    }

    static async getCuratorTweets(params = {}) {
        const search = new URLSearchParams()
        for (const [key, value] of Object.entries(params)) {
            if (value === undefined || value === null || value === '') continue
            search.append(key, String(value))
        }
        const query = search.toString()
        return this.request(`/curator/tweets${query ? `?${query}` : ''}`, {}, { curator: true })
    }

    static async createCuratorTweet(data) {
        return this.request('/curator/tweets', {
            method: 'POST',
            body: JSON.stringify(data),
        }, { curator: true })
    }

    static async updateCuratorTweet(id, data) {
        return this.request(`/curator/tweets/${id}`, {
            method: 'PUT',
            body: JSON.stringify(data),
        }, { curator: true })
    }

    static async deleteCuratorTweet(id) {
        return this.request(`/curator/tweets/${id}`, {
            method: 'DELETE',
        }, { curator: true })
    }

    static async attachCuratorTweet(tweetId, newsletterId) {
        return this.request(`/curator/tweets/${tweetId}/attach`, {
            method: 'POST',
            body: JSON.stringify({ newsletter_id: newsletterId }),
        }, { curator: true })
    }

    static async detachCuratorTweet(tweetId) {
        return this.request(`/curator/tweets/${tweetId}/detach`, {
            method: 'POST',
        }, { curator: true })
    }

    static async getCuratorPlayers(params = {}) {
        const search = new URLSearchParams()
        for (const [key, value] of Object.entries(params)) {
            if (value === undefined || value === null || value === '') continue
            search.append(key, String(value))
        }
        const query = search.toString()
        return this.request(`/curator/players${query ? `?${query}` : ''}`, {}, { curator: true })
    }

    // Admin Journalist Management API methods
    static async adminGetJournalists() {
        return this.request('/journalists')
    }

    static async adminGetJournalistDetails(journalistId) {
        return this.request(`/journalists/${journalistId}`)
    }

    static async adminGetUsers() {
        return this.request('/admin/users', {}, { admin: true })
    }

    static async adminUpdateUserRole(userId, isJournalist) {
        return this.request(`/admin/users/${userId}/role`, {
            method: 'POST',
            body: JSON.stringify({ is_journalist: isJournalist })
        }, { admin: true })
    }

    // Journalist Subscription Statistics API methods
    static async getJournalistOwnStats() {
        return this.request('/journalist/stats')
    }

    static async getJournalistPublicStats(journalistId) {
        return this.request(`/journalists/${journalistId}/stats/public`)
    }

    static async adminGetJournalistStats() {
        return this.request('/admin/journalist-stats', {}, { admin: true })
    }

    static async adminGetJournalistAllAssignments(journalistId) {
        return this.request(`/admin/journalists/${journalistId}/all-assignments`, {}, { admin: true })
    }

    static async adminAssignLoanTeams(journalistId, loanTeams) {
        return this.request(`/admin/journalists/${journalistId}/loan-team-assignments`, {
            method: 'POST',
            body: JSON.stringify({ loan_teams: loanTeams })
        }, { admin: true })
    }

    // Team Tracking Management API methods
    static async getTeamTrackingStatus(teamId) {
        return this.request(`/teams/${teamId}/tracking-status`)
    }

    static async submitTrackingRequest(teamId, payload = {}) {
        return this.request(`/teams/${teamId}/request-tracking`, {
            method: 'POST',
            body: JSON.stringify(payload)
        })
    }

    static async adminListTrackingRequests(params = {}) {
        const q = new URLSearchParams(params)
        return this.request(`/admin/tracking-requests?${q}`, {}, { admin: true })
    }

    static async adminUpdateTrackingRequest(requestId, payload) {
        return this.request(`/admin/tracking-requests/${requestId}`, {
            method: 'POST',
            body: JSON.stringify(payload)
        }, { admin: true })
    }

    static async adminDeleteTeamData(teamId, dryRun = false) {
        const q = dryRun ? '?dry_run=true' : ''
        return this.request(`/admin/teams/${teamId}/data${q}`, {
            method: 'DELETE'
        }, { admin: true })
    }

    static async adminSyncTeamFixtures(teamId, { background = false, dryRun = false } = {}) {
        return this.request(`/admin/teams/${teamId}/sync-all-fixtures`, {
            method: 'POST',
            body: JSON.stringify({ background, dry_run: dryRun })
        }, { admin: true })
    }

    static async adminPurgeLoansExcept(keepTeamIds, { dryRun = true } = {}) {
        return this.request('/admin/loans/purge-except', {
            method: 'POST',
            body: JSON.stringify({ keep_team_ids: keepTeamIds, dry_run: dryRun })
        }, { admin: true })
    }

    static async adminUpdateTeamTracking(teamId, isTracked) {
        return this.request(`/admin/teams/${teamId}/tracking`, {
            method: 'POST',
            body: JSON.stringify({ is_tracked: isTracked })
        }, { admin: true })
    }

    static async adminBulkUpdateTeamTracking(payload) {
        return this.request('/admin/teams/bulk-tracking', {
            method: 'POST',
            body: JSON.stringify(payload)
        }, { admin: true })
    }

    static async adminUpdateTeamName(teamId, name) {
        return this.request(`/admin/teams/${teamId}/name`, {
            method: 'PUT',
            body: JSON.stringify({ name })
        }, { admin: true })
    }

    static async adminListPlaceholderTeamNames(params = {}) {
        const query = new URLSearchParams(params).toString()
        return this.request(`/admin/teams/placeholder-names${query ? '?' + query : ''}`, {}, { admin: true })
    }

    static async adminBulkFixTeamNames(payload) {
        return this.request('/admin/teams/bulk-fix-names', {
            method: 'POST',
            body: JSON.stringify(payload)
        }, { admin: true })
    }

    static async adminPropagateTeamNames(payload) {
        return this.request('/admin/teams/propagate-names', {
            method: 'POST',
            body: JSON.stringify(payload)
        }, { admin: true })
    }

    static async adminCheckNewsletterReadiness(targetDate, teamIds = []) {
        const params = new URLSearchParams()
        if (targetDate) params.append('target_date', targetDate)
        if (teamIds.length) params.append('team_ids', teamIds.join(','))
        const query = params.toString()
        return this.request(`/newsletters/readiness${query ? '?' + query : ''}`, {}, { admin: true })
    }

    // Sponsor API methods
    static async getSponsors() {
        return this.request('/sponsors')
    }

    static async trackSponsorClick(sponsorId) {
        return this.request(`/sponsors/${sponsorId}/click`, {
            method: 'POST'
        })
    }

    static async adminGetSponsors() {
        return this.request('/admin/sponsors', {}, { admin: true })
    }

    static async adminCreateSponsor(data) {
        return this.request('/admin/sponsors', {
            method: 'POST',
            body: JSON.stringify(data)
        }, { admin: true })
    }

    static async adminUpdateSponsor(sponsorId, data) {
        return this.request(`/admin/sponsors/${sponsorId}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        }, { admin: true })
    }

    static async adminDeleteSponsor(sponsorId) {
        return this.request(`/admin/sponsors/${sponsorId}`, {
            method: 'DELETE'
        }, { admin: true })
    }

    static async adminReorderSponsors(sponsorIds) {
        return this.request('/admin/sponsors/reorder', {
            method: 'POST',
            body: JSON.stringify({ sponsor_ids: sponsorIds })
        }, { admin: true })
    }

    // Team Aliases
    static async adminListTeamAliases() {
        return this.request('/admin/team-aliases', {}, { admin: true })
    }

    static async adminCreateTeamAlias(data) {
        return this.request('/admin/team-aliases', {
            method: 'POST',
            body: JSON.stringify(data)
        }, { admin: true })
    }

    static async adminDeleteTeamAlias(aliasId) {
        return this.request(`/admin/team-aliases/${aliasId}`, {
            method: 'DELETE'
        }, { admin: true })
    }

    // Manual Player Submissions
    static async submitManualPlayer(data) {
        return this.request('/writer/manual-players', {
            method: 'POST',
            body: JSON.stringify(data)
        })
    }

    static async listManualSubmissions() {
        return this.request('/writer/manual-players')
    }

    static async adminListManualPlayers(params = {}) {
        const queryString = new URLSearchParams(params).toString()
        return this.request(`/admin/manual-players?${queryString}`, {}, { admin: true })
    }

    static async adminReviewManualPlayer(submissionId, data) {
        return this.request(`/admin/manual-players/${submissionId}/review`, {
            method: 'POST',
            body: JSON.stringify(data)
        }, { admin: true })
    }

    // ==========================================================================
    // Editor / Managed Writers API
    // ==========================================================================

    // Toggle editor role (admin only)
    static async adminUpdateEditorRole(userId, isEditor) {
        return this.request(`/admin/users/${userId}/editor-role`, {
            method: 'POST',
            body: JSON.stringify({ is_editor: isEditor })
        }, { admin: true })
    }

    // List managed/placeholder writers (editor sees theirs, admin sees all)
    static async getEditorManagedWriters() {
        return this.request('/editor/writers')
    }

    // Get a single managed writer's details
    static async getEditorWriter(writerId) {
        return this.request(`/editor/writers/${writerId}`)
    }

    // Create a placeholder writer account
    static async createPlaceholderWriter(data) {
        return this.request('/editor/writers', {
            method: 'POST',
            body: JSON.stringify(data)
        })
    }

    // Update a placeholder writer's profile
    static async updatePlaceholderWriter(writerId, data) {
        return this.request(`/editor/writers/${writerId}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        })
    }

    // Delete a placeholder writer (only if no content)
    static async deletePlaceholderWriter(writerId) {
        return this.request(`/editor/writers/${writerId}`, {
            method: 'DELETE'
        })
    }

    // Assign parent club teams to a managed writer
    static async editorAssignTeams(writerId, teamIds) {
        return this.request(`/editor/writers/${writerId}/assign-teams`, {
            method: 'POST',
            body: JSON.stringify({ team_ids: teamIds })
        })
    }

    // Assign loan teams to a managed writer
    static async editorAssignLoanTeams(writerId, loanTeams) {
        return this.request(`/editor/writers/${writerId}/loan-teams`, {
            method: 'POST',
            body: JSON.stringify({ loan_teams: loanTeams })
        })
    }

    // Send claim invitation email to a placeholder writer
    static async sendClaimInvite(writerId) {
        return this.request(`/editor/writers/${writerId}/send-claim-invite`, {
            method: 'POST'
        })
    }

    // ==========================================================================
    // Claim Account Flow (public endpoints)
    // ==========================================================================

    // Validate a claim token
    static async validateClaimToken(token) {
        return this.request('/claim/validate', {
            method: 'POST',
            body: JSON.stringify({ token })
        })
    }

    // Complete account claim and get auth token
    static async completeAccountClaim(token) {
        return this.request('/claim/complete', {
            method: 'POST',
            body: JSON.stringify({ token })
        })
    }

    // ==========================================================================
    // Contributor Profiles
    // ==========================================================================

    // Get contributor profiles created by the current writer
    static async getWriterContributors() {
        return this.request('/writer/contributors')
    }

    // Create a new contributor profile
    static async createContributor(payload) {
        return this.request('/writer/contributors', {
            method: 'POST',
            body: JSON.stringify(payload)
        })
    }

    // Update an existing contributor profile
    static async updateContributor(contributorId, payload) {
        return this.request(`/writer/contributors/${contributorId}`, {
            method: 'PUT',
            body: JSON.stringify(payload)
        })
    }

    // Delete a contributor profile
    static async deleteContributor(contributorId) {
        return this.request(`/writer/contributors/${contributorId}`, {
            method: 'DELETE'
        })
    }

    // ==========================================================================
    // Community Takes
    // ==========================================================================

    // Public: List approved community takes
    static async getCommunityTakes(params = {}) {
        const query = new URLSearchParams(params).toString()
        return this.request(`/community-takes${query ? '?' + query : ''}`)
    }

    // Public: Submit a quick take for moderation
    static async submitQuickTake(data) {
        return this.request('/community-takes/submit', {
            method: 'POST',
            body: JSON.stringify(data)
        })
    }

    // Admin: List community takes (with status filter)
    static async adminListCommunityTakes(params = {}) {
        const query = new URLSearchParams(params).toString()
        return this.request(`/admin/community-takes${query ? '?' + query : ''}`, {}, { admin: true })
    }

    // Admin: List pending submissions
    static async adminListSubmissions(params = {}) {
        const query = new URLSearchParams(params).toString()
        return this.request(`/admin/community-takes/submissions${query ? '?' + query : ''}`, {}, { admin: true })
    }

    // Admin: Approve a community take
    static async adminApproveTake(takeId, data = {}) {
        return this.request(`/admin/community-takes/${takeId}/approve`, {
            method: 'POST',
            body: JSON.stringify(data)
        }, { admin: true })
    }

    // Admin: Reject a community take
    static async adminRejectTake(takeId, data = {}) {
        return this.request(`/admin/community-takes/${takeId}/reject`, {
            method: 'POST',
            body: JSON.stringify(data)
        }, { admin: true })
    }

    // Admin: Approve a quick take submission
    static async adminApproveSubmission(submissionId) {
        return this.request(`/admin/community-takes/submissions/${submissionId}/approve`, {
            method: 'POST'
        }, { admin: true })
    }

    // Admin: Reject a quick take submission
    static async adminRejectSubmission(submissionId, data = {}) {
        return this.request(`/admin/community-takes/submissions/${submissionId}/reject`, {
            method: 'POST',
            body: JSON.stringify(data)
        }, { admin: true })
    }

    // Admin: Create a community take directly
    static async adminCreateTake(data) {
        return this.request('/admin/community-takes', {
            method: 'POST',
            body: JSON.stringify(data)
        }, { admin: true })
    }

    // Admin: Delete a community take
    static async adminDeleteTake(takeId) {
        return this.request(`/admin/community-takes/${takeId}`, {
            method: 'DELETE'
        }, { admin: true })
    }

    // Admin: Get community takes statistics
    static async adminTakesStats() {
        return this.request('/admin/community-takes/stats', {}, { admin: true })
    }

    // ==========================================================================
    // Academy Tracking
    // ==========================================================================

    // Admin: List academy leagues
    static async adminListAcademyLeagues() {
        return this.request('/admin/academy-leagues', {}, { admin: true })
    }

    // Admin: Create academy league
    static async adminCreateAcademyLeague(data) {
        return this.request('/admin/academy-leagues', {
            method: 'POST',
            body: JSON.stringify(data)
        }, { admin: true })
    }

    // Admin: Update academy league
    static async adminUpdateAcademyLeague(leagueId, data) {
        return this.request(`/admin/academy-leagues/${leagueId}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        }, { admin: true })
    }

    // Admin: Delete academy league
    static async adminDeleteAcademyLeague(leagueId) {
        return this.request(`/admin/academy-leagues/${leagueId}`, {
            method: 'DELETE'
        }, { admin: true })
    }

    // Admin: Sync academy league
    static async adminSyncAcademyLeague(leagueId, data = {}) {
        return this.request(`/admin/academy-leagues/${leagueId}/sync`, {
            method: 'POST',
            body: JSON.stringify(data)
        }, { admin: true })
    }

    // Admin: Sync all academy leagues
    static async adminSyncAllAcademyLeagues(data = {}) {
        return this.request('/admin/academy-leagues/sync-all', {
            method: 'POST',
            body: JSON.stringify(data)
        }, { admin: true })
    }

    // Admin: List academy appearances
    static async adminListAcademyAppearances(params = {}) {
        const query = new URLSearchParams(params).toString()
        return this.request(`/admin/academy-appearances${query ? '?' + query : ''}`, {}, { admin: true })
    }

    // Admin: Get academy stats summary
    static async adminAcademyStatsSummary() {
        return this.request('/admin/academy-stats/summary', {}, { admin: true })
    }

    // Public: Get player academy stats
    static async getPlayerAcademyStats(playerId, params = {}) {
        const query = new URLSearchParams(params).toString()
        return this.request(`/players/${playerId}/academy-stats${query ? '?' + query : ''}`)
    }

    // ==========================================================================
    // Player Journey
    // ==========================================================================

    // Public: Get player journey (full career data)
    static async getPlayerJourney(playerId, params = {}) {
        const query = new URLSearchParams(params).toString()
        return this.request(`/players/${playerId}/journey${query ? '?' + query : ''}`)
    }

    // Public: Get player journey for map display
    static async getPlayerJourneyMap(playerId) {
        return this.request(`/players/${playerId}/journey/map`)
    }

    // Public: Get all club locations
    static async getClubLocations() {
        return this.request('/club-locations')
    }

    // Public: Get specific club location
    static async getClubLocation(clubApiId) {
        return this.request(`/club-locations/${clubApiId}`)
    }

    // Admin: Trigger journey sync for a player
    static async adminSyncPlayerJourney(playerId, data = {}) {
        return this.request(`/admin/journey/sync/${playerId}`, {
            method: 'POST',
            body: JSON.stringify(data)
        }, { admin: true })
    }

    // Admin: Bulk sync player journeys
    static async adminBulkSyncJourneys(playerIds, forceFull = false) {
        return this.request('/admin/journey/bulk-sync', {
            method: 'POST',
            body: JSON.stringify({ player_ids: playerIds, force_full: forceFull })
        }, { admin: true })
    }

    // Admin: Seed club locations
    static async adminSeedClubLocations() {
        return this.request('/admin/journey/seed-locations', {
            method: 'POST'
        }, { admin: true })
    }

    // Admin: Add/update club location
    static async adminAddClubLocation(data) {
        return this.request('/admin/club-locations', {
            method: 'POST',
            body: JSON.stringify(data)
        }, { admin: true })
    }

    // ==========================================================================
    // Cohorts
    // ==========================================================================

    static async getCohorts(filters = {}) {
        const params = new URLSearchParams(filters).toString()
        return this.request(`/cohorts${params ? '?' + params : ''}`)
    }

    static async getCohort(cohortId, params = {}) {
        const query = new URLSearchParams(params).toString()
        return this.request(`/cohorts/${cohortId}${query ? '?' + query : ''}`)
    }

    static async getFeederCompetitions() {
        return this.request('/feeder/competitions')
    }

    static async getFeederTeams(leagueApiId, season) {
        return this.request(`/feeder/competitions/${leagueApiId}/teams?season=${season}`)
    }

    static async getSquadOrigins(teamApiId, { league, season } = {}) {
        const params = new URLSearchParams()
        if (league) params.set('league', league)
        if (season) params.set('season', season)
        const qs = params.toString()
        return this.request(`/feeder/teams/${teamApiId}/origins${qs ? `?${qs}` : ''}`)
    }

    static async getCohortTeams() {
        return this.request('/cohorts/teams')
    }

    static async getCohortAnalytics() {
        return this.request('/cohorts/analytics')
    }

    static async adminSeedCohort(data) {
        return this.request('/admin/cohorts/seed', {
            method: 'POST',
            body: JSON.stringify(data)
        }, { admin: true })
    }

    static async adminSeedAllTrackedPlayers(data = {}) {
        return this.request('/admin/tracked-players/seed-all-tracked', {
            method: 'POST',
            body: JSON.stringify(data),
        }, { admin: true })
    }

    static async adminSeedBig6(data = {}) {
        return this.request('/admin/cohorts/seed-big6', {
            method: 'POST',
            body: JSON.stringify(data)
        }, { admin: true })
    }

    static async adminFullRebuild(data = {}) {
        return this.request('/admin/academy/full-rebuild', {
            method: 'POST',
            body: JSON.stringify(data)
        }, { admin: true })
    }

    static async adminSyncCohortJourneys(cohortId) {
        return this.request(`/admin/cohorts/${cohortId}/sync-journeys`, {
            method: 'POST'
        }, { admin: true })
    }

    static async adminRefreshCohortStats(cohortId) {
        return this.request(`/admin/cohorts/${cohortId}/refresh-stats`, {
            method: 'POST'
        }, { admin: true })
    }

    static async adminGetCohortSeedStatus() {
        return this.request('/admin/cohorts/seed-status', {}, { admin: true })
    }

    static async adminDeleteCohort(cohortId) {
        return this.request(`/admin/cohorts/${cohortId}`, {
            method: 'DELETE'
        }, { admin: true })
    }

    static async adminGetJobStatus(jobId) {
        return this.request(`/admin/jobs/${jobId}`, {}, { admin: true })
    }

    static async adminGetActiveJobs() {
        return this.request('/admin/jobs/active', {}, { admin: true })
    }

    static async adminCancelJob(jobId) {
        return this.request(`/admin/jobs/${jobId}/cancel`, { method: 'POST' }, { admin: true })
    }

    // ==========================================================================
    // Formations
    // ==========================================================================

    static async adminGetFormations(teamId) {
        return this.request(`/admin/teams/${teamId}/formations`, {}, { admin: true })
    }

    static async adminCreateFormation(teamId, payload) {
        return this.request(`/admin/teams/${teamId}/formations`, {
            method: 'POST',
            body: JSON.stringify(payload)
        }, { admin: true })
    }

    static async adminGetFormation(teamId, formationId) {
        return this.request(`/admin/teams/${teamId}/formations/${formationId}`, {}, { admin: true })
    }

    static async adminUpdateFormation(teamId, formationId, payload) {
        return this.request(`/admin/teams/${teamId}/formations/${formationId}`, {
            method: 'PUT',
            body: JSON.stringify(payload)
        }, { admin: true })
    }

    static async adminDeleteFormation(teamId, formationId) {
        return this.request(`/admin/teams/${teamId}/formations/${formationId}`, {
            method: 'DELETE'
        }, { admin: true })
    }

    // ==========================================================================
    // GOL Assistant
    // ==========================================================================

    static async getGolSuggestions() {
        return this.request('/gol/suggestions')
    }

    static async streamChat(message, history, sessionId, signal) {
        const headers = { 'Content-Type': 'application/json' }
        if (this.userToken) headers['Authorization'] = `Bearer ${this.userToken}`
        return fetch(`${API_BASE_URL}/gol/chat`, {
            method: 'POST',
            headers,
            body: JSON.stringify({ message, history, session_id: sessionId }),
            signal,
        })
    }

    // ==========================================================================
    // Academy Network
    // ==========================================================================

    static async getAcademyNetwork(teamApiId, params = {}) {
        const query = new URLSearchParams(params).toString()
        return this.request(`/teams/${teamApiId}/academy-network${query ? '?' + query : ''}`)
    }
}
