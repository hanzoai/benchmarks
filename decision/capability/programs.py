"""Synthetic dependent decision programs with known structure, from a seed.

Two families, each five typed variables over one state. The state carries the evidence and the
policy that decides every variable, so each answer follows from the state alone; the gold is
computed from a latent world by that policy, and it satisfies every rule.

    maintenance  fault -> severity -> readiness -> action -> review  (ground vehicle maintenance)
    trade        option -> evidence, risk -> readiness -> review     (acquisition source selection)

A case is [state, questions, gold] with gold {qid: {"idx"}, "_wf": family}; GRAPHS holds each
family's parents and rules in bench refine's format ({"if": {..}, "then"|"not": {..}}).
"""
import itertools
import random

SUBSYSTEMS = {  # fault: (sensor, unit, limit, direction, nominal, symptoms, codes)
    "engine": ("coolant temperature", "°C", 105, 1, 88, ["temperature climbs on long grades", "white smoke at idle",
               "loss of power under load"], ["P0217 engine over-temperature", "P0128 coolant thermostat"]),
    "transmission": ("transmission fluid temperature", "°C", 120, 1, 95, ["hard shifts from 2nd to 3rd",
                     "slipping under acceleration", "burnt fluid smell"],
                     ["P0700 transmission control", "P0730 incorrect gear ratio"]),
    "brakes": ("brake pad thickness", "mm", 3.0, -1, 9.0, ["soft pedal", "pulls left when braking",
               "grinding at low speed"], ["C0035 wheel speed sensor, brakes", "C0265 brake pump motor"]),
    "hydraulics": ("hydraulic pressure", "bar", 180, -1, 210, ["slow ramp actuation", "fluid seep at the pump",
                   "whine from the pump"], ["H1021 hydraulic pressure low", "H1107 hydraulic pump"]),
    "electrical": ("battery voltage", "V", 24.0, -1, 27.6, ["dash lights flicker", "intermittent CAN bus faults",
                   "slow cranking"], ["U0100 lost communication, CAN bus", "P0562 system voltage low"]),
}
FAULTS = ["none"] + list(SUBSYSTEMS)
READY = {"FMC": "fully mission capable", "PMC": "partially mission capable: usable with restrictions",
         "NMC": "not mission capable"}
ACTIONS = {"continue_mission": "no maintenance needed now", "schedule_maintenance": "book routine maintenance",
           "repair_before_dispatch": "repair before the next dispatch", "ground_vehicle": "take the vehicle out of service"}
POLICY_R = ("Sensor readings and trouble codes outrank operator notes. Severity: 0 no fault; 1 a fault whose "
            "reading is within its limit; 2 a reading past its limit by less than 10%; 3 past it by 10% or more. "
            "A brake fault is at least severity 2. Readiness: FMC at severity 0 or 1, PMC at 2, NMC at 3. "
            "Action: continue_mission at severity 0, schedule_maintenance at 1, repair_before_dispatch when PMC, "
            "ground_vehicle when NMC. A human reviews every grounding and every case where the operator note "
            "names a different subsystem than the sensors.")

VENDORS = ["A", "B", "C"]
POLICY_T = ("Choose the lowest unit cost among the vendors that meet every threshold; none if no vendor does. "
            "Evidence for the chosen vendor: 0 no government tests, 1 one test, 2 two or three, 3 four or more. "
            "Schedule risk for the chosen vendor: 0 on time or early, 1 one to three months late, 2 four to six, "
            "3 more than six; with no compliant vendor, evidence is 0 and risk is 3. Readiness: not_ready with no "
            "compliant vendor or at risk 3, needs_more_evidence at evidence 0 or 1, otherwise ready. The milestone "
            "decision authority reviews every decision that is not ready and every buy over $50M.")

GRAPHS = {
    "maintenance": {
        "parents": {"severity": ["fault"], "readiness": ["fault", "severity"],
                    "action": ["severity", "readiness"], "review": ["fault", "action"]},
        "rules": [{"if": {"fault": "none"}, "then": {"severity": 0}},
                  {"if": {"severity": 0}, "then": {"fault": "none"}},
                  {"if": {"fault": "brakes"}, "not": {"severity": 1}},
                  {"if": {"severity": 0}, "then": {"readiness": "FMC"}},
                  {"if": {"severity": 1}, "then": {"readiness": "FMC"}},
                  {"if": {"severity": 2}, "then": {"readiness": "PMC"}},
                  {"if": {"severity": 3}, "then": {"readiness": "NMC"}},
                  {"if": {"severity": 0}, "then": {"action": "continue_mission"}},
                  {"if": {"severity": 1}, "then": {"action": "schedule_maintenance"}},
                  {"if": {"readiness": "PMC"}, "then": {"action": "repair_before_dispatch"}},
                  {"if": {"readiness": "NMC"}, "then": {"action": "ground_vehicle"}},
                  {"if": {"action": "ground_vehicle"}, "then": {"review": True}}]},
    "trade": {
        "parents": {"evidence": ["option"], "risk": ["option"], "readiness": ["option", "evidence", "risk"],
                    "review": ["readiness"]},
        "rules": [{"if": {"option": "none"}, "then": {"evidence": 0}},
                  {"if": {"option": "none"}, "then": {"risk": 3}},
                  {"if": {"option": "none"}, "then": {"readiness": "not_ready"}},
                  {"if": {"risk": 3}, "then": {"readiness": "not_ready"}},
                  {"if": {"evidence": 0}, "not": {"readiness": "ready"}},
                  {"if": {"evidence": 1}, "not": {"readiness": "ready"}},
                  {"if": {"readiness": "not_ready"}, "then": {"review": True}},
                  {"if": {"readiness": "needs_more_evidence"}, "then": {"review": True}}]},
}

QUESTIONS = {
    "maintenance": {
        "fault": {"type": "choice", "instructions": "Which subsystem is at fault, by the policy in the state?",
                  "criteria": {f: ("no fault" if f == "none" else "the %s" % f) for f in FAULTS}},
        "severity": {"type": "score", "instructions": "How severe is the fault, by the policy's levels?",
                     "criteria": ["0: no fault", "1: fault within its limit", "2: past its limit by under 10%",
                                  "3: past its limit by 10% or more"]},
        "readiness": {"type": "choice", "instructions": "What is the vehicle's readiness status?", "criteria": READY},
        "action": {"type": "choice", "instructions": "What maintenance action does the policy call for?",
                   "criteria": ACTIONS},
        "review": {"type": "noul", "instructions": "The policy requires a human to review this case.",
                   "criteria": {"true": "a human must review it", "false": "no human review is required"}},
    },
    "trade": {
        "option": {"type": "choice", "instructions": "Which vendor does the selection rule choose?",
                   "criteria": {**{v: "vendor %s" % v for v in VENDORS}, "none": "no vendor meets every threshold"}},
        "evidence": {"type": "score", "instructions": "How sufficient is the test evidence for the chosen vendor?",
                     "criteria": ["0: no government tests", "1: one test", "2: two or three tests", "3: four or more"]},
        "risk": {"type": "score", "instructions": "What is the schedule risk of the chosen vendor?",
                 "criteria": ["0: on time or early", "1: one to three months late", "2: four to six months late",
                              "3: more than six months late, or no compliant vendor"]},
        "readiness": {"type": "choice", "instructions": "Is the source selection ready for decision?",
                      "criteria": {"ready": "ready for the decision", "needs_more_evidence": "needs more test evidence",
                                   "not_ready": "not ready"}},
        "review": {"type": "noul", "instructions": "The milestone decision authority must review this decision.",
                   "criteria": {"true": "the authority must review it", "false": "no review is required"}},
    },
}


def order(q):
    t, c = q["type"], q.get("criteria")
    return [False, True] if t == "noul" else list(range(len(c))) if t == "score" else list(c)


def readiness(rng, i):
    fault = rng.choice(FAULTS)
    conflict = fault != "none" and rng.random() < 0.2
    sensors, codes, note = [], [], "Routine inspection; the operator reports no complaints."
    sev = 0
    for f, (name, unit, lim, sign, nom, sym, dtc) in SUBSYSTEMS.items():
        v = nom + rng.uniform(-0.03, 0.03) * nom
        if f == fault:
            band = rng.choice([1, 2, 3])
            gap = {1: rng.uniform(-0.08, -0.01), 2: rng.uniform(0.01, 0.09), 3: rng.uniform(0.11, 0.3)}[band]
            v = lim * (1 + sign * gap)
            sev = max(band, 2) if f == "brakes" else band
            codes.append(rng.choice(dtc))
            note = "Operator reports: %s." % rng.choice(sym)
        sensors.append({"sensor": name, "reading": round(v, 1), "unit": unit,
                        "limit": ("at most %g" if sign > 0 else "at least %g") % lim})
    if conflict:
        other = rng.choice([f for f in SUBSYSTEMS if f != fault])
        note = "Operator reports: %s." % rng.choice(SUBSYSTEMS[other][5])
    rng.shuffle(sensors)
    ready = ["FMC", "FMC", "PMC", "NMC"][sev]
    action = ["continue_mission", "schedule_maintenance", "repair_before_dispatch", "ground_vehicle"][sev]
    state = {"vehicle": "LTV-%04d" % (1000 + i), "mission": rng.choice(["patrol", "convoy", "training", "reserve"]),
             "operator_note": note, "sensors": sensors, "trouble_codes": codes, "policy": POLICY_R}
    gold = {"fault": fault, "severity": sev, "readiness": ready, "action": action,
            "review": action == "ground_vehicle" or conflict}
    return state, gold


def trade(rng, i):
    need = {"range_km": rng.choice([300, 400, 500]), "mtbf_h": rng.choice([500, 750, 1000]),
            "unit_cost_musd": rng.choice([1.5, 2.0, 2.5])}
    vendors, ok = [], []
    for v in VENDORS:
        meets = rng.random() < 0.55
        spec = {"vendor": v,
                "range_km": need["range_km"] + rng.randint(0, 120) if meets or rng.random() < 0.5 else
                need["range_km"] - rng.randint(10, 80),
                "mtbf_h": need["mtbf_h"] + rng.randint(0, 400) if meets or rng.random() < 0.5 else
                need["mtbf_h"] - rng.randint(20, 200),
                "unit_cost_musd": round(need["unit_cost_musd"] - rng.uniform(0.05, 0.6), 2) if meets or rng.random() < 0.5
                else round(need["unit_cost_musd"] + rng.uniform(0.05, 0.6), 2),
                "government_tests": rng.choice([0, 1, 2, 3, 4, 5]),
                "delivery_months_late": rng.choice([-2, 0, 0, 1, 2, 3, 5, 6, 8, 11])}
        good = spec["range_km"] >= need["range_km"] and spec["mtbf_h"] >= need["mtbf_h"] and \
            spec["unit_cost_musd"] <= need["unit_cost_musd"]
        if good:
            ok.append(spec)
        vendors.append(spec)
    qty = rng.choice([10, 20, 30])
    best = min(ok, key=lambda s: s["unit_cost_musd"]) if ok else None
    if best:
        t, late = best["government_tests"], best["delivery_months_late"]
        ev = 0 if t == 0 else 1 if t == 1 else 2 if t <= 3 else 3
        risk = 0 if late <= 0 else 1 if late <= 3 else 2 if late <= 6 else 3
    else:
        ev, risk = 0, 3
    ready = "not_ready" if not best or risk == 3 else "needs_more_evidence" if ev <= 1 else "ready"
    over = bool(best) and best["unit_cost_musd"] * qty > 50
    state = {"program": "vehicle power unit, lot %d" % (i + 1), "quantity": qty, "thresholds": {
        "range_km": "at least %d" % need["range_km"], "mtbf_h": "at least %d" % need["mtbf_h"],
        "unit_cost_musd": "at most %.2f" % need["unit_cost_musd"]}, "vendors": vendors, "policy": POLICY_T}
    gold = {"option": best["vendor"] if best else "none", "evidence": ev, "risk": risk, "readiness": ready,
            "review": ready != "ready" or over}
    return state, gold


def cases(n=200, seed=13):
    """n cases of each family, [state, questions, gold]."""
    out = []
    for fam, make in (("maintenance", readiness), ("trade", trade)):
        rng = random.Random("%d/%s" % (seed, fam))
        for i in range(n):
            st, g = make(rng, i)
            qs = QUESTIONS[fam]
            gold = {q: {"idx": order(qs[q]).index(g[q])} for q in qs}
            gold["_wf"] = fam
            assert not broken(fam, {q: g[q] for q in qs}), (fam, g)
            out.append([st, qs, gold])
    return out


def broken(fam, a):
    """The rules an assignment {qid: value} breaks."""
    out = []
    for r in GRAPHS[fam]["rules"]:
        if all(a[k] == v for k, v in r["if"].items()):
            if "then" in r and any(a[k] != v for k, v in r["then"].items()):
                out.append(r)
            if "not" in r and all(a[k] == v for k, v in r["not"].items()):
                out.append(r)
    return out


def project(fam, marg):
    """The assignment of greatest joint log-probability under independent marginals
    {qid: [p, ...] in harness order} that breaks no rule; exhaustive over the product."""
    qs = QUESTIONS[fam]
    ids = list(qs)
    import math
    best, arg = -math.inf, None
    for combo in itertools.product(*[range(len(order(qs[q]))) for q in ids]):
        a = {q: order(qs[q])[i] for q, i in zip(ids, combo)}
        if broken(fam, a):
            continue
        s = sum(math.log(max(marg[q][i], 1e-12)) for q, i in zip(ids, combo))
        if s > best:
            best, arg = s, dict(zip(ids, combo))
    return arg
