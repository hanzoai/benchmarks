#!/usr/bin/env bash
set -euo pipefail
NS=${NS:-cloud-bench}
K=${KUBECTL:-kubectl}
$K delete ns "$NS" --ignore-not-found
echo ">> $NS torn down (k3s cluster left running; 'sudo k3s-killall.sh' stops k3s)"
