# Changelog

## v1.1.0 - Target Coordinate Tracking

### Added
- Added a Coordinate Browser tab for viewing and filtering DD2 internal coordinates.
- Added target coordinate tracking for selected internal coordinates.
- Added automatic metal-ligand stretch detection based on atom indices/elements and `STRE` coordinates.
- Added long-format PED table export (`*_PED_terms_long_*.csv`).
- Added target hits export (`*_target_hits_*.csv`).
- Added target summary by mode export (`*_target_summary_by_mode_*.csv`).
- Added target summary by coordinate export (`*_target_summary_by_coord_*.csv`).
- Added target matrix export (`*_target_matrix_*.csv`) for spreadsheet heatmaps.
- Added output folder selection in the GUI.
- Added GUI option to include or exclude `alternative_k` / `alternative_v` coordinate-set outputs.
- Added program version information in the GUI and precheck summary.
- Added English and Japanese standalone manuals.
- Added repository URL metadata for GitHub publication.

### Changed
- Integrated target-coordinate tracking into the main `veda_ped_analyzer.py` program.
- Alternative coordinate-set outputs are now optional and disabled by default.
- JSON settings now store target definitions, output options, PED thresholds, and frequency range.
- README files were updated to describe the target-tracking workflow and new CSV outputs.

### Notes
- The standard top-N PED table workflow is retained for backward-compatible mode-centered inspection.
- The long-format and target-summary outputs are recommended when important internal coordinates appear below the top-N cutoff.

## v1.0.0
- Initial public release.
- Parse VEDA PED output (`.ved`, `.dd2`) and export CSV tables.
- Support QC output parsing for ORCA (`.out`) and Gaussian (`.log` / `.out`).
- Rename `intensity` column to `IR_intensity` for clarity.
