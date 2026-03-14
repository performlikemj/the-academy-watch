/**
 * Formation presets for the Formation Board.
 *
 * Coordinates use a 100×100 grid where:
 *   x = 0 is left touchline, x = 100 is right touchline
 *   y = 0 is the top (attacking end), y = 100 is the bottom (goalkeeper end)
 */

const GK = { key: 'GK', label: 'GK', positionGroup: 'Goalkeeper' }

export const FORMATION_PRESETS = {
  '4-4-2': [
    { ...GK, x: 50, y: 90 },
    { key: 'LB', label: 'LB', positionGroup: 'Defender', x: 15, y: 72 },
    { key: 'CB1', label: 'CB', positionGroup: 'Defender', x: 37, y: 76 },
    { key: 'CB2', label: 'CB', positionGroup: 'Defender', x: 63, y: 76 },
    { key: 'RB', label: 'RB', positionGroup: 'Defender', x: 85, y: 72 },
    { key: 'LM', label: 'LM', positionGroup: 'Midfielder', x: 15, y: 50 },
    { key: 'CM1', label: 'CM', positionGroup: 'Midfielder', x: 37, y: 54 },
    { key: 'CM2', label: 'CM', positionGroup: 'Midfielder', x: 63, y: 54 },
    { key: 'RM', label: 'RM', positionGroup: 'Midfielder', x: 85, y: 50 },
    { key: 'ST1', label: 'ST', positionGroup: 'Forward', x: 37, y: 26 },
    { key: 'ST2', label: 'ST', positionGroup: 'Forward', x: 63, y: 26 },
  ],
  '4-3-3': [
    { ...GK, x: 50, y: 90 },
    { key: 'LB', label: 'LB', positionGroup: 'Defender', x: 15, y: 72 },
    { key: 'CB1', label: 'CB', positionGroup: 'Defender', x: 37, y: 76 },
    { key: 'CB2', label: 'CB', positionGroup: 'Defender', x: 63, y: 76 },
    { key: 'RB', label: 'RB', positionGroup: 'Defender', x: 85, y: 72 },
    { key: 'CM1', label: 'CM', positionGroup: 'Midfielder', x: 30, y: 52 },
    { key: 'CM2', label: 'CM', positionGroup: 'Midfielder', x: 50, y: 56 },
    { key: 'CM3', label: 'CM', positionGroup: 'Midfielder', x: 70, y: 52 },
    { key: 'LW', label: 'LW', positionGroup: 'Forward', x: 18, y: 28 },
    { key: 'ST', label: 'ST', positionGroup: 'Forward', x: 50, y: 22 },
    { key: 'RW', label: 'RW', positionGroup: 'Forward', x: 82, y: 28 },
  ],
  '3-5-2': [
    { ...GK, x: 50, y: 90 },
    { key: 'CB1', label: 'CB', positionGroup: 'Defender', x: 25, y: 76 },
    { key: 'CB2', label: 'CB', positionGroup: 'Defender', x: 50, y: 78 },
    { key: 'CB3', label: 'CB', positionGroup: 'Defender', x: 75, y: 76 },
    { key: 'LWB', label: 'LWB', positionGroup: 'Midfielder', x: 10, y: 54 },
    { key: 'CM1', label: 'CM', positionGroup: 'Midfielder', x: 32, y: 54 },
    { key: 'CM2', label: 'CM', positionGroup: 'Midfielder', x: 50, y: 50 },
    { key: 'CM3', label: 'CM', positionGroup: 'Midfielder', x: 68, y: 54 },
    { key: 'RWB', label: 'RWB', positionGroup: 'Midfielder', x: 90, y: 54 },
    { key: 'ST1', label: 'ST', positionGroup: 'Forward', x: 37, y: 26 },
    { key: 'ST2', label: 'ST', positionGroup: 'Forward', x: 63, y: 26 },
  ],
  '3-4-3': [
    { ...GK, x: 50, y: 90 },
    { key: 'CB1', label: 'CB', positionGroup: 'Defender', x: 25, y: 76 },
    { key: 'CB2', label: 'CB', positionGroup: 'Defender', x: 50, y: 78 },
    { key: 'CB3', label: 'CB', positionGroup: 'Defender', x: 75, y: 76 },
    { key: 'LM', label: 'LM', positionGroup: 'Midfielder', x: 15, y: 52 },
    { key: 'CM1', label: 'CM', positionGroup: 'Midfielder', x: 37, y: 55 },
    { key: 'CM2', label: 'CM', positionGroup: 'Midfielder', x: 63, y: 55 },
    { key: 'RM', label: 'RM', positionGroup: 'Midfielder', x: 85, y: 52 },
    { key: 'LW', label: 'LW', positionGroup: 'Forward', x: 20, y: 28 },
    { key: 'ST', label: 'ST', positionGroup: 'Forward', x: 50, y: 22 },
    { key: 'RW', label: 'RW', positionGroup: 'Forward', x: 80, y: 28 },
  ],
  '4-2-3-1': [
    { ...GK, x: 50, y: 90 },
    { key: 'LB', label: 'LB', positionGroup: 'Defender', x: 15, y: 72 },
    { key: 'CB1', label: 'CB', positionGroup: 'Defender', x: 37, y: 76 },
    { key: 'CB2', label: 'CB', positionGroup: 'Defender', x: 63, y: 76 },
    { key: 'RB', label: 'RB', positionGroup: 'Defender', x: 85, y: 72 },
    { key: 'CDM1', label: 'CDM', positionGroup: 'Midfielder', x: 37, y: 60 },
    { key: 'CDM2', label: 'CDM', positionGroup: 'Midfielder', x: 63, y: 60 },
    { key: 'LAM', label: 'LAM', positionGroup: 'Midfielder', x: 22, y: 42 },
    { key: 'CAM', label: 'CAM', positionGroup: 'Midfielder', x: 50, y: 38 },
    { key: 'RAM', label: 'RAM', positionGroup: 'Midfielder', x: 78, y: 42 },
    { key: 'ST', label: 'ST', positionGroup: 'Forward', x: 50, y: 22 },
  ],
  '4-1-4-1': [
    { ...GK, x: 50, y: 90 },
    { key: 'LB', label: 'LB', positionGroup: 'Defender', x: 15, y: 72 },
    { key: 'CB1', label: 'CB', positionGroup: 'Defender', x: 37, y: 76 },
    { key: 'CB2', label: 'CB', positionGroup: 'Defender', x: 63, y: 76 },
    { key: 'RB', label: 'RB', positionGroup: 'Defender', x: 85, y: 72 },
    { key: 'CDM', label: 'CDM', positionGroup: 'Midfielder', x: 50, y: 62 },
    { key: 'LM', label: 'LM', positionGroup: 'Midfielder', x: 15, y: 44 },
    { key: 'CM1', label: 'CM', positionGroup: 'Midfielder', x: 37, y: 46 },
    { key: 'CM2', label: 'CM', positionGroup: 'Midfielder', x: 63, y: 46 },
    { key: 'RM', label: 'RM', positionGroup: 'Midfielder', x: 85, y: 44 },
    { key: 'ST', label: 'ST', positionGroup: 'Forward', x: 50, y: 22 },
  ],
}

export const FORMATION_OPTIONS = Object.keys(FORMATION_PRESETS)

/**
 * Map API-Football position strings to a position group.
 * API-Football uses both short (G, D, M, F) and long (Goalkeeper, Defender, …) forms.
 */
export function getPositionGroup(position) {
  if (!position) return 'Unknown'
  const p = position.trim()
  if (/^(G|Goalkeeper|Attacker.*keeper)$/i.test(p)) return 'Goalkeeper'
  if (/^(D|Defender)$/i.test(p)) return 'Defender'
  if (/^(M|Midfielder)$/i.test(p)) return 'Midfielder'
  if (/^(F|Forward|Attacker)$/i.test(p)) return 'Forward'
  return 'Unknown'
}
