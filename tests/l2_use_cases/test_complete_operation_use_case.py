"""Completion policy can run with a port double, without an API or a real store."""

from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import Cancelled
from studio.l1_entities.operation import OperationOutput
from studio.l2_use_cases.boundaries.operation_gateway import OperationGateway
from studio.l2_use_cases.complete_operation_use_case import CompleteOperationUseCase


def test_completion_returns_the_original_result_and_publishes_the_prepared_value():
    gateway = Mock(spec=OperationGateway)
    gateway.finish.return_value = 12.5
    result = object()
    answer = CompleteOperationUseCase(gateway).execute("owned", lambda: OperationOutput(result, {"images": []}))

    assert answer.value is result
    assert answer.finished_at == 12.5
    gateway.finish.assert_called_once_with("owned", {"images": []})
    gateway.fail.assert_not_called()


@pytest.mark.parametrize("error", [ValueError("engine failed"), Cancelled("cancelled")])
def test_failed_or_cancelled_actions_publish_the_same_exception_and_propagate_it(error):
    gateway = Mock(spec=OperationGateway)

    def action():
        raise error

    with pytest.raises(type(error)) as raised:
        CompleteOperationUseCase(gateway).execute("owned", action)

    assert raised.value is error
    gateway.fail.assert_called_once_with("owned", error)
    gateway.finish.assert_not_called()
