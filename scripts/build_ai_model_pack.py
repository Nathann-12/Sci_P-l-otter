"""Build a verified .scimodel bundle for an offline/full SciPlotter release."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.license_texts import APACHE_2_LICENSE  # noqa: E402
from ai.model_catalog import MODEL_CATALOG_VERSION, get_model_pack  # noqa: E402


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(pack_id: str, model_file: Path, output: Path) -> Path:
    pack = get_model_pack(pack_id)
    if model_file.stat().st_size != pack.size_bytes:
        raise SystemExit("Model size does not match the pinned catalogue entry.")
    if file_sha256(model_file) != pack.sha256:
        raise SystemExit("Model SHA-256 does not match the pinned catalogue entry.")
    if output.suffix.casefold() != ".scimodel":
        output = output.with_suffix(".scimodel")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "catalog_version": MODEL_CATALOG_VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "pack": asdict(pack),
    }
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("LICENSE-model.txt", APACHE_2_LICENSE)
        archive.writestr(
            "MODEL-NOTICE.txt",
            f"{pack.display_name}\nSource: {pack.source_url}\nLicense: {pack.license_url}\n",
        )
        archive.write(model_file, pack.filename)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pack_id", help="Pinned ID from ai/model_catalog.py")
    parser.add_argument("model_file", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(build(args.pack_id, args.model_file, args.output))


if __name__ == "__main__":
    main()
