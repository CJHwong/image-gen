"""Restore the measured Turbo encoder without replacing diffusion weights."""

from pathlib import Path

from studio.l3_interface_adapters.gateways.image.shared.mflux_runtime import release_mlx_buffers


def restore_text_encoder(model, *, model_path: str, quantize: int | None) -> None:
    from mflux.models.qwen21.model.qwen21_text_encoder.qwen21_text_encoder import Qwen21TextEncoder
    from mflux.models.qwen21.qwen21_initializer import Qwen21Initializer
    from mflux.models.qwen21.weights.qwen21_weight_definition import Qwen21WeightDefinition

    class EncoderOnly(Qwen21WeightDefinition):
        @staticmethod
        def get_components():
            return [
                component for component in Qwen21WeightDefinition.get_components() if component.name == "text_encoder"
            ]

    bits = model.bits
    model.text_encoder = Qwen21TextEncoder()
    try:
        Qwen21Initializer.load_components(model, Path(model_path), EncoderOnly, quantize, validate=True)
    except Exception:
        model.text_encoder = None
        release_mlx_buffers()
        raise
    finally:
        # The component loader changes this shared field. The transformer keeps its original precision.
        model.bits = bits
