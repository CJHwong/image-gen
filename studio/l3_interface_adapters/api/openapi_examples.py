"""Named requests for the rendered reference and programmatic clients."""

from typing import Any

# A real one-pixel PNG tests transport only. It is not a useful visual reference.
PNG_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
VIDEO_SETTINGS = {
    "backend": "ltx25_mlx",
    "width": 384,
    "height": 384,
    "num_frames": 121,
    "frame_rate": 24,
    "seed": 7,
    "enhance": True,
}
CAMERA_VALUES = {
    "Subject": "A blue ceramic teapot",
    "surface": "a wooden table",
    "Foreground object": "A red cup",
    "background object": "a green plant",
    "subject name": "the teapot",
    "light": "Soft daylight enters through a window",
    "sound": "quiet room tone",
}


def image_examples(edit: bool = False) -> dict[str, Any]:
    if edit:
        return {
            "instruction_edit": {
                "summary": "Change one supplied image",
                "description": "Replace the transport-test PNG with base64 from your image. The request selects qwen21_turbo.",
                "value": {
                    "backend": "qwen21_turbo",
                    "prompt": "Change the wall to pale blue. Keep the subject, pose, and camera framing.",
                    "references": [PNG_BASE64],
                    "size": "match",
                    "steps": 8,
                    "seed": 7,
                },
            },
            "each_reference": {
                "summary": "Give each reference its own instruction",
                "description": "Replace both PNG values. count is the total number of outputs, not outputs per reference.",
                "value": {
                    "backend": "qwen21_turbo",
                    "prompt": "Keep the original composition.",
                    "references": [PNG_BASE64, PNG_BASE64],
                    "each_reference": True,
                    "per_reference_prompts": ["Make the wall blue.", "Make the wall green."],
                    "count": 2,
                    "size": "match",
                    "steps": 8,
                    "seed": 7,
                },
            },
        }
    return {
        "product_photo": {
            "summary": "A useful first image with the official Turbo model",
            "description": "The request selects qwen21_turbo. Its official schedule uses exactly eight steps. Omit steps for another model's default.",
            "value": {
                "backend": "qwen21_turbo",
                "prompt": "A blue ceramic teapot on a pale oak table, soft window light, clean product photograph.",
                "size": "768x768",
                "steps": 8,
                "seed": 7,
            },
        },
        "seed_variations": {
            "summary": "Four variations of one image prompt",
            "description": "One server operation owns the whole batch. Seeds increment from seven.",
            "value": {
                "backend": "qwen21_turbo",
                "prompt": "A small red sailboat on calm water at sunrise, watercolor illustration.",
                "size": "768x768",
                "steps": 8,
                "seed": 7,
                "count": 4,
            },
        },
    }


def video_examples(edit: bool = False) -> dict[str, Any]:
    if edit:
        return {
            "deblur": {
                "summary": "Sharpen a soft clip with the Deblur effect",
                "description": "Replace clip.data with the raw base64 bytes of your MP4. The literal DEBLUR trigger, output size, and frame count follow this effect's measured recipe.",
                "value": {
                    "backend": "ltx25_mlx",
                    "prompt": "DEBLUR. The same shot, sharp and in focus, every edge crisp and the texture of each surface visible. One continuous shot.",
                    "adapter": "deblur",
                    "adapter_strength": 1,
                    "width": 960,
                    "height": 544,
                    "num_frames": 121,
                    "frame_rate": 24,
                    "seed": 7,
                    "clip": {"name": "soft-clip.mp4", "data": "<replace with base64 of your MP4>"},
                },
            },
            "day_to_night": {
                "summary": "Relight a daylight clip",
                "description": "Replace clip.data with actual MP4 bytes. Read the chosen adapter's prompt and dimensions from discovery; effects have different recipes.",
                "value": {
                    "backend": "ltx25_mlx",
                    "prompt": "The same room at night, blue moonlight through the windows, identical composition and subjects.",
                    "adapter": "day-to-night",
                    "adapter_strength": 1,
                    "width": 768,
                    "height": 448,
                    "num_frames": 97,
                    "frame_rate": 24,
                    "seed": 7,
                    "clip": {"name": "daylight.mp4", "data": "<replace with base64 of your MP4>"},
                },
            },
        }
    return {
        "fast_preview": {
            "summary": "Try Fast mode on a short LTX-2.5 clip",
            "description": "Reduced transformer compute precision; same model weights. Details and motion may differ from default even with the same seed. Omit fast_mode or set false for default rendering. Applies per request and must be the same for all batch items.",
            "value": {
                **VIDEO_SETTINGS,
                "num_frames": 49,
                "fast_mode": True,
                "prompt": "A blue ceramic teapot on an oak table. Steam rises as the camera slowly moves closer. Soft daylight, quiet room tone.",
            },
        },
        "slow_push_in": {
            "summary": "Use the measured Slow push-in template",
            "description": "Use structured template fields when the model offers a matching template. Do not copy template text into prompt. Field names and capitalization must match discovery.",
            "value": {**VIDEO_SETTINGS, "template": "Slow push-in", "template_values": CAMERA_VALUES},
        },
        "generated_speech": {
            "summary": "One person says an exact sentence on camera",
            "description": "This generates a new voice and clip. It does not guarantee exact mouth alignment.",
            "value": {
                **VIDEO_SETTINGS,
                "template": "Speak to camera",
                "template_values": {
                    "speaker": "a woman in a blue shirt",
                    "background": "a plain gray wall",
                    "light": "Soft window light illuminates her face",
                    "Subject pronoun": "She",
                    "Possessive pronoun": "Her",
                    "language": "English",
                    "dialogue": "Please bring my blue bag.",
                    "sound": "quiet room tone",
                },
            },
        },
        "first_keyframe": {
            "summary": "Animate your first image",
            "description": "The included PNG is a real transport-test pixel. Replace it with your scene. Video keyframes require bare base64, not a data URL.",
            "value": {
                **VIDEO_SETTINGS,
                "prompt": "The person in the reference turns toward the window. One continuous shot, gentle daylight.",
                "references": [{"name": "first.png", "image": PNG_BASE64, "frame_index": 0, "strength": 1}],
            },
        },
        "supplied_speech": {
            "summary": "Generate a clip that follows your audio",
            "description": "Replace audio.data with raw base64 from your actual WAV. This placeholder is not playable audio. Studio preserves supplied audio and pads a short track with silence.",
            "value": {
                **VIDEO_SETTINGS,
                "prompt": "A woman speaks the supplied line to camera, natural facial movement, fixed medium close-up.",
                "audio": {"name": "line.wav", "data": "<replace with base64 of your WAV>"},
            },
        },
    }


def rewrite_examples(workspace: str) -> dict[str, Any]:
    prompt = (
        "A teapot on a table. The camera moves closer." if workspace == "video" else "A blue teapot on an oak table."
    )
    examples = {
        "expand_draft": {
            "summary": "Expand a short draft before generation",
            "description": "A rewrite returns suggested text. Review it before using it in a generation request. Apply Looks when generating, not when rewriting.",
            "value": {"prompt": prompt, "mode": "generate"},
        }
    }

    if workspace == "video":
        examples["animate_reference"] = {
            "summary": "Enhance motion instructions while reading your image",
            "description": "Replace the transport-test PNG with your scene. Gemma reads the first reference. Reuse the returned prompt and same first image in Generate to skip duplicate enhancement in this server session.",
            "value": {
                "prompt": "It slowly moves to the right.",
                "mode": "generate",
                "references": [{"png_base64": PNG_BASE64}],
            },
        }
    return examples


def operation_examples() -> dict[str, Any]:
    return {
        "image_variations": {
            "summary": "Start four image variations and return immediately",
            "value": {"kind": "image", **image_examples()["seed_variations"]["value"]},
        },
        "camera_template": {
            "summary": "Start a video using a measured camera template",
            "value": {"kind": "video", **video_examples()["slow_push_in"]["value"]},
        },
        "image_storyboard": {
            "summary": "Two images with different prompts and shared settings",
            "value": {
                "kind": "image",
                "backend": "qwen21_turbo",
                "size": "768x768",
                "steps": 8,
                "seed": 7,
                "items": [
                    {"prompt": "A red sailboat leaves a quiet harbor at sunrise, watercolor illustration."},
                    {"prompt": "The red sailboat reaches open water at noon, watercolor illustration.", "seed": 8},
                ],
            },
        },
        "video_shots": {
            "summary": "Two video shots under one operation",
            "description": "Each item yields one clip. Shared settings apply unless an item overrides them. The server runs items in order.",
            "value": {
                "kind": "video",
                **VIDEO_SETTINGS,
                "items": [
                    {"prompt": "A blue teapot on an oak table, soft window light, fixed camera."},
                    {"template": "Slow push-in", "template_values": CAMERA_VALUES, "seed": 8},
                ],
            },
        },
        "drama_batch": {
            "summary": "Drama-3: two directed clips share one warm engine",
            "description": "Each item is one independent WAV. Ordered generation reuses weights and cached references; it is not parallel tensor batching. Use a shared reference and ref_text when a consistent cloned speaker is needed.",
            "value": {
                "kind": "voice",
                "backend": "drama3",
                "mode": "generate",
                "seed": 7,
                "items": [
                    {
                        "template": "Whisper",
                        "template_values": {"script": "Keep your voice down. Someone is listening."},
                    },
                    {
                        "template": "Excited",
                        "template_values": {"script": "We finally made it! This is wonderful!"},
                        "seed": 8,
                    },
                ],
            },
        },
        "voice_design_templates": {
            "summary": "Compare two voice designs under one operation",
            "description": "Each template builds a voice description while text stays the spoken script. Fields not supplied use the template defaults. Designs can produce different speakers; clone one saved WAV when continuity matters.",
            "value": {
                "kind": "voice",
                "backend": "auk",
                "mode": "design",
                "seconds": 4,
                "convert": "off",
                "seed": 7,
                "items": [
                    {
                        "template": "Narration",
                        "text": "The river flows past the quiet village.",
                        "template_values": {"tone": "warm and thoughtful"},
                    },
                    {
                        "template": "Conversation",
                        "text": "I am glad you made it home.",
                        "template_values": {"emotion": "warmth and gentle concern"},
                    },
                ],
            },
        },
        "voice_segments": {
            "summary": "Two narration segments share one reference voice",
            "description": "Replace the WAV placeholder. A shared reference keeps the speaker consistent. Design once, then clone its saved WAV for later segments when continuity matters.",
            "value": {
                "kind": "voice",
                "backend": "auk",
                "mode": "clone",
                "seconds": 0,
                "convert": "off",
                "seed": 7,
                "reference": {"name": "narrator.wav", "wav_base64": "<replace with base64 of your WAV>"},
                "items": [
                    {"text": "First, place the blue cup on the table."},
                    {"text": "Next, pour the tea slowly and serve.", "seed": 8},
                ],
            },
        },
        "rewrite_video": {
            "summary": "Rewrite a video draft without replacing the browser draft",
            "value": {
                "kind": "rewrite",
                "workspace": "video",
                "prompt": "A teapot on a table. Move closer.",
                "mode": "generate",
            },
        },
    }


def voice_examples() -> dict[str, Any]:
    reference = {"name": "speaker.wav", "wav_base64": "<replace with base64 of your WAV>"}
    return {
        "drama_delivery": {
            "summary": "Drama-3: direct the performance inside the script",
            "description": "No voice description or duration is needed. The local eight-bit engine uses automatic duration and emits indeterminate progress until complete. First use downloads about 42 GB.",
            "value": {
                "backend": "drama3",
                "mode": "generate",
                "text": "[whispers] Keep your voice down. Someone is listening.",
                "temperature": 0.7,
                "top_p": 0.7,
                "top_k": 30,
                "max_tokens": 2048,
                "seed": 7,
            },
        },
        "drama_clone": {
            "summary": "Drama-3: clone a speaker with an exact reference transcript",
            "description": "Replace the WAV placeholder and ref_text with a real clean recording and its exact words. References are resampled to 44.1 kHz. Finished clips never become implicit references for later batch items.",
            "value": {
                "backend": "drama3",
                "mode": "clone",
                "text": "The next train leaves from platform three.",
                "reference": reference,
                "ref_text": "The blue teapot is beside the window.",
                "seed": 7,
            },
        },
        "design_template": {
            "summary": "Design a narrator with editable voice attributes",
            "description": "The Narration template fills the voice description, not the spoken text. Multiple sentences in text form one continuous clip. Read the selected model capabilities for names, fields and defaults. Omitted fields use their declared defaults.",
            "value": {
                "backend": "auk",
                "mode": "design",
                "template": "Narration",
                "template_values": {
                    "speaker": "documentary narrator",
                    "subject": "an everyday discovery",
                    "pace": "measured, unhurried",
                    "tone": "warm and thoughtful",
                },
                "text": "The river flows past the quiet village. The first light reaches the bridge.",
                "seconds": 0,
                "convert": "off",
                "seed": 7,
            },
        },
        "designed_narration": {
            "summary": "Design a voice with a detailed description",
            "description": "Describe age, tone, pace, volume, and accent. Short descriptions can become spoken content. seconds zero selects duration from the text.",
            "value": {
                "backend": "auk",
                "mode": "design",
                "text": "The next train leaves from platform three. Please keep your ticket ready.",
                "voice": "A woman in her thirties reads a public announcement. Her voice sounds calm, clear, and warm. She speaks at a steady pace and medium volume, with a neutral American accent.",
                "seconds": 0,
                "convert": "off",
                "seed": 7,
            },
        },
        "clone_with_auk": {
            "summary": "Clone with the 32-step AuK model",
            "description": "Selects the AuK Base model explicitly. Replace reference.wav_base64 with real WAV bytes. The first Base run downloads its missing pinned variant files.",
            "value": {
                "backend": "auk_base",
                "mode": "clone",
                "text": "The recording is ready for the next scene.",
                "reference": reference,
                "seconds": 4,
                "convert": "off",
                "seed": 7,
            },
        },
        "clone_reference": {
            "summary": "Read new text with a reference voice",
            "description": "Replace reference.wav_base64 with actual WAV bytes. The placeholder is not playable audio. Use one clear speaker recording.",
            "value": {
                "backend": "auk",
                "mode": "clone",
                "text": "Please bring my blue bag to the front desk.",
                "reference": reference,
                "seconds": 0,
                "convert": "off",
                "seed": 7,
            },
        },
        "change_speed": {
            "summary": "Speed up a recording and adjust its duration",
            "description": "Replace reference.wav_base64 with actual WAV bytes. The Speed template divides the decoded reference duration by 1.5. A positive seconds value overrides this rule.",
            "value": {
                "backend": "auk",
                "mode": "edit",
                "template": "Speed",
                "template_values": {"speed": "1.5"},
                "reference": reference,
                "seconds": 0,
                "convert": "off",
                "seed": 7,
            },
        },
        "clean_recording": {
            "summary": "Remove noise and room echo from a recording",
            "description": "Replace reference.wav_base64 with actual WAV bytes. This instruction follows the offered Enhance edit template.",
            "value": {
                "backend": "auk",
                "mode": "edit",
                "text": "Preserve all speakers, remove noise and reverberation, and output clean speech of the same length.",
                "reference": reference,
                "seconds": 0,
                "convert": "off",
                "seed": 7,
            },
        },
    }
