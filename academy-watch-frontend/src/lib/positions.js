const CODES = new Map(Object.entries({
  g: 'GK', gk: 'GK', goalkeeper: 'GK', 'goal keeper': 'GK', keeper: 'GK', goalie: 'GK',
  d: 'DEF', defender: 'DEF', defence: 'DEF', defense: 'DEF',
  rb: 'RB', 'right back': 'RB', 'right full back': 'RB',
  cb: 'CB', 'centre back': 'CB', 'center back': 'CB', 'central defender': 'CB', 'left centre back': 'CB', 'right centre back': 'CB', 'left center back': 'CB', 'right center back': 'CB', 'centre half': 'CB', 'center half': 'CB', sweeper: 'SW',
  lb: 'LB', 'left back': 'LB', 'left full back': 'LB',
  'full back': 'FB', fullback: 'FB', 'wing back': 'WB', wingback: 'WB',
  rwb: 'RWB', 'right wing back': 'RWB', 'right wingback': 'RWB', lwb: 'LWB', 'left wing back': 'LWB', 'left wingback': 'LWB',
  'defensive mid': 'DM',
  'holding mid': 'DM',
  'central mid': 'CM',
  'centre mid': 'CM',
  'center mid': 'CM',
  'attacking mid': 'AM',
  'right mid': 'RM',
  'left mid': 'LM',
  m: 'MID', midfielder: 'MID', midfield: 'MID',
  dm: 'DM', cdm: 'DM', 'defensive midfielder': 'DM', 'defensive midfield': 'DM',
  'holding midfielder': 'DM', 'holding midfield': 'DM',
  cm: 'CM', 'central midfielder': 'CM', 'central midfield': 'CM', 'centre midfielder': 'CM', 'centre midfield': 'CM', 'center midfielder': 'CM', 'center midfield': 'CM',
  am: 'AM', cam: 'AM', 'attacking midfielder': 'AM', 'attacking midfield': 'AM',
  'number 10': 'AM', 'no 10': 'AM',
  rm: 'RM', 'right midfielder': 'RM', 'right midfield': 'RM', lm: 'LM', 'left midfielder': 'LM', 'left midfield': 'LM',
  rw: 'RW', 'right winger': 'RW', 'right wing': 'RW',
  lw: 'LW', 'left winger': 'LW', 'left wing': 'LW', winger: 'W',
  f: 'FW', fw: 'FW', forward: 'FW', attacker: 'FW',
  st: 'ST', striker: 'ST', cf: 'CF', 'centre forward': 'CF', 'center forward': 'CF',
  ss: 'SS', 'second striker': 'SS',
}))

export function positionAbbreviation(position) {
  const value = String(position ?? '').trim().toLowerCase().replace(/[-_]/g, ' ').replace(/\s+/g, ' ')
  if (!value) return '—'
  if (CODES.has(value)) return CODES.get(value)
  // A stated list keeps its first position, rather than inventing a new code.
  const first = value.split(/[,/;]|\s+&\s+/)[0].trim()
  return CODES.get(first) || first.toUpperCase().slice(0, 3)
}
