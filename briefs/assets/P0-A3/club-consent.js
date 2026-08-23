// Copy for the club-consent page. Pure functions so the wording is unit-tested without React.

export function describeConsentDecision(decision) {
  const scoutName = decision?.scout?.name || 'A verified scout'
  const organization = decision?.scout?.organization ? ` (${decision.scout.organization})` : ''
  const program = decision?.program_name || 'your club'
  const player = decision?.player_reference || 'one of your players'
  const grant = decision?.action === 'grant'
  return {
    title: grant ? 'Allow this introduction?' : 'Decline this introduction?',
    body: `${scoutName}${organization} asked to contact ${player} at ${program}. ` + (grant
      ? 'Confirming lets the conversation open once the player also accepts.'
      : 'Confirming closes this request; the scout is told the club declined.'),
    confirmLabel: grant ? 'Allow introduction' : 'Decline introduction',
    tone: grant ? 'grant' : 'decline',
  }
}

export function describeConsentOutcome(decision) {
  if (decision === 'granted') {
    return { title: 'Introduction allowed', body: 'Thanks — the scout can message once the player accepts. Nothing else is needed from you.' }
  }
  if (decision === 'declined') {
    return { title: 'Introduction declined', body: 'Thanks — this request is closed and the scout has been told the club declined.' }
  }
  return { title: 'Decision recorded', body: 'Thanks — your answer has been recorded.' }
}

export const INVALID_LINK_COPY = {
  title: 'This link is no longer valid',
  body: 'It may have expired, already been used, or the request may have been withdrawn. If you still need to act, ask the scout to send a new request.',
}
