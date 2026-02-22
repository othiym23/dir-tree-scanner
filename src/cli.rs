use crate::scanner;
use crate::state::{LoadOutcome, ScanState};
use std::path::Path;
use std::process;

/// Load scan state from disk, handling all three outcomes.
/// Exits the process on unrecoverable errors.
pub fn load_state(path: &Path, verbose: bool) -> ScanState {
    match ScanState::load(path) {
        LoadOutcome::Loaded(s) => {
            if verbose {
                eprintln!("loaded state from {}", path.display());
            }
            s
        }
        LoadOutcome::NotFound => {
            if verbose {
                eprintln!("no previous state, starting fresh");
            }
            ScanState::default()
        }
        LoadOutcome::Invalid(reason) => {
            eprintln!("warning: {}: {}, rescanning", path.display(), reason);
            ScanState::default()
        }
    }
}

/// Run the scanner and log stats. Exits on error.
pub fn run_scan(root: &Path, state: &mut ScanState, exclude: &[String], verbose: bool) {
    match scanner::scan(root, state, exclude, verbose) {
        Ok(stats) => {
            if verbose {
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
}

/// Parse glob ignore patterns, warning on and discarding invalid ones.
pub fn parse_ignore_patterns(patterns: &[String]) -> Vec<glob::Pattern> {
    patterns
        .iter()
        .filter_map(|p| match glob::Pattern::new(p) {
            Ok(pat) => Some(pat),
            Err(e) => {
                eprintln!("warning: invalid glob pattern '{}': {}, discarding", p, e);
                None
            }
        })
        .collect()
}

/// Save scan state to disk. Exits on error.
pub fn save_state(state: &ScanState, path: &Path, verbose: bool) {
    if let Err(e) = state.save(path) {
        eprintln!("error saving state: {}", e);
        process::exit(1);
    }
    if verbose {
        eprintln!("saved state to {}", path.display());
    }
}
