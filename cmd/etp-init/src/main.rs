use clap::Parser;
use std::fs;

#[derive(Parser)]
#[command(
    name = "etp-init",
    about = "Create a default configuration file",
    version = concat!(env!("CARGO_PKG_VERSION"), " (", env!("GIT_HASH"), ")")
)]
struct Cli {
    /// Overwrite existing config file
    #[arg(long)]
    force: bool,
}

const CONFIG_TEMPLATE: &str = r##"// euterpe-tools runtime configuration
//
// This file controls display-time filtering defaults and database nicknames.
// Edit the values below or uncomment sections as needed.
// Regenerate with: etp init --force

// Default database nickname — used when no --db is specified
// and no .etp.db exists in the target directory.
// default-database "music"

// CAS (content-addressable storage) directory for embedded images.
// Defaults to platform data directory. Set this to share a single CAS
// between machines (e.g. NAS and workstation).
// cas-dir "/volume1/data/etp/assets"

// System files: NAS/OS byproducts. Always scanned, counted in disk
// usage, but hidden from listings unless --include-system-files is
// passed. Remove or add patterns as needed for your environment.
system-files {
    pattern "@eaDir"
    pattern "@eaStream"
    pattern "@tmp"
    pattern "@SynoResource"
    pattern "@SynoEAStream"
    pattern "#recycle"
    pattern ".SynologyWorkingDirectory"
    pattern ".etp.db"
    pattern ".etp.db-wal"
    pattern ".etp.db-shm"
}

// User excludes: hidden from listings AND excluded from size
// calculations. Uses glob patterns matched against file/directory
// names. Dotfile hiding is separate (controlled by -a/--all).
user-excludes {
    // pattern "*.bak"
    // pattern "Thumbs.db"
}

// Database nicknames: map short names to root + db path pairs.
// After configuring, use "etp tree music" instead of
// "etp tree /volume1/music --db /path/to/music.db".
//
// database "music" {
//     root "/volume1/music"
//     db "/path/to/music.db"
// }
//
// database "television" {
//     root "/volume1/data/video/Television"
//     db "/path/to/television.db"
// }
"##;

fn main() {
    let cli = Cli::parse();

    let config_dir = etp_lib::paths::config_dir().unwrap_or_else(|e| {
        eprintln!("error: cannot determine config directory: {e}");
        std::process::exit(1);
    });

    let config_path = config_dir.join("config.kdl");

    if config_path.exists() && !cli.force {
        eprintln!(
            "error: config file already exists at {}",
            config_path.display()
        );
        eprintln!("use --force to overwrite");
        std::process::exit(1);
    }

    if let Err(e) = fs::create_dir_all(&config_dir) {
        eprintln!("error: cannot create config directory: {e}");
        std::process::exit(1);
    }

    if let Err(e) = fs::write(&config_path, CONFIG_TEMPLATE) {
        eprintln!("error: cannot write config file: {e}");
        std::process::exit(1);
    }

    println!("{}", config_path.display());
}
