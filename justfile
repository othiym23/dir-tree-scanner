# Build for local machine (macOS ARM)
build:
    cargo build --release

# Build for NAS (x86_64 Linux, statically linked)
build-nas:
    cargo build --release --target x86_64-unknown-linux-musl

# Build for NAS using cross (if musl toolchain not installed)
build-nas-cross:
    cross build --release --target x86_64-unknown-linux-musl

# Run against a directory
run dir:
    cargo run --release -- {{dir}} -v
