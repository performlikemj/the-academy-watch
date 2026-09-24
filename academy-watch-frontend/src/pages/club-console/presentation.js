export const initials = (name) => (name || '?').split(/\s+/).map((s) => s[0]).slice(0, 2).join('').toUpperCase()
export function positionGroup(position) {
  const text = (position || '').toLowerCase()
  if (/keeper|^gk$|^g$/.test(text)) return 'Goalkeepers'
  if (/defend|back|^d$|^cb$|^lb$|^rb$/.test(text)) return 'Defenders'
  if (/midfield|^m$|^cm$|^dm$|^am$/.test(text)) return 'Midfielders'
  if (/forward|strik|wing|attack|^f$|^st$/.test(text)) return 'Forwards'
  return 'Other'
}

export function ageDescription(member) {
  const age = member.age ?? member.age_label
  return age == null ? null : `Age ${age}`
}
