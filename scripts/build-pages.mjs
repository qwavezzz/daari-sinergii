import { spawnSync } from 'node:child_process'
import { resolve } from 'node:path'

const base = process.env.PAGES_BASE_PATH || '/daari-sinergii/'
if (!/^\/(?:[a-zA-Z0-9_-]+\/)*$/.test(base))
  throw new Error('PAGES_BASE_PATH must be an absolute directory path.')
const env = {
  ...process.env,
  PAGES_BASE_PATH: base,
  VITE_STATIC_DEMO: 'true',
  VITE_BASE: `${base}static/dist/`,
  VITE_OUTPUT_DIR: 'var/pages-dist',
}
function run(command, args) {
  const result = spawnSync(command, args, { env, stdio: 'inherit' })
  if (result.error) throw result.error
  if (result.status !== 0) process.exit(result.status || 1)
}
run(process.execPath, ['node_modules/vite/bin/vite.js', 'build', '--configLoader', 'native'])
const python =
  process.env.PAGES_PYTHON ||
  resolve(process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python')
run(python, ['scripts/export-pages.py'])
