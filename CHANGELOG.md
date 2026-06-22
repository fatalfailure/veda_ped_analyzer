# Changelog

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
