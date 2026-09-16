#!/usr/bin/env bash
# Can anyone fetch what this binary is built from?
#
# `run.sh` counts private module paths in go.mod, which is a property of a file.
# This asks the public Go proxy for every module the binary actually needs, with
# no credential: a module that answers is one anybody can fetch, and a module
# that does not is a dependency only we can resolve.
#
# It ends by asking for a module that does not exist. A probe that answers 200
# for everything would report a clean sweep for a tree full of private
# dependencies, so the run fails unless the absent one is refused.
set -uo pipefail
# The lane runs from the cloud source, which is a different repository now.
# `cloud_src` finds it or says how to get it (../host.sh).
HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/../host.sh"
SRC="$(cloud_src)" || exit 1
cd "$SRC"
export GOWORK=off

host

# The Go proxy lowercases an uppercase letter and marks it with a bang, so a
# module path is not its own URL.
esc() {
  python3 -c 'import sys, re; print(re.sub(r"[A-Z]", lambda m: "!" + m.group(0).lower(), sys.argv[1]))' "$1"
}

ask() { curl -s -o /dev/null -w '%{http_code}' --max-time 20 "https://proxy.golang.org/$(esc "$1")/@v/list"; }

mods=$(go list -deps -f '{{if .Module}}{{.Module.Path}}{{end}}' ./cmd/cloud 2>/dev/null | sort -u | grep -v '^$')
total=$(echo "$mods" | wc -l | tr -d ' ')

ok=0; refused=0
while read -r m; do
  [ -z "$m" ] && continue
  if [ "$(ask "$m")" = "200" ]; then ok=$((ok + 1)); else refused=$((refused + 1)); echo "  not public: $m"; fi
done <<<"$mods"

say "modules the binary needs" "$total"
say "fetchable with no credential" "$ok"
say "not" "$refused"

# AND CAN ANYONE DEPEND ON THIS ONE? Every row above is about what the binary is
# built FROM. Ownership also means the thing itself is consumable, and those are
# different questions with different answers: hanzoai/cloud is public, has 571
# tags, and not one of them is semver — so `go get` resolves it to a
# pseudo-version of whatever is on main, and there is no release to pin.
#
# Worse, the proxy still serves 471 versions that were deleted from the repo, so
# a pin to one of them fetches cache rather than code anyone can check out. That
# is the shape this row exists to make visible.
mod=$(awk '/^module /{print $2; exit}' go.mod)
latest=$(curl -s --max-time 20 "https://proxy.golang.org/$(esc "$mod")/@latest" |
  python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("Version",""))
except Exception: print("")' 2>/dev/null)
case "$latest" in
  v0.0.0-*) say "this module, published as" "no release — $latest is a pseudo-version of main" ;;
  "")       say "this module, published as" "the proxy does not serve it" ;;
  *)        # THE MODULE PATH IS THE REPOSITORY, and `origin` is not. A Go module
            # path resolves to exactly one URL by construction, whereas origin is
            # whatever this checkout was cloned from — in a worktree of the private
            # tree it is hanzo-inc/cloud, so the tag was looked for in the wrong
            # repository and a published release read back as ABSENT.
            upstream=$(git ls-remote "https://${mod%%/*}/$(echo "$mod" | cut -d/ -f2-)" "refs/tags/$latest" 2>/dev/null | wc -l | tr -d ' ')
            [ "${upstream:-0}" -gt 0 ] \
              && say "this module, published as" "$latest" \
              || say "this module, published as" "$latest — SERVED BY THE PROXY, ABSENT FROM THE REPO" ;;
esac

control=$(ask "github.com/hanzoai/a-module-that-does-not-exist")
say "control: an absent module" "$control"
[ "$control" = "200" ] && {
  echo "the proxy answered for a module that does not exist; the sweep above is not evidence" >&2
  exit 1
}
[ "$refused" -gt 0 ] && exit 1
exit 0
