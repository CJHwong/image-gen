// krea2 — Krea 2 image generation on Apple MLX (txt2img / img2img / edit / pose-control).
// Thin CLI over the SceneWorks/mlx-gen `mlx-gen-krea` provider crate. NOT URL-runnable:
// a compiled Rust binary — build it with `cargo build --release` from krea2-harness/.
// See `../krea2` (the bash wrapper) or README.md for build + weight-download instructions.

mod krea;

use std::path::PathBuf;

use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(
    name = "krea2",
    version,
    about = "Krea 2 image generation on Apple MLX — txt2img, img2img, edit, pose-control"
)]
pub struct Cli {
    #[command(subcommand)]
    pub mode: Mode,

    /// Suppress per-step progress on stderr.
    #[arg(global = true, long)]
    pub quiet: bool,
}

#[derive(Subcommand)]
pub enum Mode {
    Txt2img(Txt2imgArgs),
    Img2img(Img2imgArgs),
    Edit(EditArgs),
    Control(ControlArgs),
}

/// Flags shared by every subcommand.
#[derive(clap::Args)]
pub struct Common {
    /// Output PNG path.
    #[arg(short, long, default_value = "out.png")]
    pub out: PathBuf,

    /// Random seed.
    #[arg(long)]
    pub seed: Option<u64>,

    /// Sampling steps. Default: 8 (txt2img/img2img/control), 16 (edit).
    #[arg(long)]
    pub steps: Option<u32>,

    /// Weights snapshot directory. Fallbacks: KREA_WEIGHTS, then the per-mode default
    /// (KREA_TURBO_Q4 for txt2img/img2img, KREA_RAW for edit, KREA_TURBO_BF16 for control).
    #[arg(long, env = "KREA_WEIGHTS")]
    pub weights: Option<PathBuf>,
}

#[derive(clap::Args)]
pub struct Txt2imgArgs {
    #[command(flatten)]
    pub common: Common,
    /// Text prompt.
    #[arg(long, required = true)]
    pub prompt: String,
    /// Output size WxH.
    #[arg(long, default_value = "1024x1024")]
    pub size: Size,
    /// Load-time quantize a DENSE snapshot (q4/q8). Do NOT pass this with a pre-packed
    /// turnkey — point --weights at the q4/ or q8/ dir instead.
    #[arg(long)]
    pub quant: Option<QuantArg>,
}

#[derive(clap::Args)]
pub struct Img2imgArgs {
    #[command(flatten)]
    pub common: Common,
    /// Text prompt.
    #[arg(long, required = true)]
    pub prompt: String,
    /// Input reference image.
    #[arg(long, required = true)]
    pub image: PathBuf,
    /// Strength (0.0–1.0): deviation from the reference.
    #[arg(long, default_value = "0.6")]
    pub strength: f32,
    #[arg(long, default_value = "1024x1024")]
    pub size: Size,
    #[arg(long)]
    pub quant: Option<QuantArg>,
}

#[derive(clap::Args)]
pub struct EditArgs {
    #[command(flatten)]
    pub common: Common,
    /// Text prompt (the edit instruction).
    #[arg(long, required = true)]
    pub prompt: String,
    /// Source image to edit.
    #[arg(long, required = true)]
    pub source: PathBuf,
    /// Optional second reference (person) for scene+person edit.
    #[arg(long)]
    pub person: Option<PathBuf>,
    /// CFG guidance (edit runs full-CFG on the Raw base).
    #[arg(long, default_value = "3.0")]
    pub guidance: f32,
    /// krea2-identity-edit LoRA .safetensors (env KREA_EDIT_LORA).
    #[arg(long, env = "KREA_EDIT_LORA")]
    pub edit_lora: Option<PathBuf>,
    /// Load-time quantize the Raw base to q4 (saves memory). Default: dense bf16.
    #[arg(long)]
    pub quant: Option<QuantArg>,
}

#[derive(clap::Args)]
pub struct ControlArgs {
    #[command(flatten)]
    pub common: Common,
    /// Text prompt.
    #[arg(long, required = true)]
    pub prompt: String,
    /// Pose skeleton image.
    #[arg(long, required = true)]
    pub pose: PathBuf,
    /// Pose ControlNet overlay .safetensors (env KREA_POSE_OVERLAY). Dense bf16 base only.
    #[arg(long, env = "KREA_POSE_OVERLAY")]
    pub overlay: PathBuf,
    /// Pose adherence (0.0 = base passthrough, 1.0 = strict pose).
    #[arg(long, default_value = "0.6")]
    pub control_scale: f32,
    #[arg(long, default_value = "1024x1024")]
    pub size: Size,
}

/// `WxH` output size.
#[derive(Clone, Debug)]
pub struct Size {
    pub w: u32,
    pub h: u32,
}

impl std::str::FromStr for Size {
    type Err = String;
    fn from_str(s: &str) -> std::result::Result<Self, Self::Err> {
        let (w, h) = s.split_once('x').ok_or_else(|| format!("expected WxH, got {s:?}"))?;
        Ok(Size {
            w: w.parse().map_err(|e: std::num::ParseIntError| e.to_string())?,
            h: h.parse().map_err(|e: std::num::ParseIntError| e.to_string())?,
        })
    }
}

#[derive(Clone, Copy, Debug)]
pub enum QuantArg {
    Q4,
    Q8,
}

impl QuantArg {
    pub fn into_quant(self) -> mlx_gen::gen_core::Quant {
        match self {
            QuantArg::Q4 => mlx_gen::gen_core::Quant::Q4,
            QuantArg::Q8 => mlx_gen::gen_core::Quant::Q8,
        }
    }
}

impl std::str::FromStr for QuantArg {
    type Err = String;
    fn from_str(s: &str) -> std::result::Result<Self, Self::Err> {
        match s.to_ascii_lowercase().as_str() {
            "q4" => Ok(QuantArg::Q4),
            "q8" => Ok(QuantArg::Q8),
            other => Err(format!("expected q4 or q8, got {other:?}")),
        }
    }
}

fn main() -> std::process::ExitCode {
    // --help is handled by clap during parse, so it stays instant even off-platform.
    let cli = Cli::parse();

    // MLX is Apple-Silicon-only; fail fast with a clear message rather than a Metal panic.
    #[cfg(not(all(target_arch = "aarch64", target_os = "macos")))]
    {
        eprintln!("krea2: Apple Silicon (aarch64 macOS) only — MLX is Metal-only.");
        return std::process::ExitCode::from(1);
    }

    let quiet = cli.quiet;
    let res = match cli.mode {
        Mode::Txt2img(a) => krea::run_txt2img(a, quiet),
        Mode::Img2img(a) => krea::run_img2img(a, quiet),
        Mode::Edit(a) => krea::run_edit(a, quiet),
        Mode::Control(a) => krea::run_control(a, quiet),
    };
    match res {
        Ok(()) => std::process::ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("krea2: {e:#}");
            std::process::ExitCode::from(1)
        }
    }
}