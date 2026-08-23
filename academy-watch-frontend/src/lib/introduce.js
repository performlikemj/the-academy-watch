// Copy + error mapping for the Introduce dialog. Pure, so it is unit-tested without React.

export const MESSAGE_MAX = 2000
export const ATTESTATION_TEXT = 'I confirm I already have the current club’s permission to approach this player.'

export function describeIntroduceError(err) {
  const code = err?.body?.code
  const status = err?.status
  if (code === 'attestation_required') {
    return { kind: 'attestation', message: err?.body?.error || 'The club’s permission is required before continuing.' }
  }
  if (code === 'scout_not_verified' || status === 403 && !code) {
    return { kind: 'verify', message: 'Only verified scouts can introduce themselves.', href: '/scout/verification' }
  }
  if (code === 'player_not_claimable') {
    return { kind: 'blocked', message: 'This player isn’t available for contact.' }
  }
  if (code === 'active_request_exists') {
    return { kind: 'blocked', message: 'You already have an open request with this player.' }
  }
  if (code === 'decline_cooldown_active') {
    const days = err?.body?.cooldown_days
    return { kind: 'blocked', message: days ? `A recent request was declined — try again in ${days} days.` : 'A recent request was declined — try again later.' }
  }
  if (status === 401) {
    return { kind: 'verify', message: 'Sign in to introduce yourself.', href: null }
  }
  return { kind: 'error', message: err?.body?.error || err?.message || 'Could not send. Try again.' }
}

export function canSend(message, attestationRequired, attested) {
  const trimmed = String(message || '').trim()
  if (!trimmed || trimmed.length > MESSAGE_MAX) return false
  if (attestationRequired && !attested) return false
  return true
}
