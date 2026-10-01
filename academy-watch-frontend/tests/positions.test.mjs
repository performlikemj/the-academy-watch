import { test } from 'node:test'
import assert from 'node:assert/strict'
import { positionAbbreviation } from '../src/lib/positions.js'

for (const [value, expected] of [
  ['G', 'GK'], ['Goalkeeper', 'GK'], ['right-back', 'RB'], ['Centre back', 'CB'],
  ['Left back', 'LB'], ['Defensive midfield', 'DM'], ['Central midfield', 'CM'],
  ['Attacking midfielder', 'AM'], ['Right winger', 'RW'], ['Left wing', 'LW'],
  ['Striker', 'ST'], ['LWB', 'LWB'], ['Midfielder', 'MID'], ['Defender', 'DEF'],
  ['Attacker', 'FW'], ['Winger', 'W'], ['CM, AM', 'CM'], ['  goalKeeper  ', 'GK'],
  [null, '—'], ['Utility player', 'UTI'], ['', '—'], ['   ', '—'],
  ['Centre half', 'CB'], ['Center-half', 'CB'], ['Right Midfield', 'RM'], ['Left Midfield', 'LM'],
  ['Full-back', 'FB'], ['Wing back', 'WB'], ['Holding midfielder', 'DM'], ['Number 10', 'AM'],
  ['Centre forward', 'CF'], ['Sweeper', 'SW'], ['Goalie', 'GK'],
  ['Goal keeper', 'GK'], ['Centre midfield', 'CM'], ['Center midfield', 'CM'],
  ['Centre mid', 'CM'], ['Defensive mid', 'DM'], ['Attacking mid', 'AM'],
  ['Right wingback', 'RWB'], ['Left wingback', 'LWB'], ['Left centre back', 'CB'],
  ['Right center-back', 'CB'], ['Holding mid', 'DM'], ['Right mid', 'RM'],
  ['Left mid', 'LM'], ['Central mid', 'CM'],
  ['constructor', 'CON'], ['__proto__', 'PRO'], ['toString', 'TOS'], ['hasOwnProperty', 'HAS'],
]) {
  test(`position ${value} becomes ${expected}`, () => assert.equal(positionAbbreviation(value), expected))
}
