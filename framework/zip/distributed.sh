#!/usr/bin/env bash
# Distributed load: server on THIS box (spark), load driven from a separate host
# (evo, 32c x86) over the network — so the server doesn't fight the load generator
# for cores. Reveals whether you're CPU-bound (server) or I/O-bound (the link).
#
#   ./distributed.sh                 # LOADER=evo, server on spark
#   LOADER=evo CONN=1000 DUR=8s ./distributed.sh
#
# Finding on the 192.168.77.0/24 eno1 link (spark<->evo): ~194k req/sec at c=1000,
# and it gets WORSE with more conns (c4000→167k/24ms, c8000→154k/52ms) — classic
# congestion collapse. The 1GbE-class link's packet rate is the ceiling, not spark's
# 20 cores (which sit mostly idle at 194k). Loopback on spark hits 365k only because
# it shares cores with the loader; the true serving ceiling is higher than both and
# needs a faster link (10GbE/RDMA) or the tighter ZAP binary transport to expose.
set -euo pipefail
cd "$(dirname "$0")"
LOADER=${LOADER:-evo}; CONN=${CONN:-1000}; DUR=${DUR:-8s}
FH=${FH:-8392}; ZP=${ZP:-8391}
export GOFLAGS=-mod=mod GOPRIVATE="github.com/hanzoai,github.com/luxfi,github.com/zap-proto"
BIN=$(mktemp); trap 'rm -f "$BIN"; kill ${PIDS:-} 2>/dev/null || true' EXIT
go build -o "$BIN" .
"$BIN" -fw fasthttp -addr ":$FH" >/tmp/zb-fh.log 2>&1 & PIDS+=" $!"
"$BIN" -fw zip      -addr ":$ZP" >/tmp/zb-zip.log 2>&1 & PIDS+=" $!"
command curl -s --retry 20 --retry-connrefused --retry-delay 1 -m2 -o /dev/null "http://127.0.0.1:$FH/health"
ssh "$LOADER" bash -s <<EOF 2>&1 | grep -iE 'spark ip|conn=|Reqs/sec|Latency|2xx|== '
export PATH=\$HOME/go/bin:\$PATH
command -v bombardier >/dev/null || GOFLAGS= GOBIN=\$HOME/go/bin go install github.com/codesenberg/bombardier@latest >/dev/null 2>&1
SIP=\$(getent hosts spark.local | awk '{print \$1}' | head -1); echo "spark ip=\$SIP"
curl -s -m3 -o /dev/null -w "conn=%{http_code}\n" http://\$SIP:$FH/health
echo "== fasthttp (c$CONN) =="; bombardier -c $CONN -d $DUR http://\$SIP:$FH/health 2>&1 | grep -iE 'Reqs/sec|Latency|2xx'
echo "== zip http (c$CONN) =="; bombardier -c $CONN -d $DUR http://\$SIP:$ZP/health 2>&1 | grep -iE 'Reqs/sec|Latency|2xx'
EOF
