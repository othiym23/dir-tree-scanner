use crate::state::ScanState;
use std::io;
use std::path::Path;

pub fn write_csv(state: &ScanState, output: &Path) -> io::Result<()> {
    let file = std::fs::File::create(output)?;
    let mut wtr = csv::Writer::from_writer(file);

    wtr.write_record(["path", "size", "ctime", "mtime"])
        .map_err(|e| io::Error::new(io::ErrorKind::Other, e))?;

    // Sort directories for stable output
    let mut dirs: Vec<_> = state.dirs.keys().collect();
    dirs.sort();

    for dir in dirs {
        let entry = &state.dirs[dir];
        for file in &entry.files {
            let path = dir.join(&file.filename);
            wtr.write_record(&[
                path.to_string_lossy().as_ref(),
                &file.size.to_string(),
                &file.ctime.to_string(),
                &file.mtime.to_string(),
            ])
            .map_err(|e| io::Error::new(io::ErrorKind::Other, e))?;
        }
    }

    wtr.flush().map_err(|e| io::Error::new(io::ErrorKind::Other, e))?;
    Ok(())
}
