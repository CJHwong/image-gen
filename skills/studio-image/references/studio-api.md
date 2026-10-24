# Open Imagine Image API

Use live discovery as the contract. The examples below illustrate transport and workflow; choose the
actual backend, dimensions, fields, and limits from the running server.

## Discover without changing selection

GET these routes relative to the user's base URL:

| Route | Read for |
|---|---|
| `/api/v1/state` | Active operation across all three media modes |
| `/api/v1/studio` | `image.active`, `image.backends`, `image.capabilities` |
| `/api/v1/images/backends/{id}` | A listed model's capabilities without selecting it |
| `/api/v1/openapi.json` | Request schemas, named examples, descriptions, official prompt references |
| `/api/docs` | Rendered API documentation |

Inspect the chosen mode's `params`, `min_references`, `max_references`, `each_reference`,
`region_marking`, `looks`, `templates` and `estimate`. The page computes the time of one image as
`steps x step_cost x (1 + per_reference x max(0, references - 1)) x megapixels ^ exponent`, plus
`overhead` once per image or once per batch (`overhead_per_image`). Give the user that figure as a
rough guide, and compare it with each result's `elapsed`. A listed backend is not proof that its
weights are already installed. Missing weights follow the server's download policy; an accepted
request can still fail during preparation. Do not silently change the user's model.

## Submit and follow your operation

POST JSON to `/api/v1/operations` with `kind: "image"`, an explicit `backend`, and `mode:
"generate"` or `"edit"`. Use defaults from that mode; Turbo and full models can require different
sampling settings. Prefer an offered `size` for Generate and the Edit mode's `resolution: "match"`
when appropriate. Do not assume Generate and Edit parameter names are interchangeable. Match follows
the model's resolution policy, not necessarily the original pixel dimensions: read `width` and
`height` from the result.

Copy parameter ids from the mode's `params`, not from an example. On the Qwen backends, Generate
takes `size` and `guidance`, and Edit takes `resolution` (`match`, or a long side such as 512, 768,
1024 or 1344) and `cfg`. A `negative` does nothing unless `guidance` or `cfg` is above 1; above 1
each step runs twice, so an image takes about twice as long. Turbo's `steps` has one allowed value
(8 on Qwen-Image-2.1-Turbo); omit it to take the default.

An illustrative Generate payload (use only if discovery offers these values):

```json
{
  "kind": "image",
  "backend": "qwen21_turbo",
  "mode": "generate",
  "prompt": "Product photograph of one matte blue ceramic teapot on warm ivory paper. Three-quarter view, soft window light from the left, a grounded contact shadow. Teapot on the right, plain space on the left for copy. No lettering.",
  "size": "768x768",
  "seed": 7,
  "count": 1
}
```

Assign a unique `client_id` per submission and persist it with the exact request locally. Save the
returned `id` and `status_url` immediately. Poll that URL at a modest interval, such as 2 seconds.
Terminal statuses are `succeeded`, `failed`, and `cancelled`; `running` and `stopping` are not
finished. Read the terminal `error` when present. A progress counter reaching 100% does not mean an
operation succeeded.

Only one operation runs on the server. A `409` busy response creates no queued request: wait or
report it; never cancel someone else's operation to get a turn. Recheck state before submitting, and
still handle a busy response because another caller can race you. If a POST times out, read
`/api/v1/state` and look for an operation with that `client_id` before resubmitting: it might have
been accepted. If there is no unambiguous match, report the uncertainty rather than risking
duplicate work. Cancel only your operation when requested or needed within the authorized task, with
`POST /api/v1/operations/{id}/cancel`. Do not stop/restart the server.

## Results and durable files

Follow the operation's `result_url` when available. A normal Image result is JSON with `images`;
each image has `png_base64`, `width`, `height`, `seed`, `steps`, `prompt`, and `elapsed`. Decode the
base64 into a PNG and save metadata without duplicating its large base64 string. Check dimensions
from the result rather than assuming the request's size. An ordinary single job's result may return
`409` while running.

An explicit batch returns a manifest with `items`, `completed`, and `batch_total`. Follow each
completed item's own `result_url` to fetch its Image JSON. Indices start at one. Completed item
results can be downloaded while later items run, and after failure or cancellation. Inspect
`result_url` even after a terminal error to recover retained partial outputs. Do not confuse a
manifest with an `images` document.

Server results are temporary: retention is bounded by age, operation count, and bytes, and
restarting clears them. Save files promptly; keep the original request and operation metadata in the
output directory. Opening the browser is not required to create a result. The UI observes API
operations, but its browser library is not your durable export folder.

## References, templates, and edits

For Image Edit, put the instruction in `prompt` and send `references` as a list of actual base64
image strings or objects with `png_base64`. Data URLs work too. Normalize local references to PNG
when necessary; do not send filenames or pretend that a local path is an uploaded image. An edit of
a keeper uses `mode: "edit"`, its encoded PNG in `references`, an instruction such as “Change only
the backdrop to pale sage; preserve the teapot's silhouette, spout, handle, glaze and lighting,” and
that mode's supported settings.

Generate can also take one reference, when its `max_references` allows it: send it in `references`
as for Edit, with a `strength` between 0.05 and 1. A higher strength stays closer to the reference.
Use it to remake a small scout at a larger size with the same composition (see the [guided
flow](guided-flow.md)).

`looks` maps offered row names to option labels. `template` is an exact offered name;
`template_values` maps each complete bracket name in its text to replacement text. For `[product:
…]`, the key includes `product: …`, not just `product`. Templates supply the prompt; do not assume a
separate `prompt` is appended. Looks are appended afterward and some Image Looks also add negatives
and adjust guidance.

For region edits, use only the model's advertised `region_marking` path, with one picture. The Image
API takes the mark as the final reference with `mask: true` (on the item or the request). The page's
convention, which the API also accepts: an opaque PNG at the picture's size, black outside the area
and one flat named color inside it (orange `#e2761e`, red `#e2381f`, green `#2f9e4f` or blue
`#2f6fe0`), and a prompt that names the area as "the orange area of <image2>". There is no generic
rectangle-coordinate argument. See [editing](editing.md) for what a mark does and does not hold.

## Choose the right batch shape

- Same prompt, several variations: use `count` as the **total output count**.
- Distinct independent shots: use `items` with shared top-level defaults. Each item makes one output
  and can override prompt, seed, settings, or references. An item's `count` must be 1 and its
  `each_reference` false; the server rejects anything else.
- One instruction applied separately to multiple references: use the mode's `each_reference: true`;
  `per_reference_prompts` supplies one instruction per reference when needed. `count` remains the
  total, not the number per reference.
- One output combining several references: ordinary Edit with all references together,
  `each_reference: false`, and explicit roles in the prompt.

Explicit operation batches accept up to 16 items in the current API. The Image backend's `max_batch`
limits the simpler `count` path and may be lower (4 on the Qwen backends; confirm it live). With
`each_reference`, that path's limit also depends on the reference count. It is not a promise of GPU
concurrency. Confirm live limits. Batch submission does not guarantee simultaneous execution or a
particular speedup. Keep dependent hero-to-variation edits in later operations.
