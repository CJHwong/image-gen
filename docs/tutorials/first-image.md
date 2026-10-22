# Generate and edit your first image

In this tutorial you will create an elevator opening onto a beach, then change the view to snow.
You need an Apple Silicon Mac, [uv](https://docs.astral.sh/uv/), and space for the default image model (about 32.5 GB).
Development and model checks use a Mac with 64 GB of unified memory.

## Start Open Imagine

```sh
git clone https://github.com/CJHwong/open-imagine.git
cd open-imagine
uv run studio
```

Open **http://127.0.0.1:8765** when the terminal says Ready. Stay in **Image** with its default Qwen Image Turbo model.
Startup loads no weights; your first generation downloads and loads the model.

## Generate a scene

Paste this into **Prompt**, choose **16:9**, and press **Generate**:

> A realistic photograph from inside an old office elevator. Beige walls, scratched stainless-steel doors, fluorescent ceiling light. The open doors reveal a sunny tropical beach directly outside, with sand starting at the elevator threshold. Wide-angle lens, neutral exposure, realistic materials.

Watch progress in the preview. When the image finishes, it appears in the preview and gallery.
Your scene will vary; the elevator and beach are the elements to look for.

![An elevator opening onto a beach](../images/generate.jpg)

## Edit the view

Choose the image’s **Edit** action. Paste this into **What to change**, then press **Edit**:

> Keep the elevator interior unchanged. Replace the beach with snowy mountains during a mild snowstorm. Add windblown snow just inside the threshold. Match the cold outdoor light while preserving the fluorescent lighting inside.

The result keeps a link to its source. Drag the before-and-after divider to compare them.
Click either gallery thumbnail to view that image, then use its download action to save a copy.

![The edited image with a before-and-after comparison](../images/hero.jpg)

You have generated a scene, reused it as an edit reference, and saved the result.
Next, [work with references and previews](../how-to/work-with-media.md) or [submit the same kinds of jobs through the API](../how-to/use-the-api.md).
