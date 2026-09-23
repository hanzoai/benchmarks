package graph

// The CronQuestions driver for the graph assertion plane (hanzoai/benchmarks,
// cronquestions/). It is compiled INTO this package by `go test -overlay` and
// lives nowhere in the cloud tree: the store's read and the admission path are
// unexported, and an overlay reaches them without a fork. The leading underscore
// keeps the benchmarks module's own `go test ./...` from compiling it there.
//
// One store, opened as production opens it minus the key (sqlite.OpenDB, one
// connection). Every assertion passes the API's own admission (fromWire); the
// only thing the driver chooses is the server clock that admission stamps:
//
//	wire    the clock is now, as for any caller of POST /v1/graph
//	replay  the clock is the assertion's own instant, as if a live pipeline had
//	        filed each fact the moment it became so

import (
	"bufio"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/hanzoai/cloud/sqlpool"
	"github.com/hanzoai/sqlite"
)

var (
	cqFacts = flag.String("cq.facts", "", "facts.tsv from cron.py")
	cqPlan  = flag.String("cq.plan", "", "plan-<split>.jsonl from cron.py")
	cqOut   = flag.String("cq.out", "", "where the results go")
	cqClock = flag.String("cq.clock", "wire", "wire or replay")
	cqHost  = flag.String("cq.host", "", "the host line, recorded with the results")
)

type cqQuestion struct {
	I     int      `json:"i"`
	Calls []cqCall `json:"calls"`
}

type cqCall struct {
	Op       string `json:"op"`
	Entity   string `json:"entity"`
	Relation string `json:"relation"`
	Dir      string `json:"dir"`
	T        int    `json:"t"`
}

// A fact is valid for whole years: it opens at the first instant of its first
// year and closes at the last second of its last. A question about a year asks
// at mid-year, so a fact that opens or closes that year is in force for it.
func cqOpen(y int) time.Time  { return time.Date(y, 1, 1, 0, 0, 0, 0, time.UTC) }
func cqClose(y int) time.Time { return time.Date(y, 12, 31, 23, 59, 59, 0, time.UTC) }
func cqMid(y int) time.Time   { return time.Date(y, 7, 1, 0, 0, 0, 0, time.UTC) }

// cqLoad is the host's one-minute load average. A timing taken on a busy
// machine measures the machine, so every timed phase carries its peak.
func cqLoad() float64 {
	out, err := exec.Command("sysctl", "-n", "vm.loadavg").Output()
	if err != nil {
		b, err := os.ReadFile("/proc/loadavg")
		if err != nil {
			return -1
		}
		out = b
	}
	v, _ := strconv.ParseFloat(strings.Fields(strings.Trim(string(out), "{} \n"))[0], 64)
	return v
}

// cqWatch samples the load every second until the returned func is called,
// which answers the highest reading.
func cqWatch() func() float64 {
	stop, peak := make(chan struct{}), make(chan float64)
	go func() {
		hi := cqLoad()
		tick := time.NewTicker(time.Second)
		defer tick.Stop()
		for {
			select {
			case <-tick.C:
				hi = max(hi, cqLoad())
			case <-stop:
				peak <- max(hi, cqLoad())
				return
			}
		}
	}()
	return func() float64 { close(stop); return <-peak }
}

// inverse is the relation filed from the object's end. resolve answers one
// (entity, relation), so "who held P in T" needs the fact filed about P.
func inverse(r string) string { return "~" + r }

// assertions files one KG fact as four assertions: an edge from each end at the
// open instant, and a retraction of each at the close. A retraction is an
// assertion (HIP-1198 §2): an empty property on the same pair, which wins from
// its instant on. The evidence is the KG line, so an open and its close pair.
func assertions(line, s, r, o string, a, b int) []graphFact {
	ev := "full.txt:" + line
	at := func(t time.Time) string { return t.Format(time.RFC3339) }
	return []graphFact{
		{Entity: s, Relation: r, Value: o, Names: true, At: at(cqOpen(a)), Source: "wikidata", Evidence: ev},
		{Entity: o, Relation: inverse(r), Value: s, Names: true, At: at(cqOpen(a)), Source: "wikidata", Evidence: ev},
		{Entity: s, Relation: r, Value: "", At: at(cqClose(b)), Source: "wikidata", Evidence: ev},
		{Entity: o, Relation: inverse(r), Value: "", At: at(cqClose(b)), Source: "wikidata", Evidence: ev},
	}
}

// intervals pairs each open with its close by evidence. An open whose close the
// store did not return is open-ended (null).
func intervals(facts []Fact) [][]any {
	closed := map[string]int{}
	for _, f := range facts {
		if !f.Names {
			closed[f.Evidence] = f.At.Year()
		}
	}
	rows := [][]any{}
	for _, f := range facts {
		if !f.Names {
			continue
		}
		var end any
		if y, ok := closed[f.Evidence]; ok {
			end = y
		}
		rows = append(rows, []any{f.Value, f.At.Year(), end})
	}
	return rows
}

func TestCronQuestions(t *testing.T) {
	if *cqFacts == "" || *cqPlan == "" || *cqOut == "" {
		t.Fatal("-cq.facts, -cq.plan and -cq.out are required")
	}
	replay := *cqClock == "replay"
	if !replay && *cqClock != "wire" {
		t.Fatalf("-cq.clock %q is not wire or replay", *cqClock)
	}
	ctx := context.Background()
	db, err := sqlite.OpenDB(filepath.Join(t.TempDir(), "graph.db"), nil)
	if err != nil {
		t.Fatal(err)
	}
	sqlpool.Single(db)
	st, err := openStore(db)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = st.Close() }()

	// ── load ────────────────────────────────────────────────────────────────
	f, err := os.Open(*cqFacts)
	if err != nil {
		t.Fatal(err)
	}
	var kg [][]string
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		kg = append(kg, strings.Split(sc.Text(), "\t"))
	}
	_ = f.Close()
	if err := sc.Err(); err != nil {
		t.Fatal(err)
	}

	atStart := cqLoad()
	watch := cqWatch()
	start := time.Now()
	now := start.UTC()
	written, refused := 0, map[string]int{}
	batch := make([]Fact, 0, 4096)
	flush := func() {
		n, err := st.record(ctx, batch)
		if err != nil {
			t.Fatal(err)
		}
		written += n
		batch = batch[:0]
	}
	for _, x := range kg {
		a, _ := strconv.Atoi(x[4])
		b, _ := strconv.Atoi(x[5])
		for _, w := range assertions(x[0], x[1], x[2], x[3], a, b) {
			clock := now
			if replay {
				clock, _ = time.Parse(time.RFC3339, w.At)
			}
			fact, err := fromWire(w, "cronquestions", clock)
			if err != nil {
				refused[err.Error()]++
				continue
			}
			batch = append(batch, fact)
		}
		if len(batch) >= 4000 {
			flush()
		}
	}
	flush()
	load := time.Since(start).Seconds()
	loadPeak := watch()
	var size int64
	if err := db.QueryRow(`SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()`).Scan(&size); err != nil {
		t.Fatal(err)
	}

	// ── queries ─────────────────────────────────────────────────────────────
	pf, err := os.Open(*cqPlan)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = pf.Close() }()
	of, err := os.Create(*cqOut)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = of.Close() }()
	out := bufio.NewWriter(of)
	enc := json.NewEncoder(out)

	truncated := 0
	run := func(c cqCall) ([][]any, error) {
		rel := c.Relation
		if c.Dir == "in" {
			rel = inverse(rel)
		}
		switch c.Op {
		case "at": // what ops.resolve does, minus the tenant lookup
			asOf := cqMid(c.T)
			facts, err := st.read(ctx, filter{Entity: c.Entity, Relation: rel, AsOf: asOf, Newest: true})
			if err != nil {
				return nil, err
			}
			if len(facts) == walkBound {
				truncated++
			}
			win, _, _, ok := Resolve(facts, asOf)
			if !ok || !win.Names {
				return [][]any{}, nil
			}
			return [][]any{{win.Value, win.At.Year(), nil}}, nil
		case "history", "touch": // what ops.read does
			fl := filter{Entity: c.Entity, Relation: rel}
			if c.Op == "touch" {
				fl.Relation = ""
			}
			facts, err := st.read(ctx, fl)
			if err != nil {
				return nil, err
			}
			if len(facts) == walkBound {
				truncated++
			}
			return intervals(facts), nil
		}
		return nil, fmt.Errorf("op %q", c.Op)
	}

	var plans []cqQuestion
	ps := bufio.NewScanner(pf)
	ps.Buffer(make([]byte, 1<<20), 1<<20)
	for ps.Scan() {
		var p cqQuestion
		if err := json.Unmarshal(ps.Bytes(), &p); err != nil {
			t.Fatal(err)
		}
		plans = append(plans, p)
	}
	if err := ps.Err(); err != nil {
		t.Fatal(err)
	}

	type result struct {
		I    int       `json:"i"`
		Rows [][][]any `json:"rows"`
		Ms   []float64 `json:"ms"`
	}
	results := make([]result, 0, len(plans))
	watch = cqWatch()
	qstart := time.Now()
	for _, p := range plans {
		r := result{I: p.I}
		for _, c := range p.Calls {
			t0 := time.Now()
			rows, err := run(c)
			ms := float64(time.Since(t0).Nanoseconds()) / 1e6
			if err != nil {
				t.Fatalf("%+v: %v", c, err)
			}
			r.Rows = append(r.Rows, rows)
			r.Ms = append(r.Ms, ms)
		}
		results = append(results, r)
	}
	wall := time.Since(qstart).Seconds()
	queryPeak := watch()

	head := map[string]any{
		"store": fmt.Sprintf("hanzoai/cloud apps/graph, clock=%s, %s %s/%s", *cqClock, runtime.Version(), runtime.GOOS, runtime.GOARCH),
		"host":  *cqHost,
		"load_1m": map[string]float64{
			"at_start":     atStart,
			"peak_loading": loadPeak,
			"peak_queries": queryPeak,
		},
		"load": map[string]any{
			"facts":            len(kg),
			"assertions":       written,
			"refused":          refused,
			"seconds":          load,
			"facts_per_s":      float64(len(kg)) / load,
			"assertions_per_s": float64(written) / load,
			"bytes":            size,
		},
		"notes": map[string]any{
			"truncated_reads": truncated,
			"query_wall_s":    wall,
			"calls_timed":     "every call",
		},
	}
	if err := enc.Encode(head); err != nil {
		t.Fatal(err)
	}
	for _, r := range results {
		if err := enc.Encode(r); err != nil {
			t.Fatal(err)
		}
	}
	if err := out.Flush(); err != nil {
		t.Fatal(err)
	}
	t.Logf("clock=%s load %.1fs (%d facts, %d assertions, refused %v) · %d questions in %.1fs · truncated %d · load average %.2f, peak %.2f loading, %.2f querying",
		*cqClock, load, len(kg), written, refused, len(results), wall, truncated, atStart, loadPeak, queryPeak)
}
