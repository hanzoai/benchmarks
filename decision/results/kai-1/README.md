# kai-1 on the frozen harness

kai-1's answers to every harness question, the ones the Decision Suite's harness rows and the research runs `<suite>-harness-kai-1.0834a74f-kai` (api.hanzo.ai/v1/research, ended 2026-10-03) were scored from.

| | |
|---|---|
| model | kai-1: the a7-512 checkpoint, `model.safetensors` SHA-256 `0834a74f2d140642a453373da09e5a128e3d2c8d9e8bb1dcaf86d7210a4ecdfc`, with a HelpSteer2 capability routed by keys no harness question uses, so the base answers every question here |
| preds | `preds.json.gz`: `bench preds` (hanzo-inc/kai) over `results/states.json.gz`, CUDA BF16, 2026-10-03; 11,099 of 11,099 questions answered. Its `model` field was a local path and reads `kai-1` here; nothing else changed |
| scores | `scores.json`, `table.md`: `python harness/merge.py --kai results/kai-1/preds.json.gz --out results/kai-1`, Laya and Jev beside it from their recorded preds |

`python harness/digest.py results/kai-1/preds.json.gz` prints each suite's digest; each equals the `preds sha256` in the notes of that suite's research run, as `harness/digest.py results/jev/preds.json.gz` does for Jev's. Every accuracy and calibration figure the runs report equals `scores.json`.

The weights are not public. Asking Kai again (`harness/run_kai.py`) measures the model api.hanzo.ai serves at the time, not these bits; see `../../SUITE.md`.
