import { APIService } from './api.js'

let seasonDirectoryPromise

export function getSeasonDirectory() {
  if (!seasonDirectoryPromise) {
    seasonDirectoryPromise = APIService.getSeasons().catch((error) => {
      seasonDirectoryPromise = undefined
      throw error
    })
  }
  return seasonDirectoryPromise
}
