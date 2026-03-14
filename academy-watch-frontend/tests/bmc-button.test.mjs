import test from 'node:test'
import assert from 'node:assert/strict'
import { createBuyMeCoffeeScriptConfig } from '../src/components/bmcButtonConfig.js'

test('createBuyMeCoffeeScriptConfig exposes the expected button options', () => {
  const config = createBuyMeCoffeeScriptConfig()
  assert.equal(config.src, 'https://cdnjs.buymeacoffee.com/1.0.0/button.prod.min.js')
  assert.equal(config.dataset.slug, 'TheAcademyWatch')
  assert.equal(config.dataset.text, 'Buy me a coffee')
  assert.equal(config.dataset.color, '#100f0f')
  assert.equal(config.dataset.fontColor, '#ffffff')
})
