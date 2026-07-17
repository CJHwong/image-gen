// Per-mode dispatch over mlx-gen-krea. The provider crate self-registers its generator ids
// (krea_2_turbo / krea_2_edit / krea_2_turbo_control) via `inventory::submit!`; the bare
// `use mlx_gen_krea as _;` anchor forces the linker to keep those registrations so
// `mlx_gen::registry::load(id, ...)` can resolve them (the upstream smoke-test idiom).

use std::path::{Path, PathBuf};

use anyhow::{anyhow, Result};
use mlx_gen::gen_core::{
    CancelFlag, Conditioning, ControlKind, GenerationOutput, GenerationRequest, LoadSpec,
    WeightsSource,
};
use mlx_gen::media::Image;
use mlx_gen::{AdapterKind, AdapterSpec, Progress};
use mlx_gen_krea as _;

use crate::{ControlArgs, EditArgs, Img2imgArgs, Txt2imgArgs};

pub fn run_txt2img(a: Txt2imgArgs, quiet: bool) -> Result<()> {
    let weights = weights_of(&a.common.weights, "KREA_TURBO_Q4")?;
    let steps = a.common.steps.unwrap_or(8);
    let mut spec = LoadSpec::new(WeightsSource::Dir(weights));
    if let Some(q) = a.quant {
        spec = spec.with_quant(q.into_quant());
    }
    let gen = mlx_gen::registry::load("krea_2_turbo", &spec)?;
    let req = GenerationRequest {
        prompt: a.prompt,
        width: a.size.w,
        height: a.size.h,
        seed: a.common.seed,
        steps: Some(steps),
        count: 1,
        cancel: CancelFlag::new(),
        ..Default::default()
    };
    let img = generate(&*gen, req, quiet)?;
    save_png(&img, &a.common.out)
}

pub fn run_img2img(a: Img2imgArgs, quiet: bool) -> Result<()> {
    let weights = weights_of(&a.common.weights, "KREA_TURBO_Q4")?;
    let steps = a.common.steps.unwrap_or(8);
    let mut spec = LoadSpec::new(WeightsSource::Dir(weights));
    if let Some(q) = a.quant {
        spec = spec.with_quant(q.into_quant());
    }
    let gen = mlx_gen::registry::load("krea_2_turbo", &spec)?;
    // Resize the reference to the target grid so the VAE-encoded latent lines up with the
    // denoise canvas (Turbo is a multiple-of-16, 1024–2048 rectified-flow model).
    let ref_img = load_rgb_resized(&a.image, a.size.w, a.size.h)?;
    let req = GenerationRequest {
        prompt: a.prompt,
        width: a.size.w,
        height: a.size.h,
        seed: a.common.seed,
        steps: Some(steps),
        conditioning: vec![Conditioning::Reference {
            image: ref_img,
            strength: Some(a.strength),
        }],
        count: 1,
        cancel: CancelFlag::new(),
        ..Default::default()
    };
    let img = generate(&*gen, req, quiet)?;
    save_png(&img, &a.common.out)
}

pub fn run_edit(a: EditArgs, quiet: bool) -> Result<()> {
    let weights = weights_of(&a.common.weights, "KREA_RAW")?;
    let steps = a.common.steps.unwrap_or(16);
    let lora = a
        .edit_lora
        .ok_or_else(|| anyhow!("edit needs --edit-lora or KREA_EDIT_LORA"))?;
    let mut spec = LoadSpec::new(WeightsSource::Dir(weights))
        .with_adapters(vec![AdapterSpec::new(lora, 1.0, AdapterKind::Lora)]);
    if let Some(q) = a.quant {
        spec = spec.with_quant(q.into_quant());
    }
    let gen = mlx_gen::registry::load("krea_2_edit", &spec)?;

    // Edit denoises from noise under full CFG; output follows the source resolution.
    let source = load_rgb(&a.source)?;
    let (w, h) = (source.width, source.height);
    let conditioning = match a.person {
        Some(p) => {
            let person = load_rgb(&p)?;
            vec![Conditioning::MultiReference {
                images: vec![source, person],
            }]
        }
        None => vec![Conditioning::Reference {
            image: source,
            strength: None,
        }],
    };
    let req = GenerationRequest {
        prompt: a.prompt,
        width: w,
        height: h,
        seed: a.common.seed,
        steps: Some(steps),
        guidance: Some(a.guidance),
        conditioning,
        count: 1,
        cancel: CancelFlag::new(),
        ..Default::default()
    };
    let img = generate(&*gen, req, quiet)?;
    save_png(&img, &a.common.out)
}

pub fn run_control(a: ControlArgs, quiet: bool) -> Result<()> {
    let weights = weights_of(&a.common.weights, "KREA_TURBO_BF16")?;
    let steps = a.common.steps.unwrap_or(8);
    // Dense bf16 base + the pose overlay as the required control checkpoint. The engine
    // rejects a `quantize` override, so this path never sets one.
    let spec = LoadSpec::new(WeightsSource::Dir(weights))
        .with_control(WeightsSource::File(a.overlay));
    let gen = mlx_gen::registry::load("krea_2_turbo_control", &spec)?;
    let pose = load_rgb_resized(&a.pose, a.size.w, a.size.h)?;
    let req = GenerationRequest {
        prompt: a.prompt,
        width: a.size.w,
        height: a.size.h,
        seed: a.common.seed,
        steps: Some(steps),
        conditioning: vec![Conditioning::Control {
            image: pose,
            kind: ControlKind::Pose,
            scale: Some(a.control_scale),
        }],
        count: 1,
        cancel: CancelFlag::new(),
        ..Default::default()
    };
    let img = generate(&*gen, req, quiet)?;
    save_png(&img, &a.common.out)
}

fn generate(
    gen: &dyn mlx_gen::gen_core::Generator,
    req: GenerationRequest,
    quiet: bool,
) -> Result<Image> {
    let out = gen.generate(&req, &mut |p| {
        if !quiet {
            if let Progress::Step { current, total } = p {
                eprintln!("step {current}/{total}");
            }
        }
    })?;
    match out {
        GenerationOutput::Images(mut imgs) => {
            imgs.pop().ok_or_else(|| anyhow!("generator returned no images"))
        }
        _ => Err(anyhow!("generator returned non-image output")),
    }
}

fn weights_of(given: &Option<PathBuf>, fallback_env: &str) -> Result<PathBuf> {
    if let Some(w) = given {
        return Ok(w.clone());
    }
    if let Ok(v) = std::env::var(fallback_env) {
        if !v.is_empty() {
            return Ok(PathBuf::from(v));
        }
    }
    Err(anyhow!(
        "no weights for this mode — pass --weights, set KREA_WEIGHTS, or set {fallback_env}"
    ))
}

fn load_rgb(path: &Path) -> Result<Image> {
    let dyn_img = image::open(path).map_err(|e| anyhow!("open {path:?}: {e}"))?;
    let rgb = dyn_img.to_rgb8();
    let (w, h) = rgb.dimensions();
    Ok(Image {
        width: w,
        height: h,
        pixels: rgb.into_raw(),
    })
}

fn load_rgb_resized(path: &Path, w: u32, h: u32) -> Result<Image> {
    let dyn_img = image::open(path).map_err(|e| anyhow!("open {path:?}: {e}"))?;
    let rgb = dyn_img
        .resize_exact(w, h, image::imageops::FilterType::Lanczos3)
        .to_rgb8();
    Ok(Image {
        width: w,
        height: h,
        pixels: rgb.into_raw(),
    })
}

fn save_png(img: &Image, path: &Path) -> Result<()> {
    let buf: image::RgbImage = image::ImageBuffer::from_raw(img.width, img.height, img.pixels.clone())
        .ok_or_else(|| anyhow!("output pixel buffer mismatch ({},{})", img.width, img.height))?;
    buf.save(path).map_err(|e| anyhow!("save {path:?}: {e}"))
}