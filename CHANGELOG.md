# Changelog

This project records user-visible changes here using calendar versions in the
normalized `YYYY.M.D` form.

## Unreleased

### Added

- Multiple initial reads and writes per command, including inclusive read ranges.
- A typed transport interface with deterministic serial-port cleanup and
  configurable read and write timeouts.
- A `pyuartsi` console command with validated, hyphenated options.
- Unit tests, strict type checking, Ruff checks, distribution smoke tests, and
  a supported-Python CI matrix.

### Changed

- Adopted the uv-native build backend and `src` project layout.
- Made the package export surface explicit while retaining compatibility names.
- Updated package licensing to PEP 639 SPDX metadata.
- Made ELF self-check failures raise `ELFVerificationError`.
- Split serial transport, protocol, FESVR, and CLI responsibilities.

### Removed

- Removed the unused experimental C serial implementation from distributions.
