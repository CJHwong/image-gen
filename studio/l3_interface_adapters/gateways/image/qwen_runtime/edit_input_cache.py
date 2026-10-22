"""Bound evaluated edit encodings to exact inputs and one model's lifetime."""

import hashlib
from collections import OrderedDict
from collections.abc import Callable
from typing import Any


class EvaluatedCache:
    def __init__(self, *, max_entries: int = 8, max_bytes: int = 64 * 1024**2):
        self.entries: OrderedDict[Any, tuple[Any, int]] = OrderedDict()
        self.bytes = 0
        self._max_entries = max_entries
        self._max_bytes = max_bytes

    def get(self, key, encode: Callable):
        if key in self.entries:
            self.entries.move_to_end(key)
            return self.entries[key][0]
        import mlx.core as mx

        try:
            encoded = encode()
            arrays = encoded if isinstance(encoded, tuple) else (encoded,)
            mx.eval(*arrays)
        except Exception:
            self.entries.clear()
            self.bytes = 0
            raise
        size = sum(array.nbytes for array in arrays)
        if size > self._max_bytes:
            return encoded
        while self.entries and (self.bytes + size > self._max_bytes or len(self.entries) >= self._max_entries):
            _, (_, removed_bytes) = self.entries.popitem(last=False)
            self.bytes -= removed_bytes
        self.entries[key] = (encoded, size)
        self.bytes += size
        return encoded


def cache_edit_inputs(model) -> None:
    import numpy as np

    prompts, references = EvaluatedCache(), EvaluatedCache()
    original_prompt, original_reference = model._encode_prompt, model.vae.encode

    def encode_prompt(prompt, images):
        key = (prompt, tuple((image.mode, image.size, _digest(image.tobytes())) for image in images))
        return prompts.get(key, lambda: original_prompt(prompt, images))

    def encode_reference(pixels):
        numeric = np.asarray(pixels)
        key = (numeric.shape, str(numeric.dtype), _digest(numeric.tobytes()))
        return references.get(key, lambda: original_reference(pixels))

    model._encode_prompt = encode_prompt
    model.vae.encode = encode_reference


def _digest(content: bytes) -> bytes:
    return hashlib.sha256(content).digest()
