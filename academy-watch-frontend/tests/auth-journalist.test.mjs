import test from 'node:test'
import assert from 'node:assert/strict'

import { APIService } from '../src/lib/api.js'
import { buildAuthSnapshot } from '../src/context/buildAuthSnapshot.js'

const createLocalStorageMock = () => {
  const store = new Map()
  return {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => {
      store.set(key, String(value))
    },
    removeItem: (key) => {
      store.delete(key)
    },
    clear: () => store.clear(),
    key: (index) => Array.from(store.keys())[index] ?? null,
    get length() { return store.size },
  }
}

globalThis.localStorage = createLocalStorageMock()

const resetAuthState = () => {
  localStorage.clear()
  APIService.userToken = null
  APIService.isAdminFlag = false
  APIService.isJournalistFlag = false
  APIService.displayName = null
  APIService.displayNameConfirmedFlag = false
  APIService.adminKey = null
}

test('login result persists journalist flag', () => {
  resetAuthState()
  APIService._recordLoginResult({ token: 't', role: 'user', is_journalist: true })
  assert.equal(APIService.isJournalist(), true)
  assert.equal(localStorage.getItem('academy_watch_is_journalist'), 'true')
})

test('auth snapshot includes journalist flag from APIService', () => {
  resetAuthState()
  APIService.setIsJournalist(true)
  const snapshot = buildAuthSnapshot()
  assert.equal(snapshot.isJournalist, true)
})
