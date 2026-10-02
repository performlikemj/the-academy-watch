import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import test from 'node:test'

const workflow = fs.readFileSync(new URL('../../.github/workflows/ci.yml', import.meta.url), 'utf8')
const job = name => workflow.match(new RegExp(`^  ${name}:\\n([\\s\\S]*?)(?=^  [a-z-]+:|$(?![\\s\\S]))`, 'm'))?.[1]

for (const name of ['frontend-build', 'backend-lint', 'backend-tests', 'frontend-tests']) {
  test(`${name} follows N4: skip drafts, run ready PRs and main`, () => {
    const condition = job(name)?.match(/^    if: (.+)$/m)?.[1]
    assert.ok(condition, `${name} requires a job-level draft guard`)
    for (const [eventName, draft, expected] of [['pull_request', true, false], ['pull_request', false, true], ['push', undefined, true]]) {
      const actual = vm.runInNewContext(condition, { github: { event_name: eventName, event: { pull_request: { draft } } } })
      assert.equal(actual, expected, `${eventName}, draft=${draft}`)
    }
  })
}

test('dependency security still scans draft PRs', () => {
  assert.ok(job('dependency-security'))
  assert.doesNotMatch(job('dependency-security'), /^    if:/m)
  assert.match(workflow, /types: \[opened, synchronize, reopened, ready_for_review\]/)
  assert.match(workflow, /push:\n    branches: \[main\]/)
})
