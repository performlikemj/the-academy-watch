import { test } from 'node:test'
import assert from 'node:assert/strict'
import { positionAbbreviation } from '../src/lib/positions.js'

for (const [value, expected] of [
  ['G', 'GK'], ['Goalkeeper', 'GK'], ['right-back', 'RB'], ['Centre back', 'CB'],
  ['Left back', 'LB'], ['Defensive midfield', 'DM'], ['Central midfield', 'CM'],
  ['Attacking midfielder', 'AM'], ['Right winger', 'RW'], ['Left wing', 'LW'],
  ['Striker', 'ST'], ['LWB', 'LWB'], ['Midfielder', 'MID'], ['Defender', 'DEF'],
  ['Attacker', 'FW'], ['Winger', 'W'], ['CM, AM', 'CM'], ['  goalKeeper  ', 'GK'],
  [null, '—'], ['Utility player', '—'],
]) {
  test(`position ${value} becomes ${expected}`, () => assert.equal(positionAbbreviation(value), expected))
}
