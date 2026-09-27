"""Stub a heavy engine into sys.modules, so a unit test never loads one.

Every engine this studio uses is imported inside the function that needs it:
mflux in generator.py, mlx-vlm in rewriter.py, torch and diffusers in the two
PEP 723 child scripts. That deferred import is what makes a unit test possible
with no GPU: the test puts a stub in sys.modules first, and the real import
never runs. The weights are never read and nothing is downloaded.

The stub replaces a whole dotted chain, so `from mflux.models.flux2.variants
import Flux2Klein` resolves against the stub rather than against the model. A
name that is not declared resolves against nothing, which is deliberate: a stub
that answers to everything would hide a real import the code still makes.

Every name it touched goes back the way it was on exit, so one test cannot leak
a fake torch into the next one.

    with heavy_modules({"mflux.models.flux2.variants": {"Flux2Klein": FakeKlein}}):
        models = KleinModels(job, on_step)  # imports the stub, not the weights

`unittest.mock` supplies the recording. Give a declared name a Mock and the test
can assert the arguments the adapter passed, not only that it returned a value.
"""

import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from types import ModuleType
from typing import Any


def _chain(name: str) -> Iterator[str]:
    """Every dotted prefix of a name, shortest first: a, a.b, a.b.c."""
    parts = name.split(".")
    for end in range(1, len(parts) + 1):
        yield ".".join(parts[:end])


@contextmanager
def heavy_modules(modules: Mapping[str, Mapping[str, Any]]) -> Iterator[None]:
    """Install a stub module for each dotted name, and restore all of them after.

    Each value holds that module's own attributes. The parent chain is stubbed
    too, because `import a.b.c` imports `a` and then `a.b` before it reaches the
    leaf. Every stub is a package, so the import machinery descends into it.
    """
    saved: dict[str, ModuleType | None] = {}
    try:
        for name, attributes in modules.items():
            for prefix in _chain(name):
                if prefix in saved:
                    continue
                saved[prefix] = sys.modules.get(prefix)
                package = ModuleType(prefix)
                package.__path__ = []  # a package: `import a.b.c` descends into it
                sys.modules[prefix] = package
                parent, _, leaf = prefix.rpartition(".")
                if parent:
                    setattr(sys.modules[parent], leaf, package)
            for attribute, value in attributes.items():
                setattr(sys.modules[name], attribute, value)
        yield
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
