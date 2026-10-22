"""Publish completion or failure through the same operation lifecycle for all clients."""

from collections.abc import Callable

from studio.l1_entities.operation import CompletedOperation, OperationOutput
from studio.l2_use_cases.boundaries.operation_gateway import OperationGateway


class CompleteOperationUseCase:
    def __init__(self, operations: OperationGateway):
        self._operations = operations

    def execute(self, operation_id: str, action: Callable[[], OperationOutput]) -> CompletedOperation:
        try:
            output = action()
            completed_at = self._operations.finish(operation_id, output.retained)
            return CompletedOperation(output.value, completed_at)
        except Exception as error:
            self._operations.fail(operation_id, error)
            raise
