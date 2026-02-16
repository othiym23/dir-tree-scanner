# Plan: Replace bincode with rkyv, add state file validation

## Context

bincode's maintainer abandoned the project (v3.0.0 is a protest release
containing only a compiler error). The user wants to migrate to rkyv for state
file serialization. Additionally, state files can be long-lived and shared
across software versions, so we need robust format detection, corruption
handling, and automatic recreation when files are invalid.

## Approach: rkyv with magic bytes + version header

### PathBuf challenge

rkyv 0.8 doesn't natively support `PathBuf` (it's in `ffi` but only has
`CString`). Options considered:

1. **`#[rkyv(with = Map<AsString, Identity>)]`** on the HashMap field — complex,
   may not work for HashMap keys
2. **Change `HashMap<PathBuf, DirEntry>` to `HashMap<String, DirEntry>`** —
   cleanest for rkyv, but requires touching every file that uses `state.dirs`
3. **Serialize via a proxy type** — convert `ScanState` to an rkyv-friendly
   intermediate before writing

**Choice: option 2** — change the internal representation to `String` keys.
PathBuf→String conversion is already lossy in the current code (filenames go
through `to_string_lossy` in several places), and all paths in this project are
UTF-8 (Unix filesystem paths from walkdir). The callers already work with
`Path`/`PathBuf` at the boundary — we just convert at insert/lookup time.

### State file format with header

Add a magic number + version byte prefix to state files so we can distinguish:

- Valid rkyv state files (current format)
- Old bincode state files (pre-migration)
- Corrupt/truncated files
- Random garbage

Format:

```
[magic: 4 bytes "FSSN"] [version: u8] [rkyv data...]
```

Version 1 = rkyv 0.8 format. If we ever change the struct layout or rkyv
version, bump the version byte.

### Load behavior

`ScanState::load()` returns a new enum to distinguish outcomes:

```rust
pub enum LoadOutcome {
    /// Successfully loaded state
    Loaded(ScanState),
    /// File doesn't exist — fresh start
    NotFound,
    /// File exists but is corrupt, wrong version, or unreadable format.
    /// Contains the error description for logging.
    Invalid(String),
}
```

The **callers** (main.rs, cached_tree.rs) decide policy:

- `NotFound` → start fresh (same as today)
- `Invalid` → log warning, start fresh, state will be overwritten on save
- `Loaded` → use the state

This keeps `state.rs` as a pure data layer — it reports what it found, callers
decide what to do. Both binaries already have the same pattern (match on load
result, fall back to default), so the change is straightforward.

### Save behavior

`ScanState::save()` writes the magic + version header, then rkyv data. No change
in caller behavior — save always overwrites. An invalid state file gets replaced
on the next successful save.

## Files to modify

### `Cargo.toml`

- Remove `bincode = "1"` and `serde = { version = "1", features = ["derive"] }`
- Add `rkyv = { version = "0.8", features = ["bytecheck"] }`
- Remove `serde` — only used for bincode derives in state.rs, nothing else

### `src/state.rs`

1. Replace `serde::{Serialize, Deserialize}` with
   `rkyv::{Archive, Serialize, Deserialize}` derives
2. Change `ScanState.dirs` from `HashMap<PathBuf, DirEntry>` to
   `HashMap<String, DirEntry>`
3. Add `MAGIC` and `VERSION` constants
4. Replace `load()` return type with `LoadOutcome` enum
5. Implement validation in `load()`:
   - File not found → `NotFound`
   - File < 5 bytes → `Invalid("truncated")`
   - Wrong magic → `Invalid("not a state file")`
   - Wrong version → `Invalid("unsupported version N")`
   - rkyv `from_bytes` fails → `Invalid("corrupt data: {err}")`
6. Implement `save()` with header prefix + `rkyv::to_bytes`

### `src/scanner.rs`

Update all `state.dirs` operations to use `String` keys:

- `state.dirs.get(&dir_path)` → `state.dirs.get(dir_path.to_str().unwrap())` or
  similar (wrap in a helper if repeated)
- `state.dirs.insert(dir_path, ...)` →
  `state.dirs.insert(dir_path.to_string_lossy().into_owned(), ...)`
- `state.dirs.remove(k)` — k is already from `keys()`, stays as `String`
- The `seen_dirs` HashSet and stale-dir removal loop operate on keys, adapt

### `src/bin/cached_tree.rs`

- `state.dirs.keys()` iteration: keys are now `String`, convert to `PathBuf`
  where needed for path operations (`.parent()`, `.file_name()`)
- `state.dirs.get(dir_path)` calls: convert `dir_path: &Path` to string for
  lookup

### `src/csv_writer.rs`

- `state.dirs.keys()` → keys are `String`, sort as strings (already
  deterministic since byte-order sort on UTF-8 = byte-order sort on the original
  PathBuf)
- `state.dirs[dir]` lookups adapt to string keys

### `src/main.rs` and `src/bin/cached_tree.rs` (caller changes)

Update the `match ScanState::load(...)` blocks to handle `LoadOutcome`:

```rust
let mut scan_state = match ScanState::load(&state_path) {
    LoadOutcome::Loaded(s) => { /* verbose log */ s }
    LoadOutcome::NotFound => { /* verbose log */ ScanState::default() }
    LoadOutcome::Invalid(reason) => {
        eprintln!("warning: {}: {}, rescanning", state_path.display(), reason);
        ScanState::default()
    }
};
```

### `CLAUDE.md`

Update the serialization design decision: rkyv 0.8 replaces bincode, state files
have a `FSSN` + version header, `LoadOutcome` enum for validation.

## Tests (in `src/state.rs`)

### Existing tests to update

- `round_trip_populated_state` — adapt to String keys, rkyv format
- `round_trip_empty_state` — same
- `load_nonexistent_returns_err` → `load_nonexistent_returns_not_found`
- `load_garbage_returns_invalid_data` — still works, check for `Invalid`
- `save_to_valid_path_succeeds` — same

### New tests to add

1. **`load_truncated_file`** — file with only 2 bytes → `Invalid`
2. **`load_wrong_magic`** — file starting with "XXXX" + valid-length data →
   `Invalid("not a state file")`
3. **`load_wrong_version`** — correct magic but version byte = 99 →
   `Invalid("unsupported version")`
4. **`load_corrupt_rkyv_data`** — correct header but garbled rkyv payload →
   `Invalid("corrupt data")`
5. **`load_old_bincode_state`** — a real bincode-format state file (craft one
   with known bytes or use a fixture) → `Invalid` (magic won't match)
6. **`load_empty_file`** — 0 bytes → `Invalid`
7. **`save_overwrites_corrupt_file`** — write garbage, then save valid state,
   then load → `Loaded` with correct data
8. **`round_trip_large_state`** — state with many dirs/files to exercise the
   serialization at scale

## Verification

1. `cargo clippy -- -D warnings`
2. `cargo test` — all unit tests + trycmd snapshot tests pass
3. `cargo build --release --target x86_64-unknown-linux-musl` — rkyv is pure
   Rust, no C deps
4. Manually test: run `cached-tree` / `fsscan` against a directory, verify state
   file is created, re-run to confirm cached behavior works
5. Test migration path: run against a directory with an existing bincode
   `.fsscan.state` → should warn and rescan
