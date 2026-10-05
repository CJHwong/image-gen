"""Temporary: give the edit path the viggle schedule.

mflux 0.21.0 wires `--scheduler` into the text-to-image command only. The edit
variant's `generate_image` takes no scheduler argument and builds its `Config`
without one, so `Config` falls back to its own "linear" default. The viggle
distillation was trained on the raw nodes `[1.0, 0.9375, 0.875, 0.75, 0.5, 0.25]`
with no terminal rescale, and the model card says the base config's 0.02 terminal
"wrecks the last step". Sampling six steps on the wrong one of those schedules is
not a subtle difference.

So for the length of one call this module makes `Config`'s own default the viggle
schedule. It is a patch on a third-party class, and it exists only until mflux
gives the edit path a scheduler argument.
`test_upstream_still_lacks_a_scheduler_argument` fails on the day that lands, and
this module goes with it.

`Config` takes `scheduler` as a keyword with a default, and nothing in mflux passes
it positionally, so supplying the keyword when the caller omitted it is enough.

This sits beside the backends rather than inside one, because a backend that used
it would otherwise import another backend. `mflux_runtime` and `image_sizes` are
here for the same reason.
"""

from contextlib import contextmanager


@contextmanager
def viggle_schedule():
    """Make `Config`'s default the viggle schedule for the length of the block."""
    # Importing this module is what registers the schedule under its name.
    import mflux.models.qwen21.model.qwen21_scheduler  # noqa: F401
    from mflux.models.common.config.config import Config

    original = Config.__init__

    def with_viggle(self, *args, **kwargs):
        kwargs.setdefault("scheduler", "viggle_turbo")
        original(self, *args, **kwargs)

    Config.__init__ = with_viggle
    try:
        yield
    finally:
        Config.__init__ = original
