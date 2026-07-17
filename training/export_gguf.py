"""Convert a merged HF model to GGUF, quantize it, and emit release metadata."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_quantizer(llama_dir: Path) -> Path:
    names = ("llama-quantize.exe", "llama-quantize")
    candidates = [llama_dir / name for name in names]
    candidates += [llama_dir / "build" / "bin" / name for name in names]
    for path in candidates:
        if path.is_file():
            return path
    raise SystemExit("Could not find llama-quantize in the supplied llama.cpp directory.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", type=Path, help="Merged Hugging Face model directory")
    parser.add_argument("llama_cpp", type=Path, help="Pinned llama.cpp source/build directory")
    parser.add_argument("output", type=Path)
    parser.add_argument("--quantization", default="Q8_0", choices=("Q8_0", "Q4_K_M"))
    parser.add_argument("--pack-id", default="sciplotter-mini-0.6b-v1")
    parser.add_argument("--display-name", default="SciPlotter Mini 0.6B v1")
    args = parser.parse_args()

    converter = args.llama_cpp / "convert_hf_to_gguf.py"
    if not converter.is_file():
        raise SystemExit("convert_hf_to_gguf.py was not found in llama.cpp.")
    quantizer = find_quantizer(args.llama_cpp)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    intermediate = args.output.with_name(args.output.stem + "-F16.gguf")
    subprocess.run(
        [sys.executable, str(converter), str(args.model), "--outfile", str(intermediate), "--outtype", "f16"],
        check=True,
    )
    subprocess.run(
        [str(quantizer), str(intermediate), str(args.output), args.quantization],
        check=True,
    )
    intermediate.unlink(missing_ok=True)
    release = {
        "pack_id": args.pack_id,
        "display_name": args.display_name,
        "model_id": args.pack_id,
        "filename": args.output.name,
        "download_url": "REPLACE_WITH_SIGNED_RELEASE_URL",
        "sha256": sha256(args.output),
        "size_bytes": args.output.stat().st_size,
        "min_ram_gb": 3.0,
        "recommended_ram_gb": 4.0,
        "context_size": 4096,
        "quantization": args.quantization,
        "license_name": "Apache-2.0",
        "license_url": "INCLUDE_RELEASE_LICENSE_URL",
        "source_url": "INCLUDE_MODEL_CARD_URL",
        "description": "SciPlotter bilingual scientific tool router.",
        "commercial_use": True,
        "backend": "llama.cpp",
    }
    manifest = args.output.with_suffix(".catalog-entry.proposed.json")
    manifest.write_text(
        json.dumps(release, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(release, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
