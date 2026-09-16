/**
 * One row of a lane's table, and — when `BENCH_JSON` names a file — one entry in
 * it. The shell lanes have this in `host.sh`; these are the same two lines for
 * the ones written in node, so a row reaches the terminal and the file by the
 * same call and the two cannot disagree.
 *
 * The value is a string. A lane says "455 MB (477 bytes per agent)" as readily
 * as it says a number, and a reader that wants a number knows which row it
 * asked for.
 */
import { appendFileSync, existsSync, readFileSync, writeFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { cpus, arch, loadavg } from 'node:os'

const FILE = process.env.BENCH_JSON || ''

export function say(label, value) {
  console.log(`${String(label).padEnd(26)} ${value}`)
  if (!FILE) return
  let rows = []
  if (existsSync(FILE)) {
    try {
      rows = JSON.parse(readFileSync(FILE, 'utf8'))
    } catch {
      rows = []
    }
  }
  rows.push({ label: String(label), value: String(value) })
  writeFileSync(FILE, JSON.stringify(rows, null, 1))
}

/**
 * The machine a number came from, for the lanes written in node.
 *
 * host.sh has had this for the shell lanes and MEASURED.md said "every lane that
 * measures time prints its host" — but fleet, sandbox and pricing printed none,
 * and platform.mjs harvests lane output by looking for exactly this line, so it
 * recorded no host for any of them. One sentence, true of both halves now.
 *
 * The load average is part of it: the same lane on one laptop read 601 bytes per
 * agent at load 3 and 594 at load 73, and a reader cannot tell after the fact.
 */
export function host() {
  let cpu = 'unknown', os = process.platform
  try {
    if (process.platform === 'darwin') {
      cpu = execFileSync('sysctl', ['-n', 'machdep.cpu.brand_string'], { encoding: 'utf8' }).trim()
      os = `macOS ${execFileSync('sw_vers', ['-productVersion'], { encoding: 'utf8' }).trim()}`
    } else {
      cpu = cpus()[0]?.model?.trim() || 'unknown'
    }
  } catch {}
  console.log(`host: ${cpu} · ${cpus().length} cores · ${arch()} · ${os} · load ${loadavg()[0].toFixed(2)}\n`)
}
