"""Operation boundary records keep the original output separate from retained data."""

from dataclasses import FrozenInstanceError

import pytest

from studio.l1_entities.operation import CompletedOperation, OperationOutput


def test_operation_outputs_preserve_value_identity_and_do_not_allow_reassignment():
    value = object()
    prepared = OperationOutput(value, {"items": []})
    completed = CompletedOperation(prepared.value, 12.5)

    assert completed.value is value
    assert prepared.retained == {"items": []}
    with pytest.raises(FrozenInstanceError):
        completed.finished_at = 25  # ty: ignore[invalid-assignment] - exercise the runtime boundary
