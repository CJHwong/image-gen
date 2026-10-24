# Open Imagine documentation

Choose a page for the task you have. The documentation follows [Diátaxis](https://diataxis.fr/): learning, doing, looking up facts, and understanding decisions.

| Need | Start here |
|---|---|
| **Tutorial — learn by completing a small project** | [Generate and edit your first image](tutorials/first-image.md) |
| **How-to — complete a task** | [Set up model weights and engines](how-to/set-up-models.md) · [Work with media](how-to/work-with-media.md) · [Use the API](how-to/use-the-api.md) · [Add a model plugin](how-to/add-a-model-plugin.md) |
| **Reference — look up a contract or setting** | [CLI and configuration](reference/configuration.md) · [Models](reference/models.md) · [Plugin contract](reference/model-plugins.md) · [Model licenses](reference/model-licenses.md) · [API specification and recipes](../API.md) |
| **Explanation — understand how and why** | [Shared operations and storage](explanation/operations-and-storage.md) · [Design decisions and measurements](explanation/design-decisions.md) · [Architecture](../studio/ARCHITECTURE.md) |

[Model-specific prompt aids](../studio/l3_interface_adapters/gateways/PROMPTS.md) records the tested Looks and templates.

For agent-led image work, use [Studio Image](../skills/studio-image/SKILL.md).
Ask your agent to read that file and use it with your running Studio URL. The skill covers
a guided flow for users new to photography and art, an index of looks tested on
Qwen-Image-2.1-Turbo, shoot planning, photo and art directions, composition, camera and lighting cues, design and
text layouts, illustration and game assets, prompt writing and Rewrite, reference-based edits,
visual review, and saved deliverables.
To install it into each agent's skill folder that exists (`~/.agents/skills`, `~/.codex/skills`,
`~/.claude/skills`), run:

```sh
uv run https://raw.githubusercontent.com/CJHwong/open-imagine/main/scripts/install_skills.py
```

Run it again to update. It replaces an installed copy and prints a warning for each one.
