
    static async setClubConsent(id, { action, note = null }) {
        return this.request(`/contact/requests/${encodeURIComponent(id)}/club-consent`, {
            method: 'POST',
            body: JSON.stringify({ action, note }),
        })
    }

    static async getContactMessages(id, { limit = 100, offset = 0 } = {}) {
        const query = new URLSearchParams({ limit: String(limit), offset: String(offset) }).toString()
        return this.request(`/contact/requests/${encodeURIComponent(id)}/messages?${query}`)
    }

    static async sendContactMessage(id, body) {
        return this.request(`/contact/requests/${encodeURIComponent(id)}/messages`, {
            method: 'POST',
            body: JSON.stringify({ body }),
        })
    }

    static async reportContactOutcome(id, { stage, notes = null, occurred_at = null }) {
        return this.request(`/contact/requests/${encodeURIComponent(id)}/outcome`, {
            method: 'POST',
            body: JSON.stringify({ stage, notes, occurred_at }),
        })
    }

    static async getClubConsentSummary(token) {
        return this.request(`/contact/club-consent/${encodeURIComponent(token)}`)
    }

    static async submitClubConsent(token) {
        return this.request(`/contact/club-consent/${encodeURIComponent(token)}`, { method: 'POST' })
    }
