# Build for local machine (macOS ARM)
build:
    cargo build --release

# Build for NAS (x86_64 Linux, statically linked)
build-nas:
    cargo build --release --target x86_64-unknown-linux-musl

# Build for NAS using cross (if musl toolchain not installed)
build-nas-cross:
    cross build --release --target x86_64-unknown-linux-musl

# Run Cargo binaries in a given directory
run dir:
    cargo run --release -- {{dir}} -v

# Format sources
format:
    # Rust
    cargo fmt
    # Python
    cd scripts && uv run ruff format --exclude _vendor

# Lint, format-check, and typecheck source files
check:
    # Rust
    cargo fmt --check
    cargo clippy -- -D warnings
    # Python
    cd scripts && \
      uv run ruff check --exclude _vendor && \
      uv run ruff format --check --exclude _vendor
    cd scripts && \
      uv run pyright

# Run all tests (Rust + Python)
test:
    cargo test
    cd scripts && uv run pytest test_catalog.py -v

nas_home := "/Volumes/home"

# Mount NAS home directory via SMB if not already mounted
mount-home:
    #!/usr/bin/env bash
    set -euo pipefail
    if mount | grep -q "{{ nas_home }}"; then
        echo "{{ nas_home }} already mounted"
    else
        sudo mkdir -p "{{ nas_home }}"
        sudo mount_smbfs "//ogd@euterpe.local/home" "{{ nas_home }}"
        echo "Mounted {{ nas_home }}"
    fi

# Build for NAS and deploy binary + scripts to NAS home directory
deploy: check test build-nas mount-home
    #!/usr/bin/env bash
    set -euo pipefail
    # binaries
    mkdir -p "{{ nas_home }}/bin"
    cp target/x86_64-unknown-linux-musl/release/fsscan "{{ nas_home }}/bin"
    cp target/x86_64-unknown-linux-musl/release/cached-tree "{{ nas_home }}/bin"
    # catalog-nas
    mkdir -p "{{ nas_home }}/scripts"
    cp scripts/catalog-nas.py "{{ nas_home }}/scripts"
    cp scripts/catalog.toml "{{ nas_home }}/scripts"
    rsync -r --delete scripts/_vendor/ "{{ nas_home }}/scripts/_vendor/"
    # permissions – current invocation is via the python interpreter
    chmod 0640 "{{ nas_home }}/scripts/catalog-nas.py"
