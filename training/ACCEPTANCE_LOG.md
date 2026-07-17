# SciPlotter Mini acceptance log

Acceptance sets are single-use gates. Once results are viewed, their prompts
must not influence another training run; a later candidate needs a fresh test.

## Thai hard-negative acceptance v1 — consumed

- Dataset: `training/data/acceptance_test_v1_consumed.jsonl`
- SHA-256: `72209a4c318682463ef2636c992e3d83817f2d64b3f63bb68e52b8bfaea360b6`
- Scope: 28 unseen Thai intents, two per each of the 14 v2 failure groups
- Privacy: synthetic columns/values only; no researcher data
- Evaluated: 2026-07-16 Asia/Bangkok
- Status: **consumed; do not use to tune v3 or a later model**

| Candidate | JSON | Tool | Arguments / exact | Wall time |
|---|---:|---:|---:|---:|
| v2 (pre-repair control) | 100% | 92.86% | 60.71% | 524.7 s |
| v3 (frozen after validation selection) | 100% | 100% | 75.00% | 422.1 s |

The focused repair improved exact Thai tool calls by 14.29 percentage points
and tool selection by 7.14 points on the untouched set. It did not pass the
92% argument release gate. No training change was made from these acceptance
failures.

## Final balanced acceptance v2 — consumed

- Dataset: `training/data/final_acceptance_test.jsonl`
- SHA-256: `e2ef1f374b0fbe3318ca2d6e7c61aa4d1097f089a3feb3b27be9c4a229e6eeb1`
- Scope: 26 unseen intents: 14 tool calls and 12 direct answers; 13 English
  and 13 Thai
- Privacy: synthetic columns/values only; no researcher data
- Candidate: v4, frozen after validation selection and before this audit
- Evaluated: 2026-07-16 Asia/Bangkok
- Status: **consumed; do not use these failures to tune v4, v5 or a later model**

| Gate | Overall | English | Thai | Release target |
|---|---:|---:|---:|---:|
| Valid JSON | 100% | 100% | 100% | >= 99% |
| Correct tool | 92.86% | 100% | 85.71% | >= 97%; >= 95% each language |
| Exact tool call | 64.29% | 85.71% | 42.86% | — |
| Exact arguments | 71.43% | — | — | >= 92% |
| Direct answer | 83.33% | 100% | 66.67% | >= 95% |

- Exact records: 19/26 (73.08%)
- Wall time: 332.129 s; 692 generated tokens; 2.084 tokens/s
- Decision: **fail — do not merge, convert to GGUF, package or publish v4**

Manual review found seven genuine failures: one wrong tool selection, four
wrong argument sets, and two Thai requests that explicitly asked the assistant
not to act but received a tool call. The argument failures included an invented
parameter, an invalid weighting enum, reversing backward/forward fill, and
swapping gas-on/gas-off times. A future candidate needs new training evidence
that is independent of this audit and a completely fresh acceptance v3 set.

## v4 validation selection

Before the final audit was opened, v4 was selected using the existing grouped
validation set. On one record per semantic seed it achieved:

- tool calls: JSON 100%, correct tool 97.73%, exact arguments 86.36%
- English tool selection 100%; Thai tool selection 95.45%
- direct answers: 3/3 exact (100%)
- best validation loss: 0.19933929167900907 (epoch 1 of 2)

This repaired v3's direct-answer regression and modestly improved tool routing,
but exact arguments were already below the 92% release gate. The untouched
final audit then confirmed that the adapter is not ready for distribution.

## Historical v3 validation trade-off

On the existing 47-intent validation gate, v3 improved tool-call exactness from
68.18% to 84.09% and Thai tool-call exactness from 54.55% to 77.27%. However,
the compact repair set replayed only one direct-answer record, and direct-answer
accuracy regressed from 100% to 0%. v3 is therefore an experimental candidate,
not a release model.

## Release acceptance v3 — sealed and unopened

- Dataset: `training/data/release_acceptance_v3.jsonl`
- SHA-256: `342d1d34ee6b36c805fc214c161c09dc5e6e19a63090955fb8954c389bec1fef`
- Scope: 56 synthetic intents: one for every 44 registered tools plus 12
  direct answers; 28 English and 28 Thai
- Sealed: 2026-07-17 Asia/Bangkok, before full 1.7B training
- Status: **unopened; not consumed**

The gate was not evaluated because no Qwen3-1.7B candidate passed the existing
validation gates. Keeping it unopened preserves a useful independent test for
a future candidate trained without reading these prompts.

### Qwen3-1.7B validation experiment

All candidates used LoRA rank 8, NF4 QLoRA and the same schema v1.4 validation
set. Metrics use one record per held-out semantic seed.

| Candidate | Selection history | Eval loss | Tool | Arguments | Direct answer |
|---|---|---:|---:|---:|---:|
| v1 | one base epoch | 0.307851 | 95.45% | 70.45% | 33.33% |
| v2 | v1 + repair with grouped answer replay | 0.252277 | 95.45% | 68.18% | 66.67% |
| v3 | v2 + low-LR base stabilization | 0.247118 | 95.45% | 70.45% | 33.33% |
| v4-balanced | v1 + corrected 18-group answer replay | 0.248217 | 95.45% | 63.64% | 100% |
| v5-base2 | v1 + second base epoch | 0.241827 | 95.45% | 68.18% | 100% |

English tool selection reached 100% in all measured candidates, but Thai tool
selection remained 90.91%, below the 95% per-language gate. Manual review also
found semantic argument errors—wrong column spellings, invented thresholds and
sampling rates, wrong axes and wrong tool choice—which JSON grammar cannot
repair. Therefore no 1.7B adapter was merged, converted, packaged or published.

During this experiment, the repair sampler was found to group two answer
wrappers under each shared seed, so only 9 of the intended 18 answer records
were selected per epoch. The replay IDs are now unique; the corrected repair
file contains 118 records and 118 seed groups. Acceptance v3 remained byte-for-
byte unchanged after this correction.
