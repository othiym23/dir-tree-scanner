use caching_scanners::ops;
use clap::{Parser, Subcommand};
use std::path::{Path, PathBuf};

#[derive(Parser)]
#[command(
    name = "dir-tree-scanner",
    about = "Incremental filesystem scanner with CSV and tree output",
    version = concat!(env!("CARGO_PKG_VERSION"), " (", env!("GIT_HASH"), ")")
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Scan a directory and produce a CSV metadata index
    Csv {
        /// Root directory to scan
        directory: PathBuf,

        /// CSV output path
        #[arg(short, long)]
        output: Option<PathBuf>,

        /// State file path for incremental scanning
        #[arg(short, long)]
        state: Option<PathBuf>,

        /// Directory names to exclude from scanning
        #[arg(short, long, default_values_t = [String::from("@eaDir")])]
        exclude: Vec<String>,

        /// Print cache hit/miss info
        #[arg(short, long)]
        verbose: bool,
    },
    /// Scan a directory and display a tree view
    Tree {
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
    },
}

fn main() {
    let cli = Cli::parse();

    match cli.command {
        Command::Csv {
            directory,
            output,
            state,
            exclude,
            verbose,
        } => run_csv(&directory, output, state, &exclude, verbose),
        Command::Tree {
            directory,
            state,
            exclude,
            no_escape,
            ignore,
            all,
            verbose,
        } => run_tree(
            &directory, state, &exclude, no_escape, &ignore, all, verbose,
        ),
    }
}

fn run_csv(
    root: &Path,
    output: Option<PathBuf>,
    state: Option<PathBuf>,
    exclude: &[String],
    verbose: bool,
) {
    ops::validate_directory(root);

    let output = output.unwrap_or_else(|| root.join("index.csv"));
    let state_path = ops::resolve_state_path(state, root);

    let mut scan_state = ops::load_state(&state_path, verbose);
    ops::run_scan(root, &mut scan_state, exclude, verbose);
    ops::write_csv(&scan_state, &output, verbose);
    ops::save_state(&scan_state, &state_path, verbose);
}

fn run_tree(
    root: &Path,
    state: Option<PathBuf>,
    exclude: &[String],
    no_escape: bool,
    ignore: &[String],
    all: bool,
    verbose: bool,
) {
    if verbose {
        eprintln!("root is {}", root.display());
    }
    ops::validate_directory(root);

    let state_path = ops::resolve_state_path(state, root);
    if verbose {
        eprintln!("state_path is {}", state_path.display());
    }

    let mut scan_state = ops::load_state(&state_path, verbose);
    ops::run_scan(root, &mut scan_state, exclude, verbose);
    ops::save_state(&scan_state, &state_path, verbose);
    ops::render_tree(&scan_state, root, ignore, no_escape, all);
}
