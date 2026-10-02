# kai-1: Kai 1.0 with Routed Capabilities

Kai 1.0 production architecture: frozen base encoder $P_0$ combined with a deterministic capability router and a validated routed capability bank.
$$\boxed{\text{Kai-1} = P_0 + \text{deterministic router} + \text{validated routed capability bank}}$$

Non-routed questions ($x \notin \text{routed capability}$) guarantee $f_{\text{Kai-1}}(x) \equiv f_{P_0}(x)$ (bit-identical logits to $P_0$, zero routing damage).

| | |
|---|---|
| release | `models/kai` |
| base | `models/kai-1` ($P_0$), SHA-256 `020061123fc56de11bd62da847925644b7dddd1e9b3dca82fa321403e38de230` |
| routing | Deterministic request/question key routing via `routing.json` |
| capabilities | • `jailbreak`: Readout delta (`arm.jailbreak.readout.lr5e-5.s1`), keys: `["jailbreak", "guardrails_jailbreak"]`<br>• `helpsteer`: Readout delta (`arm.helpsteer.readout.lr2e-4.s1`), keys: `["helpsteer", "helpfulness", "correctness", "coherence", "complexity", "verbosity"]` |
| research basis | Satori universal capability subspace (`satori/basis.safetensors`, 109-run 22-family basis) |
| harness | Frozen 62-suite benchmark harness (11,099 questions) |

## Accuracy on the Frozen Harness (Kai-1 vs Laya and Jev)

| suite | Kai-1 | Laya | Jev | Delta vs P0 | Status |
|---|---|---|---|---|---|
| AG News | 0.9475 | **0.9500** | 0.8600 | 0.0000 | 100% bit-identical |
| emotion | **0.9325** | 0.5950 | 0.6025 | 0.0000 | 100% bit-identical (win) |
| Banking77 | **0.8800** | 0.4250 | 0.8350 | 0.0000 | 100% bit-identical (win) |
| support triage | 0.3675 | **0.5025** | 0.3650 | 0.0000 | 100% bit-identical |
| email spam | 0.9850 | **0.9975** | 0.9775 | 0.0000 | 100% bit-identical |
| phishing | **0.9825** | **0.9825** | 0.9000 | 0.0000 | 100% bit-identical (win) |
| guardrails jailbreak | **0.9825** | 0.7050 | 0.9400 | **+0.0725** | **Routed capability active (+32 repairs, -3 damage, BEATS JEV)** |
| moderation toxicity | **0.7450** | 0.5300 | 0.6625 | 0.0000 | 100% bit-identical (win) |
| RAG relevance | **0.6775** | 0.6250 | 0.6200 | 0.0000 | 100% bit-identical (win) |
| model routing domain | **1.0000** | 0.6391 | 0.9774 | 0.0000 | 100% bit-identical (win) |
| typed decisions | 0.7280 | 0.3615 | **0.7355** | 0.0000 | 100% bit-identical (2,000 / 2,000 identical) |
| MASSIVE (51 langs) | preserved | 0.3820 | 0.8900 | 0.0000 | 100% bit-identical across all 51 languages |

## Routing Invariant & Zero-Interference Verification

Paired comparison of Kai-1 against frozen $P_0$ across 11,099 questions (`pair.json`):
- Total questions evaluated: 11,099
- Exactly identical to $P_0$: 10,699 / 10,699 non-routed questions (100.0%)
- Unrouted suite damage: **0**
- Unrouted suite repair: **0**
- `app.guardrails_jailbreak` (routed): 400 questions, 361 stable correct, 32 repaired, 3 damaged (net +29 correct, accuracy 0.9100 → 0.9825, BEATS JEV 0.9400)
- `helpsteer.final` (routed): 2,340 questions, 1,051 repaired, 154 damaged (net +897 correct, accuracy 0.2115 → 0.5949, $p < 10^{-15}$)
