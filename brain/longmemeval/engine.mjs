/**
 * LongMemEval-S through the Context engine: the LoCoMo engine, unchanged, frozen, untuned.
 *
 * Every question's haystack becomes one engine index — its turns with the vectors
 * retrieve.mjs cached (same embedder, same `role: content` text), BM25 over the
 * turn bodies, each turn dated by its session's `haystack_dates`, adjacency within
 * a session — and `retrieve()` runs with `frozenConfig('+iterative hops')`: the
 * weights and budgets the LoCoMo dev sweep froze. Nothing here was tuned on
 * LongMemEval, so there is no dev split to declare; all 500 questions are the
 * report. LongMemEval ships no fact layer, so the fact, entity and typed-graph
 * generators have nothing to propose and the second hop is asked with the top two
 * turns (hopText's no-facts path).
 *
 * A session scores its best turn under the engine's one scorer: the fused score
 * for a turn a generator nominated, its dense similarity for a turn none did (a
 * contribution not made is zero). That is turn-max with the engine's score in
 * place of the cosine, so the two rows differ only in the engine. Scored exactly
 * as retrieve.mjs scores: R@5/10 ALL and ANY over `answer_session_ids`, MRR, per
 * type; the 30 abstention items (`_abs`) stay in their types, as there, and are
 * also shown as their own slice.
 *
 *   EMBED=all-minilm node longmemeval/retrieve.mjs        # the cache, and the baseline
 *   node longmemeval/engine.mjs --embed=minilm            # this row → runs/longmemeval-all-context-minilm/
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { execSync } from 'node:child_process'
import { retrieve, frozenConfig, hopText, qvecMany, ixs } from '../context.mjs'
import { ci, quantile } from '../metrics.mjs'
import { digest } from '../digest.mjs'

const EMBED = process.env.EMBED_MODEL
if (!EMBED) { console.error('pass --embed=<name> (context.mjs maps minilm → all-minilm), the embedder retrieve.mjs cached'); process.exit(1) }
const DATA = new URL('../data/longmemeval/', import.meta.url).pathname
const CACHE = DATA + `vec-${EMBED.replace(/[^a-z0-9.-]/gi, '_')}.f32`
if (!existsSync(CACHE)) { console.error(`no ${CACHE} — run EMBED=${EMBED} node longmemeval/retrieve.mjs first`); process.exit(1) }
const items = JSON.parse(readFileSync(DATA + 'longmemeval_s', 'utf8'))
// the engine's BM25, taken from a built index so there is one BM25
const BM25 = ixs[0].bm25.constructor

// the cache's order, rebuilt the way retrieve.mjs wrote it: unique sessions in first-seen order, turn by turn, then questions
const sessions = new Map()
for (const it of items) it.haystack_session_ids.forEach((sid, i) => { if (!sessions.has(sid)) sessions.set(sid, it.haystack_sessions[i]) })
const h = JSON.parse(readFileSync(CACHE + '.json', 'utf8')), buf = readFileSync(CACHE), f = new Float32Array(buf.buffer, buf.byteOffset, buf.byteLength / 4)
const vecOf = (n) => f.subarray(n * h.dim, (n + 1) * h.dim)
const first = new Map(); let n = 0
for (const [sid, turns] of sessions) { first.set(sid, n); n += turns.length }
if (n !== h.turns || items.length !== h.questions) { console.error(`cache holds ${h.turns} turns / ${h.questions} questions, the data ${n} / ${items.length}`); process.exit(1) }

const date = (s) => { const m = s?.match(/^(\d{4})\/(\d{2})\/(\d{2})/); return m ? { y: +m[1], m: +m[2], d: +m[3] } : null }
const dot = (a, b) => { let s = 0; for (let i = 0; i < a.length; i++) s += a[i] * b[i]; return s }

/** One haystack as an engine index. No fact layer: the fact-driven generators propose nothing. */
function index(q, qi) {
  const turns = [], seen = new Set()
  q.haystack_session_ids.forEach((sid, si) => { if (seen.has(sid)) return; seen.add(sid)
    sessions.get(sid).forEach((t, j) => turns.push({ id: `${sid}#${j}`, i: turns.length, sess: sid, when: date(q.haystack_dates[si]), v: vecOf(first.get(sid) + j), text: `${t.role}: ${t.content}`, body: t.content, speaker: t.role })) })
  return { ci: qi, turns, byId: new Map(turns.map((t) => [t.id, t])), facts: [], citing: new Map(), byEntity: new Map(), aliases: new Map(), speakers: new Set(['user', 'assistant']), bm25: new BM25(turns.map((t) => t.body)), answers: new Map() }
}

const cfg = frozenConfig('+iterative hops'), frozen = JSON.parse(readFileSync(new URL('../ablations/frozen-locomo.json', import.meta.url), 'utf8'))
console.log(`${items.length} questions · embed ${EMBED} · engine row "+iterative hops", frozen on LoCoMo dev at ${frozen.commit} (engine ${frozen.engine}), no tuning here`)
const KS = [5, 10], RANKERS = ['tm', 'ctx'], started = new Date(), t0 = Date.now()
// the second hop's queries, embedded in batches first, as prepare() does on LoCoMo, so latency is retrieval alone
const unit = (v) => { const n = Math.sqrt(dot(v, v)) || 1; return v.map((x) => x / n) }
await qvecMany(items.map((q, qi) => { const ix = index(q, qi), qv = unit(vecOf(h.turns + qi)), d = ix.turns.map((t) => dot(qv, t.v))
  return hopText(ix, q, cfg, [...d.keys()].sort((a, b) => d[b] - d[a]), null) }))
const rows = [], traces = [], latency = []
for (const [qi, q] of items.entries()) {
  const ix = index(q, qi), qv = vecOf(h.turns + qi), gold = q.answer_session_ids
  const dense = ix.turns.map((t) => dot(qv, t.v))
  const r = await retrieve(ix, { question: q.question, v: qv }, cfg); latency.push(r.ms)
  // ranked over the haystack list as retrieve.mjs ranks it: 15 haystacks list a session twice, and both copies take a place
  const score = (ranker) => { const best = new Map(q.haystack_session_ids.map((sid) => [sid, -Infinity]))
    ix.turns.forEach((t, i) => { const s = ranker === 'ctx' ? (r.contrib.get(i)?.score ?? dense[i]) : dense[i]; if (s > best.get(t.sess)) best.set(t.sess, s) })
    return q.haystack_session_ids.map((sid) => [sid, best.get(sid)]).sort((a, b) => b[1] - a[1]).map(([sid]) => sid) }
  const row = { qid: q.question_id, type: q.question_type, abs: q.question_id.endsWith('_abs') }
  const trace = { qid: q.question_id, type: q.question_type, gold }
  for (const ranker of RANKERS) { const ranked = score(ranker), G = new Set(gold), at = ranked.findIndex((s) => G.has(s))
    row[`${ranker}:mrr`] = at < 0 ? 0 : 1 / (at + 1)
    for (const k of KS) { const top = new Set(ranked.slice(0, k)); const hits = gold.filter((g) => top.has(g)).length; row[`${ranker}:all@${k}`] = Number(hits === gold.length); row[`${ranker}:any@${k}`] = Number(hits > 0) }
    trace[ranker] = ranked.slice(0, 10) }
  trace.examined = r.examined; rows.push(row); traces.push(trace)
  if (qi % 25 === 0) process.stderr.write(`\r  ${qi + 1}/${items.length}  ${((Date.now() - t0) / 1000).toFixed(0)}s`)
}
const wall = (Date.now() - t0) / 1000
process.stderr.write('\n')

// the baseline's shape (counts, keyed ranker@k) beside a summary of rates with intervals
const slices = { ALL: rows }; for (const r of rows) { (slices[r.type] ??= []).push(r); if (r.abs) (slices.abstention ??= []).push(r) }
const tally = {}, summary = {}
for (const [type, rs] of Object.entries(slices)) {
  const t = tally[type] = { n: rs.length, mrr: {}, all: {}, any: {} }
  for (const ranker of RANKERS) { t.mrr[ranker] = rs.reduce((a, r) => a + r[`${ranker}:mrr`], 0)
    for (const k of KS) for (const kind of ['all', 'any']) t[kind][`${ranker}@${k}`] = rs.reduce((a, r) => a + r[`${ranker}:${kind}@${k}`], 0) }
  summary[type] = { n: rs.length, ...Object.fromEntries(KS.flatMap((k) => ['all', 'any'].map((kind) => [`${kind}@${k}`, ci(rs.map((r) => r[`ctx:${kind}@${k}`]))]))), mrr: ci(rs.map((r) => r['ctx:mrr'])),
    'cosine all@5': ci(rs.map((r) => r['tm:all@5'])), 'cosine all@10': ci(rs.map((r) => r['tm:all@10'])), 'cosine mrr': ci(rs.map((r) => r['tm:mrr'])) }
}
// the cosine column is the baseline recomputed on the same cache; it has to agree with the committed file count for count
const base = JSON.parse(readFileSync(new URL(`./baseline-${EMBED.replace(/[^a-z0-9.-]/gi, '_')}.json`, import.meta.url), 'utf8'))
const differ = Object.entries(base.tally).flatMap(([type, b]) => ['all', 'any'].flatMap((kind) => KS.map((k) => `tm@${k}`).filter((key) => b[kind][key] !== tally[type]?.[kind][key]).map((key) => `${type} ${kind} ${key}`)))
if (differ.length) { console.error(`cosine column disagrees with baseline-${EMBED}.json: ${differ.join(', ')}`); process.exit(1) }
const p = (x) => (x * 100).toFixed(1).padStart(5)
console.log(`\n── LongMemEval-S · session recall · ${EMBED} · cosine turn-max vs the engine ──`)
console.log(`type                        n    cosine R@5 all/any  R@10 all/any  MRR     engine R@5 all/any  R@10 all/any  MRR`)
for (const [type, t] of Object.entries(tally)) { const c = (r, kind, k) => p(t[kind][`${r}@${k}`] / t.n)
  console.log(`${type.padEnd(26)} ${String(t.n).padStart(4)}    ${c('tm', 'all', 5)}/${c('tm', 'any', 5)}   ${c('tm', 'all', 10)}/${c('tm', 'any', 10)}  ${(t.mrr.tm / t.n).toFixed(3)}    ${c('ctx', 'all', 5)}/${c('ctx', 'any', 5)}   ${c('ctx', 'all', 10)}/${c('ctx', 'any', 10)}  ${(t.mrr.ctx / t.n).toFixed(3)}`) }
const latency_ms = { p50: quantile(latency, 0.5), p95: quantile(latency, 0.95) }
console.log(`engine retrieval p50 ${latency_ms.p50.toFixed(2)} ms · p95 ${latency_ms.p95.toFixed(2)} ms · wall ${wall.toFixed(0)} s (query-time hop embeddings included)`)

const commit = (() => { try { return execSync('git rev-parse --short=12 HEAD', { cwd: new URL('.', import.meta.url).pathname }).toString().trim() } catch { return 'unknown' } })()
const dir = new URL(`../runs/longmemeval-all-context-${process.argv.find((a) => a.startsWith('--embed='))?.slice(8) ?? EMBED}/`, import.meta.url); mkdirSync(dir, { recursive: true })
writeFileSync(new URL('metrics.json', dir), JSON.stringify({ row: '+iterative hops', cfg, split: 'all', k: KS, embed: EMBED, frozen: { commit: frozen.commit, engine: frozen.engine, objective: 'LoCoMo dev; no tuning on LongMemEval' }, summary, tally, latency_ms }, null, 1))
writeFileSync(new URL('traces.jsonl', dir), traces.map((x) => JSON.stringify(x)).join('\n'))
writeFileSync(new URL('meta.json', dir), JSON.stringify({ commit, ...digest(new URL('../', import.meta.url)), embedding: EMBED, dataset: 'xiaowu0162/longmemeval longmemeval_s', k: KS, split: 'all', when: started.toISOString(), wall_seconds: Math.round(wall), questions: items.length, answered: rows.length, finished: new Date().toISOString() }, null, 1))
console.log(`wrote ${dir.pathname}`)
