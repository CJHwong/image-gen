"""The discovery shapes agents need before selecting model-specific controls."""

from typing import Any


def discovery_schemas() -> dict[str, Any]:
    string = {"type": "string"}
    integer = {"type": "integer"}
    number = {"type": "number"}
    boolean = {"type": "boolean"}
    nullable_number = {"type": ["number", "null"]}
    pairs = {"type": "array", "items": {"type": "array", "prefixItems": [string, string], "minItems": 2, "maxItems": 2}}
    return {
        "Template": {
            "type": "object",
            "required": ["name", "hint", "text"],
            "properties": {
                "name": {"type": "string", "description": "Send this exact name as template"},
                "hint": string,
                "text": {
                    "type": "string",
                    "description": "Every [field] needs a template_values entry. Preserve capitalization. Use template and template_values instead of copying this text into prompt.",
                },
            },
        },
        "LookRow": {
            "type": "object",
            "properties": {"name": string, "options": pairs, "avoids": pairs},
            "description": "Each option is [label, appended prompt text]. Send the label in looks, keyed by row name. Avoid entries add image negative text.",
        },
        "Parameter": {
            "type": "object",
            "properties": {
                "id": string,
                "kind": {"enum": ["number", "choice", "text"]},
                "default": {"type": ["string", "integer", "number", "boolean", "null"]},
                "minimum": nullable_number,
                "maximum": nullable_number,
                "integer": boolean,
                "step": nullable_number,
                "choices": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"value": string, "label": string}},
                },
                "with_negative": nullable_number,
            },
            "description": "Send id as a request field. Choice requests use value, not label. Omitted values use default. Respect model-specific ranges.",
        },
        "Estimate": {
            "type": ["object", "null"],
            "properties": {
                "step_cost": number,
                "exponent": number,
                "overhead": number,
                "overhead_per_image": boolean,
                "match_cap": {"type": ["integer", "null"]},
                "two_pass": boolean,
                "per_reference": number,
                "strength_scales_steps": boolean,
            },
        },
        "ImageMode": {
            "type": "object",
            "properties": {
                "id": string,
                "label": string,
                "params": {"type": "array", "items": {"$ref": "#/components/schemas/Parameter"}},
                "min_references": integer,
                "max_references": integer,
                "prompt_hint": string,
                "prompt_required": string,
                "looks": {"type": "array", "items": {"$ref": "#/components/schemas/LookRow"}},
                "templates": {"type": "array", "items": {"$ref": "#/components/schemas/Template"}},
                "estimate": {"$ref": "#/components/schemas/Estimate"},
                "reference_estimate": {"$ref": "#/components/schemas/Estimate"},
                "region_marking": boolean,
                "each_reference": boolean,
            },
        },
        "ImageCapabilities": {
            "type": "object",
            "properties": {
                "backend_id": string,
                "name": string,
                "badge": string,
                "description": string,
                "max_batch": integer,
                "modes": {"type": "array", "items": {"$ref": "#/components/schemas/ImageMode"}},
            },
        },
        "VideoMode": {
            "type": "object",
            "properties": {
                "id": string,
                "label": string,
                "needs_clip": boolean,
                "accepts_audio": boolean,
                "looks": {"type": "array", "items": {"$ref": "#/components/schemas/LookRow"}},
                "min_references": integer,
                "max_references": integer,
                "prompt_label": string,
                "placeholder": string,
                "run_label": string,
            },
        },
        "VideoAdapter": {
            "type": "object",
            "properties": {
                "id": string,
                "label": string,
                "hint": string,
                "mode": string,
                "file": string,
                "prompt": {
                    "type": "string",
                    "description": "Use this measured trigger or scene instruction when selecting this adapter.",
                },
                "prompt_mode": {"enum": ["text", "optional", "empty"]},
                "strength": number,
                "min_strength": number,
                "max_strength": number,
                "strength_step": number,
                "stage_2_conditioning": boolean,
                "doubles_output": boolean,
                "width": integer,
                "height": integer,
                "num_frames": integer,
                "card": string,
            },
            "description": "Send id as adapter and strength as adapter_strength. Use the declared width, height and num_frames, including portrait swaps where supported. Zero geometry means derive it from the input clip. doubles_output requires twice the input dimensions.",
        },
        "VideoCapabilities": {
            "type": "object",
            "properties": {
                "backend_id": string,
                "name": string,
                "badge": string,
                "description": string,
                "shapes": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"ratio": string, "width": integer, "height": integer}},
                },
                "default_shape_ratio": string,
                "min_frames": integer,
                "max_frames": integer,
                "frame_step": integer,
                "duration_presets": {"type": "array", "items": integer},
                "default_frames": integer,
                "frame_rate": integer,
                "max_references": integer,
                "min_reference_strength": number,
                "max_reference_strength": number,
                "reference_strength_step": number,
                "default_reference_strength": number,
                "min_seed": {"type": ["integer", "null"]},
                "max_seed": {"type": ["integer", "null"]},
                "min_dimension": integer,
                "max_dimension": integer,
                "dimension_step": integer,
                "templates": {"type": "array", "items": {"$ref": "#/components/schemas/Template"}},
                "modes": {"type": "array", "items": {"$ref": "#/components/schemas/VideoMode"}},
                "adapters": {"type": "array", "items": {"$ref": "#/components/schemas/VideoAdapter"}},
                "max_clip_megabytes": number,
                "precision": string,
                "max_audio_megabytes": number,
            },
            "description": "Choose an exact shape pair. Frame counts follow min_frames plus whole multiples of frame_step. Generation templates live here; Looks live inside each mode.",
        },
        "MediaInput": {
            "type": "object",
            "required": ["name", "data"],
            "properties": {
                "name": string,
                "data": {
                    "type": "string",
                    "contentEncoding": "base64",
                    "description": "Raw base64 of the actual media bytes, without a data URL prefix. Angle-bracket example values must be replaced.",
                },
            },
        },
        "ImageReference": {
            "oneOf": [string, {"type": "object", "required": ["png_base64"], "properties": {"png_base64": string}}],
            "description": "An image as bare base64, a data URL, or an object with png_base64. JPEG inputs also work; the server converts them to PNG.",
        },
        "LoadingPolicy": {
            "type": "object",
            "properties": {
                "policy": {"type": "string", "examples": ["download_on_first_use"]},
                "repository": string,
                "revision": string,
                "note": string,
            },
        },
        "VoiceCapabilities": {
            "type": "object",
            "properties": {
                "backend_id": string,
                "name": string,
                "badge": string,
                "max_batch": integer,
                "modes": {"type": "array", "items": {"$ref": "#/components/schemas/VoiceMode"}},
                "default_mode": {
                    "type": "string",
                    "description": "Mode used when omitted; AuK uses design, Drama-3 uses generate.",
                },
                "reference_sample_rate": {
                    "type": "integer",
                    "description": "Preferred reference normalization rate; API WAV inputs are resampled by the engine adapter.",
                },
                "max_reference_seconds": {
                    "type": "number",
                    "description": "Model-specific reference duration limit, checked before loading weights.",
                },
                "max_reference_megabytes": number,
                "max_seconds": number,
                "max_batch_items": integer,
                "loading": {"$ref": "#/components/schemas/LoadingPolicy"},
            },
        },
        "VoiceMode": {
            "type": "object",
            "properties": {
                "id": string,
                "label": string,
                "min_references": integer,
                "max_references": integer,
                "text_hint": string,
                "text_required": string,
                "params": {"type": "array", "items": {"$ref": "#/components/schemas/VoiceParameter"}},
                "templates": {"type": "array", "items": {"$ref": "#/components/schemas/VoiceTemplate"}},
                "estimate": {"type": ["object", "null"], "properties": {"rtf": number, "overhead": number}},
            },
        },
        "VoiceParameter": {
            "type": "object",
            "properties": {
                "id": string,
                "kind": string,
                "default": {},
                "minimum": {"type": ["number", "null"]},
                "maximum": {"type": ["number", "null"]},
                "integer": boolean,
                "step": {"type": ["number", "null"]},
                "hint": string,
                "required": boolean,
                "choices": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"value": string, "label": string}},
                },
            },
        },
        "VoiceTemplate": {
            "type": "object",
            "properties": {
                "name": string,
                "hint": string,
                "text": string,
                "group": string,
                "length_by": string,
                "target": {
                    "enum": ["voice", "text"],
                    "description": "Whether this template fills the voice description or the spoken script/edit instruction.",
                },
                "fields": {"type": "array", "items": {"$ref": "#/components/schemas/VoiceParameter"}},
            },
            "description": "Send the exact name as template and field values as template_values. The server fills {field} placeholders. length_by divides the reference duration by the named field when seconds is zero or absent.",
        },
    }
