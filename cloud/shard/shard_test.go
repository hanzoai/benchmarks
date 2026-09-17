// Package shard benchmarks the cloud horizontal-writer-scale routing primitive:
// hanzoai/ha HRW/rendezvous org→owner election, which underpins the in-binary shard
// router (cloud/shardrouter.go). It proves the two properties horizontal scale rests
// on — EXACTLY ONE owner per org (the no-two-writers invariant) and EVEN spread across
// N pods (linear write capacity, since per-org SQLite has no shared lock) — and
// measures the per-request routing tax.
package shard

import (
	"fmt"
	"math"
	"sort"
	"strings"
	"testing"

	"github.com/hanzoai/ha"
)

// ring builds an N-pod StatefulSet writer set, exactly as cloud parsePeers(CLOUD_PEERS) does.
func ring(n int) []ha.Member {
	m := make([]ha.Member, n)
	for i := range m {
		id := fmt.Sprintf("cloud-%d", i)
		m[i] = ha.Member{ID: id, Addr: id + ".cloud.hanzo.svc:8000"}
	}
	return m
}

func orgSlug(i int) string { return fmt.Sprintf("org-%08x", i) }

// BenchmarkRoute measures electing an org's owner pod (one rendezvous hash over the
// ring) — the per-request tax every sharded request pays before it serves or forwards.
func BenchmarkRoute(b *testing.B) {
	for _, n := range []int{3, 10, 32, 100} {
		peers := ring(n)
		b.Run(fmt.Sprintf("N=%d", n), func(b *testing.B) {
			b.ReportAllocs()
			for i := 0; i < b.N; i++ {
				_, _ = ha.Owner(orgSlug(i), peers)
			}
		})
	}
}

// TestScaleProof prints (with -v) the horizontal-scale properties over 1M tenants:
// exactly one owner per org and even spread across N pods (no hot shard). Fails if a
// pod owns nothing (wasted capacity) or an org elects no owner.
func TestScaleProof(t *testing.T) {
	const orgs = 1_000_000
	for _, n := range []int{3, 10, 100} {
		peers := ring(n)
		count := map[string]int{}
		for i := range orgs {
			o, ok := ha.Owner(orgSlug(i), peers)
			if !ok {
				t.Fatalf("N=%d org %d: no owner elected", n, i)
			}
			count[o.ID]++
		}
		if len(count) != n {
			t.Errorf("N=%d: only %d/%d pods own any org (wasted capacity)", n, len(count), n)
		}
		ids := make([]string, 0, len(count))
		for id := range count {
			ids = append(ids, id)
		}
		sort.Strings(ids)
		mean := float64(orgs) / float64(n)
		min, max, sumsq := orgs, 0, 0.0
		for _, id := range ids {
			c := count[id]
			if c < min {
				min = c
			}
			if c > max {
				max = c
			}
			d := float64(c) - mean
			sumsq += d * d
		}
		stddev := math.Sqrt(sumsq / float64(n))
		t.Logf("N=%3d | %s orgs | per-pod mean=%.0f  stddev=%.0f (%.2f%%)  min=%d max=%d  max-skew=%.2f%%",
			n, commas(orgs), mean, stddev, stddev/mean*100, min, max, float64(max-min)/mean*100)
		if n <= 10 {
			for _, id := range ids {
				bars := int(float64(count[id]) / mean * 24)
				t.Logf("   %-9s |%s %s", id, strings.Repeat("#", bars), commas(count[id]))
			}
		}
	}
}

// TestDeterministicSingleOwner proves the invariant directly: re-electing an org's
// owner from the same static ring (as any pod would) yields the SAME pod every time,
// so two pods never both believe they own an org's files.
func TestDeterministicSingleOwner(t *testing.T) {
	peers := ring(7)
	for i := range 100_000 {
		a, ok := ha.Owner(orgSlug(i), peers)
		if !ok {
			t.Fatalf("org %d: no owner", i)
		}
		for range 5 {
			b, _ := ha.Owner(orgSlug(i), peers)
			if b.ID != a.ID {
				t.Fatalf("org %d: owner diverged %q vs %q — dual-writer risk", i, a.ID, b.ID)
			}
		}
	}
	t.Log("100k orgs x 6 elections each: every org has ONE stable owner — no dual-writer")
}

// TestMinimalReshuffleOnScale documents the cost of changing N: rendezvous hashing
// moves only ~1/N' of orgs when a pod is added (vs ~all for modulo hashing), so a
// scale-up remaps the fewest tenant files.
func TestMinimalReshuffleOnScale(t *testing.T) {
	const orgs = 200_000
	before, after := ring(4), ring(5)
	moved := 0
	for i := range orgs {
		s := orgSlug(i)
		a, _ := ha.Owner(s, before)
		b, _ := ha.Owner(s, after)
		if a.ID != b.ID {
			moved++
		}
	}
	pct := float64(moved) / orgs * 100
	ideal := 1.0 / 5.0 * 100 // adding the 5th pod: ideally ~1/5 move to it
	t.Logf("4->5 pods: %.2f%% of orgs remap (ideal ~%.1f%%) — rendezvous minimizes tenant-file moves", pct, ideal)
	if pct > ideal*1.5 {
		t.Errorf("reshuffle %.2f%% far exceeds ideal %.1f%% — not a rendezvous hash?", pct, ideal)
	}
}

func commas(n int) string {
	s := fmt.Sprintf("%d", n)
	var out []byte
	for i := 0; i < len(s); i++ {
		if i > 0 && (len(s)-i)%3 == 0 {
			out = append(out, ',')
		}
		out = append(out, s[i])
	}
	return string(out)
}
