const CODES = {
  g: 'GK', gk: 'GK', goalkeeper: 'GK', keeper: 'GK',
  d: 'DEF', defender: 'DEF', defence: 'DEF', defense: 'DEF',
  rb: 'RB', 'right back': 'RB', 'right full back': 'RB',
  cb: 'CB', 'centre back': 'CB', 'center back': 'CB', 'central defender': 'CB',
  lb: 'LB', 'left back': 'LB', 'left full back': 'LB',
  rwb: 'RWB', 'right wing back': 'RWB', lwb: 'LWB', 'left wing back': 'LWB',
  m: 'MID', midfielder: 'MID', midfield: 'MID',
  dm: 'DM', cdm: 'DM', 'defensive midfielder': 'DM', 'defensive midfield': 'DM',
  cm: 'CM', 'central midfielder': 'CM', 'central midfield': 'CM', 'centre midfielder': 'CM', 'center midfielder': 'CM',
  am: 'AM', cam: 'AM', 'attacking midfielder': 'AM', 'attacking midfield': 'AM',
  rm: 'RM', 'right midfielder': 'RM', lm: 'LM', 'left midfielder': 'LM',
  rw: 'RW', 'right winger': 'RW', 'right wing': 'RW',
  lw: 'LW', 'left winger': 'LW', 'left wing': 'LW', winger: 'W',
  f: 'FW', fw: 'FW', forward: 'FW', attacker: 'FW',
  st: 'ST', striker: 'ST', cf: 'CF', 'centre forward': 'CF', 'center forward': 'CF',
  ss: 'SS', 'second striker': 'SS',
}

export function positionAbbreviation(position) {
  const value = String(position ?? '').trim().toLowerCase().replace(/[-_]/g, ' ').replace(/\s+/g, ' ')
  if (CODES[value]) return CODES[value]
  // A stated list keeps its first position, rather than inventing a new code.
  const first = value.split(/[,/;]|\s+&\s+/)[0].trim()
  return CODES[first] || '—'
}
