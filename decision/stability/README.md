# decision/stability

The same request, three times: does a model give the same answer? A model that answers one request two ways cannot be thresholded for automation.

`requests.jsonl.gz` holds 4,200 `/v1/decisions` bodies, Hanzo's own: each a support-ticket state (customer, account, order, device, message) and one typed question, a team to route to (choice of three), whether the user asks to cancel (yes/no) or how severe the issue is (score of three levels). Some messages carry text addressed to the model; they are part of the set as written. A request's `id` is the first 16 hex digits of the SHA-256 of its body (keys sorted, compact).

Each request was sent three times to each model, repeat 1 over every request before repeat 2. A request is identical when its three answers are the same JSON object: the same decision and the same probabilities, to the last digit the wire carries.

| model | identical | read |
|---|---|---|
| Kai: the kai-1.2 release (base weights `0834a74f2d140642a453373da09e5a128e3d2c8d9e8bb1dcaf86d7210a4ecdfc`, yes/no reader `3b85b6bd…`), `kai serve --device cpu --reach 32768`, four replicas on arm64-host, repeat r of request i on replica (i + r) mod 4 | 4,200 / 4,200 (100.0%) | 2026-10-14 |
| Jev: `typesafe/jev-1.13`, answered as `typesafe/jev-1.13-20260917`, through OpenRouter, the body with only `model` set | 1,858 / 4,200 (44.2%) | 2026-10-14 |

`results/<model>.json.gz` keeps, per request, the digest of each of its three answers (the first 16 hex digits of the SHA-256 of the answer, keys sorted), and what served them; the counts above are recomputed from them:

```sh
python stability/score.py                                                 # the recorded runs
export HANZO_API_KEY=...
python stability/run.py --url https://api.hanzo.ai --out runs/kai.jsonl   # every request, three times
python stability/run.py --url https://api.hanzo.ai --out runs/kai.jsonl --limit 100
python stability/score.py runs/kai.jsonl
```

`run.py --url a,b,c` spreads the repeats of a request over replicas as the recorded Kai run did. api.hanzo.ai serves the current production Kai through its gateway, which picks the replica. No file here calls Jev: its count is its recorded run (`--jev recorded`).
