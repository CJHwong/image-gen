"""Compose JSON adapters explicitly, as the production composition root does."""

from studio.l2_use_cases.complete_operation_use_case import CompleteOperationUseCase
from studio.l2_use_cases.prepare_batch_use_case import PrepareBatchUseCase
from studio.l3_interface_adapters.api.json_api import JsonApi
from studio.l3_interface_adapters.gateways.in_memory_operation_gateway import InMemoryOperationGateway


def api_for(controller, video=None, voice=None):
    operations = InMemoryOperationGateway()
    return JsonApi(
        controller,
        video,
        voice,
        operations=operations,
        completion=CompleteOperationUseCase(operations),
        batches=PrepareBatchUseCase(),
    )
