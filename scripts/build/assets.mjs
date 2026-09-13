import { cp, mkdir, rm } from 'node:fs/promises'
import { resolve, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const repository = fileURLToPath(new URL('../../', import.meta.url))
const build = resolve(repository, 'var/build')
const destination = resolve(build, 'static')
if (relative(build, destination) !== 'static') throw new Error('Invalid static build directory.')

// Only disposable build output is replaced; uploads and collectstatic output stay separate.
await mkdir(build, { recursive: true })
await rm(destination, { recursive: true, force: true })
await cp(resolve(repository, 'public'), destination, { recursive: true })
console.log('Public assets copied to var/build/static; source files stay in assets/.')
