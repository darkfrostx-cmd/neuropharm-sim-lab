#!/usr/bin/env node
import { spawn } from 'node:child_process'

const args = process.argv.slice(2)
const cleanedArgs = args.filter((arg) => arg !== '--watch=false' && arg !== '--watch')

function run(command, commandArgs) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, commandArgs, { stdio: 'inherit', shell: process.platform === 'win32' })
    child.on('exit', (code) => {
      if (code === 0) {
        resolve()
      } else {
        reject(new Error(`${command} exited with code ${code}`))
      }
    })
  })
}

// Allow skipping Playwright e2e in constrained environments
const runE2E = process.env.SKIP_E2E !== '1'
const shouldInstallBrowsers = runE2E && process.env.PLAYWRIGHT_SKIP_BROWSER_INSTALL !== '1'

try {
  const vitestPool = process.env.VITEST_POOL ? ['--pool', process.env.VITEST_POOL] : []
  await run('npx', ['vitest', 'run', ...vitestPool, ...cleanedArgs])

  if (runE2E) {
    if (shouldInstallBrowsers) {
      await run('npx', ['playwright', 'install', '--with-deps', 'chromium'])
    }
    await run('npx', ['playwright', 'test', ...cleanedArgs])
  }
} catch (error) {
  console.error(error)
  process.exit(1)
}
