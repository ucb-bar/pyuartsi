# Changelog

This project records user-visible changes here using calendar versions in the
normalized `YYYY.M.D` form.

## Unreleased

### Added

- A typed transport interface with deterministic serial-port cleanup and
  configurable read and write timeouts.
- A `pyuartsi` console command with validated, hyphenated options.
- Unit tests, strict type checking, Ruff checks, distribution smoke tests, and
  a supported-Python CI matrix.
- `UARTTSI.get_htif_addresses()`, which returns the `tohost` and `fromhost`
  addresses from the ELF symbols.

### Changed

- Adopted the uv-native build backend and `src` project layout.
- Made the package export surface explicit while retaining compatibility names.
- Updated package licensing to PEP 639 SPDX metadata.
- Made ELF self-check failures raise `ELFVerificationError`.
- Split serial transport, protocol, FESVR, and CLI responsibilities.
- `--cflush-addr` defaults to 0, which disables cache flushes. On designs with
  a SiFive L2 cache, set it to `0x02010200`.

### Fixed

- `--fesvr` no longer stops the TSI link on designs without an L2 cache.
- `--fesvr` finds `tohost` and `fromhost` from the ELF symbols. Baremetal-IDE
  programs put `fromhost` first.
- `--fesvr` no longer clears `tohost` on start, which lost the first request of
  a running program.

### Removed

- Removed the unused experimental C serial implementation from distributions.
