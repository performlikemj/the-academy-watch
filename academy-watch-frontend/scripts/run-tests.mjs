import { spawnSync } from 'node:child_process'

const extraArgs = process.argv.slice(2).filter((arg) => arg !== '--runInBand')
const result = spawnSync(process.execPath, ['--test', '--test-concurrency=1', ...extraArgs], {
  stdio: 'inherit'
})

process.exit(result.status ?? 1)
