"""Sensors and media: decisions over signals, not prose.

Laya and Jev read text only, so each signal reaches them as its best text rendering, a JSON state:
per-channel summary statistics with units (mean, std, min, max, RMS and the domain's standard
ones), then a downsampled series; statistics come first, so a state cut at the checkpoint's
max_len loses series before statistics. Kai's Evidence encoders would read the signals
themselves; until they land, a Kai checkpoint answers the same text (`bench preds`).

har     UCI HAR (Anguita et al. 2013), CC BY 4.0, archive.ics.uci.edu/static/public/240,
        sha256 c00b8030..1031. Test split (subjects unseen in training), 300 windows by seed 13:
        9 raw inertial channels (body and total acceleration in g, gyroscope in rad/s), 128
        samples at 50 Hz, in mg and mrad/s; 32 points per channel. choice: 6 activities.
cmapss  C-MAPSS FD001 (Saxena et al. 2008, NASA Ames PCoE), U.S. Government work (public
        domain), phm-datasets.s3.amazonaws.com/NASA/6.+Turbofan+Engine+Degradation+Simulation+
        Data+Set.zip, sha256 c9c5dec1..b3b2. All 100 test engines, gold RUL_FD001: the 14
        sensors that vary, each with its mean over the first and the last 30 cycles, its slope
        over the last 30, and the fleet's mean when new and at failure (from train_FD001); 24
        points for four of them. score: remaining life 0-25, 26-50, 51-100,
        >100 cycles.
mimii   MIMII (Purohit et al. 2019), CC BY-SA 4.0, zenodo.org/records/3384388 6_dB_valve.zip
        (6.9 GB, md5 fe5fb7c3..1892): only the members used are read, by HTTP range. 100
        recordings, 50 normal and 50 abnormal, across valves id_00/02/04/06 by seed 13, channel
        0 of 8, 16 kHz, 10 s: level, crest factor, kurtosis, zero-crossing rate, spectral
        centroid, roll-off and flatness, six band energies, beside the same valve's normal
        reference (mean and std over 10 other normal recordings), then a 40-frame loudness
        envelope. noul: abnormal. The data is used, not redistributed (cases are gitignored).
cwru    dropped: the CWRU Bearing Data Center (engineering.case.edu/bearingdatacenter) states no
        licence or terms of use on any of its pages (welcome, project-history,
        apparatus-and-procedures, download-data-file, 12k-drive-end-bearing-fault-data,
        normal-baseline-data; checked 2026-09-25), only a university copyright notice.

Laya runs as its router sends these states (English checkpoint, max_len 512) and, as long., on
the multilingual checkpoint with max_len 8192, its README's recipe for long documents.

Keys cap/sensors/<who>/[long.]<dataset>.<metric>: accuracy, macrof1, ece, brier, unanswered,
zeroprob; auc for mimii (p(abnormal) against the label); laya statecut (share of states cut at
max_len) and rejected; jev p50ms, usd and errors.

    python sensors.py [--who laya,jev,kai] [--kai CHECKPOINT]
"""
import argparse
import concurrent.futures as cf
import hashlib
import io
import json
import os
import random
import struct
import threading
import time
import urllib.error
import urllib.request
import zipfile

import numpy as np

import cap

RAW = os.path.join(cap.SCRATCH, "data")
CASES = os.path.join(cap.CASES, "sensors.json.gz")
SEED = 13
SOURCES = {
    "har": ("https://archive.ics.uci.edu/static/public/240/human+activity+recognition+using+smartphones.zip",
            "c00b803081a5c797cd5e4b83700a9810b38d53d9d84e01917e090e1fdbc81031", "CC BY 4.0"),
    "cmapss": ("https://phm-datasets.s3.amazonaws.com/NASA/6.+Turbofan+Engine+Degradation+Simulation+Data+Set.zip",
               "c9c5dec12a945a82e8bb4446589d7fb3cc057b5e5d81fa1a12e25ee9912ad3b2", "U.S. Government work"),
    "mimii": ("https://zenodo.org/records/3384388/files/6_dB_valve.zip?download=1",
              "md5:fe5fb7c337cd701b1d31dc641e621892", "CC BY-SA 4.0"),
}
DROPPED = {"cwru": "no licence or terms of use stated by engineering.case.edu/bearingdatacenter (checked "
                   "2026-09-25: welcome, project-history, apparatus-and-procedures, download-data-file, "
                   "12k-drive-end-bearing-fault-data, normal-baseline-data); only a copyright notice"}


def r3(x):
    return float("%.4g" % x)


def r6(x):
    return float("%.6g" % x)


def fetch(name):
    url, digest, _ = SOURCES[name]
    path = os.path.join(RAW, name + ".zip")
    if not os.path.exists(path):
        os.makedirs(RAW, exist_ok=True)
        urllib.request.urlretrieve(url, path)
    assert cap.sha(path) == digest, "%s: sha256 differs from the pinned archive" % name
    return zipfile.ZipFile(path)


# ------------------------------------------------------------------ UCI HAR
ACTS = {"walking": "walking on level ground", "walking_upstairs": "walking up stairs",
        "walking_downstairs": "walking down stairs", "sitting": "sitting still", "standing": "standing still",
        "laying": "lying down"}
CHANNELS = [("body_acc_%s" % a, "mg") for a in "xyz"] + [("body_gyro_%s" % a, "mrad/s") for a in "xyz"] + \
           [("total_acc_%s" % a, "mg") for a in "xyz"]


def har(n=300):
    outer = fetch("har")
    inner = zipfile.ZipFile(io.BytesIO(outer.read("UCI HAR Dataset.zip")))
    base = "UCI HAR Dataset/test/"
    y = np.loadtxt(io.BytesIO(inner.read(base + "y_test.txt")), dtype=int)
    sig = {c: np.loadtxt(io.BytesIO(inner.read(base + "Inertial Signals/%s_test.txt" % c))) for c, _ in CHANNELS}
    idx = sorted(random.Random(SEED).sample(range(len(y)), n))
    q = {"type": "choice", "instructions": "Which activity was the person doing during this window of motion data "
         "from a smartphone worn at the waist?", "criteria": ACTS}
    rows = []
    for i in idx:
        stats, series = {}, {}
        for c, unit in CHANNELS:
            x = 1e3 * sig[c][i]  # g -> mg, rad/s -> mrad/s
            stats[c] = [unit] + [round(float(v), 1) for v in (x.mean(), x.std(), x.min(), x.max(), np.sqrt((x ** 2).mean()))]
            series[c] = [int(round(v)) for v in x[::4]]
        st = {"sensor": "smartphone accelerometer and gyroscope at the waist", "window": "2.56 s at 50 Hz, 128 samples",
              "stat_columns": ["unit", "mean", "std", "min", "max", "rms"], "channels": stats,
              "series_every_4th_sample": series}
        rows.append([st, {"activity": q}, {"activity": {"idx": int(y[i]) - 1}}])
    return rows


# ------------------------------------------------------------------ C-MAPSS FD001
SENSORS = {  # column: (name, description, unit); the 14 that vary in FD001
    2: ("T24", "total temperature at LPC outlet", "°R"), 3: ("T30", "total temperature at HPC outlet", "°R"),
    4: ("T50", "total temperature at LPT outlet", "°R"), 7: ("P30", "total pressure at HPC outlet", "psia"),
    8: ("Nf", "physical fan speed", "rpm"), 9: ("Nc", "physical core speed", "rpm"),
    11: ("Ps30", "static pressure at HPC outlet", "psia"), 12: ("phi", "fuel flow to Ps30 ratio", "pps/psi"),
    13: ("NRf", "corrected fan speed", "rpm"), 14: ("NRc", "corrected core speed", "rpm"),
    15: ("BPR", "bypass ratio", "-"), 17: ("htBleed", "bleed enthalpy", "-"),
    20: ("W31", "HPT coolant bleed", "lbm/s"), 21: ("W32", "LPT coolant bleed", "lbm/s")}
SERIES = (4, 7, 11, 12)
BANDS = [(0, 25), (26, 50), (51, 100), (101, 10 ** 6)]


def table(z, name):
    return np.loadtxt(io.BytesIO(z.read(name)))


def cmapss():
    outer = fetch("cmapss")
    inner = zipfile.ZipFile(io.BytesIO(outer.read("6. Turbofan Engine Degradation Simulation Data Set/CMAPSSData.zip")))
    train, test = table(inner, "train_FD001.txt"), table(inner, "test_FD001.txt")
    rul = np.loadtxt(io.BytesIO(inner.read("RUL_FD001.txt")), dtype=int)
    col = lambda s: 4 + s  # unit, cycle, 3 settings, then s1..s21
    units = np.unique(train[:, 0])
    new = {s: float(np.mean([train[train[:, 0] == u][:30, col(s)].mean() for u in units])) for s in SENSORS}
    end = {s: float(np.mean([train[train[:, 0] == u][-1, col(s)] for u in units])) for s in SENSORS}
    q = {"type": "score", "instructions": "How many operating cycles remain before this engine fails?",
         "criteria": ["25 cycles or fewer", "26 to 50 cycles", "51 to 100 cycles", "more than 100 cycles"]}
    rows = []
    for k, u in enumerate(np.unique(test[:, 0])):
        h = test[test[:, 0] == u]
        stats = {}
        for s, (nm, desc, unit) in SENSORS.items():
            x = h[:, col(s)]
            last = x[-30:]
            stats["%s, %s" % (nm, desc)] = [unit, r6(x[:30].mean()), r6(last.mean()),
                                            r3(np.polyfit(np.arange(len(last)), last, 1)[0]), r6(new[s]), r6(end[s])]
        pick = np.linspace(0, len(h) - 1, min(24, len(h))).round().astype(int)
        series = {SENSORS[s][0]: [r6(v) for v in h[pick, col(s)]] for s in SERIES}
        st = {"asset": "turbofan engine %d (simulated, sea-level fleet, one fault mode)" % int(u),
              "cycles_observed": int(len(h)),
              "columns": ["unit", "mean of first 30 cycles", "mean of last 30 cycles", "slope per cycle over last 30",
                          "fleet mean when new", "fleet mean at failure"],
              "sensors": stats, "series_24_points_over_history": series}
        band = next(i for i, (lo, hi) in enumerate(BANDS) if lo <= rul[k] <= hi)
        rows.append([st, {"remaining_life": q}, {"remaining_life": {"idx": band}}])
    return rows


# ------------------------------------------------------------------ MIMII valve, 6 dB
class Remote(io.RawIOBase):
    """A file read by HTTP range requests: zipfile over it reads only the members asked for."""

    def __init__(self, url):
        self.url, self.pos = url, 0
        r = urllib.request.urlopen(urllib.request.Request(url, headers={"Range": "bytes=0-0"}), timeout=60)
        self.size = int(r.headers["Content-Range"].split("/")[1])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.size + off
        return self.pos

    def readinto(self, b):
        n = min(len(b), self.size - self.pos)
        if n <= 0:
            return 0
        req = urllib.request.Request(self.url, headers={"Range": "bytes=%d-%d" % (self.pos, self.pos + n - 1)})
        for attempt in range(10):  # Zenodo answers 429 to bursts
            try:
                d = urllib.request.urlopen(req, timeout=300).read()
                break
            except urllib.error.HTTPError as e:
                if e.code not in (429, 500, 502, 503, 504) or attempt == 9:
                    raise
                time.sleep(int(e.headers.get("Retry-After") or 0) or min(120, 5 * 2 ** attempt))
        b[:len(d)] = d
        self.pos += len(d)
        return len(d)


def members():
    """(test [(name, abnormal)], reference {id: [name]}): 50 normal and 50 abnormal recordings
    spread over the four valves, and 10 other normal recordings of each valve."""
    d = os.path.join(RAW, "mimii")
    listing = os.path.join(d, "names.txt")
    if os.path.exists(listing):
        names = open(listing).read().split()
    else:
        os.makedirs(d, exist_ok=True)
        names = [n for n in zipfile.ZipFile(io.BufferedReader(Remote(SOURCES["mimii"][0]), 1 << 20)).namelist()
                 if n.endswith(".wav")]
        open(listing, "w").write("\n".join(names))
    rng = random.Random(SEED)
    ids = sorted({n.split("/")[1] for n in names})
    test, ref = [], {}
    for j, i in enumerate(ids):
        k = 13 if j < 2 else 12  # 13 + 13 + 12 + 12 = 50 of each kind
        normal = sorted(n for n in names if n.split("/")[1] == i and "/normal/" in n)
        abnormal = sorted(n for n in names if n.split("/")[1] == i and "/abnormal/" in n)
        pick = rng.sample(normal, k + 10)
        ref[i] = pick[k:]
        test += [(n, False) for n in pick[:k]] + [(n, True) for n in rng.sample(abnormal, k)]
    return test, ref


LOCAL = threading.local()


def get(name):
    """A member of the archive, cached under RAW/mimii; one remote zip per thread."""
    path = os.path.join(RAW, "mimii", name.replace("/", "_"))
    if not os.path.exists(path):
        if not hasattr(LOCAL, "zip"):
            LOCAL.zip = zipfile.ZipFile(io.BufferedReader(Remote(SOURCES["mimii"][0]), 1 << 20))
        with open(path + ".part", "wb") as f:
            f.write(LOCAL.zip.read(name))
        os.rename(path + ".part", path)
    return path


def wav(name):
    """Channel 0 of a member as float in [-1, 1]."""
    b = open(get(name), "rb").read()  # RIFF chunks; the files are WAVE_FORMAT_EXTENSIBLE, which wave refuses
    i, ch, rate, bits, data = 12, 0, 0, 0, None
    while i + 8 <= len(b):
        tag, n = b[i:i + 4], struct.unpack("<I", b[i + 4:i + 8])[0]
        if tag == b"fmt ":
            ch, rate, bits = struct.unpack("<H", b[i + 10:i + 12])[0], struct.unpack("<I", b[i + 12:i + 16])[0], \
                struct.unpack("<H", b[i + 22:i + 24])[0]
        elif tag == b"data":
            data = b[i + 8:i + 8 + n]
        i += 8 + n + (n & 1)
    assert bits in (16, 32) and data is not None, (path, bits)
    x = np.frombuffer(data, dtype=np.int16 if bits == 16 else np.int32).reshape(-1, ch)[:, 0]
    return x / float(2 ** (bits - 1)), rate


AUDIO = ("level_dbfs", "peak_dbfs", "crest_factor", "kurtosis", "zero_crossings_per_s", "spectral_centroid_hz",
         "spectral_rolloff85_hz", "spectral_flatness")
EDGES = [0, 250, 500, 1000, 2000, 4000, 8000]


def audio(x, rate):
    db = lambda v: 20 * np.log10(max(v, 1e-9))
    rms = np.sqrt((x ** 2).mean())
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / rate)
    c = np.cumsum(spec) / spec.sum()
    z = (x - x.mean()) / (x.std() + 1e-12)
    out = {"level_dbfs": db(rms), "peak_dbfs": db(np.abs(x).max()), "crest_factor": np.abs(x).max() / (rms + 1e-12),
           "kurtosis": float((z ** 4).mean()), "zero_crossings_per_s": float((np.diff(np.sign(x)) != 0).sum() / (len(x) / rate)),
           "spectral_centroid_hz": float((f * spec).sum() / spec.sum()), "spectral_rolloff85_hz": float(f[np.searchsorted(c, 0.85)]),
           "spectral_flatness": float(np.exp(np.log(spec + 1e-20).mean()) / spec.mean())}
    for lo, hi in zip(EDGES[:-1], EDGES[1:]):
        out["band_%d_%d_hz_db" % (lo, hi)] = 10 * np.log10(max(spec[(f >= lo) & (f < hi)].sum() / spec.sum(), 1e-12))
    return {k: r3(v) for k, v in out.items()}


def mimii():
    test, ref = members()
    with cf.ThreadPoolExecutor(3) as ex:
        list(ex.map(get, [n for n, _ in test] + [n for ns in ref.values() for n in ns]))
    base = {i: [audio(*wav(n)) for n in ns] for i, ns in ref.items()}
    q = {"type": "noul", "instructions": "This valve recording is abnormal: the valve is malfunctioning, judged "
         "against the same valve's normal reference.",
         "criteria": {"true": "the valve is malfunctioning", "false": "the valve is operating normally"}}
    rows, digest = [], hashlib.sha256()
    for n, bad in test:
        x, rate = wav(n)
        digest.update(n.encode() + hashlib.sha256(x.tobytes()).digest())
        i = n.split("/")[1]
        feats = audio(x, rate)
        refs = {k: {"mean": r3(np.mean([b[k] for b in base[i]])), "std": r3(np.std([b[k] for b in base[i]]))}
                for k in feats}
        frame = len(x) // 40
        env = [round(20 * np.log10(max(np.sqrt((x[j * frame:(j + 1) * frame] ** 2).mean()), 1e-9)), 1) for j in range(40)]
        st = {"machine": "solenoid valve %s, factory recording with background noise at 6 dB SNR" % i.replace("_", " "),
              "recording": "10 s at %d Hz, microphone channel 0 of 8" % rate, "features": feats,
              "normal_reference_10_recordings": refs, "loudness_envelope_dbfs_250ms_frames": env}
        rows.append([st, {"abnormal": q}, {"abnormal": {"idx": int(bad)}}])
    return rows, digest.hexdigest()


# ------------------------------------------------------------------ run
def cases():
    if os.path.exists(CASES):
        return cap.load(CASES)
    rows, digest = mimii()
    S = {"har": har(), "cmapss": cmapss(), "mimii": rows, "_mimii_members_sha256": digest}
    cap.dump(S, CASES)
    return S


def auc(rows, p):
    """ROC AUC of p(true) for a noul question, over answered cases (ties count half)."""
    s = [(p["%d/%s" % (ci, q)][1], g[q]["idx"]) for ci, (_, qs, g) in enumerate(rows) for q in qs
         if p.get("%d/%s" % (ci, q)) is not None]
    pos = [a for a, y in s if y == 1]
    neg = [a for a, y in s if y == 0]
    if not pos or not neg:
        return None
    return float(np.mean([(a > b) + 0.5 * (a == b) for a in pos for b in neg]))


def main(who, kai_model):
    C = cases()
    S = cap.trim({k: v for k, v in C.items() if not k.startswith("_")})
    B = cap.backends(who, kai_model)
    keys, detail, spent = cap.Keys("sensors"), {"dropped": DROPPED}, 0.0
    pending = {"kai": "Evidence encoders not landed (hanzoai/decision origin/main %s); a checkpoint given here "
                      "answers the text rendering" % os.environ.get("DECISION_MAIN", "20742d5, 2026-09-25")}
    for w, b in B.items():
        runs = {}
        if w == "laya":
            for n, rows in S.items():
                runs[n] = b.preds(rows, tag="laya " + n)
                runs[n]["fit"] = b.fit(rows)
            ag = b.agent("multilingual")
            was = dict(ag.cfg)
            ag.cfg["max_len"] = 8192
            for n, rows in S.items():
                runs["long." + n] = b.preds(rows, model="multilingual", tag="laya long " + n)
                runs["long." + n]["fit"] = b.fit(rows, model="multilingual")
            ag.cfg.clear()
            ag.cfg.update(was)
        elif w == "jev":
            runs = {n: b.preds(rows, "sensors." + n) for n, rows in S.items()}
        else:
            path = os.path.join(cap.SCRATCH, "sensors.json.gz")
            cap.dump(S, path)
            try:
                runs = b.preds(path, path + ".kai.json.gz")
            except cap.Pending as e:
                pending["kai"] += "; " + str(e)
                continue
        for n, r in runs.items():
            rows = S[n.split(".")[-1]]
            m = cap.score(rows, r["p"])
            if n.endswith("mimii"):
                m["auc"] = auc(rows, r["p"])
            keys.metrics(w, n + ".", m, ("accuracy", "macro_f1", "ece", "brier", "unanswered", "zero_prob", "auc"))
            if "fit" in r:
                keys.put(w, n + ".statecut", r["fit"]["state_cut"] / r["fit"]["questions"])
                keys.put(w, n + ".rejected", r["fit"]["rejected"] / r["fit"]["questions"])
            if w == "jev":
                keys.put(w, n + ".p50ms", cap.pct(r["latency_ms"], 50))
                keys.put(w, n + ".usd", r["cost_usd"])
                keys.put(w, n + ".errors", r["n_errors"])
                spent += r["cost_usd"]
            if r.get("seconds") and m.get("n"):
                keys.put(w, n + ".msperq", 1e3 * r["seconds"] / m["n"])
            detail.setdefault(n, {})[w] = {"metrics": m, **{x: r[x] for x in ("fit", "dropped", "route", "n_errors",
                                           "error_kinds", "errors", "served", "cost_usd", "input_tokens") if x in r}}
            cap.dump(r["p"], os.path.join(cap.RESULTS, "sensors", "%s.%s.preds.json.gz" % (w, n)))
    meta = {w: b.meta for w, b in B.items()}
    meta.update(pending=pending, jev_usd=round(spent, 6), mimii_members_sha256=C["_mimii_members_sha256"],
                sources={k: {"url": u, "digest": d, "licence": l} for k, (u, d, l) in SOURCES.items()},
                cases={n: len(r) for n, r in S.items()},
                chars={n: int(np.median([len(json.dumps(r[0], ensure_ascii=False)) for r in rows])) for n, rows in S.items()})
    return cap.save("sensors", keys, detail, meta)


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--who", default="laya,jev")
    a.add_argument("--kai")
    x = a.parse_args()
    main(x.who.split(","), x.kai)
