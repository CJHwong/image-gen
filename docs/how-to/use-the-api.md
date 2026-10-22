# Submit and observe an API operation

Start Open Imagine, then inspect the available controls:

```sh
curl -sS http://127.0.0.1:8765/api/v1/studio
```

Choose a backend, mode, and supported size from that response. Submit this small Image job:

```sh
curl -sS http://127.0.0.1:8765/api/v1/operations \
  -H 'Content-Type: application/json' \
  -d '{"kind":"image","backend":"qwen21_turbo","prompt":"A red pear on a wooden table, soft window light.","width":768,"height":768,"seed":7}'
```

Poll the returned `status_url` until its status is `succeeded`, `failed`, or `cancelled`.
On success, fetch `result_url`. For an ordered batch, submit `items` with the shared settings and follow each item’s result URL.
One operation reserves the engine; a conflicting request returns `409`.

Read `/api/v1/state` for activity across workspaces and tabs.
To stop work, POST an empty JSON object to `/api/v1/operations/{id}/cancel`.
Download finished results before server retention expires.

For other media and modes, use the named examples at **http://127.0.0.1:8765/api/docs**.
The raw OpenAPI document is `/api/v1/openapi.json`.
[API.md](../../API.md) documents model differences, media encoding, batches, validation, and official prompting guides.
