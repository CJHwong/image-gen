"""Publisher prompting references for Image and Video, separate from Studio capabilities."""

IMAGE_PROMPT_REFERENCES = """## Official Image prompting references

For Qwen-Image-2.1 start with the [publisher model card](https://huggingface.co/Qwen/Qwen-Image-2.1),
[2.1 release examples](https://qwen.ai/blog?id=qwen-image-2.1), and
[official repository](https://github.com/QwenLM/Qwen-Image). These provide generation, editing,
text-rendering and transparency examples; they are not a separate comprehensive 2.1 prompt manual.
Describe the desired image concretely. In Edit, identify what changes and what should remain consistent;
when supplying multiple references, explain each image's role. For lettering, specify the exact words
and their placement. Use the model card's transparency wording only if the discovered local output path
supports the required alpha behavior; a prompt alone is not an output-format guarantee.

These sources describe the full upstream model. Studio's selected backend capabilities determine reference
counts, dimensions, alpha output and available controls. Turbo is a separate accelerated checkpoint:
do not copy the full-model step count into Turbo requests. Use discovered defaults and named API examples.
Prompt examples are guidance, not proof that every upstream task works on the pinned MLX engine.
References checked 2026-10-22.
"""

VIDEO_PROMPT_REFERENCES = """## Official Video prompting references

Start with Lightricks' [prompting guide](https://docs.ltx.io/api-documentation/implementation-guides/prompting-guide)
for shot framing, visible action, characters, camera movement, lighting and audio. Describe action in time,
make camera movement relative to the subject explicit, and put spoken dialogue in quotation marks.
For one take use a flowing present-tense description; match the amount of action to the requested length.
The guide's multi-shot section is explicitly about LTX-2.5. Use a continuous shot for uninterrupted camera
movement or dialogue in one framing; do not assume 2.5-specific behavior transfers to 2.3.

| Reference | Scope and use |
|---|---|
| [LTX-2.3 model card](https://huggingface.co/Lightricks/LTX-2.3) | Version-specific upstream assets and examples. |
| [LTX-2.5 model card](https://huggingface.co/Lightricks/LTX-2.5) | Version-specific upstream assets and examples. |
| [Text-to-Video](https://docs.ltx.io/open-source-model/usage-guides/text-to-video) | LTX-2.5 workflow and prompting examples. |
| [Image-to-Video](https://docs.ltx.io/open-source-model/usage-guides/image-to-video) | LTX-2.5 motion from an opening image; upstream first/last-frame controls are not automatically Studio controls. |
| [Audio-to-Video](https://docs.ltx.io/open-source-model/usage-guides/audio-to-video) | LTX-2.5 supplied-audio conditioning; describe compatible visible action rather than contradictory dialogue. |
| [Workflow and asset compatibility](https://docs.ltx.io/open-source-model/reference/workflow-asset-compatibility) | Check 2.3 versus 2.5 compatibility before choosing an adapter. |
| [Publisher documentation index](https://docs.ltx.io/llms.txt) | Discover current guides and task-specific adapter instructions. |

The publisher covers hosted services, ComfyUI and native PyTorch. Studio uses pinned MLX pipelines:
its discovered modes, adapters, reference formats, frame counts and size limits are the API contract.
Hosted retake/extend/reframe, duration prediction, HDR and other upstream workflows are not enabled by
adding their fields to a Studio payload. Multi-shot prose does not create an API batch or guarantee cuts
on the pinned checkpoint. Studio automatically enhances LTX Generate prompts, including 2.3 and 2.5;
the upstream enhancer toggle and implementation do not override that product behavior. Rewrite remains
a separate API operation. References checked 2026-10-22.
"""
