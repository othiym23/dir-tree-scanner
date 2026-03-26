# etp-anime parsing and substitution rules

This document captures all parsing logic, text substitution rules,
configuration, and workflow details for `etp-anime`.

## Subcommands

`etp-anime` (invoked via `etp anime`) has three subcommands:

- `etp anime triage [pattern]` — bulk import from downloads directory
- `etp anime series [pattern]` — sync from Sonarr-managed anime directory
- `etp anime episode <file> --anidb ID | --tvdb ID` — single-file import

All three share filename construction, directory resolution, conflict handling,
and file copying logic. See ADR `2026-03-26-01-anime-subcommand-split.md`.

## Configuration

### anime-ingestion.kdl

Loaded from `$XDG_CONFIG_HOME/euterpe-tools/anime-ingestion.kdl` (via
`paths.anime_config()`). Stores default paths and per-series ID mappings.

```kdl
paths {
  downloads-dir "/volume1/docker/pvr/data/downloads"
  anime-source-dir "/volume1/docker/pvr/data/anime"
  anime-dest-dir "/volume1/video/anime"
}

// Multi-ID mappings for multi-season AniDB series
series "Chained Soldier (2024)" {
  anidb 17330
  anidb 18548
}

series "Re ZERO Starting Life in Another World" {
  tvdb 305089
}
```

Series mappings are saved automatically when the user provides IDs during triage
or series sync. A series can have multiple IDs (one per AniDB season).

### anime.env

Loaded from `$XDG_CONFIG_HOME/euterpe-tools/anime.env` (via
`paths.anime_env()`). Simple `KEY=VALUE` format for API credentials:

```
ANIDB_CLIENT=myapp
ANIDB_CLIENTVER=1
TVDB_API_KEY=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

Existing environment variables are not overwritten.

## Source filename parsing

`parse_source_filename` extracts structured metadata from anime release
filenames. Patterns are tried in the order listed; the first match wins for each
field.

### Release group

Four patterns are tried in priority order:

1. **Bracket at start**: `^\[([^\]]+)\]` — fansub convention
   - `[Cyan] Show - 05.mkv` → `Cyan`
   - `[FLE] Re ZERO ... [4CC4766E].mkv` → `FLE`
2. **Scene trailing dash**: `-([A-Za-z][A-Za-z0-9]+)` before the file extension
   - `Show.S03E09.1080p.WEB-DL.DUAL-VARYG.mkv` → `VARYG`
3. **Sonarr metadata block**: `\[GROUP QUALITY-res,...]` where the first word
   before a quality keyword is the release group
   - `Show - s01e01 - Title [VARYG WEBDL-1080p,8bit,x264,AAC].mkv` → `VARYG`
   - `Show - s01e07 [Erai-raws WEBDL-1080p,...].mkv` → `Erai-raws`
   - Quality keywords: `WEBDL`, `WEB-DL`, `Bluray`, `HDTV`, `DVD`, `SDTV`, `Raw`
4. **Bracket anywhere** (fallback): `\[([A-Za-z]{2,6})\]` — short all-alpha tags
   that aren't CRC32 hashes (which are 8 hex chars)
   - `Re ZERO ... [Dual Audio] [PMR].mkv` → `PMR`

When no release group is detected, the user is prompted in interactive mode. In
batch mode, the metadata block omits the group.

### Episode number

Patterns are tried in order of specificity (most constrained first). All allow
an optional `v\d+` version suffix (e.g., `05v2`).

1. **Dot S/E** (scene naming): `.S01E05.` with dots on both sides
   - `Show.S01E05.1080p.mkv` → season 1, episode 5
2. **S/E** (general): `S01E05` anywhere
   - `[Group] Show - s1e05 - Title.mkv` → season 1, episode 5
3. **Dash** (fansub naming): ` - 05` followed by whitespace, bracket, dot, or
   end
   - `[Cyan] Show - 08 [1080p].mkv` → episode 8
   - `[MTBB] Show - 05v2 [hash].mkv` → episode 5, version 2
4. **EP prefix**: `EP05` or `E5` followed by whitespace, bracket, dot, or end
   - `Show EP12 [720p].mkv` → episode 12

When no episode number is detected, the user is prompted interactively. In batch
mode, the entry is marked with a `(todo)` tag.

### Version

Captured from the `v\d+` suffix on any episode pattern. Stored as an integer
(e.g., `2` for `v2`). When present, the version is appended to the release group
in the metadata block: `MTBB` → `MTBB(v2)`.

### CRC32 hash

Pattern: `\[([0-9A-Fa-f]{8})\]`

Matches an 8-character hex string in brackets anywhere in the filename.

### CRC32 verification

When a hash is present, it is verified against the actual file contents before
copying. `verify_hash` computes the CRC32 of the file and returns both the match
result and the computed hash (avoiding a redundant re-read on mismatch).

- **Match**: hash is preserved in the destination filename
- **Mismatch**: in interactive mode, the user is prompted; in batch mode, a
  `// CRC32 MISMATCH` comment is added to the manifest. If the copy proceeds,
  the hash is **stripped** from the destination filename.

### Source type

Keyword-based detection (word boundary, case-insensitive):

- **BD**: `BD`, `Blu-Ray`, `BluRay`, `BDRip`, `BDREMUX`
- **Web**: `WEB`, `WEBRip`, `WEB-DL`, `CR`, `AMZN`, `DSNP`, `HULU`, `NF`

### REMUX detection

Pattern: `REMUX` (case-insensitive). Sets `is_remux = True`.

### Series name extraction

For grouping files by series in triage mode, `_extract_group_name` determines
the series name:

- **Files in subdirectories**: uses the immediate subdirectory name (batch
  releases typically share a directory, e.g.,
  `[FLE] Re ZERO S01 (BD 1080p)/[FLE] Re ZERO S01E01...`)
- **Files directly in a source directory**: uses the filename

In both cases, `_strip_series_name` strips release metadata from the stem:

1. Strip leading release group: `[Group] ` prefix
2. Strip trailing CRC32 hash: ` [ABCD1234]`
3. Strip episode suffix (tried in order, first match wins):
   - ` - 05 [...` (dash-episode followed by metadata)
   - ` - S01E05...` (dash then SxEy)
   - `.S01E05...` (dot then SxEy, scene naming)
   - ` S01E05...` (space then SxEy, no separator)
   - ` - 05` at end of string (trailing dash-episode, no metadata)
4. Strip trailing whitespace

### Grouping normalization

`_normalize_for_grouping` lowercases the name and strips all non-alphanumeric
characters for use as a dict key when grouping files by series in triage mode.

## AniDB API response parsing

`_parse_anidb_xml` processes the XML response from AniDB's HTTP API.

### Series titles

Title elements have `xml:lang` and `type` attributes. Candidates are collected
in a single pass, then selected by priority:

**Japanese title** (highest to lowest priority):

1. `lang="ja" type="official"` — native Japanese (kanji/kana)
2. `lang="ja" type="main"` — Japanese main title
3. `lang="x-jat" type="main"` — romaji (romanized Japanese)
4. Any `type="main"` title (language-agnostic fallback)

**English title** (highest to lowest priority):

1. `lang="en" type="official"`
2. `lang="en" type="main"`

### Episode titles

For each episode element, titles are extracted from child `<title>` elements:

- `lang="en"` → `title_en` (first match; backticks replaced with apostrophes)
- `lang="ja"` → `title_ja` (first match)

### Episode type mapping

The `type` attribute on `<epno>` maps to episode types:

| AniDB type | Episode type | Tag format |
| ---------- | ------------ | ---------- |
| `1`        | `regular`    | (none)     |
| `2`        | `special`    | `S1`, `S2` |
| `3`        | `credit`     | `C1`, `C2` |
| `4`        | `trailer`    | `T1`, `T2` |
| `5`        | `parody`     | `P1`, `P2` |
| `6`        | `other`      | `O1`, `O2` |

## TheTVDB API response parsing

`_parse_tvdb_json` processes JSON responses from the TheTVDB v4 API.

### Series titles

Title resolution uses canonical translations from the
`/series/{id}/translations/{lang}` endpoint when available, falling back to the
series data and aliases. Only `eng` and `jpn` translations are fetched, and only
when listed in the series' `nameTranslations` array.

**Japanese title** (highest to lowest priority):

1. Canonical `jpn` translation (from translations endpoint)
2. Primary `name` field (the original-language title — Japanese for anime)

**English title** (highest to lowest priority):

1. Canonical `eng` translation (from translations endpoint)
2. First alias with `language: "eng"` from the `aliases` array

### Episode titles

Episodes are fetched from `/series/{id}/episodes/default/eng` to get
English-language episode names. Episode matching uses both episode number and
season number to avoid cross-season title mismatches.

### Episode type mapping

Episodes with `seasonNumber == 0` are classified as specials (tag `S{number}`).
All other episodes are regular, with the `season` field preserved for matching.

## Path sanitization

`_sanitize_path` is applied to all title strings before they are used in
directory names or filenames:

- `/` is replaced with space-dash-space — path separator on all platforms
- `:` is replaced with `-` — HFS legacy separator on macOS

## Redundant year stripping

`_strip_redundant_year` removes a trailing ` (YYYY)` suffix from a title when
the year matches the series release year, to avoid duplication in directory
names that already include the year.

## KDL string escaping

`_escape_kdl` escapes `\` and `"` in strings written to KDL files (manifests and
config). Used for filenames, paths, and series names that may contain special
characters (e.g., episode titles with quotes).

## Output format reference

### Directory name

Full format (when Japanese title contains kanji/kana and English title differs):

```
{title_ja} [{title_en}] ({year})
```

Single-title format (when Japanese title is romaji or empty, English title is
empty, or both titles are identical after sanitization):

```
{title} ({year})
```

### Episode filename

```
{concise_name} - s{season}e{episode:02d} - {episode_name} [{metadata}] [{hash}].{ext}
```

Variations:

- **No episode name**: `Name - s1e05 [metadata].mkv`
- **Special**: `Name - S1 - Episode Name [metadata] [hash].mkv`
- **Movie**: `DirName - complete movie [metadata] [hash].mkv`
- **Hash stripped** (CRC32 mismatch): hash bracket omitted entirely

### Metadata block

Format: `{prefix},{technical fields}`

**Prefix** (space-separated):

- Release group with optional version: `MTBB(v2)` or `MTBB`
- Source type: `BD` or `Web` (defaults to `Web` when not detected)

**Technical fields** (comma-separated, in order):

1. `REMUX` (if flagged)
2. Resolution (e.g., `1080p`)
3. Video codec (e.g., `HEVC`, `AVC`)
4. HDR type (e.g., `HDR`, `DoVi`) — if present
5. `10bit` — if bit depth >= 10
6. Encoding library (e.g., `x264`, `x265`) — if detected
7. Audio codecs joined by `+` (e.g., `flac+aac`)
8. Audio language: `dual-audio` (ja+en), `multi-audio` (ja+en+other), or omitted

Example: `MTBB(v2) BD,REMUX,1080p,HEVC,10bit,x265,flac+aac,dual-audio`

## Batch manifest (KDL format)

Both `triage` and `series` subcommands generate a KDL manifest file grouped by
season, with source and destination filenames on separate lines. The manifest is
opened in `$VISUAL` / `$EDITOR` / `vi` for editing.

```kdl
// etp-anime triage manifest
// Series: 葬送のフリーレン [Frieren- Beyond Journey's End] (2023)
// AniDB: 17617
// Series dir: /volume1/video/anime/...

season 1 {
  episode 1 {
    source "/volume1/.../[FLE] Show - S01E01 ... [4CC4766E].mkv"
    downloaded "/volume1/.../[FLE] Show - 01 [BD 1080p] [4CC4766E].mkv"
    dest "Show - s1e01 - Episode Title [FLE BD,...] [4CC4766E].mkv"
  }
}
```

- Entries are sorted by episode number within each season group
- `source` is the full path to the source file (read-only reference)
- `downloaded` is the matched download file path (read-only, present when
  `series` mode enriches metadata from downloads)
- `dest` is the target filename (editable)
- Season/specials directory is derived from the parent node
- `/- episode ...` (KDL slashdash) skips an entry
- `(todo)` tagged entries are rejected at parse time until resolved
- `// CRC32 MISMATCH` comments mark files where the hash was stripped
- Strings containing `"` or `\` are escaped in the KDL output

## Download index matching (series mode)

The `series` subcommand builds a `DownloadIndex` from the downloads directory to
enrich Sonarr-renamed files with original release metadata:

- **`by_series`**: normalized series name → list of
  `(season, episode, path, size)`. Uses parent directory name for batch
  releases.
- **`by_episode`**: `(season, episode)` → `(path, size)` as a global fallback.

For each source file, `_match_to_downloads` tries series-specific matching
first, then falls back to the global index. When multiple candidates exist, the
closest file size is used as a tiebreaker. File sizes are cached at index build
time to avoid repeated stat calls on NAS spinning disks.

The matched download's release group, CRC32 hash, version, and source type
replace the Sonarr-reformatted values on the source file.

## AniDB per-season handling

AniDB assigns separate IDs per season. Both `triage` and `series` subcommands
process one AniDB ID at a time against a shrinking pool of files:

1. Show candidate seasons with file counts
2. User picks which season maps to this AniDB ID
3. Sort the season's files by episode number
4. If the season has more files than the AniDB entry's episode count, take only
   the first N and leave the rest for the next AniDB ID
5. Renumber episodes to start at 1 if needed (e.g., S03E13 → s1e01)

Each AniDB ID gets its own series directory with `s1eYY` numbering. The config
file stores multiple IDs per series for subsequent runs.

### Specials handling

Specials may use AniDB naming (S1, NCOP1a, T1, O01), TVDB naming (S00EYY), or
have no clear numbering. Ambiguous files are included with `(todo)` tag.

## Destination conflict resolution

Before copying, the script checks for existing files at the destination:

1. **Exact path match**: checks if `dest_path` exists
2. **Fuzzy episode match**: scans the destination directory for a file with the
   same episode tag (by parsing `sXeYY` as integers), handling different
   zero-padding conventions (e.g., `s1e01` finds `s01e01`)

When a conflict is found:

- **Same metadata** (release group, source type, video codec, audio codecs):
  - File sizes compared first (short-circuit)
  - If sizes match, CRC32 computed for both files
  - CRC32 match → auto-replace silently (fixing naming)
  - CRC32 mismatch → prompt user
- **Different metadata**: show both filenames (using the intended dest name, not
  the source name) with mediainfo summaries and file sizes, prompt
  `[k]eep / [r]eplace / [s]kip`

## Triage copy tracking

Processed files are tracked in a JSON manifest at
`$XDG_CACHE_HOME/etp/triage/copied.json`. Files copied, kept, skipped, or marked
"done" (via the `d` command) are all recorded. Previously processed files are
filtered out on subsequent runs unless `--force` is used. The `q` command saves
progress and exits.
