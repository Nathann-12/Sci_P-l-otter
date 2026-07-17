"""Pinned local-model catalogue for commercial SciPlotter distributions.

Downloads are immutable GGUF files with an exact size and SHA-256.  A release
must update this source file (and therefore the signed application) to change a
model URL; the app never trusts an unsigned remote catalogue.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Iterable

MODEL_CATALOG_VERSION = "1.0"


@dataclass(frozen=True)
class ModelPack:
    pack_id: str
    display_name: str
    model_id: str
    filename: str
    download_url: str
    sha256: str
    size_bytes: int
    min_ram_gb: float
    recommended_ram_gb: float
    context_size: int
    quantization: str
    license_name: str
    license_url: str
    source_url: str
    description: str
    commercial_use: bool = True
    backend: str = "llama.cpp"

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "ModelPack":
        fields = cls.__dataclass_fields__
        return cls(**{name: data[name] for name in fields if name in data})


BUILTIN_MODEL_PACKS = (
    ModelPack(
        pack_id="qwen3-0.6b-q8",
        display_name="SciPlotter AI Starter (Qwen3 0.6B)",
        model_id="Qwen/Qwen3-0.6B-GGUF:Q8_0",
        filename="Qwen3-0.6B-Q8_0.gguf",
        download_url=(
            "https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/resolve/main/"
            "Qwen3-0.6B-Q8_0.gguf"
        ),
        sha256="9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031",
        size_bytes=639_446_688,
        min_ram_gb=3.0,
        recommended_ram_gb=4.0,
        context_size=4096,
        quantization="Q8_0",
        license_name="Apache-2.0",
        license_url="https://huggingface.co/Qwen/Qwen3-0.6B/blob/main/LICENSE",
        source_url="https://huggingface.co/Qwen/Qwen3-0.6B-GGUF",
        description="Smallest pack; best for routing plots and common analyses.",
    ),
    ModelPack(
        pack_id="qwen3-1.7b-q4",
        display_name="SciPlotter AI Plus (Qwen3 1.7B)",
        model_id="ggml-org/Qwen3-1.7B-GGUF:Q4_K_M",
        filename="Qwen3-1.7B-Q4_K_M.gguf",
        download_url=(
            "https://huggingface.co/ggml-org/Qwen3-1.7B-GGUF/resolve/main/"
            "Qwen3-1.7B-Q4_K_M.gguf"
        ),
        sha256="d2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5",
        size_bytes=1_282_439_264,
        min_ram_gb=4.0,
        recommended_ram_gb=8.0,
        context_size=4096,
        quantization="Q4_K_M",
        license_name="Apache-2.0",
        license_url="https://huggingface.co/Qwen/Qwen3-1.7B/blob/main/LICENSE",
        source_url="https://huggingface.co/ggml-org/Qwen3-1.7B-GGUF",
        description="Higher-capacity optional pack for local scientific assistance.",
    ),
)


def model_packs() -> Iterable[ModelPack]:
    return BUILTIN_MODEL_PACKS


def get_model_pack(pack_id: str) -> ModelPack:
    for pack in BUILTIN_MODEL_PACKS:
        if pack.pack_id == pack_id:
            return pack
    raise KeyError(f"Unknown model pack: {pack_id}")
