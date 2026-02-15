use caching_scanners::scanner;
use caching_scanners::state::{LoadOutcome, ScanState};
use clap::Parser;
use glob::Pattern;
use icu_collator::CollatorBorrowed;
use icu_collator::options::{AlternateHandling, CollatorOptions, Strength};
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};
use std::process;

#[derive(Parser)]
#[command(
    name = "cached-tree",
    about = "tree-compatible output using fsscan incremental state"
)]
struct Cli {
    /// Root directory to display
    directory: PathBuf,

    /// State file path for incremental scanning
    #[arg(short, long)]
    state: Option<PathBuf>,

    /// Directory names to exclude from scanning
    #[arg(short, long, default_values_t = [String::from("@eaDir")])]
    exclude: Vec<String>,

    /// Print names as-is (no character escaping)
    #[arg(short = 'N', long = "no-escape")]
    no_escape: bool,

    /// Glob pattern to exclude from output (repeatable)
    #[arg(short = 'I', long = "ignore")]
    ignore: Vec<String>,

    /// Show hidden files (names starting with '.')
    #[arg(short, long)]
    all: bool,

    /// Print scan info on stderr
    #[arg(short, long)]
    verbose: bool,
}

fn main() {
    let cli = Cli::parse();

    let root = &cli.directory;
    if cli.verbose {
        eprintln!("root is {}", root.display())
    }
    if !root.is_dir() {
        eprintln!("error: {} is not a directory", root.display());
        process::exit(1);
    }

    // Load state, scan, save
    let state_path = cli.state.unwrap_or_else(|| root.join(".fsscan.state"));
    if cli.verbose {
        eprintln!("state_path is {}", state_path.display())
    }

    let mut scan_state = match ScanState::load(&state_path) {
        LoadOutcome::Loaded(s) => {
            if cli.verbose {
                eprintln!("loaded state from {}", state_path.display());
            }
            s
        }
        LoadOutcome::NotFound => {
            if cli.verbose {
                eprintln!("no previous state, starting fresh");
            }
            ScanState::default()
        }
        LoadOutcome::Invalid(reason) => {
            eprintln!("warning: {}: {}, rescanning", state_path.display(), reason);
            ScanState::default()
        }
    };

    match scanner::scan(root, &mut scan_state, &cli.exclude, cli.verbose) {
        Ok(stats) => {
            if cli.verbose {
                eprintln!(
                    "dirs: {} cached, {} scanned, {} removed",
                    stats.dirs_cached, stats.dirs_scanned, stats.dirs_removed
                );
            }
        }
        Err(e) => {
            eprintln!("error scanning: {}", e);
            process::exit(1);
        }
    }

    if let Err(e) = scan_state.save(&state_path) {
        eprintln!("error saving state: {}", e);
        process::exit(1);
    }

    // Parse ignore patterns
    let patterns: Vec<Pattern> = cli
        .ignore
        .iter()
        .filter_map(|p| match Pattern::new(p) {
            Ok(pat) => Some(pat),
            Err(e) => {
                eprintln!("warning: invalid glob pattern '{}': {}", p, e);
                None
            }
        })
        .collect();

    // Render tree
    let (dir_count, file_count) = render_tree(&scan_state, root, &patterns, cli.no_escape, cli.all);
    println!("\n{} directories, {} files", dir_count, file_count);
}

/// Escape non-printable and non-ASCII bytes to '?' (matching tree's default behavior).
/// With -N, returns the name unchanged.
fn maybe_escape(name: &str, no_escape: bool) -> String {
    if no_escape {
        return name.to_string();
    }
    name.chars()
        .map(|c| {
            if c.is_ascii_graphic() || c == ' ' {
                c
            } else {
                '?'
            }
        })
        .collect()
}

/// Shared context for recursive tree rendering.
struct TreeContext<'a> {
    state: &'a ScanState,
    children: BTreeMap<PathBuf, BTreeSet<String>>,
    patterns: &'a [Pattern],
    collator: CollatorBorrowed<'static>,
    no_escape: bool,
    show_hidden: bool,
}

fn render_tree(
    state: &ScanState,
    root: &Path,
    patterns: &[Pattern],
    no_escape: bool,
    show_hidden: bool,
) -> (usize, usize) {
    // Build child-directory map: for each dir in state, register it as a child of its parent
    let mut children: BTreeMap<PathBuf, BTreeSet<String>> = BTreeMap::new();
    for dir_key in state.dirs.keys() {
        let dir_path = Path::new(dir_key);
        if let Some(parent) = dir_path.parent()
            && let Some(name) = dir_path.file_name()
        {
            children
                .entry(parent.to_path_buf())
                .or_default()
                .insert(name.to_string_lossy().into_owned());
        }
    }

    let mut options = CollatorOptions::default();
    options.strength = Some(Strength::Quaternary);
    options.alternate_handling = Some(AlternateHandling::Shifted);
    let collator = CollatorBorrowed::try_new(Default::default(), options).unwrap();

    let ctx = TreeContext {
        state,
        children,
        patterns,
        collator,
        no_escape,
        show_hidden,
    };

    println!("{}", root.display());

    let mut dir_count = 1; // count the root directory itself, matching tree's behavior
    let mut file_count = 0;
    render_dir(&ctx, root, "", &mut dir_count, &mut file_count);
    (dir_count, file_count)
}

/// Entry in the merged directory listing — either a file or subdirectory.
enum Entry {
    File(String),
    Dir(String),
}

impl Entry {
    fn name(&self) -> &str {
        match self {
            Entry::File(n) | Entry::Dir(n) => n,
        }
    }
}

fn merge_entries(files: &[String], child_dirs: &BTreeSet<String>, ctx: &TreeContext) -> Vec<Entry> {
    let mut entries: Vec<Entry> = files
        .iter()
        .map(|f| Entry::File(f.clone()))
        .chain(child_dirs.iter().map(|d| Entry::Dir(d.clone())))
        .filter(|e| {
            let n = e.name();
            if !ctx.show_hidden && n.starts_with('.') {
                return false;
            }
            !ctx.patterns.iter().any(|p| p.matches(n))
        })
        .collect();

    entries.sort_by(|a, b| ctx.collator.compare(a.name(), b.name()));
    entries
}

fn render_dir(
    ctx: &TreeContext,
    dir_path: &Path,
    prefix: &str,
    dir_count: &mut usize,
    file_count: &mut usize,
) {
    let dir_key = dir_path.to_string_lossy();
    let files: Vec<String> = ctx
        .state
        .dirs
        .get(dir_key.as_ref())
        .map(|d| d.files.iter().map(|f| f.filename.clone()).collect())
        .unwrap_or_default();
    let empty = BTreeSet::new();
    let child_dirs = ctx.children.get(dir_path).unwrap_or(&empty);

    let entries = merge_entries(&files, child_dirs, ctx);
    let total = entries.len();
    for (i, entry) in entries.iter().enumerate() {
        let is_last = i + 1 == total;
        let connector = if is_last { "└── " } else { "├── " };
        let child_prefix = if is_last { "    " } else { "│\u{a0}\u{a0} " };

        match entry {
            Entry::File(name) => {
                println!(
                    "{}{}{}",
                    prefix,
                    connector,
                    maybe_escape(name, ctx.no_escape)
                );
                *file_count += 1;
            }
            Entry::Dir(name) => {
                println!(
                    "{}{}{}",
                    prefix,
                    connector,
                    maybe_escape(name, ctx.no_escape)
                );
                *dir_count += 1;
                let child_path = dir_path.join(name);
                render_dir(
                    ctx,
                    &child_path,
                    &format!("{}{}", prefix, child_prefix),
                    dir_count,
                    file_count,
                );
            }
        }
    }
}
