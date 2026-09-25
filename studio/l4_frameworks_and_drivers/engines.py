"""Which engine this machine can run. The one place the platform decides.

The probe answers a capability, not a platform string, so a Mac that later
wants the diffusers engine and a host that can only run diffusers come through
one function instead of a branch on `sys.platform`. Today the answer has one
value: both backends generate through mflux, which is MLX.
`gateways/qwen21/PORTABILITY.md` records what a second engine needs.
"""


class EngineUnavailable(Exception):
    """No engine for this machine. The message names the remedy."""


def mlx_available() -> bool:
    """Whether this machine can run MLX, answered as a yes or a no.

    A build without the metal submodule answers no rather than raising, so a
    caller always gets a decision to act on.
    """
    try:
        import mlx.core as mx
    except ImportError:
        return False
    metal = getattr(mx, "metal", None)
    return bool(metal is not None and metal.is_available())


def require_mlx() -> None:
    """Refuse a real studio where no backend can run.

    The stub passes through, so the page stays workable on a host that cannot
    run a model. The refusal happens before the port is bound, so such a host
    never occupies it.
    """
    if not mlx_available():
        raise EngineUnavailable(
            "no MLX on this machine, so no backend can generate here: MLX runs on Apple Silicon only. "
            "The diffusers generate path is not built; see studio/l3_interface_adapters/gateways/qwen21/PORTABILITY.md."
        )
