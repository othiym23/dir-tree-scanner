use caching_scanners::ops;
use clap::Parser;
use std::path::PathBuf;

#[derive(Parser)]
#[command(name = "fsscan", about = "Fast incremental filesystem scanner")]
struct Cli {
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
}

fn main() {
    let args = Cli::parse();

    let root = &args.directory;
    ops::validate_directory(root);

    let output = args.output.unwrap_or_else(|| root.join("index.csv"));
    let state_path = ops::resolve_state_path(args.state, root);

    let mut scan_state = ops::load_state(&state_path, args.verbose);
    ops::run_scan(root, &mut scan_state, &args.exclude, args.verbose);
    ops::write_csv(&scan_state, &output, args.verbose);
    ops::save_state(&scan_state, &state_path, args.verbose);
}
