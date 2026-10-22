"""Whether this machine can run the MLX image engine.

Image backends use mflux, which requires MLX. The LTX video runner uses its
configured Python environment, but studio startup still checks MLX.
`gateways/image/qwen21/PORTABILITY.md` records the unverified CUDA path.
"""


class EngineUnavailable(Exception):
    """No engine for this machine. The message names the remedy."""


def mlx_available() -> bool:
    """Whether MLX can use a GPU on this machine.

    The generic device check covers Metal and CUDA builds.
    """
    try:
        import mlx.core as mx
    except ImportError:
        return False
    gpu = mx.Device(mx.DeviceType.gpu)
    return mx.is_available(gpu)


def require_mlx() -> None:
    """Refuse a real studio where no backend can run.

    The stub passes through, so the page stays workable on a host that cannot
    run a model. The refusal happens before the port is bound, so such a host
    never occupies it.
    """
    if not mlx_available():
        raise EngineUnavailable(
            "no MLX GPU is available on this machine, so no backend can run here: every image backend uses mflux, "
            "and mflux requires an MLX GPU. "
            "See studio/l3_interface_adapters/gateways/image/qwen21/PORTABILITY.md."
        )
