#!/usr/bin/env bash
# CronQuestions: one plan, two temporal stores, one machine, both in-process.
#
#   bash cronquestions/run.sh [test|valid]
#
# Fetches the data if it is missing, writes the facts and the plan, then runs
# the control (dictionaries over the facts), the graph store under both clocks
# and Semantica, and scores each into runs/<row>-<split>/.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/../host.sh"
SPLIT=${1:-test}
SEMANTICA_SRC=${SEMANTICA_SRC:-$HOME/work/semantica/semantica}
SRC="$(cloud_src)" || exit 1
cd "$HERE"

# A timing taken on a busy machine measures the machine. Before each store runs,
# wait up to ten minutes for the one-minute load average to fall under 2; each
# run records the load it actually had either way, and metrics.json says it.
load1() { uptime | sed 's/.*averages*: *//' | awk '{print $1 + 0}'; }
quiet() {
  local i=0
  until awk -v l="$(load1)" 'BEGIN { exit !(l < 2) }'; do
    if [ $i -ge 40 ]; then echo "load $(load1) after ten minutes; timing anyway"; return; fi
    if [ $((i % 20)) -eq 0 ]; then echo "waiting for a quiet machine: load $(load1)"; fi
    sleep 15
    i=$((i + 1))
  done
}
subject() { printf '%s %s' "$(git -C "$1" remote get-url origin | sed 's#.*[:/]\([^/]*/[^/]*\)$#\1#; s#\.git$##')" "$(git -C "$1" rev-parse --short=12 HEAD)"; }

if [ ! -f data/data_v2.zip ]; then
  mkdir -p data
  # data_v2 is the release with the {tail2} fix (CronKGQA README).
  uvx gdown 'https://drive.google.com/uc?id=1fe7-x7ChszqzczKncoZcpwmWc1PBq1_0' -O data/data_v2.zip
  (cd data && unzip -q data_v2.zip)
fi
python3 cron.py facts
python3 cron.py plan "$SPLIT"
python3 cron.py exact "$SPLIT"
python3 cron.py score "$SPLIT" kg "data/results-kg-$SPLIT.jsonl"

# The graph driver is compiled into apps/graph from the cloud source, and
# compiled before the wait so the compiler is not in the timing.
BIN=$(mktemp -u)
OVERLAY=$(mktemp)
trap 'rm -f "$OVERLAY" "$BIN"' EXIT
printf '{"Replace":{"%s/apps/graph/cronquestions_test.go":"%s/_graph_test.go"}}' "$SRC" "$HERE" >"$OVERLAY"
(cd "$SRC" && GOWORK=off go test -c -overlay "$OVERLAY" -o "$BIN" ./apps/graph) 2>&1 | grep -v '^ld: warning' || true
CLOUD="$(subject "$SRC"), $(git -C "$SRC" status --porcelain -- apps/graph claim | grep -q . && echo 'apps/graph MODIFIED' || echo 'apps/graph clean')"
for clock in wire replay; do
  quiet
  "$BIN" -test.run '^TestCronQuestions$' -test.count 1 -test.timeout 0 -test.v \
    -cq.facts data/facts.tsv -cq.plan "data/plan-$SPLIT.jsonl" -cq.out "data/results-hanzo-$clock-$SPLIT.jsonl" \
    -cq.clock "$clock" -cq.host "$(host | head -1)" | grep -E 'clock=|FAIL'
  python3 cron.py score "$SPLIT" "hanzo-$clock" "data/results-hanzo-$clock-$SPLIT.jsonl" "$CLOUD"
done

[ -x .venv/bin/python ] || uv venv -q .venv --python 3.12
uv pip install -q --python .venv/bin/python -e "$SEMANTICA_SRC"
quiet
.venv/bin/python temporal.py data/facts.tsv "data/plan-$SPLIT.jsonl" "data/results-semantica-$SPLIT.jsonl" "$(host | head -1)" "${SAMPLE:-50}"
python3 cron.py score "$SPLIT" semantica "data/results-semantica-$SPLIT.jsonl" "$(subject "$SEMANTICA_SRC")"
