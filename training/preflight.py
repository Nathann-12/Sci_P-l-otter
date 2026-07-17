"""Fail early when the local machine cannot safely start a training run."""
from __future__ import annotations

import importlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "torch", "transformers", "accelerate", "peft", "bitsandbytes", "numpy", "pandas"
)


def inspect_environment() -> dict:
    missing = []
    import_errors = {}
    for name in REQUIRED:
        if importlib.util.find_spec(name) is None:
            missing.append(name)
            continue
        try:
            importlib.import_module(name)
        except Exception as exc:
            missing.append(name)
            import_errors[name] = str(exc)
    result = {
        "python": sys.version.split()[0],
        "missing_packages": missing,
        "import_errors": import_errors,
        "cuda_available": False,
        "gpu": "",
        "vram_total_gb": 0.0,
        "vram_free_gb": 0.0,
        "recommended_mode": "unavailable",
        "ready": False,
        "warnings": [],
    }
    if "torch" not in missing:
        import torch

        result["torch"] = torch.__version__
        result["cuda_available"] = bool(torch.cuda.is_available())
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            free, total = torch.cuda.mem_get_info(0)
            result.update(
                gpu=props.name,
                vram_total_gb=round(total / 1024**3, 2),
                vram_free_gb=round(free / 1024**3, 2),
            )
            has_bnb = importlib.util.find_spec("bitsandbytes") is not None
            result["recommended_mode"] = "qlora" if has_bnb else "lora"
            if total < 3.5 * 1024**3:
                result["warnings"].append("Less than 3.5 GB total VRAM; training is unsupported.")
            if free < 3.0 * 1024**3:
                result["warnings"].append(
                    "Less than 3 GB VRAM is currently free; close GPU-using apps before training."
                )
        else:
            result["warnings"].append("CUDA is unavailable; CPU fine-tuning is intentionally disabled.")
    result["ready"] = not missing and result["cuda_available"] and result["vram_total_gb"] >= 3.5
    return result


def main() -> None:
    result = inspect_environment()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ready"] else 2)


if __name__ == "__main__":
    main()
