import { APIService } from '../lib/api.js'

export function buildAuthSnapshot(detail = {}) {
  const token = detail.token !== undefined ? detail.token : APIService.userToken
  const isAdmin = detail.isAdmin !== undefined ? detail.isAdmin : APIService.isAdmin()
  const isJournalist = detail.isJournalist !== undefined ? detail.isJournalist : APIService.isJournalist()
  const isCurator = detail.isCurator !== undefined ? detail.isCurator : APIService.isCurator()
  const hasApiKey = detail.hasApiKey !== undefined ? detail.hasApiKey : !!APIService.adminKey
  const hasCuratorKey = detail.hasCuratorKey !== undefined ? detail.hasCuratorKey : !!APIService.curatorKey
  const displayName = detail.displayName !== undefined ? detail.displayName : APIService.displayName
  const displayNameConfirmed = detail.displayNameConfirmed !== undefined ? detail.displayNameConfirmed : APIService.displayNameConfirmed()
  return {
    token,
    isAdmin,
    isJournalist,
    isCurator,
    hasApiKey,
    hasCuratorKey,
    displayName,
    displayNameConfirmed,
    role: detail.role || (isAdmin ? 'admin' : (isJournalist ? 'journalist' : (isCurator ? 'curator' : 'user'))),
    expiresIn: detail.expiresIn || null,
  }
}
