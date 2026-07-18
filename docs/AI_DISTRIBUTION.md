# SciPlotter local AI distribution

SciPlotter AI is an optional, local-only product component. Research data,
prompts, tool results, and plots are not sent to a cloud service. The only
network requests made by the model manager download public, version-pinned
model/runtime files chosen by the user.

## Product editions

| Edition | Installer contents | Intended buyer |
| --- | --- | --- |
| Core | SciPlotter, no model or runtime | Buyers who do not need AI; smallest download |
| AI Starter | Core + pinned llama.cpp runtime + Qwen3 0.6B Q8 pack | 4 GB office/lab PCs |
| AI Plus | Core + runtime; 1.7B Q4 pack downloaded on demand or bundled | 8 GB+ PCs and better Thai/multi-step routing |
| Offline Lab | AI Starter installer + `.scimodel` files on USB/institutional storage | Air-gapped research computers |

Do not put both models in the default installer. The app works without AI and
the **Models** screen installs only what the customer selects. This keeps the
Core download small and prevents model bandwidth from being paid for by every
customer.

## Current release status

The managed installer and Safe Router are product foundations, but the
fine-tuned **SciPlotter Mini** model is not yet a release model. The current
Router v2 candidate stays development-only until it passes the unchanged
overall and per-language gates and then the sealed acceptance set. Public Qwen
catalogue packs remain fallback/preview packs; never advertise the development
adapter as released or silently replace an existing catalogue hash.

On a clean installation the AI dock shows **Set up local AI**, never **Ready**.
Ready means the selected model, runtime, and minimum-memory checks all pass.
It is a technical readiness state, not a model-quality release claim; current
fallback packs are visibly labelled **Preview**. Catalogue metadata also binds
each pack to a router protocol and tool-schema version.
The Models screen's primary setup action installs the pinned runtime first,
then the selected model, and activates it only when the complete stack exists.
Separate component downloads and `.scimodel` import/export remain available for
administrators and air-gapped workflows.

## Release contract

1. Pin every URL, byte size, SHA-256, version, source, and license in
   `ai/model_catalog.py` or `ai/runtime_manager.py`.
2. Ship `llama-server` and all DLLs from the pinned runtime archive beside the
   application under `runtime/llama/<runtime-id>/`, together with the same
   verified `manifest.json` used by the per-user installer. The app also
   recognises a verified per-user runtime installed by the Models screen.
   A full installer may stage a verified model under
   `models/<pack-id>/` beside the executable; the same `manifest.json` and GGUF
   layout used by the per-user model directory is recognised automatically.
3. Include the Qwen Apache-2.0 license and llama.cpp MIT license in the product's
   Third Party Notices. Offline `.scimodel` files already contain the model
   license and source notice.
4. Code-sign the Windows installer and executable. Never replace the built-in
   catalogue with unsigned remote JSON.
5. Test the installer on a clean Windows VM with no Python, Ollama, or developer
   tools installed.

## Building an offline model file

Download the exact GGUF referenced by the catalogue, then run:

```powershell
.venv\Scripts\python.exe scripts\build_ai_model_pack.py `
  qwen3-0.6b-q8 Qwen3-0.6B-Q8_0.gguf dist\qwen3-0.6b-q8.scimodel
```

The script refuses files whose size or SHA-256 differs from the signed
catalogue. A customer can install the resulting file from **AI > Models >
Install offline pack** without internet access.

## Privacy and safety behaviour

- `llama-server` binds to `127.0.0.1` on a temporary port and its web UI is
  disabled.
- Local inference uses a dedicated no-proxy, no-redirect HTTP opener, so an
  operating-system or environment proxy cannot receive loopback prompts. Model
  and runtime downloads continue to follow the customer's normal proxy policy.
- Model and runtime downloads use HTTPS and are installed only after SHA-256
  verification.
- Ollama-compatible endpoints are accepted only on literal loopback hosts
  (`localhost`, `127.0.0.0/8`, or `::1`). Credentials, LAN/cloud hosts, and
  ambiguous URLs are rejected again at the network-client boundary.
- Archives reject POSIX and Windows traversal, drive/UNC paths, NTFS alternate
  streams, case-insensitive destination collisions, suspicious compression
  ratios, and unexpectedly large extraction sizes.
- Installed manifests must match the complete built-in catalogue record and
  catalogue version. Runtime executables must also be non-empty. A future deep
  verification command should re-hash installed files without blocking app
  startup.
- A custom executable or a same-named program found on `PATH` is not sufficient
  for the managed backend's Ready state. The runtime must come from the pinned,
  manifest-verified SciPlotter runtime installation.
- The model sees at most eight relevant tool descriptions per turn, not all app
  tools.
- Safe Router v2 gives current llama.cpp runtimes a strict, per-turn JSON Schema
  that permits only an answer or one offered tool name. The model is not allowed
  to author executable arguments. Older runtimes may still emit the legacy
  `arguments` object, but SciPlotter discards it.
- Tool arguments are rebuilt from the original request, registered enums and
  the active Book's real column names. Unstated numbers are omitted; missing
  required values, unknown quoted columns and ambiguous column roles produce a
  clarification instead of a tool call. Unit-bearing scientific inputs are
  converted only through explicit allowlists (for example cm to m and mm² to
  m²); incompatible units are rejected before execution.
- Data mutation and device control still require a native confirmation dialog
  after deterministic resolution and before execution.
- Cancellation is checked again after model inference and before a newly
  selected tool starts. An operation already executing may still finish, and
  the UI says so instead of claiming that no action ran.
- Statistics and scientific calculations remain deterministic SciPlotter code;
  the model is only an intent router and short-language explainer.

## Fine-tuned SciPlotter Mini

Keep the public Qwen pack IDs as the fallback while training. A future LoRA
release should be merged into a full checkpoint, converted to GGUF, quantized,
evaluated against the tool-routing test set, and added as a **new** immutable
catalogue entry. Never overwrite an existing pack ID or hash. Preserve the base
model license and add the fine-tune dataset/model notice to the offline bundle.
