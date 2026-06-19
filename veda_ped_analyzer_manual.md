# veda_ped_analyzer User Manual

Current version: **v1.1.0 - Target Coordinate Tracking**

## Repository

GitHub: https://github.com/fatalfailure/veda_ped_analyzer

## 1. Purpose

`veda_ped_analyzer.py` is a GUI tool for analyzing VEDA PED (Potential Energy Distribution) results and tracking **which vibrational modes contain selected internal coordinates**.

The tool is especially useful for coordination complexes where a metal-ligand stretching coordinate does not appear as a single isolated normal mode, but is instead distributed across many modes in the fingerprint region.

The original mode-centered PED table is retained. Version 1.1.0 adds coordinate-centered target tracking, allowing selected internal coordinates to be followed across all modes, even when they are below the usual top-N PED cutoff.

---

## 2. Required input files

| File | Required | Description |
|---|---:|---|
| `.ved` | Yes | VEDA output containing the PED matrix |
| `.dd2` | Yes | VEDA internal-coordinate definition file |
| `.fmu` | Recommended | Atom-index to element-symbol mapping |
| `.out` or `.log` | Yes | ORCA or Gaussian vibrational analysis output |

If `.fmu` is not available, the program attempts to infer atom labels from the QC output geometry block. For metal-ligand tracking, providing `.fmu` is recommended.

---

## 3. Starting the program

Run:

```bash
python veda_ped_analyzer.py
```

The GUI will open.

---

## 4. GUI tabs

| Tab | Role |
|---|---|
| Files / Precheck | Select input files and check whether parsing is possible |
| Coordinate Browser | View, filter, and select DD2 internal coordinates |
| Target Definition | Define the internal coordinates to track |
| Run Analysis | Set output options, PED thresholds, frequency range, and run analysis |
| Results Preview | Quick preview of important output tables |
| User Guide | Built-in help |

---

## 5. Basic workflow

### Step 1. Select files

In `Files / Precheck`, select:

1. `.ved`
2. `.dd2`
3. optional `.fmu`
4. QC output (`.out` / `.log`)
5. optional output folder

When a `.ved` file is selected, files with the same stem and extensions `.dd2`, `.fmu`, `.out`, or `.log` are automatically suggested if present in the same folder.

If no output folder is selected, CSV files are written to the same folder as the `.ved` file.

### Step 2. Run precheck

Press:

```text
Load / Precheck
```

The program checks:

- whether the VEDA PED matrix can be read
- whether DD2 internal coordinates can be parsed
- whether an atom map can be built from `.fmu` or QC output
- whether ORCA or Gaussian frequencies and IR intensities can be parsed
- whether VEDA modes and QC modes can be matched by frequency
- which PED blocks and coordinate codes are available

Important precheck values:

```text
Mode mapping matched
Max abs freq diff
Detected coordinate sets
Atom map entries
```

If `Max abs freq diff` is large, the VEDA file and QC output may not correspond to the same calculation.

---

## 6. Coordinate Browser

The `Coordinate Browser` tab lists internal coordinates read from the DD2 file.

Main columns:

| Column | Meaning |
|---|---|
| `coord_id` | DD2 internal coordinate ID |
| `code` | Coordinate interpretation code, e.g. `s`, `k`, `v` |
| `group` | Coordinate type, e.g. `STRE`, `BEND`, `TORS` |
| `atoms` | Atom indices involved in the coordinate |
| `atom_label` | Atom labels with element symbols |
| `label` | Simplified label, e.g. `str(Co1-N14)` |
| `raw_label` | Raw label from DD2/VEDA |

### Useful filters

| Filter | Example | Use |
|---|---|---|
| Code | `s` | Show only standard coordinates |
| Group | `STRE` | Show only stretching coordinates |
| Contains atom index | `1` | Show coordinates containing a specific metal atom index |
| Contains element | `Co` | Show coordinates containing Co |
| Label contains | `Co-N` | Search by text label |

For metal-ligand stretches, start with:

```text
Group = STRE
Contains atom index = metal atom index
```

Then select the desired rows and press `Add selected to target`.

---

## 7. Target Definition

A target is a set of internal coordinates to track across vibrational modes.

For example, to track Co-N stretching in a cobalt complex, register all Co-N stretching `coord_id` values as one target set.

### Method A: manual selection

1. Open `Coordinate Browser`.
2. Select the desired internal-coordinate rows.
3. Press `Add selected to target`.
4. The IDs are added to the `Target coord_id list`.

### Method B: automatic metal-ligand stretch detection

In `Target Definition`, set:

| Field | Example | Meaning |
|---|---|---|
| Target set name | `Co-N_stretch` | Name written to output CSV files |
| Metal atom index/indices | `1` | Metal atom index or indices |
| Ligand atom indices | `14 15 16 17` | Optional restriction by atom index |
| Ligand elements | `N O S Cl` | Optional restriction by element |

Then press:

```text
Replace by auto-detect
```

or:

```text
Auto-detect metal-ligand stretches
```

Automatic detection primarily selects DD2 coordinates satisfying:

```text
coord_group starts with STRE
number of atoms is 2
one atom is a metal atom
the other atom is a ligand atom
```

For coordination-complex analysis, explicitly specifying the metal atom index is recommended.

---

## 8. Run Analysis settings

### Output options

| Option | Recommended | Description |
|---|---:|---|
| Standard top-N PED table | ON | Original mode-centered PED table |
| Long PED table | ON | Long-format table containing all PED contributors above threshold |
| Target hits | ON | Modes where target coordinates are detected |
| Target summary by mode | ON | Mode-centered total target PED summary |
| Target summary by coordinate | ON | Coordinate-centered summary |
| Target matrix | ON | Mode × target-coordinate matrix |
| Include alternative coordinate sets (k/v) | Usually OFF | Also export `alternative_k` / `alternative_v` coordinate interpretations |
| Include target modes below total threshold | As needed | Keep target modes even if total target PED is below threshold |

Normally, keep `Include alternative coordinate sets (k/v)` OFF. Turn it ON only when you need to inspect alternative VEDA/DD2 internal-coordinate interpretations.

### Thresholds and frequency range

| Field | Example | Meaning |
|---|---:|---|
| Top N in standard table | `6` or `10` | Number of top PED terms in the standard table |
| Standard table min PED (%) | `0.1` | Minimum PED shown in the standard table |
| Long table min PED (%) | `0.1` | Minimum PED saved in long table |
| Target hit min PED (%) | `0.1` | Minimum PED counted as a target hit |
| Target total min PED per mode (%) | `1.0` | Minimum total target PED retained in summary by mode |
| Freq min (cm^-1) | `200` | Lower frequency limit |
| Freq max (cm^-1) | `800` | Upper frequency limit |

For metal-ligand stretches in the fingerprint region, a useful starting point is:

```text
Freq min = 200
Freq max = 800
Target hit min PED = 0.1
Target total min PED per mode = 1.0
```

---

## 9. Running the analysis

Press:

```text
RUN TARGET ANALYSIS
```

When complete, the program lists the saved CSV files. A preview of key results is shown in the `Results Preview` tab.

---

## 10. Output files

The output file names are based on the input `.ved` file stem.

### 10.1 Standard PED table

```text
sample_PED_table_standard.csv
```

The following files are generated only if `Include alternative coordinate sets (k/v)` is enabled:

```text
sample_PED_table_alternative_k.csv
sample_PED_table_alternative_v.csv
```

This is the original-style table. Each vibrational mode is listed with the top-N PED contributors.

Main columns:

| Column | Meaning |
|---|---|
| `mode_veda` | VEDA mode number |
| `mode_qc` | ORCA/Gaussian mode number |
| `freq_veda` | VEDA frequency |
| `freq_qc` | QC output frequency |
| `IR_intensity` | IR intensity from ORCA/Gaussian |
| `PED1_label`, `PED1_val` | Largest PED contributor |
| `PED2_label`, `PED2_val` | Second contributor |
| `total_target_PED` | Total PED from selected target coordinates |
| `top_target_terms` | Main target-coordinate terms in the mode |

### 10.2 Long PED table

```text
sample_PED_terms_long_standard.csv
```

This file stores PED contributors in long format: one row per mode-coordinate contribution.

Main columns:

| Column | Meaning |
|---|---|
| `mode_veda` | VEDA mode |
| `mode_qc` | QC mode |
| `freq_qc` | QC frequency |
| `PED_rank` | Rank within the mode |
| `PED_value` | PED contribution |
| `coord_id` | DD2 internal coordinate ID |
| `coord_code` | Coordinate code |
| `coord_group` | STRE/BEND/TORS etc. |
| `atom_label` | Atom label with element symbols |
| `label` | Internal-coordinate label |
| `is_target` | Whether this coordinate is part of the target set |

This table is important when an internal coordinate is hidden below the standard top-N cutoff.

### 10.3 Target hits

```text
sample_target_hits_standard.csv
```

Lists every detected target coordinate in each mode.

Main columns:

| Column | Meaning |
|---|---|
| `target_set_name` | Target name |
| `coord_id` | Target internal coordinate ID |
| `label` | Internal-coordinate label |
| `mode_qc` | QC mode |
| `freq_qc` | QC frequency |
| `PED_value` | PED contribution of the target coordinate |
| `PED_rank` | Rank within that mode |
| `IR_intensity` | IR intensity |

Use this table to find which modes contain a specific coordinate, such as a given Co-N stretch.

### 10.4 Target summary by mode

```text
sample_target_summary_by_mode_standard.csv
```

This is often the most important output for split metal-ligand stretches.

Each row summarizes a vibrational mode by adding the PED contributions from all target coordinates.

Main columns:

| Column | Meaning |
|---|---|
| `mode_qc` | QC mode |
| `freq_qc` | QC frequency |
| `IR_intensity` | IR intensity |
| `total_target_PED` | Sum of PED contributions from the target coordinate set |
| `max_target_PED` | Maximum individual target-coordinate PED in the mode |
| `n_target_coords_detected` | Number of target coordinates detected in the mode |
| `best_target_rank` | Best rank among target coordinates in that mode |
| `top_target_terms` | Main target-coordinate contributions |

Start by checking modes with large `total_target_PED`.

### 10.5 Target summary by coordinate

```text
sample_target_summary_by_coord_standard.csv
```

This summarizes results for each target internal coordinate.

Main columns:

| Column | Meaning |
|---|---|
| `coord_id` | Internal coordinate ID |
| `label` | Internal-coordinate label |
| `max_PED` | Maximum PED value for this coordinate |
| `mode_qc_at_max` | QC mode where this coordinate has maximum PED |
| `mode_veda_at_max` | VEDA mode where this coordinate has maximum PED |
| `freq_qc_at_max` | QC frequency at maximum PED |
| `freq_veda_at_max` | VEDA frequency at maximum PED |
| `sum_PED_in_range` | Sum of PED contributions within the selected frequency range |
| `weighted_mean_freq` | PED-weighted mean frequency |
| `n_modes_detected` | Number of modes where this coordinate was detected |
| `top_modes` | Main modes containing this coordinate |

### 10.6 Target matrix

```text
sample_target_matrix_standard.csv
```

Rows are vibrational modes and columns are target coordinate IDs. Values are PED percentages. This format is convenient for Excel or pandas heatmaps.

### 10.7 Coordinates lookup

```text
sample_coordinates_lookup.csv
```

A lookup table of DD2 internal coordinates.

---

## 11. Results Preview

The `Results Preview` tab displays three tables:

| Table | Use |
|---|---|
| Summary by mode | Find modes with large total target PED |
| Target hits | Inspect individual target-coordinate appearances |
| Summary by coordinate | See how each coordinate is distributed over modes |

The first table to inspect is usually `Summary by mode`. Important columns are:

```text
total_target_PED
freq_qc
IR_intensity
top_target_terms
```

Modes with large `total_target_PED` and large `IR_intensity` are often useful candidates for vibrational assignment.

---

## 12. Recommended workflow for metal-ligand stretching

Example: find Co-N stretching modes between 200 and 800 cm^-1.

1. Select files in `Files / Precheck`.
2. Press `Load / Precheck`.
3. In `Coordinate Browser`, filter:

```text
Group = STRE
Contains atom index = Co atom index
```

4. Select Co-N coordinates and press `Add selected to target`.
5. Set the target name, e.g.:

```text
Co-N_stretch
```

6. In `Run Analysis`, set:

```text
Freq min = 200
Freq max = 800
Target hit min PED = 0.1
Target total min PED per mode = 1.0
```

7. Press `RUN TARGET ANALYSIS`.
8. Open `target_summary_by_mode` and inspect modes with large `total_target_PED`.
9. Use `target_hits` and `PED_terms_long` for detailed inspection.

---

## 13. Settings JSON and log files

The program stores previous GUI settings in:

```text
veda_ped_analyzer.json
```

If the program directory is not writable, the JSON file is saved in the user's home directory.

The log file is normally:

```text
veda_ped_analyzer.log
```

or the same file name in the user's home directory.

The JSON file stores items such as:

- previous file paths
- output folder
- target name
- metal atom indices
- ligand atom indices/elements
- target coordinate ID list
- PED thresholds
- frequency range
- output options

Local `.json` and `.log` files should normally not be committed to Git.

---

## 14. Common problems

### Coordinate Browser is empty

Check:

- whether `.dd2` was selected correctly
- whether `Load / Precheck` was run
- whether the DD2 format is compatible with the parser

### Element symbols are missing

The atom map may not have been built. Try:

- selecting `.fmu` explicitly
- checking that the QC output contains a geometry block
- checking `Atom map entries` in the precheck summary

### Target auto-detection returns no coordinates

Check:

- whether the metal atom index is correct
- whether ligand elements are correct
- whether the DD2 coordinates are labeled as `STRE`
- whether atom indices match the FMU/QC geometry atom order

### Target summary by mode is empty

Check:

- whether the target coordinate ID list is empty
- whether `Target total min PED per mode (%)` is too high
- whether the frequency range is too narrow
- try enabling `Include target modes below total threshold`

### VEDA/QC mode mapping looks suspicious

Check `Max abs freq diff` in the precheck summary. Large differences may indicate:

- mismatched VEDA and QC files
- different treatment of imaginary or low-frequency modes
- different numbers of modes
- accidentally selecting the wrong QC output file

---

## 15. How to read `target_summary_by_coord` and `top_modes`

`target_summary_by_coord` is a coordinate-centered CSV. For each selected target coordinate, it summarizes where that coordinate appears across vibrational modes.

### 15.1 Main columns

| Column | Meaning |
|---|---|
| `mode_veda_at_max` | VEDA mode where this coordinate has the largest PED contribution |
| `freq_qc_at_max` | QC frequency of the maximum-PED mode, in cm^-1 |
| `freq_veda_at_max` | VEDA frequency of the maximum-PED mode, in cm^-1 |
| `sum_PED_in_range` | Sum of PED contributions for this coordinate within the selected frequency range |
| `weighted_mean_freq` | PED-weighted mean frequency |
| `n_modes_detected` | Number of detected modes above the target-hit threshold |
| `top_modes` | Main modes containing this coordinate, sorted by PED contribution |

`weighted_mean_freq` is conceptually:

```text
weighted_mean_freq = Σ(freq × PED) / Σ(PED)
```

It indicates the frequency center of gravity for that internal coordinate.

### 15.2 Format of `top_modes`

Example:

```text
QC107/V271@594.0:15.1% (rank 1)
```

This means:

| Part | Meaning |
|---|---|
| `QC107` | QC output mode 107 |
| `V271` | VEDA mode 271 |
| `@594.0` | QC frequency 594.0 cm^-1 |
| `15.1%` | PED contribution of this internal coordinate |
| `rank 1` | This coordinate is the largest PED contributor in that mode |

Thus, this entry means that in QC mode 107 / VEDA mode 271 at 594.0 cm^-1, the target coordinate contributes 15.1% and is the largest PED contributor in that mode.

### 15.3 Example interpretation

If `top_modes` contains:

```text
QC107/V271@594.0:15.1% (rank 1);
QC113/V265@635.8:12.9% (rank 1);
QC116/V262@743.5:6.2% (rank 4);
QC15/V363@72.6:5.5% (rank 5);
QC91/V287@480.3:3.5% (rank 10)
```

then the coordinate appears most strongly near:

```text
594.0 cm^-1: 15.1%
635.8 cm^-1: 12.9%
743.5 cm^-1: 6.2%
```

The coordinate also appears as smaller mixed components at lower or intermediate frequencies. The `rank 10` entry would not appear in a conventional top-6 PED table, but it is captured by target tracking.

When interpreting `top_modes`, consider:

1. PED value
2. rank within the mode
3. IR intensity
4. whether the frequency region is chemically reasonable

---

## 16. Recommended starting settings

For metal-ligand stretching searches:

```text
Top N in standard table = 6 or 10
Standard table min PED (%) = 0.1
Long table min PED (%) = 0.1
Target hit min PED (%) = 0.1
Target total min PED per mode (%) = 1.0
Freq min = 200
Freq max = 800
```

If too many results appear:

```text
Target hit min PED (%) = 0.5
Target total min PED per mode (%) = 2.0
```

If too few results appear:

```text
Target total min PED per mode (%) = 0.3
Include target modes below total threshold = ON
```

---

## 17. Minimal workflow

1. Select files in `Files / Precheck`.
2. Run `Load / Precheck`.
3. Filter `STRE` coordinates by metal atom index in `Coordinate Browser`.
4. Add M-L stretching coordinates to the target list.
5. Set frequency range in `Run Analysis`.
6. Run analysis.
7. Open `target_summary_by_mode` and inspect modes with large `total_target_PED`.
