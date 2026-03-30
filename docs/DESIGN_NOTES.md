# Design Notes

Implementation details and architecture for euterpe-tools. For conventions and
commands, see [CLAUDE.md](../CLAUDE.md). For architectural decisions, see
[docs/adrs/](adrs/).

## Repository Structure

- `crates/` — Rust libraries (etp-lib, etp-cue)
- `cmd/` — all plumbing commands (Rust binaries and Python entry points)
- `pylib/` — Python shared library (`etp_lib`)
- `conf/` — KDL configuration files

## Rust Crates

Library crate (`crates/etp-lib/src/lib.rs`) re-exports shared modules:

- `ops.rs` — shared operations used by all binary crates
- `scanner.rs` — walkdir-based scanning; skips unchanged directories by mtime
- `csv_writer.rs` — sorted CSV output (`path,size,ctime,mtime`)
- `tree.rs` — tree rendering with ICU4X collation for Unicode-aware sorting
- `finder.rs` — regex matching against file records
- `metadata.rs` — media metadata reading with dual backend: lofty for audio
  formats, mediainfo subprocess for video (MKV, MP4, AVI) and gap audio (WMA,
  MKA). Extension-based dispatch. Extracts audio properties (duration, bitrate,
  channels) and video properties (width, height, bit depth, codec, frame rate,
  HDR). Tag names normalized to `lowercase_snake_case`. See
  `docs/adrs/2026-03-28-01-mediainfo-over-taglib.md`.
- `cas.rs` — content-addressable blob storage using BLAKE3 hashing with atomic
  filesystem writes (safe on Btrfs)
- `db/mod.rs` — SQLite connection factory (WAL mode, foreign keys, cache
  pragmas); dual-path init: new databases use clean `schema.sql`, existing
  databases use incremental `migrations/`. FK enforcement disabled during
  migrations for table recreation compatibility.
- `db/dao.rs` — all database queries (scan CRUD, file UPSERT, metadata, blobs,
  images, cue sheets, move tracking). `FULL_PATH_SQL` constant for path
  reconstruction used across query functions.
- `config.rs` — KDL configuration parsing: catalog config (`Config`) for
  catalog.kdl and runtime config (`RuntimeConfig`) for config.kdl. Runtime
  config provides system file patterns, user excludes, CAS directory override,
  database nicknames, and default database setting.
- `paths.rs` — XDG/native path resolution (etcetera crate)
- `profiling.rs` — self-instrumentation (feature-gated behind `profiling`)

Standalone library crate (`etp-cue/`):

- CUE sheet parser, MusicBrainz disc ID computation (SHA-1 + custom Base64), and
  three display formatters (album summary, CUEtools TOC, EAC TOC)
- Supports multi-file CUE sheets via per-file duration accumulation
- No database dependency — pure data transformation

Each binary crate has a `build.rs` that embeds the short git hash in
`--version`. Binary crates: `etp-csv`, `etp-tree`, `etp-find`, `etp-meta`,
`etp-cas`, `etp-query`.

## Python Package

Python commands live in `cmd/etp/etp_commands/`:

- `dispatcher.py` — git-style dispatcher (`etp <cmd>` → `etp-<cmd>`)
- `anime.py` — interactive anime collection manager
- `catalog.py` — KDL-configured catalog orchestrator

Python shared library lives in `pylib/etp_lib/`:

- `paths.py` — XDG-based path resolution and binary search
- `media_vocab.py` — vocabulary sets, Token/TokenKind types, and mapping tables
  shared between the parser and its recognizers
- `media_parser.py` — three-phase media filename parser (see below)
- `anidb.py`, `tvdb.py` — API clients with local caching
- `types.py` — shared data types (AnimeInfo, Episode, SourceFile, MediaInfo)
- `manifest.py` — KDL manifest generation, parsing, and execution
- `naming.py` — episode filename formatting and series directory naming
- `conflicts.py` — destination conflict resolution
- `mediainfo.py` — mediainfo subprocess wrapper for audio/video metadata

`conf/` contains KDL configuration files.

## Media Filename Parser

The parser (`media_parser.py`) extracts metadata from anime/media filenames that
follow loosely adopted conventions (fansub, scene, Sonarr, Japanese BD). See
`docs/adrs/2026-03-30-02-heuristic-media-filename-parsing.md`.

Three-phase pipeline:

1. **Structural tokenization** (`tokenize_component`): Character-by-character
   scan identifies delimiters (brackets, parens, lenticular quotes). Scene-style
   dot-separated text is handled by `scan_dot_segments`, which uses parsy-based
   recognizers to identify compound tokens (H.264, AAC2.0) across dot
   boundaries. Separator-style text (`-`) is split by `_split_separators`.

2. **Semantic classification** (`classify`): Walks the token list with
   positional state to reclassify content. Uses `_try_recognize` (parsy
   recognizers) for word-level classification and `scan_words` for multi-word
   pattern matching with dash-compound splitting.

3. **Assembly** (`_build_parsed_media`): Extracts series name, episode title,
   and metadata fields from classified tokens into a `ParsedMedia` dataclass.

Token recognition uses parsy `Parser` objects as typed recognizers — each
returns a frozen dataclass (Resolution, VideoCodec, AudioCodec, Source, etc.) on
success or a failure. The recognizers are ordered by specificity in the
`_RECOGNIZERS` list (compound audio codecs before simple, SxxExx before S-only
seasons). See
`docs/adrs/2026-03-30-01-parsy-primitives-for-token-recognition.md`.

`parse_media_path` handles full relative paths by parsing directory and filename
components separately, then merging: the filename is primary for
episode/metadata, directories provide series name, release group, and fill
metadata gaps (resolution, codec, source type, audio codecs) via `scan_words` on
directory text.

Vocabulary sets (`_SOURCES`, `_VIDEO_CODECS`, `_AUDIO_CODECS`, etc.) live in
`media_vocab.py` to avoid circular imports between the parser and its
recognizers. The parser re-exports them for backward compatibility.

## Database

SQLite with sqlx, WAL mode, single-threaded tokio (`current_thread`). The
canonical schema is `etp-lib/schema.sql`. Pool is `max_connections(1)` — all
queries are sequential. FK enforcement is disabled during migration execution
(some migrations recreate tables referenced by foreign keys).

Defaults: database is `<dir>/.etp.db`. The scanner indexes everything on disk
(no default excludes). Display-time filtering hides system files and user
excludes — see "Display Filtering" below.

File sync uses UPSERT to preserve file IDs across rescans. When a file's mtime
changes, `metadata_scanned_at` is cleared so the metadata scanner re-reads it.
See `docs/adrs/2026-03-27-03-upsert-file-sync.md`.

File-move tracking: after all directories are flushed, a reconciliation pass
matches removed files against newly appeared files by size, then verifies with
streaming BLAKE3 hash. Matched files get an UPDATE to `dir_id` + `filename`,
preserving their ID and all dependent metadata. Unmatched files are deleted with
dependent cleanup.

## Display Filtering

The scanner indexes everything on disk. Filtering happens at display time via
three independent layers:

1. **System files** (`@eaDir`, `@eaStream`, `.etp.db*`, etc.) — NAS/OS
   byproducts. Hidden from listings by default, but included in `--du` size
   calculations. Shown with `--include-system-files`. Patterns are exact name
   matches against file/directory names.

2. **Dotfiles** (names starting with `.`) — hidden by default, shown with
   `-A`/`--all`. Managed by the `show_hidden` field in `FilterConfig`, not by
   user excludes. System files starting with `.` (like `.etp.db`) are exempt
   from dotfile hiding. See
   `docs/adrs/2026-03-28-02-dotfile-hiding-via-all-flag.md`.

3. **User excludes** (empty by default) — glob patterns from `--exclude` and
   `--ignore`, matched against filenames only (not the full path, since absolute
   paths may contain unrelated dot-directories).

System files are exempt from both dotfile hiding and user exclude matching.
`etp-query` does not apply dotfile hiding (it's a lower-level search command).

`FilterConfig` in `ops.rs` bundles all filter state: system patterns, user
excludes, `include_system_files`, and `show_hidden`. It provides `should_show()`
(for full path + filename checks) and `should_show_name()` (for individual name
checks in tree rendering).

## Runtime Configuration (config.kdl)

`config.kdl` lives in the platform config directory (`etp-init` generates it).
It provides:

- **System file patterns** — override `DEFAULT_SYSTEM_PATTERNS`
- **User exclude patterns** — override `DEFAULT_USER_EXCLUDES`
- **CAS directory** — override the platform default for blob storage
- **Database nicknames** — map short names to `(root, db)` path pairs
- **Default database** — nickname used when no `--db` and no `.etp.db` exists

All commands load config via `RuntimeConfig::load_or_default()`. If the file
doesn't exist, hardcoded defaults are used. Invalid config (e.g.,
`default-database` naming a nonexistent nickname) errors at load time.

Database nicknames resolve in this order: if the argument exists as a directory
or file, use it as a path; otherwise look it up in config. `resolve_nickname`
prints the resolution to stderr so users can see what's happening.

The `default-database` fallback is used by etp-tree, etp-csv, etp-find, and
etp-query. etp-scan is excluded to prevent accidental writes to the wrong
database. See `docs/adrs/2026-03-28-04-default-database-fallback.md`.

## CLI Boolean Flag Pairs

For flags where both the positive and negative form are meaningful (e.g.,
`--scan` / `--no-scan`, `--include-system-files` / `--no-include-system-files`),
both forms are defined as separate clap args with `default_value_t = false`.
Resolution uses `ops::resolve_bool_pair()`:

- Only `--flag` passed → true
- Only `--no-flag` passed → false
- Neither passed → default
- Both passed → prints a warning to stderr and uses the default

This avoids clap's `overrides_with` (which silently picks the last one) in favor
of explicit conflict detection. The warning helps users who may be combining
flags from shell aliases or scripts without realizing the conflict.

## Profiling

Self-instrumented via `tracing` + `tracing-chrome`, gated behind the `profiling`
Cargo feature. Trace files are named `etp-trace-<binary>-<timestamp>.json` and
written to cwd. On Linux, `/proc/self/io` and `/proc/self/status` metrics are
sampled at phase boundaries. The feature adds no runtime cost when `--profile`
is not passed.

```bash
just build-profile      # native with profiling
just build-nas-profile  # NAS with profiling
etp-csv /path/to/dir --profile
# Open trace in Perfetto: https://ui.perfetto.dev
```

## Cross-Compilation

`.cargo/config.toml` sets the linker for `x86_64-unknown-linux-musl` to
`x86_64-linux-musl-gcc`. Two options:

1. **musl toolchain**: `brew install filosottile/musl-cross/musl-cross`, then
   `rustup target add x86_64-unknown-linux-musl`
2. **cross (Docker-based)**: Must use the git version
   (`cargo install cross --git https://github.com/cross-rs/cross`) — the
   crates.io release (0.2.5) lacks ARM64 Docker image support and fails on Apple
   Silicon.
