// swift-tools-version: 6.0
import PackageDescription

// Standalone harness package for the uncensored Qwen3-8B encoder + FLUX.2 klein-9B
// experiment. The engine (Flux2Core) comes from the pristine upstream submodule at
// ../flux-2-swift-mlx. SPM identifies a path dep by its dir name ("flux-2-swift-mlx"),
// not the upstream Package.swift name field, so the product ref uses that dir name.
let package = Package(
    name: "flux2-harness",
    platforms: [.macOS(.v15)],
    products: [
        .executable(name: "Flux2UncensoredTest", targets: ["Flux2UncensoredTest"]),
    ],
    dependencies: [
        // Pristine upstream engine, pinned as a git submodule.
        .package(path: "../flux-2-swift-mlx"),
        // Declared directly so ArgumentParser is linkable from this root package;
        // transitive deps via Flux2Swift are not auto-exposed. Range matches upstream.
        .package(url: "https://github.com/apple/swift-argument-parser", from: "1.8.2"),
    ],
    targets: [
        .executableTarget(
            name: "Flux2UncensoredTest",
            dependencies: [
                .product(name: "Flux2Core", package: "flux-2-swift-mlx"),
                .product(name: "ArgumentParser", package: "swift-argument-parser"),
            ],
            path: "Sources/Flux2UncensoredTest"
        ),
    ]
)