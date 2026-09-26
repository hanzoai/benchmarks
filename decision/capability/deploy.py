"""Deployment facts, each from a check run here, not a score.

    offline     the backend answers one question inside a macOS sandbox that denies every
                network operation (sandbox-exec, `(deny network*)`), with HF_HUB_OFFLINE=1; the
                same sandbox is first shown to refuse an outbound HTTPS connection.
    leaves      whether the question's state leaves the machine: the backend needs the network
                to answer (it fails offline), or it does not.
    selfhosted  the weights are files on this machine: their path and SHA-256.
    fee         USD per call: the provider's reported usage.cost (mean over the ledger), or none.
    pinned      what fixes the answering model: a weights hash, or only a model name.

    python deploy.py [--who laya,jev,kai] [--kai CHECKPOINT]
"""
import argparse
import json
import os
import subprocess

import cap

SANDBOX = "(version 1)(allow default)(deny network*)"
STATE = {"message": "The card I ordered two weeks ago still has not arrived."}
QUESTIONS = {"intent": {"type": "choice", "instructions": "Which banking intent does `message` express?",
                        "criteria": {"card arrival": None, "lost or stolen card": None, "top up failed": None}}}


def probe(who):
    """One answer, printed as JSON; run inside and outside the sandbox."""
    if who == "net":
        import urllib.request
        urllib.request.urlopen("https://huggingface.co", timeout=10)
        print(json.dumps({"ok": True}))
    elif who == "laya":
        L = cap.Laya()
        _, r = L.call(STATE, QUESTIONS)
        print(json.dumps({"ok": True, "answer": r["answers"]["intent"]["choice"]}))
    else:
        d, _, err = cap.Jev().call(STATE, QUESTIONS, "deploy", timeout=30, tries=1)
        print(json.dumps({"ok": not err, "error": err, "served": d and d.get("model")}))


def sandboxed(args, env=None):
    e = dict(os.environ, HF_HUB_OFFLINE="1", UV_OFFLINE="1", **(env or {}))
    r = subprocess.run(["/usr/bin/sandbox-exec", "-p", SANDBOX, *args], capture_output=True, text=True, env=e,
                       timeout=900)
    tail = (r.stdout.strip().splitlines() or [""])[-1]
    return {"exit": r.returncode, "out": tail[:300], "err": (r.stderr.strip().splitlines() or [""])[-1][:300]}


def py(who):
    return [os.path.join(cap.HERE, "py"), "deploy.py", "--probe", who]


def main(who, kai_model):
    keys, detail = cap.Keys("deploy"), {}
    net = sandboxed(py("net"))
    detail["sandbox"] = {"profile": SANDBOX, "https": net}
    blocked = net["exit"] != 0
    keys.put("all", "sandbox.blocks", "yes" if blocked else "no")
    for w in who:
        d = detail.setdefault(w, {})
        if w == "kai":
            k = cap.Kai(kai_model) if kai_model else None
            if not k or not os.path.exists(k.bin):
                d["pending"] = "no Kai runtime or checkpoint"
                continue
            tiny = os.path.join(cap.SCRATCH, "deploy.cases.json.gz")
            cap.dump({"deploy": [[STATE, QUESTIONS, {"intent": {"idx": 0}}]]}, tiny)
            off = sandboxed([k.bin, "preds", "--model", kai_model, "--states", tiny, "--out", tiny + ".out"])
            d.update(offline=off, checkpoint=kai_model, weights=k.meta.get("weights"))
            ok = off["exit"] == 0
        else:
            off = sandboxed(py(w))
            ok = off["exit"] == 0 and '"ok": true' in off["out"]
            d["offline"] = off
        keys.put(w, "offline", "yes" if ok and blocked else "no")
        keys.put(w, "leaves", "no" if ok and blocked else "yes")
        if w == "laya":
            from huggingface_hub import snapshot_download
            local = snapshot_download(cap.BUNDLE, revision=cap.REV)
            files = {p: cap.sha(os.path.join(local, p)) for p in
                     ("model.safetensors", "multilingual/model.safetensors", "typed-decisions/model.safetensors")}
            d.update(weights=files, path=local, licence=open(os.path.join(os.environ["LAYA_SRC"], "LICENSE")).readline().strip())
            keys.put(w, "selfhosted", "yes")
            keys.put(w, "pinned", "weights sha256")
            keys.put(w, "fee", 0.0)
        elif w == "kai":
            keys.put(w, "selfhosted", "yes")
            keys.put(w, "pinned", "weights sha256")
            keys.put(w, "fee", 0.0)
        else:
            on = subprocess.run(py("jev"), capture_output=True, text=True, timeout=300)
            d["online"] = (on.stdout.strip().splitlines() or [""])[-1][:300]
            led = cap.load(cap.LEDGER)
            d["ledger"] = {k: led[k] for k in ("spent_usd", "calls")}
            keys.put(w, "fee", led["spent_usd"] / max(1, led["calls"]))
            try:
                from huggingface_hub import HfApi
                n = len(list(HfApi().list_models(author="typesafe", limit=100)))
            except Exception as e:
                n = "error: %s" % e
            d["hf_models_by_typesafe"] = n
            keys.put(w, "selfhosted", "no" if n == 0 else "check")
            keys.put(w, "pinned", "model name")
    return cap.save("deploy", keys, detail)


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--who", default="laya,jev")
    a.add_argument("--kai")
    a.add_argument("--probe")
    x = a.parse_args()
    probe(x.probe) if x.probe else main(x.who.split(","), x.kai)
