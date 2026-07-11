## v1.1.9 - Coordinate Browser filter help

### Changed
- Renamed `Contains atom index` to `Atom filter`.
- Renamed `Label contains` to `Text filter`.
- Added inline GUI help explaining atom-index and text filtering.
- Added bond/pair notation support in Atom filter: `3-12`, `3–12`, and `3－12` match coordinates containing both atoms.
- Preserved comma-separated atom filtering as OR semantics, e.g. `3,12` matches coordinates containing either atom.

# Changelog

## v1.1.9 - Group-qualified target references

### Fixed
- Fixed target-coordinate selection when VEDA/DD2 reuses the same coordinate-set code and numeric `coord_id` for different groups such as `STRE` and `BEND`.
- Target references are now group-qualified as `code:group:coord_id`, for example `k:STRE:126` and `k:BEND:126`.
- `Add selected to target` now records the selected row's coordinate set, group, and ID, preventing a selected stretch coordinate from being resolved as a bend coordinate in Target Definition.
- Target preview, target hits, summary by coordinate, summary by mode, and combined output now use group-qualified `target_ref` values.

### Compatibility
- Legacy references such as `k:126` and bare `126` are still accepted as wildcard-group references (`k:*:126`, `s:*:126`) but may match multiple DD2 rows. New selections should use the full `code:group:coord_id` form.

## v1.1.7 - Combined target matrix-source selection fix

### Fixed
- Fixed combined target outputs for cases where requested target references mix coordinate sets, such as `s:83` plus `k:126`, while the `.ved` file exposes only a standard PED matrix.
- Combined outputs now select an appropriate numeric PED matrix source for each requested coordinate-set code. If an explicit alternative PED block is unavailable, the standard PED matrix is reinterpreted with the requested DD2 coordinate set instead of reporting the target as missing.
- This allows `k:*` and `v:*` targets to be found when their `coord_id` appears as a PED column and the corresponding DD2 alternative coordinate exists.

### Diagnostics
- The log now reports when a PED matrix is reinterpreted with an alternative DD2 coordinate set for combined target outputs.
- The `requested_target_refs`, `found_target_refs`, and `missing_target_refs` columns remain available for checking whether every mixed target was actually included.

## v1.1.6 - Combined target DD2 fallback

### Fixed
- Added a DD2-terms fallback for combined target outputs. If a mixed target reference such as `k:126` is present in DD2 but is not found in a parsed alternative PED block, the combined output can read coordinate-centered DD2 terms and merge them by VEDA/QC mode.
- This fallback is used only when matrix-based matching cannot find the requested target.

### Diagnostics
- Combined `top_target_terms` may show `dd2_terms_alternative_k` or `dd2_terms_alternative_v` when contributions are recovered from DD2 coordinate terms rather than from a parsed PED matrix.

## v1.1.5 - Combined target PED-block fix

### Fixed
- Fixed combined target output so each code-qualified target reference is read from the matching PED block: `s:*` from standard, `k:*` from alternative_k, and `v:*` from alternative_v.
- Prevented fallback relabeling from causing mixed targets to be counted only through the standard PED block.

### Added
- Added `requested_target_refs`, `found_target_refs`, and `missing_target_refs` columns to combined summary/matrix outputs to make missing mixed targets easy to diagnose.
- Added a warning when a requested combined target reference is not found in its matching PED block.

## v1.1.4 - Coordinate Browser default filters

### Fixed
- Set the Coordinate Browser default coordinate-set filter to `s - standard`.
- Set the Coordinate Browser default group filter to `STRE - Stretching`.
- Kept these labels visible in the dropdown menus while internally filtering by raw VEDA/DD2 codes (`s`, `k`, `v`, `STRE`).

## v1.1.3 - Combined mixed-coordinate target outputs

### Added
- Added combined target outputs for target sets that intentionally mix standard and alternative coordinate references, such as `s:83` plus `k:126`.
- Added `_target_summary_by_mode_combined.csv`, `_target_hits_combined.csv`, `_target_summary_by_coord_combined.csv`, and `_target_matrix_combined.csv`.
- Added a Run Analysis option: **Combined target outputs (allow mixed s/k/v targets)**.

### Changed
- Target detection now uses exact code-qualified references (`target_ref`) rather than bare numeric `coord_id` values.
- Per-coordinate-set target outputs now avoid conflating the same numeric `coord_id` across `s`, `k`, and `v`.

## v1.1.2 - Code-qualified target coordinates

### Changed
- Target coordinates are now stored as code-qualified references such as `s:81`, `k:128`, and `v:81`.
- The same numeric `coord_id` in different coordinate sets is no longer conflated during target tracking.
- Target hits, long PED tables, coordinate summaries, and target matrices now include a `target_ref` field.
- Target matrix column names now include the coordinate-set code, e.g. `coord_s_81` and `coord_v_81`.
- Documentation was updated to clarify that `v` means ALTERNATIVE2, not necessarily an extension of `k`.

## v1.1.1 - UI and metadata refinements

### Changed
- Renamed the Coordinate Browser `Code` selector to `Coordinate set` for clarity.
- Displayed coordinate-set choices as `s - standard`, `k - alternative`, and `v - alternative2`.
- Set the Coordinate Browser default filters to `s - standard` and `STRE - Stretching`.
- Reordered Coordinate Browser dropdowns so the recommended defaults appear first.
- Changed the default target set name from `metal_ligand_stretch` to the generic `target_coordinates`.
- Made metal-ligand stretch auto-detection an explicit optional helper rather than an implied default workflow.
- Added clearer documentation for `target_set_name` as a user-defined output label.

### Documentation
- Updated README and manuals to describe the software as a general PED-analysis tool.
- Clarified that metal-ligand stretch detection is optional and intended as a convenience for coordination-complex analyses.

## v1.1.0 - Target Coordinate Tracking

### Added
- Added Coordinate Browser for DD2 internal coordinates.
- Added target coordinate tracking workflow for selected internal coordinates.
- Added optional automatic metal-ligand stretch detection.
- Added long-format PED table export.
- Added target hits export.
- Added target summary by mode export.
- Added target summary by coordinate export.
- Added target matrix export.
- Added output folder selection.
- Added English and Japanese user manuals.
- Added optional export for alternative `k` / `v` coordinate-set interpretations.

### Changed
- Integrated the target-coordinate workflow into `veda_ped_analyzer.py`.
- Alternative coordinate-set outputs are disabled by default and can be enabled from the Run Analysis tab.
- Configuration JSON stores target settings, output options, PED thresholds, and frequency range.

## v1.0.0

- Initial public release.
- Parse VEDA PED output (`.ved`, `.dd2`) and export CSV tables.
- Support QC output parsing for ORCA (`.out`) and Gaussian (`.log` / `.out`).
- Rename `intensity` column to `IR_intensity` for clarity.
