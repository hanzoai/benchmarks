"""The CronQuestions driver for Semantica's temporal query engine.

    .venv/bin/python temporal.py <facts.tsv> <plan.jsonl> <out.jsonl> [host] [sample]

Loads facts.tsv through GraphBuilder with valid_from/valid_until on every
relationship, then answers each call of the plan with TemporalGraphQuery:

    at        query_at_time(graph, "", at_time=<year>-07-01)
    history   query_time_range(graph, "", 0001-01-01, OPEN)
    touch     the same range call

and keeps the relationships that name the call's entity and relation. Neither
call takes an entity — `query` is documented as unused — so the store's answer
depends only on the instant. Every question is therefore answered from one real
call per distinct instant. Latency is timed first, on the first <sample> calls
of each op in plan order, each made in full, and each is checked against the
shared answer afterwards.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime

import semantica
from semantica.kg import GraphBuilder, TemporalBound, TemporalGraphQuery

logging.disable(logging.CRITICAL)  # the engine logs every call at INFO


def year(value):
    return value.year if isinstance(value, datetime) else int(str(value)[:4])


def main(facts, plan, out, host="", sample="50"):
    sample = int(sample)
    rels = []
    with open(facts) as f:
        for text in f:
            line, s, r, o, a, b = text.rstrip("\n").split("\t")
            rels.append({
                "id": f"full.txt:{line}", "source": s, "target": o, "type": r,
                # Whole years, the same instants the graph driver files.
                "valid_from": f"{int(a):04d}-01-01T00:00:00Z",
                "valid_until": f"{int(b):04d}-12-31T23:59:59Z",
            })
    at_start = os.getloadavg()[0]
    t0 = time.perf_counter()
    graph = GraphBuilder(enable_temporal=True, temporal_granularity="day").build({"relationships": rels})
    load = time.perf_counter() - t0
    engine = TemporalGraphQuery(temporal_granularity="day")

    def store(c):
        if c["op"] == "at":
            return engine.query_at_time(graph, "", at_time=f"{c['t']:04d}-07-01T00:00:00Z")["relationships"]
        return engine.query_time_range(graph, "", "0001-01-01T00:00:00Z", TemporalBound.OPEN)["relationships"]

    def keep(c, relationships):
        e = c["entity"]
        rows = []
        for x in relationships:
            if c["op"] == "touch":
                if x["source"] == e:
                    rows.append([x["target"], year(x["valid_from"]), year(x["valid_until"])])
                elif x["target"] == e:
                    rows.append([x["source"], year(x["valid_from"]), year(x["valid_until"])])
            elif x["type"] == c["relation"]:
                near, far = ("source", "target") if c["dir"] == "out" else ("target", "source")
                if x[near] == e:
                    rows.append([x[far], year(x["valid_from"]), year(x["valid_until"])])
        return rows

    with open(plan) as f:
        plans = [json.loads(t) for t in f]

    # Timed: the first `sample` calls of each op, each a full store call and
    # filter, back to back so the load reading covers exactly them.
    timed, count, peak = {}, {}, at_start
    for p in plans:
        for n, c in enumerate(p["calls"]):
            if count.get(c["op"], 0) >= sample:
                continue
            count[c["op"]] = count.get(c["op"], 0) + 1
            s = time.perf_counter()
            rows = keep(c, store(c))
            timed[p["i"], n] = ((time.perf_counter() - s) * 1000, rows)
            peak = max(peak, os.getloadavg()[0])

    # Answered: one real call per distinct instant, indexed by what `keep` filters on.
    shared = {}

    def answer(c):
        key = c["t"] if c["op"] == "at" else "range"
        if key not in shared:
            index = {}
            for x in store(c):
                row = (year(x["valid_from"]), year(x["valid_until"]))
                index.setdefault(("out", x["type"], x["source"]), []).append([x["target"], *row])
                index.setdefault(("in", x["type"], x["target"]), []).append([x["source"], *row])
                index.setdefault(("touch", x["source"]), []).append([x["target"], *row])
                index.setdefault(("touch", x["target"]), []).append([x["source"], *row])
            shared[key] = index
        k = ("touch", c["entity"]) if c["op"] == "touch" else (c["dir"], c["relation"], c["entity"])
        return shared[key].get(k, [])

    differing, results = 0, []
    t1 = time.perf_counter()
    for p in plans:
        rows, ms = [], []
        for n, c in enumerate(p["calls"]):
            got = answer(c)
            m, full = timed.get((p["i"], n), (None, None))
            if full is not None:
                differing += sorted(map(tuple, full)) != sorted(map(tuple, got))
            rows.append(got)
            ms.append(m)
        results.append({"i": p["i"], "rows": rows, "ms": ms})
    wall = time.perf_counter() - t1

    head = {
        "store": f"semantica {semantica.__version__} TemporalGraphQuery, python {sys.version.split()[0]}",
        "host": host,
        "load_1m": {"at_start": at_start, "peak_queries": peak},
        "load": {"facts": len(rels), "relationships": graph["metadata"]["num_relationships"],
                 "seconds": load, "facts_per_s": len(rels) / load},
        "notes": {"distinct_store_calls": len(shared), "calls_timed": count,
                  "timed_calls_differing_from_shared": differing, "answer_wall_s": wall},
    }
    with open(out, "w") as w:
        w.write(json.dumps(head) + "\n")
        for r in results:
            w.write(json.dumps(r) + "\n")
    print(f"semantica: load {load:.1f}s · {len(results)} questions in {wall:.0f}s · "
          f"{len(shared)} shared calls · timed {count} · differing {differing} · "
          f"load average {at_start:.2f}, peak {peak:.2f} timing")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
