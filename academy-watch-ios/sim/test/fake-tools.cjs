// Offline preflight doubles. Never invoke real Apple tools.
const fs = require('node:fs')
const path = require('node:path')
const tool = path.basename(process.argv[1])
const args = process.argv.slice(2)
const root = process.env.SIM_TEST_ROOT
fs.appendFileSync(path.join(root, 'calls.jsonl'), `${JSON.stringify({ tool, args })}\n`)

if (tool === 'xcrun') {
  const [query, mode] = (process.env.SIM_TEST_SIMCTL_HANG || '').split(':')
  const marker = path.join(root, 'simctl-hung')
  if (query && args.join(' ').startsWith(`simctl ${query}`) &&
      (mode === 'always' || !fs.existsSync(marker))) {
    fs.writeFileSync(marker, '')
    setInterval(() => {}, 1000)
  } else if (args.join(' ') === 'simctl list runtimes') {
    console.log('iOS 27.0 (27.0 - fake) - com.apple.CoreSimulator.SimRuntime.iOS-27-0')
  } else throw new Error(`unexpected xcrun: ${args}`)
} else if (tool === 'xcodebuild' && args.includes('build-for-testing')) {
  // Reaching this boundary proves preflight recovered; no build is needed.
  process.exit(1)
} else throw new Error(`unexpected tool: ${tool} ${args}`)
