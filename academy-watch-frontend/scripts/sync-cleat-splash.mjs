import fs from 'node:fs'
import { CLEAT_BOOT, CLEAT_CSS } from '../src/lib/cleat-loader.js'

// Run after changing the shared loader primitives. No boot-time script or asset fetch.
const file = new URL('../index.html', import.meta.url)
let html = fs.readFileSync(file, 'utf8')
const splash = `<!-- cleat-splash:start -->\n    <style>body{margin:0;background:#F3F0E8}${CLEAT_CSS}#root>.cleat-loader{min-height:100dvh;background:#F3F0E8}</style>\n    <div id="root">${CLEAT_BOOT}</div>\n    <!-- cleat-splash:end -->`
html = html.includes('<!-- cleat-splash:start -->')
  ? html.replace(/<!-- cleat-splash:start -->[\s\S]*?<!-- cleat-splash:end -->/, splash)
  : html.replace('<div id="root"></div>', splash)
fs.writeFileSync(file, html)
