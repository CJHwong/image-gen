// Flux2UncensoredTest.swift - Out-of-box uncensored image gen/edit on Apple Silicon.
//
// Loads the uncensored klein-base-9B DiT (darknight9121/FLUX.2-klein-base-9B-bucket-uncensored,
// a non-gated finetune of the BFL klein-base-9B) driven by a user-supplied
// uncensored Qwen3-8B text encoder (--encoder-path, e.g. the ponpoke encoder).
// The pipeline unloads the encoder before loading the transformer, so both fit
// in memory. qint8 transformer + small-decoder VAE are fixed; the base model
// runs classical CFG (guidance 4.0, ~20 steps).
//
// Two modes, picked by --input: text-to-image (no --input) and image-to-image
// editing (--input <ref>).

import ArgumentParser
import CoreGraphics
import Flux2Core
import Foundation
import ImageIO
import UniformTypeIdentifiers

@main
struct Flux2UncensoredTest: AsyncParsableCommand {
    @Option(name: .shortAndLong, help: "Local dir with the Qwen3-8B encoder (config.json, tokenizer.json, *.safetensors). The flux2 wrapper injects this from $FLUX_ENCODER_PATH.")
    var encoderPath: String

    @Option(name: .shortAndLong, help: "Prompt to generate.")
    var prompt: String = "a beaver building a dam, photorealistic, golden hour"

    @Option(name: .long, help: "Reference image for image-to-image editing. Omit for text-to-image.")
    var input: String?

    @Option(name: .long, help: "Output PNG path.")
    var output: String = "./uncensored_test.png"

    @Option(name: .long, help: "Image width. Omit both width and height for a 256x256 quick-test default. Pass only one to make a square of that size. For i2i, omitting both follows the reference's aspect ratio (long side capped at 1024).")
    var width: Int?

    @Option(name: .long, help: "Image height. See --width.")
    var height: Int?

    @Option(name: .long, help: "Denoising steps. More = sharper (esp. faces), slower. Default 20.")
    var steps: Int = 20

    @Option(name: .long, help: "CFG guidance. Default 4.0.")
    var guidance: Float = 4.0

    @Option(name: .long, help: "Seed. Omit for a random seed (printed so you can reproduce it). With --count > 1 and an explicit seed, seeds increment (seed, seed+1, ...).")
    var seed: UInt64?

    @Option(name: .long, help: "Generate N images from the same prompt in one run (t2i only): encode once, load the transformer once, denoise N times. Each gets its own seed and an <output>.s<seed>.png file. Default 1.")
    var count: Int = 1

    func run() async throws {
        // FLUX2_MEM=1 surfaces the engine's Metal GPU memory log (active/peak/cache).
        if ProcessInfo.processInfo.environment["FLUX2_MEM"] != nil {
            Flux2Debug.minLevel = .info
        }
        let runStart = Date()
        let token = ProcessInfo.processInfo.environment["HF_TOKEN"]
        let encoderURL = URL(fileURLWithPath: encoderPath)
        print("Encoder path : \(encoderURL.path)")

        guard count >= 1 else {
            throw ValidationError("--count must be >= 1 (got \(count))")
        }

        // Resolve the transformer's on-disk dir with the exact functions the
        // pipeline's loadTransformer uses, so the printed path can't drift from
        // what actually loads. The engine hardcodes the base variant's cache dir
        // to black-forest-labs/FLUX.2-klein-base-9B (from its HF repo id), so the
        // uncensored darknight weights we download live there and the path looks
        // stock. Name the real source repo as the identity; the BFL-namespaced
        // dir is just where the engine insists on caching it.
        let transformerVariant = ModelRegistry.TransformerVariant.variant(for: .klein9BBase, quantization: .qint8)
        let transformerDir = Flux2ModelDownloader.findModelPath(for: .transformer(transformerVariant))?.path
            ?? "NOT FOUND (fetch it - see TRANSFORMER in `flux2 help`)"
        print("Transformer  : darknight9121/FLUX.2-klein-base-9B-bucket-uncensored (qint8)")
        print("  cached at  : \(transformerDir)")
        print("Prompt       : \(prompt)")
        print("Sampling     : \(steps) steps, guidance \(guidance)")
        print("HF token     : \(token != nil ? "present" : "MISSING (set HF_TOKEN for gated transformer)")")

        let quantConfig = Flux2QuantizationConfig(textEncoder: .mlx8bit, transformer: .qint8)
        let vaeVar = ModelRegistry.VAEVariant.smallDecoder

        // The pipeline does not auto-download the VAE (it errors if missing), so
        // fetch it here when not cached. download() short-circuits if present.
        if Flux2ModelDownloader.isDownloaded(.vae(vaeVar)) {
            print("VAE          : small-decoder (cached)")
        } else {
            print("VAE          : small-decoder (not cached - downloading...)")
            let downloader = Flux2ModelDownloader(hfToken: token)
            _ = try await downloader.download(.vae(vaeVar)) { progress, status in
                print("\r  VAE \(String(format: "%.0f%%", progress * 100)) - \(status)", terminator: "")
                fflush(stdout)
            }
            print("")
        }

        let pipeline = Flux2Pipeline(
            model: .klein9BBase,
            quantization: quantConfig,
            vaeVariant: vaeVar,
            hfToken: token,
            kleinEncoderPath: encoderURL
        )

        let onProgress: Flux2ProgressCallback = { current, total in
            print("\r  Step \(current)/\(total)", terminator: "")
            fflush(stdout)
        }

        // One seed per image: explicit seed increments, absent seed is random.
        let seeds = Self.resolveSeeds(count: count, base: seed)

        if let inputPath = input {
            guard count == 1 else {
                throw ValidationError("--count > 1 is not supported with --input (i2i). Omit --input for a t2i batch.")
            }
            guard let refImage = Self.loadImage(from: inputPath) else {
                throw ValidationError("Could not load reference image at \(inputPath)")
            }
            print("Reference   : \(inputPath) (\(refImage.width)x\(refImage.height))")
            print("Mode        : image-to-image (Flux.2 conditioning - output regenerates from noise)")

            // No size given for an edit: follow the reference's aspect ratio,
            // capping the long side. One dimension given => square; both => as-is.
            let (reqWidth, reqHeight) = Self.squareIfSingle(width: width, height: height)
            var outWidth = reqWidth
            var outHeight = reqHeight
            if reqWidth == nil && reqHeight == nil {
                (outWidth, outHeight) = Self.cappedDimensions(for: refImage)
                print("Size        : \(outWidth!)x\(outHeight!) (aspect-matched to reference, /16-rounded by pipeline)")
            } else {
                print("Size        : \(outWidth!)x\(outHeight!)")
            }
            print("Seed        : \(seeds[0])")

            let genStart = Date()
            let image = try await pipeline.generateImageToImage(
                prompt: prompt,
                images: [refImage],
                height: outHeight,
                width: outWidth,
                steps: steps,
                guidance: guidance,
                seed: seeds[0],
                onProgress: onProgress
            )
            let genSeconds = Date().timeIntervalSince(genStart)
            try Self.saveImage(image, to: output)
            print("\nTiming      : generation \(String(format: "%.1f", genSeconds))s | wall \(String(format: "%.1f", Date().timeIntervalSince(runStart)))s (generation includes one-time model load)")
            print("Saved: \(output)")
            return
        }

        // Both omitted => 256x256 quick-test default; one given => square.
        let (reqWidth, reqHeight) = Self.squareIfSingle(width: width, height: height)
        let outWidth = reqWidth ?? 256
        let outHeight = reqHeight ?? 256
        print("Size        : \(outWidth)x\(outHeight)")

        if count == 1 {
            print("Seed        : \(seeds[0])")
            let genStart = Date()
            let image = try await pipeline.generateTextToImage(
                prompt: prompt,
                height: outHeight,
                width: outWidth,
                steps: steps,
                guidance: guidance,
                seed: seeds[0],
                onProgress: onProgress
            )
            let genSeconds = Date().timeIntervalSince(genStart)
            try Self.saveImage(image, to: output)
            print("\nTiming      : generation \(String(format: "%.1f", genSeconds))s | wall \(String(format: "%.1f", Date().timeIntervalSince(runStart)))s (generation includes one-time model load)")
            print("Saved: \(output)")
            return
        }

        // t2i batch: same prompt, one seed per image. The transformer loads once
        // and stays resident across iterations (guard in loadTransformer). Each
        // image runs the normal encode+denoise so classical CFG stays active.
        print("Batch        : \(count) images, seeds [\(seeds.map(String.init).joined(separator: ", "))]")

        for (index, imageSeed) in seeds.enumerated() {
            let outPath = Self.batchOutputPath(output, seed: imageSeed)
            print("[\(index + 1)/\(count)] seed \(imageSeed) -> \(outPath)")
            let genStart = Date()
            let image = try await pipeline.generateTextToImage(
                prompt: prompt,
                height: outHeight,
                width: outWidth,
                steps: steps,
                guidance: guidance,
                seed: imageSeed,
                onProgress: onProgress
            )
            let genSeconds = Date().timeIntervalSince(genStart)
            try Self.saveImage(image, to: outPath)
            print("\n  generation \(String(format: "%.1f", genSeconds))s | wall \(String(format: "%.1f", Date().timeIntervalSince(runStart)))s")
        }
        print("Batch total wall: \(String(format: "%.1f", Date().timeIntervalSince(runStart)))s")
    }

    static func saveImage(_ image: CGImage, to path: String) throws {
        let utType: CFString = path.hasSuffix(".png") ? UTType.png.identifier as CFString : UTType.jpeg.identifier as CFString
        guard let dest = CGImageDestinationCreateWithURL(URL(fileURLWithPath: path) as CFURL, utType, 1, nil) else {
            throw Flux2Error.imageProcessingFailed("Failed to create image destination at \(path)")
        }
        CGImageDestinationAddImage(dest, image, nil)
        guard CGImageDestinationFinalize(dest) else {
            throw Flux2Error.imageProcessingFailed("Failed to write image at \(path)")
        }
    }

    static func loadImage(from path: String) -> CGImage? {
        let url = URL(fileURLWithPath: path)
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
              let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
            return nil
        }
        return image
    }

    /// "Pass only one of width/height => square of that size" convenience.
    /// Both-set is respected as-is (even non-square); both-nil stays nil for the
    /// caller to fill (t2i quick-test default or i2i reference-ratio).
    static func squareIfSingle(width: Int?, height: Int?) -> (width: Int?, height: Int?) {
        switch (width, height) {
        case (let w?, nil): return (w, w)
        case (nil, let h?): return (h, h)
        default: return (width, height)
        }
    }

    /// One seed per image. An explicit base increments (base, base+1, ...) so a
    /// batch is distinct yet reproducible; no base means a fresh random seed each,
    /// which the caller prints so any result can be reproduced with --seed.
    static func resolveSeeds(count: Int, base: UInt64?) -> [UInt64] {
        if let base {
            return (0..<count).map { base &+ UInt64($0) }
        }
        var rng = SystemRandomNumberGenerator()
        return (0..<count).map { _ in UInt64.random(in: UInt64.min...UInt64.max, using: &rng) }
    }

    /// Per-image output path for a batch: `out.png` -> `out.s<seed>.png`, so each
    /// file names the seed that produced it.
    static func batchOutputPath(_ output: String, seed: UInt64) -> String {
        let url = URL(fileURLWithPath: output)
        let ext = url.pathExtension.isEmpty ? "png" : url.pathExtension
        return url.deletingPathExtension()
            .appendingPathExtension("s\(seed)")
            .appendingPathExtension(ext)
            .path
    }

    /// The image's dimensions with its aspect ratio preserved and the long side
    /// clamped to `maxSide`. The pipeline rounds each side to a /16 multiple, so
    /// no rounding is done here. Images already within the cap pass through.
    static func cappedDimensions(for image: CGImage, maxSide: Int = 1024) -> (width: Int, height: Int) {
        let width = image.width
        let height = image.height
        let longSide = max(width, height)
        guard longSide > maxSide else { return (width, height) }
        let scale = Double(maxSide) / Double(longSide)
        return (Int((Double(width) * scale).rounded()), Int((Double(height) * scale).rounded()))
    }
}
