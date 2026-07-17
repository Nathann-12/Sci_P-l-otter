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

## Release contract

1. Pin every URL, byte size, SHA-256, version, source, and license in
   `ai/model_catalog.py` or `ai/runtime_manager.py`.
2. Ship `llama-server` and all DLLs from the pinned runtime archive beside the
   application under `runtime/llama/`. The app also recognises a verified
   per-user runtime installed by the Models screen.
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
- Model and runtime downloads use HTTPS and are installed only after SHA-256
  verification.
- Archives reject traversal paths and suspiciously large extraction sizes.
- The model sees at most eight relevant tool schemas per turn, not all app tools.
- Current llama.cpp runtimes receive a strict, per-turn JSON Schema that permits
  only an answer or one of the offered tools, with exact argument names, types,
  required fields and categorical enum values. Older runtimes fall back to JSON
  object mode and still receive the same deterministic validation afterward.
- Model-authored arguments are schema-checked. Data mutation and device control
  require a native confirmation dialog before execution.
- Statistics and scientific calculations remain deterministic SciPlotter code;
  the model is only an intent router and short-language explainer.

## Fine-tuned SciPlotter Mini

Keep the public Qwen pack IDs as the fallback while training. A future LoRA
release should be merged into a full checkpoint, converted to GGUF, quantized,
evaluated against the tool-routing test set, and added as a **new** immutable
catalogue entry. Never overwrite an existing pack ID or hash. Preserve the base
model license and add the fine-tune dataset/model notice to the offline bundle.
