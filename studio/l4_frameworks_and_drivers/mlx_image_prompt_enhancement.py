"""Image-aware Gemma enhancement inside the pinned video environment.

Only this preparation pass uses mlx-vlm. Video text encoding stays on the engine's
existing implementation, and the caller frees this model before loading a video pack.
"""

import importlib
from typing import Any, cast


class ImagePromptEnhancer:
    def load(self, path):
        try:
            self._vlm = cast(Any, importlib.import_module("mlx_vlm"))
        except ModuleNotFoundError as error:
            raise RuntimeError(
                "Install mlx-vlm==0.4.3 in the LTX engine environment for image-aware enhancement."
            ) from error
        self._model, self._processor = self._vlm.load(path)
        encoder = cast(Any, importlib.import_module("ltx_core_mlx.text_encoders.gemma.encoders.base_encoder"))
        self._system = encoder.GemmaLanguageModel().default_gemma_i2v_system_prompt

    def enhance_i2v(self, prompt, image, seed):
        mx = cast(Any, importlib.import_module("mlx.core"))
        images = cast(Any, importlib.import_module("PIL.Image"))
        templates = cast(Any, importlib.import_module("mlx_vlm.prompt_utils"))
        messages = [
            {"role": "system", "content": self._system},
            {"role": "user", "content": f"User Raw Input Prompt: {prompt}."},
        ]
        formatted = templates.apply_chat_template(self._processor, self._model.config, messages, num_images=1)
        mx.random.seed(seed)
        with images.open(image) as source:
            result = self._vlm.generate(
                self._model,
                self._processor,
                formatted,
                image=[source.convert("RGB")],
                max_tokens=512,
                temperature=0.7,
                verbose=False,
            ).text.strip()
        if not result:
            raise ValueError("The image-aware LTX enhancer returned an empty prompt.")
        return result
