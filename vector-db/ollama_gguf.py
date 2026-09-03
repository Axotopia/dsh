#!/usr/bin/env python3
"""ollama_gguf: read Ollama GGUF model metadata without loading the weights.

This module reads ONLY the GGUF header and metadata key/value section (never the
weight tensors), so it is fast and memory-safe even for 100+ GB models, and it
uses only the Python standard library (no third-party packages).

It is the parsing + architecture-inference layer for ``optimize_num_ctx.py``:
it exposes enough model facts (attention layers, KV heads, KV head dim, native
context, hybrid/MLA/sliding-window kind) to estimate the KV-cache size that a
``num_ctx`` value will consume on the GPU.
"""

from __future__ import annotations

import os
import struct

# Ollama blob media types
MODEL_MEDIA_TYPE = "application/vnd.ollama.image.model"

# Number of bytes per KV-cache element by dtype.
DTYPE_BYTES = {"f32": 4, "f16": 2}

# Default compute/activation reserve (GB) used when recommending num_ctx.
DEFAULT_OVERHEAD_GB = 4


class GGUFError(ValueError):
    """Raised when a file is not a readable GGUF file."""


# --------------------------------------------------------------------------- #
# Low-level GGUF reader (metadata section only)
# --------------------------------------------------------------------------- #
def _read_string(f):
    n = struct.unpack("<Q", f.read(8))[0]
    return f.read(n).decode("utf-8", "replace")


def _read_value(f, t):
    """Read a single GGUF metadata value of type ``t`` (see GGUF enum)."""
    if t == 0:  # UINT8
        return struct.unpack("<B", f.read(1))[0]
    if t == 1:  # INT8
        return struct.unpack("<b", f.read(1))[0]
    if t == 2:  # UINT16
        return struct.unpack("<H", f.read(2))[0]
    if t == 3:  # INT16
        return struct.unpack("<h", f.read(2))[0]
    if t == 4:  # UINT32
        return struct.unpack("<I", f.read(4))[0]
    if t == 5:  # INT32
        return struct.unpack("<i", f.read(4))[0]
    if t == 6:  # FLOAT32
        return struct.unpack("<f", f.read(4))[0]
    if t == 7:  # BOOL
        return bool(struct.unpack("<B", f.read(1))[0])
    if t == 8:  # STRING
        return _read_string(f)
    if t == 9:  # ARRAY
        at = struct.unpack("<I", f.read(4))[0]
        ln = struct.unpack("<Q", f.read(8))[0]
        return [_read_value(f, at) for _ in range(ln)]
    if t == 10:  # UINT64
        return struct.unpack("<Q", f.read(8))[0]
    if t == 11:  # INT64
        return struct.unpack("<q", f.read(8))[0]
    if t == 12:  # FLOAT64
        return struct.unpack("<d", f.read(8))[0]
    return None


def parse_gguf(path):
    """Parse a GGUF file's header + metadata.

    Returns ``(version, tensor_count, metadata_dict)``. ``tensor_count`` is read
    from the header (the weight tensors themselves are never read).
    """
    with open(path, "rb") as f:
        if f.read(4) != b"GGUF":
            raise GGUFError(f"{path!r} is not a GGUF file")
        version = struct.unpack("<I", f.read(4))[0]
        tensor_count = struct.unpack("<Q", f.read(8))[0]
        kv_count = struct.unpack("<Q", f.read(8))[0]
        meta = {}
        for _ in range(kv_count):
            key = _read_string(f)
            t = struct.unpack("<I", f.read(4))[0]
            meta[key] = _read_value(f, t)
    return version, tensor_count, meta


# --------------------------------------------------------------------------- #
# Ollama store resolution (tag -> GGUF blob path)
# --------------------------------------------------------------------------- #
def ollama_models_dir():
    """Return the Ollama model store directory."""
    env = os.environ.get("OLLAMA_MODELS")
    if env:
        return env
    # Linux/macOS default
    default = os.path.join(os.path.expanduser("~"), ".ollama", "models")
    if os.path.isdir(default):
        return default
    # Windows default (Ollama keeps models under %USERPROFILE%\.ollama\models)
    return default


def _manifest_path(tag):
    """Map an Ollama tag ('ns/name:tag' or 'name:tag' or 'name') to a manifest path."""
    name, _, tagpart = tag.partition(":")
    tagpart = tagpart or "latest"
    parts = name.split("/")
    if len(parts) == 2:
        namespace, model = parts
    else:
        namespace, model = "library", parts[0]
    return os.path.join(
        ollama_models_dir(), "manifests", "registry.ollama.ai",
        namespace, model, tagpart,
    )


def resolve_gguf(target):
    """Resolve a target to a GGUF file path.

    ``target`` may be a direct path to a ``.gguf`` file, or an Ollama model tag.
    Returns ``(gguf_path, weight_bytes_or_None)``.
    """
    if os.path.isfile(target):
        return target, os.path.getsize(target)

    manifest = _manifest_path(target)
    if not os.path.isfile(manifest):
        raise GGUFError(f"no Ollama manifest found for {target!r} at {manifest!r}")

    import json

    with open(manifest, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    candidates = [
        (layer.get("digest", ""), layer.get("size", 0))
        for layer in data.get("layers", [])
        if layer.get("mediaType") == MODEL_MEDIA_TYPE
    ]
    if not candidates:
        raise GGUFError(f"no model layer found in manifest for {target!r}")

    candidates.sort(key=lambda c: c[1], reverse=True)
    digest, size = candidates[0]
    blob = os.path.join(ollama_models_dir(), "blobs", digest.replace("sha256:", "sha256-"))
    if not os.path.isfile(blob):
        raise GGUFError(f"blob for {target!r} not found at {blob!r}")
    return blob, size or os.path.getsize(blob)


# --------------------------------------------------------------------------- #
# Architecture inference from metadata
# --------------------------------------------------------------------------- #
def _num_full_attn_layers(block_count, interval):
    """Layers in a hybrid model that run full attention (every `interval`th)."""
    if not block_count or not interval:
        return block_count or 0
    return (block_count + interval - 1) // interval  # ceil(block_count/interval)


def infer_layout(meta):
    """Infer the KV-cache-relevant architecture facts from GGUF metadata.

    Returns a dict with::

        arch, kind ('dense'|'hybrid'|'mla'|'sliding-window'),
        block_count, attn_layers, kv_heads, kv_head_dim,
        native_ctx, kv_lora_rank, sliding_window
    """
    arch = meta.get("general.architecture", "")

    def g(key):
        return meta.get(f"{arch}.{key}")

    block_count = g("block_count")
    head_count_kv = g("attention.head_count_kv")
    key_length = (g("attention.key_length") or g("attention.value_length")
                  or g("attention.key_length_mla") or g("attention.head_dim"))
    if key_length is None:
        # Many GGUFs omit key/value length and only carry head_dim, or expect it
        # derived from the embedding size and query-head count.
        embedding_length = g("embedding_length")
        head_count = g("attention.head_count")
        if embedding_length and head_count:
            key_length = embedding_length // head_count
    kv_lora_rank = g("attention.kv_lora_rank")
    sliding_window = g("attention.sliding_window")
    full_interval = g("full_attention_interval")

    native_ctx = g("context_length") or meta.get("general.context_length")

    # Per-layer KV-head array (e.g. nemotron_h_moe): nonzero entries are the
    # layers that actually use attention; the rest are SSM/linear layers.
    if isinstance(head_count_kv, list):
        layers = [i for i, v in enumerate(head_count_kv) if v]
        kv_heads = max(head_count_kv) if head_count_kv else 0
        head_dim = key_length
        kind = "hybrid"
        attn_layers = len(layers)
        det = f"per-layer KV heads ({len(layers)} attention layers of {block_count})"

    elif kv_lora_rank:
        kv_heads = head_count_kv or 0
        head_dim = key_length
        kind = "mla"
        attn_layers = _num_full_attn_layers(block_count, full_interval)
        det = f"MLA (kv_lora_rank={kv_lora_rank})"

    elif full_interval:
        kv_heads = head_count_kv or 0
        head_dim = key_length
        kind = "hybrid"
        attn_layers = _num_full_attn_layers(block_count, full_interval)
        det = f"hybrid (every {full_interval}th of {block_count} = {attn_layers} attn)"

    elif sliding_window:
        kv_heads = head_count_kv or 0
        head_dim = key_length
        kind = "sliding-window"
        attn_layers = block_count or 0
        det = f"sliding-window (window={sliding_window}, {attn_layers} layers)"

    else:
        kv_heads = head_count_kv or 0
        head_dim = key_length
        kind = "dense"
        attn_layers = block_count or 0
        det = f"dense ({attn_layers} attention layers)"

    return {
        "arch": arch or "unknown",
        "kind": kind,
        "block_count": block_count,
        "attn_layers": attn_layers,
        "kv_heads": kv_heads,
        "kv_head_dim": head_dim,
        "native_ctx": native_ctx,
        "kv_lora_rank": kv_lora_rank,
        "sliding_window": sliding_window,
        "detection": det,
    }


def kv_bytes_per_token(layout, dtype="f16"):
    """Estimate KV-cache bytes consumed per token of context.

    ``dtype`` is f16 (default) or f32. For hybrid models only the full-attention
    layers grow with context; SSM/linear layers use fixed-size recurrent state.
    For sliding-window models the global layers grow (assumed first + last) and
    the rest are bounded by the window. MLA (DeepSeek/GLM) uses a compressed
    latent, estimated conservatively here.
    """
    per_elem = DTYPE_BYTES.get(dtype, 2)
    kind = layout["kind"]
    if kind == "mla":
        rank = layout.get("kv_lora_rank") or layout["kv_head_dim"] or 0
        # compressed latent shared across heads; conservative estimate
        return layout["attn_layers"] * rank * 2 * per_elem
    kv_heads = layout["kv_heads"] or 0
    head_dim = layout["kv_head_dim"] or 0
    if not kv_heads or not head_dim:
        raise GGUFError(
            f"unknown KV geometry for arch {layout.get('arch')!r} "
            f"(kv_heads={kv_heads}, head_dim={head_dim}); pass the model tag "
            f"explicitly or skip it"
        )
    if kind == "sliding-window":
        global_layers = min(2, layout["attn_layers"])
        return 2 * global_layers * kv_heads * head_dim * per_elem
    return 2 * layout["attn_layers"] * kv_heads * head_dim * per_elem
