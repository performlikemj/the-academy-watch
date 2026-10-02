import { test } from 'node:test'
import assert from 'node:assert/strict'
import { displaySeasonFromDirectory } from '../src/lib/seasons.js'

for (const [directory, expected] of [
  [{ display_season: 2025, current_season: 2026 }, 2025],
  [{ display_season: '2025', current_season: 2026 }, 2025],
  [{ current_season: 2026 }, 2026],
  [{ display_season: 'invalid', current_season: 2026 }, 2026],
  [null, undefined],
]) {
  test(`display default ${JSON.stringify(directory)}`, () => {
    assert.equal(displaySeasonFromDirectory(directory), expected)
  })
}
