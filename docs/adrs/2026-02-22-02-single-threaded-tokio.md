# Use single-threaded tokio runtime

Date: 2026-02-22

## Status

Accepted

## Context

sqlx requires an async runtime. The target deployment is a Synology NAS with
spinning disks in RAID 6 (two parity disks). Spinning disks penalize random
seeks heavily — sequential I/O patterns are critical for scan performance at
200K+ file scale. The scanner walks the filesystem in directory order
specifically to maintain sequential access.

## Decision

Use tokio with the `rt` feature only (not `rt-multi-thread`). Run a
single-threaded runtime via `#[tokio::main(flavor = "current_thread")]`. All
filesystem scanning and metadata reading proceeds sequentially in directory
order.

## Consequences

- Disk I/O remains sequential, preserving the performance characteristics that
  matter on spinning disks.
- Smaller binary — the multi-threaded runtime adds significant code.
- Simpler reasoning about concurrent state — no need for `Arc`/`Mutex` around
  scan state.
- Cannot parallelize CPU-bound work (e.g., BLAKE3 hashing of large files). This
  is acceptable because disk I/O is the bottleneck, not CPU.
- All `async fn` calls are effectively sequential, which may feel unusual but is
  intentional.
