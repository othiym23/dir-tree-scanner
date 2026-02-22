use caching_scanners::{cli, tree};
use clap::Parser;
use std::path::PathBuf;
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
    let args = Cli::parse();

    let root = &args.directory;
    if args.verbose {
        eprintln!("root is {}", root.display())
    }
    if !root.is_dir() {
        eprintln!("error: {} is not a directory", root.display());
        process::exit(1);
    }

    let state_path = args.state.unwrap_or_else(|| root.join(".fsscan.state"));
    if args.verbose {
        eprintln!("state_path is {}", state_path.display())
    }

    let mut scan_state = cli::load_state(&state_path, args.verbose);
    cli::run_scan(root, &mut scan_state, &args.exclude, args.verbose);
    cli::save_state(&scan_state, &state_path, args.verbose);

    let patterns = cli::parse_ignore_patterns(&args.ignore);

    let (dir_count, file_count) =
        tree::render_tree(&scan_state, root, &patterns, args.no_escape, args.all);
    println!("\n{} directories, {} files", dir_count, file_count);
}
