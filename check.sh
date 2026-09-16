#!/usr/bin/env bash
# Does this checkout work?
#
# Not a benchmark: a benchmark tells you what something costs, and this tells you
# whether the thing that measures it runs at all. Every lane, in the order that
# needs the least, so the first failure names the smallest missing piece.
#
#   bash check.sh                 # everything it can reach
#   CLOUD_SRC=/path bash check.sh # including the four that build the binary
#
# A lane that needs data nobody has fetched is SKIPPED and says so. A lane that
# runs and fails is a failure. The difference matters: this file existing and
# reporting "0 failed" over four skipped lanes would be the same green a broken
# suite prints.
set -uo pipefail
cd "$(dirname "$0")"
ok=0 bad=0 skip=0
run() {
  local name=$1; shift
  printf '  %-32s ' "$name"
  if "$@" >/tmp/bench-check.log 2>&1; then printf 'ok\n'; ok=$((ok + 1))
  else printf 'FAIL — %s\n' "$(grep -vE '_nvm_lazy|^ld: warning' /tmp/bench-check.log | tail -1 | cut -c1-58)"; bad=$((bad + 1)); fi
}
skipped() { printf '  %-32s skipped — %s\n' "$1" "$2"; skip=$((skip + 1)); }

echo 'needs only node'
run 'fleet'          node fleet/fleet.mjs /tmp/bench-check-fleet
run 'pricing'        node pricing/pricing.mjs
run 'sandbox'        node sandbox/sandbox.mjs
run 'market'         node market/bench.mjs
run 'market tests'   node --test market/test/market.test.mjs

echo 'needs go'
if command -v go >/dev/null; then
  run 'goroutine builds' env GOWORK=off go build -o /tmp/bench-check-g ./goroutine
  run 'transport harness builds' env GOWORK=off go build -o /tmp/bench-check-t ./transport/harness
else
  skipped 'goroutine' 'no go toolchain'; skipped 'transport harness' 'no go toolchain'
fi

echo 'needs the cloud source (CLOUD_SRC, or ../cloud)'
# NAME THE SUBJECT BEFORE MEASURING IT. These five build a binary, and two
# different repositories check out as `cloud`. Against the wrong one they run
# and fail, which reads as five broken lanes instead of one wrong path — so the
# tree is printed here, above its own results.
if . ./host.sh && cloud_src >/dev/null 2>&1; then
  cloud_src >/dev/null 2>/tmp/bench-check-src; sed 's/^/  /' /tmp/bench-check-src | grep . | head -1
  run 'self'          bash self/run.sh
  run 'self/modules'  bash self/modules.sh
  run 'cipher'        bash cipher/run.sh
  run 'egress'        bash egress/run.sh
  run 'transport'     bash transport/run.sh
else
  for l in self self/modules cipher egress transport; do skipped "$l" 'no cloud source — see README'; done
fi

echo 'needs fetched data'
if [ -f brain/brain-vectors.json ]; then run 'brain tables' node brain/results.mjs
else skipped 'brain' 'no brain-vectors.json — node brain/brain.mjs first'; fi
if [ -d data/repobench-r ]; then run 'code' node code/context-code.mjs --setting=cff --split=dev --rows=full
else skipped 'code' 'no data/repobench-r'; fi

printf '\n%d ok, %d failed, %d skipped\n' "$ok" "$bad" "$skip"
[ "$bad" -eq 0 ]
