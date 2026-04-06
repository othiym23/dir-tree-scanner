# ADR: CLI Design for AI Agent Consumption

**Date:** 2026-04-06 **Status:** Accepted

## Context

euterpe-tools commands are used both interactively by a human operator and
programmatically by AI agents (Claude Code, future automation). The existing CLI
evolved organically with convenience-oriented design: auto-detection of modes,
implicit defaults, and interactive prompts that assume a human is present.

As the tooling matures and AI-assisted orchestration becomes a goal, the CLI
needs to be predictable enough that an agent can invoke commands confidently
without understanding hidden heuristics or navigating ambiguous prompts.

## Decision

The CLI follows six principles:

### 1. Explicit over convenient

Commands require explicit arguments for anything that changes behavior. If a
command can operate in multiple modes (e.g., processing Sonarr-managed files vs.
triaging downloads), the mode must be specified via a flag. The command fails
with a clear error if the mode is ambiguous.

**Rationale:** An AI agent cannot reliably guess which mode was intended.
Auto-detection that works 90% of the time creates 10% silent failures that are
hard to diagnose.

### 2. Fast failure

Validate all arguments and preconditions before doing any work. Missing
directories, invalid IDs, and configuration errors should be caught and reported
immediately with actionable error messages.

**Rationale:** Agents should be able to distinguish "bad arguments" from
"operation failed" by checking the exit code without parsing output.

### 3. Structured output

Commands that produce data should support machine-readable output (JSON, CSV) in
addition to human-readable formats. Exit codes are meaningful:

- 0: success (files were processed)
- 1: failure (errors occurred)
- 2: nothing to do (no matching files, all already processed)

**Rationale:** Agents parse structured output; they shouldn't need to scrape
terminal formatting or interpret ANSI color codes.

### 4. Idempotent operations

Running the same command twice with the same arguments produces the same result.
File copies, config writes, and manifest saves happen at the end of processing,
not incrementally.

**Rationale:** If an agent's invocation is interrupted, re-running should be
safe. Partial state from interrupted runs should not corrupt subsequent runs.

### 5. No hidden state

All state that affects behavior comes from: command-line arguments, config files
(at known paths), or the filesystem. Caches improve performance but never change
correctness. `--no-cache` always produces the same result as a first run.

**Rationale:** An agent debugging unexpected behavior can inspect arguments +
config + filesystem state to reproduce the issue. Hidden in-memory state or
implicit session data makes debugging impossible.

### 6. Composable commands

Each command does one thing. Complex workflows (e.g., "sync from Sonarr, then
triage leftover downloads, then verify naming") are built by invoking multiple
commands in sequence, not by adding flags that make one command do everything.

**Rationale:** Agents can plan and execute multi-step workflows by composing
simple commands. A monolithic command with 20 flags is harder to reason about
than three focused commands.

## Consequences

- New commands default to failing rather than guessing when arguments are
  ambiguous.
- Interactive prompts should have non-interactive equivalents (flags or
  structured input) so agents can drive the workflow without simulating keyboard
  input.
- Human convenience features (colorized output, progress bars, smart defaults)
  remain available but are layered on top of the structured core, not baked into
  the logic.
- The `etp anime ingest` command replaces `etp anime series` and
  `etp anime triage` following these principles: `--sonarr` and `--downloads`
  flags explicitly select which sources to process.

## Supersedes

This ADR establishes new principles. It does not supersede a specific earlier
decision, but it informs the design of all future CLI additions.
