#!/usr/bin/env bash
# Live END-TO-END max req/sec: raw fasthttp vs zip's HTTP transport, SAME hello
# handler — so the delta is zip's live framework tax. Uses a BUILT binary (go run
# orphans its child server) and curl-retry warmup (no foreground sleep).
#
# Note: zip is ZAP-native — a bare addr binds the ZAP binary transport; the bench
# binds "http://" so hey/curl can drive it apples-to-apples with fasthttp.
set -euo pipefail
cd "$(dirname "$0")"
export GOFLAGS=-mod=mod GOPRIVATE="github.com/hanzoai,github.com/luxfi,github.com/zap-proto"
DUR=${DUR:-6s}; CONN=${CONN:-100}; HEY=${HEY:-$HOME/go/bin/hey}
BIN=$(mktemp); trap 'rm -f "$BIN"' EXIT
echo ">> build"; go build -o "$BIN" .

bench() { # fw addr
  local fw=$1 addr=$2
  "$BIN" -fw "$fw" -addr "$addr" >/tmp/zipbench-$fw.log 2>&1 & local pid=$!
  command curl -s --retry 30 --retry-connrefused --retry-delay 1 -m2 -o /dev/null "http://127.0.0.1$addr/health" || true
  echo "== $fw ($addr) — $DUR @ $CONN conns =="
  "$HEY" -z "$DUR" -c "$CONN" "http://127.0.0.1$addr/health" 2>&1 | grep -E 'Requests/sec|Average:|\[200\]' || true
  kill "$pid" 2>/dev/null || true
}

bench fasthttp :8292
bench zip :8291
