# Plan: Use ICU4X collation for cached-tree sorting

## Context

`cached-tree` needs to sort filenames in a way that handles multiple scripts and
languages (Latin, CJK, Korean, accented Latin, etc.). Previous attempts:

1. `libc::strcoll` — works on macOS/glibc but musl stubs it to `strcmp`
2. Hand-rolled case-insensitive + alphanumeric filter — handles Latin case but
   breaks on non-Latin scripts and doesn't match UCA ordering

The user has already added `icu = "2.1.1"` to Cargo.toml and started using
`icu::collator` in `cached_tree.rs`. The goal is to configure it correctly for
multilingual filename collation.

## How difficult would it be to copy tree's algorithm?

**Not useful — tree's sort is just `strcoll(a, b)`.** The `alnumsort` function
in tree.c is a one-liner that delegates to glibc's `strcoll`. All the real
complexity lives in glibc's locale machinery, not in tree's code. Tree also
offers `versort` via `strverscmp` for version-number-aware sorting, but the
default alphabetic sort is purely `strcoll`. Copying tree would mean either
linking against glibc (Docker/cross complexity + glibc version dependency) or
reimplementing glibc's locale tables — which is exactly what ICU4X does, better.

## ICU4X collation approach

### Locale: root (`und` / default)

For multilingual filenames spanning many scripts, the **root locale** is the
right choice:

- The UCA root collation is a **language-independent baseline** that handles all
  Unicode scripts with a deterministic, stable ordering
- Picking a specific locale (e.g. `en-us`) tailors for English, which could
  reorder characters in other scripts unexpectedly
- Root locale ordering groups by category (whitespace → punctuation → symbols →
  numbers → letters) and within letters orders by script block
- This produces a stable order that respects each script's natural collation

In ICU4X, root locale = `Default::default()` for the preferences parameter.

### Strength: Quaternary

`Strength::Primary` (currently set) is too aggressive — it ignores accents,
case, AND punctuation. For filenames we want all four levels:

- **L1 (Primary)**: Base letter differences (`a` vs `b`)
- **L2 (Secondary)**: Accent differences (`Häxan` vs `Haxan`)
- **L3 (Tertiary)**: Case differences (`File` vs `file`)
- **L4 (Quaternary)**: Punctuation/whitespace (`show - s01e01` vs `show s01e01`)

### AlternateHandling: Shifted

With `Shifted`, punctuation and symbols get IGNORE weight at L1–L3 but are
distinguished at L4. This means:

- `show - s01e01` and `show S01E01` compare equal through L3, then L4 breaks the
  tie — producing episode interleaving
- `Yuru.Camp△.S02` vs `Yuru.Camp.S2` compare by alphanumeric content first
- But `file.txt` ≠ `filetxt` because L4 catches the dot

### Performance: create Collator once

The current code creates a `Collator` inside every `cmp()` call. The Collator
should be created once and stored in `TreeContext`. Since `BTreeSet` requires
`Ord` on the type (no external state), we'll switch `merge_entries` to collect
into a `Vec<Entry>` and sort with a closure that captures the collator.

## Files to modify

### `src/bin/cached_tree.rs`

1. **Remove `Ord`/`PartialOrd`/`Eq`/`PartialEq` impls from `Entry`** — no longer
   needed since we sort with an explicit comparator
2. **Add collator to `TreeContext`** — create once in `render_tree`:
   ```rust
   let mut options = CollatorOptions::default();
   options.strength = Some(Strength::Quaternary);
   options.alternate_handling = Some(AlternateHandling::Shifted);
   let collator = Collator::try_new(Default::default(), options).unwrap();
   ```
3. **Change `merge_entries`** — accept `&TreeContext`, collect files + dirs into
   a `Vec<Entry>`, sort with `sort_by(|a, b| ctx.collator.compare(...))`, apply
   hidden/pattern filters
4. **Remove old `locale_cmp` function** and unused imports

### `CLAUDE.md`

Update collation section to document ICU4X approach, root locale choice, and
Shifted + Quaternary configuration rationale.

## Verification

1. `cargo clippy -- -D warnings`
2. `cargo test` — all trycmd tests pass (case-sort and collation tests)
3. `cargo build --release --target x86_64-unknown-linux-musl` — ICU4X is pure
   Rust with compiled-in Unicode data, no C dependencies, so musl works fine
4. Deploy to NAS and compare output against `tree` for television and movies
