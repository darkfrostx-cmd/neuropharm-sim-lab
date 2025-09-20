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

try {
  await run('npx', ['vitest', 'run', ...cleanedArgs])
  await run('npx', ['playwright', 'test', ...cleanedArgs])
} catch (error) {
  console.error(error)
  process.exit(1)
}

