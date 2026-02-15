mod csv_writer;

use caching_scanners::scanner;
use caching_scanners::state::ScanState;
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
    let cli = Cli::parse();

    let root = &cli.directory;
    if !root.is_dir() {
        eprintln!("error: {} is not a directory", root.display());
        process::exit(1);
    }

    let output = cli.output.unwrap_or_else(|| root.join("index.csv"));
    let state_path = cli.state.unwrap_or_else(|| root.join(".fsscan.state"));

    let mut scan_state = match ScanState::load(&state_path) {
        Ok(s) => {
            if cli.verbose {
                eprintln!("loaded state from {}", state_path.display());
            }
            s
        }
        Err(_) => {
            if cli.verbose {
                eprintln!("no previous state, starting fresh");
            }
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

    if let Err(e) = csv_writer::write_csv(&scan_state, &output) {
        eprintln!("error writing CSV: {}", e);
        process::exit(1);
    }
    if cli.verbose {
        eprintln!("wrote {}", output.display());
    }

    if let Err(e) = scan_state.save(&state_path) {
        eprintln!("error saving state: {}", e);
        process::exit(1);
    }
    if cli.verbose {
        eprintln!("saved state to {}", state_path.display());
    }
}
