# The machine a number came from, printed by every lane that measures time.
#
# "An M-series laptop" covered an M1 Max with 10 cores and an M4 Max with 16,
# and the goroutine lane reads about twice as fast on the second. A timing
# without its host is not reproducible and not comparable, including against
# itself a month later.
#
# Sourced, not run: `. "$(dirname "$0")/../host.sh"; host`
host() {
  local cpu cores os
  if [ "$(uname -s)" = Darwin ]; then
    cpu=$(sysctl -n machdep.cpu.brand_string 2>/dev/null)
    cores=$(sysctl -n hw.ncpu 2>/dev/null)
    os="macOS $(sw_vers -productVersion 2>/dev/null)"
  else
    cpu=$(awk -F': ' '/model name/ {print $2; exit}' /proc/cpuinfo 2>/dev/null)
    cores=$(nproc 2>/dev/null)
    os=$(. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME")
  fi
  printf 'host: %s · %s cores · %s · %s\n\n' "${cpu:-unknown}" "${cores:-?}" "$(uname -m)" "${os:-$(uname -s)}"
}

# One row of a lane's table, and — when `BENCH_JSON` names a file — one entry in
# it. Every lane already funnelled its output through a local `say`; this is that
# function, once, so a row reaches the terminal and the file by the same call and
# the two cannot disagree.
#
# The value is written as a string. A lane's rows are as often "0 of 7" or
# "refuses — …" as they are numbers, and a reader that wants a number knows which
# row it asked for.
say() {
  printf '%-34s %s\n' "$1" "$2"
  [ -n "${BENCH_JSON:-}" ] || return 0
  python3 "$(dirname "${BASH_SOURCE[0]}")/row.py" "$BENCH_JSON" "$1" "$2"
}

# Where the cloud source is, for the lanes that build it.
#
# Four lanes — self, egress, cipher, transport — measure a BINARY, so they need
# the source to build one. In hanzoai/cloud they got it from `cd ../..`, which
# was the repo they lived in. Here it is a different repository, and a relative
# climb would reach this one and fail on a missing ./cmd/cloud with no hint why.
#
# Resolution order, and it stops at the first that exists:
#   $CLOUD_SRC          named outright
#   ../cloud            a sibling checkout, which is how the estate lays out
#   $HOME/work/hanzo/cloud
#
# It does not clone. A benchmark that silently fetches a tree decides which
# revision you measured, and the whole point of the run is that you chose.
cloud_src() {
  local c
  for c in "${CLOUD_SRC:-}" "$(dirname "${BASH_SOURCE[0]}")/../cloud" "$HOME/work/hanzo/cloud"; do
    [ -n "$c" ] || continue
    [ -f "$c/go.mod" ] && [ -d "$c/cmd/cloud" ] || continue
    # SAY WHICH SOURCE, for the same reason every timing says which host.
    # `hanzoai/cloud` and `hanzo-inc/cloud` are different repositories that both
    # check out as `cloud`, and a lane pointed at the wrong one answers a
    # different question without saying so: self/modules.sh reads 127 modules on
    # one and 55 on the other, and neither number is wrong about the tree it was
    # given. Printed to stderr so `$(cloud_src)` still yields only the path.
    (cd "$c" && printf 'cloud: %s · %s · %s\n\n' \
      "$(pwd)" \
      "$(git remote get-url origin 2>/dev/null | sed 's#.*[:/]\([^/]*/[^/]*\)$#\1#; s#\.git$##' || echo 'not a checkout')" \
      "$(git rev-parse --short=12 HEAD 2>/dev/null || echo 'no commit')" >&2)
    (cd "$c" && pwd)
    return 0
  done
  cat >&2 <<'WHY'
This lane builds the cloud binary and cannot find its source.

  git clone https://github.com/hanzoai/cloud ../cloud

or point at a checkout you already have:

  CLOUD_SRC=/path/to/cloud <this script>

Looked for a directory holding both go.mod and cmd/cloud.
WHY
  return 1
}
