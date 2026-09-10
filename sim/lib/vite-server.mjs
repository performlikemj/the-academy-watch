// Opt-in launcher: inline cacheDir preserves the frontend's normal Vite config.
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const frontendDir = fileURLToPath(new URL('../../academy-watch-frontend/', import.meta.url))

export function viteOptions(host, port, cacheDir) {
  if (!cacheDir || !path.isAbsolute(cacheDir)) {
    throw new Error('SIM_VITE_CACHE_DIR must be an absolute path.')
  }
  return {
    root: frontendDir,
    cacheDir,
    server: { host, port: Number(port), strictPort: true },
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const require = createRequire(path.join(frontendDir, 'package.json'))
  const { createServer } = await import(pathToFileURL(require.resolve('vite')).href)
  const server = await createServer(viteOptions(process.argv[2], process.argv[3], process.env.SIM_VITE_CACHE_DIR))
  await server.listen()
  server.printUrls()
}
