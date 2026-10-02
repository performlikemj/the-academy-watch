import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { transformWithOxc } from 'vite'
import { GOL_MAINTENANCE_MESSAGE } from '../src/lib/gol-maintenance.js'

const hooks = { useId: () => 'maintenance-status', useEffect() {}, useRef: () => ({ current: null }), useState: initial => [initial, () => {}] }
const Button = ({ children, ...props }) => React.createElement('button', props, children)
const Icon = () => null
async function component(file, name, scope) {
  const source = readFileSync(new URL(`../src/components/gol/${file}`, import.meta.url), 'utf8')
    .replace(/^import .*\n/gm, '').replaceAll('export function', 'function')
  const transformed = await transformWithOxc(source, file, { jsx: { runtime: 'classic' } })
  return new Function('scope', `with (scope) { ${transformed.code}; return ${name} }`)({ React, ...hooks, ...scope })
}
const GolSuggestions = await component('GolSuggestions.jsx', 'GolSuggestions', {})
const GolMaintenance = await component('GolMaintenance.jsx', 'GolMaintenance', { GOL_MAINTENANCE_MESSAGE })
const GolInput = await component('GolInput.jsx', 'GolInput', { Button, Send: Icon, Square: Icon })
const GolChatWindow = await component('GolChatWindow.jsx', 'GolChatWindow', {
  GolMaintenance, GolInput, Button, GolMessage: ({ message }) => React.createElement('p', null, message.content),
  GolSuggestions, PlayerPreviewDrawer: Icon,
  CircleDollarSign: Icon, Download: Icon, FileDown: Icon, Loader2: Icon, LogIn: Icon, RotateCcw: Icon, Trash2: Icon,
})

for (const creditUiLit of [false, true]) {
  test(`maintenance switch for the assistant renders in the conversation with billing ${creditUiLit}`, () => {
    for (const messages of [[], [{ id: 'stored', role: 'assistant', content: 'Stored answer' }]]) {
      const html = renderToStaticMarkup(React.createElement(GolChatWindow, {
        messages, maintenance: true, accessState: 'available', creditUiLit,
        freeQuestionsRemaining: 3, creditBalance: 7,
      }))
      assert.match(html, /id="maintenance-status" role="status" aria-live="polite" aria-atomic="true"><\/div>/)
      assert.match(html, /aria-describedby="maintenance-status"/)
      assert.ok(html.includes('Check availability'))
      assert.match(html, /role="status"/)
      assert.match(html, /<input[^>]*disabled=""/)
      assert.equal(html.includes('3 free questions left'), creditUiLit)
      assert.ok(!html.includes('role="alert"'))
      assert.ok(!html.includes('GOL Assistant'))
    }
  })
}

test('maintenance switch for the assistant keeps the available conversation enabled', () => {
  const html = renderToStaticMarkup(React.createElement(GolChatWindow, {
    messages: [], maintenance: false, accessState: 'available', creditUiLit: false,
  }))
  assert.ok(html.includes('GOL Assistant'))
  assert.ok(!html.includes(GOL_MAINTENANCE_MESSAGE))
  assert.doesNotMatch(html, /<input[^>]*disabled=""/)
})

test('maintenance leaves a failed charged question recovery control visible', () => {
  const html = renderToStaticMarkup(React.createElement(GolChatWindow, {
    messages: [{ id: 'failed', role: 'assistant', content: 'The answer was interrupted before it finished.' }],
    maintenance: true, canRetry: true, accessState: 'available', creditUiLit: true,
    freeQuestionsRemaining: 2, creditBalance: 7,
  }))
  assert.match(html, />Retry<\/button>/)
  assert.match(html, /<input[^>]*disabled=""/)
})

test('a maintenance response hides Retry until availability recovers', () => {
  const messages = [{ id: 'paused', role: 'assistant', content: GOL_MAINTENANCE_MESSAGE, maintenance: true }]
  for (const maintenance of [true, false]) {
    const html = renderToStaticMarkup(React.createElement(GolChatWindow, {
      messages, maintenance, canRetry: true, accessState: 'available', creditUiLit: true,
      freeQuestionsRemaining: 3, creditBalance: 7,
    }))
    assert.equal(/>Retry<\/button>/.test(html), !maintenance)
  }
})
