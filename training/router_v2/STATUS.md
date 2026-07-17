# Router v2 candidate status

Last evaluated: 2026-07-17 on an RTX 3050 Laptop GPU (4 GB VRAM).

## Best trained candidate

`sciplotter-mini-1.7b-router-v2-r2` resumes the 3-epoch Qwen3-1.7B QLoRA
candidate with two conservative stabilization epochs (5e-5, then 2.5e-5).
The final epoch used 3.214 GB peak allocated VRAM and reached validation loss
0.1441317.

One deterministic prompt per held-out semantic seed (47 total) produced:

- strict selection-only JSON: 100%
- tool selection overall: 95.45% (42/44)
- English tool selection: 100% (22/22)
- Thai tool selection: 90.91% (20/22)
- direct-answer protocol: 100% (3/3)

The two remaining model-only confusions are `list_fit_models` vs `fit_curve`
and `plot_chart` vs `plot_columns` in Thai. Further fitting against the same
validation prompts was stopped to avoid turning the held-out set into training
data. The application hybrid router handles narrow, high-confidence forms of
these intents deterministically while leaving ambiguous language to the model.

## Release decision

This adapter is a development candidate, not a release model. It does not meet
the 98% overall / 95% per-language tool gates, so sealed acceptance v4 has not
been evaluated. Its SHA-256 remains:

`5b48cb06b28e582bb2dc49417a9cec0158dd7a7b9685d1a103c91be648cc4361`

The next model iteration must use new naturally written development prompts and
then pass the unchanged validation gates before acceptance v4 may be opened.
