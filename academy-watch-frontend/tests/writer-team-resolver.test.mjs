import test from 'node:test'
import assert from 'node:assert/strict'

import { resolveLatestTeamId } from '../src/pages/writer/teamResolver.js'

test('resolveLatestTeamId returns latest matching team id when found', async () => {
  const api = {
    async getTeam(id) {
      return { id, team_id: 1001 }
    },
    async getTeams() {
      return [
        { id: 1, team_id: 999, season: 2024 },
        { id: 42, team_id: 1001, season: 2025 }, // latest we want
      ]
    },
  }

  const result = await resolveLatestTeamId(5, api)
  assert.equal(result, 42)
})

test('resolveLatestTeamId falls back to original id on error', async () => {
  const api = {
    async getTeam() {
      throw new Error('boom')
    },
    async getTeams() {
      return []
    },
  }

  const result = await resolveLatestTeamId(7, api)
  assert.equal(result, 7)
})
