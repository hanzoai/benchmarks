#!/usr/bin/env bash
# Local N-pod cloud shard harness on k3s (installed at /usr/local/bin/k3s).
#
# Stands up the cloud unified binary as a StatefulSet with per-pod RWO PVCs and
# CLOUD_PEERS set to the 3 pod DNS names, so the org->owner shard router is LIVE
# locally — the same topology the prod cutover will use — without touching prod.
#
# SAFETY: a real per-org WRITE load test across N pods is only sound once the
# durable-tasks :9999 off-router blocker is fixed (a job on a non-owner pod would
# write the wrong PVC). Until then this harness proves ROUTING + READ scaling +
# failover; it refuses write-load unless HANZO_SHARD_WRITE_OK=1 is set explicitly.
set -euo pipefail
NS=${NS:-cloud-bench}
N=${N:-3}
IMAGE=${IMAGE:-ghcr.io/hanzoai/cloud:latest}   # CI-built; we never build locally
K=${KUBECTL:-kubectl}

echo ">> ensuring a local k3s cluster"
if ! $K get nodes >/dev/null 2>&1; then
  sudo k3s server --write-kubeconfig-mode 644 >/tmp/k3s.log 2>&1 &
  for i in $(seq 1 30); do $K get nodes >/dev/null 2>&1 && break || sleep 1; done
fi
$K get nodes

PEERS=""; for i in $(seq 0 $((N-1))); do
  PEERS+="${PEERS:+,}cloud-shard-$i@cloud-shard-$i.cloud-shard.$NS.svc:8000"
done
echo ">> N=$N  CLOUD_PEERS=$PEERS"

$K create ns "$NS" --dry-run=client -o yaml | $K apply -f -

# Prefer the canary StatefulSet blue authored (universe:blue/cloud-horizontal-shard).
MANIFEST=${MANIFEST:-$HOME/work/hanzo/universe/infra/k8s/cloud/cloud-statefulset.yaml}
if [[ -f "$MANIFEST" ]]; then
  echo ">> applying $MANIFEST (edit replicas=$N, CLOUD_PEERS, image as needed)"
  $K -n "$NS" apply -f "$MANIFEST"
else
  echo "!! canary manifest not found at $MANIFEST"
  echo "   checkout universe:blue/cloud-horizontal-shard, or point MANIFEST= at it."
  exit 1
fi

echo ">> waiting for $N shard pods (image pull + boot)…"
$K -n "$NS" rollout status statefulset/cloud-shard --timeout=300s || true
$K -n "$NS" get pods -o wide

cat <<EOF

>> shard stack up. Drive it:
   ROUTING/READ proof (safe now):
     $K -n $NS port-forward svc/cloud-shard 8000:8000
     # send requests with distinct X-Org-Id; confirm each org's writes land on ONE pod
     #   $K -n $NS logs cloud-shard-0 | grep 'org_slug'
   WRITE load (only after the :9999 blocker is fixed):
     HANZO_SHARD_WRITE_OK=1 ./k3s/loadgen.sh   # gated on purpose
EOF
