use caching_scanners::{cli, csv_writer};
use clap::Parser;
use std::path::PathBuf;
use std::process;

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
    if !root.is_dir() {
        eprintln!("error: {} is not a directory", root.display());
        process::exit(1);
    }

    let output = args.output.unwrap_or_else(|| root.join("index.csv"));
    let state_path = args.state.unwrap_or_else(|| root.join(".fsscan.state"));

    let mut scan_state = cli::load_state(&state_path, args.verbose);
    cli::run_scan(root, &mut scan_state, &args.exclude, args.verbose);

    if let Err(e) = csv_writer::write_csv(&scan_state, &output) {
        eprintln!("error writing CSV: {}", e);
        process::exit(1);
    }
    if args.verbose {
        eprintln!("wrote {}", output.display());
    }

    cli::save_state(&scan_state, &state_path, args.verbose);
}
