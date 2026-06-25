# Procedure: Board-Resident Test Script Policy

Temporary test scripts may be copied to the board for execution, but they must not be left there as unmanaged files.

## Rules

1. Keep the source copy on PC/VM/Git.
2. Copy to board only when needed.
3. Run the test.
4. Save logs back to PC/VM.
5. Delete the board-side temporary script.
6. Record the result in `lessons/` or module `notes/`.

## Why

Earlier testing proved that board-side leftovers make it hard to know which version is actually running. The board should contain stable services and packages, not random one-off scripts.

## Good Locations

- Module-specific tests: `modules/<module>/tests/`
- Cross-module tests: `scripts/test/`
- Recovery scripts: `scripts/recovery/`
- Logs: local-only, not committed unless small and important

## Safety

Any test that can move the chassis, arm, or pump requires explicit user safety confirmation.
