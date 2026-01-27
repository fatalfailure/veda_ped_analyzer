#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
veda_ped_analyzer (public release v17)

Purpose
- Combine the PED (Potential Energy Distribution) matrix from a VEDA .ved file with
  internal-coordinate definitions from DD2 + (FMU or ORCA geometry).
- Export the top PED contributors (internal coordinate ID / simplified label / contribution %)
  for each vibrational mode to CSV.
- Parse an QC output file (required) to obtain ORCA frequencies / irreps / IR intensities and
  map ORCA modes to VEDA modes using a frequency-based 1:1 ordered alignment.

Robustness notes (v9 changes)
- VEDA frequency extraction is stricter and section-aware (avoids "random numbers" in headers).
- PED-column ↔ dd2 mapping uses VEDA's own column IDs (when present in the PED header rows),
  so we do NOT assume "matrix column position == dd2 coord_id".
- Log/config writing no longer fails silently: if the primary path is not writable, the program
  automatically falls back to alternate locations and reports failures.
- Auto-fill "not found" messages are INFO-level (not CAUTION) to reduce log noise.

GUI features
- Selecting a .ved file auto-fills same-stem .dd2/.fmu/.out files in the same folder (if present).
- File selections are saved to JSON and restored on the next launch.
- Two-tab UI: Analysis / User Guide.
"""

from __future__ import annotations

import os
import re
import sys
import json
import math
import traceback
import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

import pandas as pd

import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import scrolledtext
from tkinter import ttk


# ------------------------------------------------------------
# Common: logging / config
# ------------------------------------------------------------

APP_NAME = "veda_ped_analyzer"

try:
    BASE_PATH = Path(__file__).resolve()
except Exception:
    # Extremely defensive fallback (should not happen in normal use)
    BASE_PATH = Path.cwd() / APP_NAME

LOG_PATHS = [
    BASE_PATH.with_suffix(".log"),
    Path.home() / f"{APP_NAME}.log",
]
CONFIG_PATHS = [
    BASE_PATH.with_suffix(".json"),
    Path.home() / f"{APP_NAME}.json",
]

# Selected paths (will be set lazily, and can change if a fallback is needed).
LOG_PATH: Optional[Path] = None
CONFIG_PATH: Optional[Path] = None


def _first_writable_path(candidates: List[Path], default_name: str) -> Path:
    """
    Choose the first path that can be opened for append.
    """
    for p in candidates:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8"):
                pass
            return p
        except Exception:
            continue
    return Path(default_name)


def _ensure_log_path() -> Path:
    global LOG_PATH
    if LOG_PATH is None:
        LOG_PATH = _first_writable_path(LOG_PATHS, f"{APP_NAME}.log")
    return LOG_PATH


def _write_log_text(text: str) -> None:
    """
    Write to the log file. If the current LOG_PATH is unwritable, automatically fall back to
    other candidates. Never fail silently.
    """
    global LOG_PATH
    # Prefer current LOG_PATH first, then other candidates.
    candidates: List[Path] = []
    if LOG_PATH is not None:
        candidates.append(LOG_PATH)
    for p in LOG_PATHS:
        if p not in candidates:
            candidates.append(p)

    last_exc: Optional[Exception] = None
    for p in candidates:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as f:
                f.write(text)
            LOG_PATH = p
            return
        except Exception as e:
            last_exc = e
            continue

    # Final fallback: stderr (in .pyw the user may not see it, but it's still not silent)
    print(f"[{APP_NAME}] LOG WRITE FAILED: {last_exc}", file=sys.stderr)


def log_message(msg: str) -> None:
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    line = f"[{ts}] {msg}\n"
    # Console print is useful when run as .py; harmless otherwise.
    print(line.rstrip("\n"))
    _ensure_log_path()
    _write_log_text(line)


def log_caution(msg: str) -> None:
    log_message(f"CAUTION: {msg}")


def log_error(context: str, exc: Exception) -> None:
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    block = (
        "=== ERROR ===\n"
        f"Time   : {ts}\n"
        f"Context: {context}\n"
        f"{tb}\n"
    )
    print(block, file=sys.stderr)
    _ensure_log_path()
    _write_log_text(block)


def load_config() -> dict:
    """Load the settings JSON from the first existing candidate path."""
    global CONFIG_PATH
    for p in CONFIG_PATHS:
        if not p.is_file():
            continue
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
            CONFIG_PATH = p
            return cfg if isinstance(cfg, dict) else {}
        except Exception as e:
            log_caution(f"Failed to load config JSON ({p}): {e}")
            log_error("load_config", e)
            continue
    return {}


def save_config(cfg: dict) -> None:
    """
    Save settings JSON. If the primary path is not writable, fall back to alternate locations.
    Never fail silently.
    """
    global CONFIG_PATH
    payload = json.dumps(cfg, ensure_ascii=False, indent=2)

    candidates: List[Path] = []
    if CONFIG_PATH is not None:
        candidates.append(CONFIG_PATH)
    for p in CONFIG_PATHS:
        if p not in candidates:
            candidates.append(p)

    last_exc: Optional[Exception] = None
    for p in candidates:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(payload, encoding="utf-8")
            CONFIG_PATH = p
            return
        except Exception as e:
            last_exc = e
            log_caution(f"Failed to save config JSON ({p}): {e}")
            log_error("save_config", e)

    log_caution(f"Failed to save config JSON anywhere. Last error: {last_exc}")


# ------------------------------------------------------------
# Numeric parsing (tolerant of formatting variations)
# ------------------------------------------------------------

def safe_float(x) -> float:
    """
    A bit more robust than float():
    - Treat Fortran 'D' exponent as 'E'
    - Lightly strip surrounding commas/semicolons/brackets
    """
    if x is None:
        raise ValueError("safe_float(None)")
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    s = s.strip().strip(",;")
    s = s.strip("()[]{}")
    s = s.replace("D", "E").replace("d", "e")
    return float(s)


# ------------------------------------------------------------
# Element helpers
# ------------------------------------------------------------

Z_TO_EL = {
    1: "H", 2: "He", 3: "Li", 4: "Be", 5: "B", 6: "C", 7: "N", 8: "O", 9: "F",
    10: "Ne", 11: "Na", 12: "Mg", 13: "Al", 14: "Si", 15: "P", 16: "S", 17: "Cl", 18: "Ar",
    19: "K", 20: "Ca", 21: "Sc", 22: "Ti", 23: "V", 24: "Cr", 25: "Mn", 26: "Fe", 27: "Co", 28: "Ni",
    29: "Cu", 30: "Zn", 31: "Ga", 32: "Ge", 33: "As", 34: "Se", 35: "Br", 36: "Kr",
    37: "Rb", 38: "Sr", 39: "Y", 40: "Zr", 41: "Nb", 42: "Mo", 43: "Tc", 44: "Ru", 45: "Rh", 46: "Pd",
    47: "Ag", 48: "Cd", 49: "In", 50: "Sn", 51: "Sb", 52: "Te", 53: "I", 54: "Xe",
    55: "Cs", 56: "Ba", 57: "La", 58: "Ce", 59: "Pr", 60: "Nd", 61: "Pm", 62: "Sm", 63: "Eu", 64: "Gd",
    65: "Tb", 66: "Dy", 67: "Ho", 68: "Er", 69: "Tm", 70: "Yb", 71: "Lu", 72: "Hf", 73: "Ta", 74: "W",
    75: "Re", 76: "Os", 77: "Ir", 78: "Pt", 79: "Au", 80: "Hg", 81: "Tl", 82: "Pb", 83: "Bi",
    84: "Po", 85: "At", 86: "Rn", 87: "Fr", 88: "Ra", 89: "Ac", 90: "Th", 91: "Pa", 92: "U"
}


def parse_atom_map_from_fmu(text_or_path: str) -> Dict[int, str]:
    """Build atomic-index → element-symbol map from an .fmu file."""
    try:
        if os.path.isfile(str(text_or_path)):
            text = Path(text_or_path).read_text(encoding="utf-8", errors="replace")
        else:
            text = str(text_or_path)
    except Exception as e:
        log_caution(f"Failed to read FMU: {text_or_path}")
        log_error("parse_atom_map_from_fmu", e)
        return {}

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return {}

    # Format (1): simple format (first token is atom count)
    if re.fullmatch(r"\d+", lines[0]):
        try:
            n = int(lines[0])
        except Exception:
            n = 0
        nums: List[int] = []
        for ln in lines[1:]:
            for tok in ln.split():
                if re.fullmatch(r"\d+", tok):
                    nums.append(int(tok))
        if n > 0 and len(nums) >= n:
            atom_map: Dict[int, str] = {}
            for i in range(1, n + 1):
                z = nums[i - 1]
                atom_map[i] = Z_TO_EL.get(z, f"Z{z}")
            return atom_map

    # Format (2): "Atomic numbers" block format
    atom_map: Dict[int, str] = {}
    in_atomic = False
    idx = 1
    for ln in lines:
        if re.search(r"Atomic numbers", ln, re.IGNORECASE):
            in_atomic = True
            continue
        if in_atomic:
            # Stop when the next section begins
            if re.match(r"^[A-Za-z].*:", ln) and not re.search(r"Atomic numbers", ln, re.IGNORECASE):
                break
            for tok in ln.split():
                if re.fullmatch(r"\d+", tok):
                    z = int(tok)
                    atom_map[idx] = Z_TO_EL.get(z, f"Z{z}")
                    idx += 1
    return atom_map




def parse_atom_map_from_orca_out(out_text: str) -> Dict[int, str]:
    """
    Build atomic-index → element-symbol map from an QC output file.

    We read the first "CARTESIAN COORDINATES (ANGSTROEM)" block (preferred),
    falling back to "CARTESIAN COORDINATES (A.U.)" if needed.

    Returns:
        {1: "C", 2: "H", ...} (1-based indices, as used by VEDA .dd2 atom lists)
    """
    if not out_text:
        return {}

    lines = out_text.splitlines()

    def _scan_block(header: str) -> Dict[int, str]:
        for i, ln in enumerate(lines):
            if ln.strip().upper() == header:
                j = i + 1
                while j < len(lines) and (not lines[j].strip() or set(lines[j].strip()) <= set("-")):
                    j += 1
                atom_map: Dict[int, str] = {}
                idx2 = 1
                while j < len(lines):
                    s = lines[j].strip()
                    if not s:
                        break
                    parts = s.split()
                    if len(parts) < 4:
                        break
                    el = parts[0]
                    if not re.fullmatch(r"[A-Za-z]{1,3}", el):
                        break
                    atom_map[idx2] = el.capitalize()
                    idx2 += 1
                    j += 1
                return atom_map
        return {}

    amap = _scan_block("CARTESIAN COORDINATES (ANGSTROEM)")
    if amap:
        return amap
    return _scan_block("CARTESIAN COORDINATES (A.U.)")





# ------------------------------------------------------------
# Gaussian (.out/.log) parser (Freq job)
# ------------------------------------------------------------

# Minimal periodic table (atomic number -> symbol) for labeling.
# (Extend if you expect elements beyond this range.)
_PERIODIC_TABLE = {
    1: "H", 2: "He", 3: "Li", 4: "Be", 5: "B", 6: "C", 7: "N", 8: "O", 9: "F", 10: "Ne",
    11: "Na", 12: "Mg", 13: "Al", 14: "Si", 15: "P", 16: "S", 17: "Cl", 18: "Ar",
    19: "K", 20: "Ca", 21: "Sc", 22: "Ti", 23: "V", 24: "Cr", 25: "Mn", 26: "Fe",
    27: "Co", 28: "Ni", 29: "Cu", 30: "Zn", 31: "Ga", 32: "Ge", 33: "As", 34: "Se",
    35: "Br", 36: "Kr", 37: "Rb", 38: "Sr", 39: "Y", 40: "Zr", 41: "Nb", 42: "Mo",
    43: "Tc", 44: "Ru", 45: "Rh", 46: "Pd", 47: "Ag", 48: "Cd", 49: "In", 50: "Sn",
    51: "Sb", 52: "Te", 53: "I", 54: "Xe", 55: "Cs", 56: "Ba", 57: "La", 58: "Ce",
    59: "Pr", 60: "Nd", 61: "Pm", 62: "Sm", 63: "Eu", 64: "Gd", 65: "Tb", 66: "Dy",
    67: "Ho", 68: "Er", 69: "Tm", 70: "Yb", 71: "Lu", 72: "Hf", 73: "Ta", 74: "W",
    75: "Re", 76: "Os", 77: "Ir", 78: "Pt", 79: "Au", 80: "Hg", 81: "Tl", 82: "Pb",
    83: "Bi", 84: "Po", 85: "At", 86: "Rn",
}


def is_gaussian_output(out_text: str) -> bool:
    """Heuristic detection for Gaussian outputs."""
    if not out_text:
        return False
    head = out_text[:6000]
    # Common markers
    if "Entering Gaussian System" in head:
        return True
    if "Gaussian, Inc." in head:
        return True
    # Some outputs omit banner; still, Normal termination is distinctive.
    if "Normal termination of Gaussian" in out_text:
        return True
    return False


def parse_atom_map_from_gaussian_out(out_text: str) -> Dict[int, str]:
    """
    Build atomic-index -> element-symbol map from Gaussian geometry tables.

    Preference:
      Standard orientation
    Fallback:
      Input orientation

    Returns {1:"C",2:"H",...} (1-based).
    """
    if not out_text:
        return {}

    # Find last occurrence (final geometry is typically the last table)
    starts = [m.start() for m in re.finditer(r"\n\s*Standard orientation:\s*\n", out_text)]
    if not starts:
        starts = [m.start() for m in re.finditer(r"\n\s*Input orientation:\s*\n", out_text)]
    if not starts:
        return {}

    chunk = out_text[starts[-1]:]
    lines = chunk.splitlines()

    # Table is delimited by dashed lines.
    dash = [i for i, ln in enumerate(lines[:200]) if re.match(r"\s*-{5,}\s*$", ln)]
    if len(dash) < 2:
        return {}

    i0 = dash[1] + 1
    atom_map: Dict[int, str] = {}
    for ln in lines[i0:]:
        if re.match(r"\s*-{5,}\s*$", ln):
            break
        # Center  Atomic  Atomic              Coordinates (Angstroms)
        # Number  Number   Type              X           Y           Z
        m = re.match(
            r"\s*(\d+)\s+(\d+)\s+(\d+)\s+([-0-9.]+)\s+([-0-9.]+)\s+([-0-9.]+)",
            ln,
        )
        if not m:
            continue
        idx = int(m.group(1))
        z = int(m.group(2))
        atom_map[idx] = _PERIODIC_TABLE.get(z, f"Z{z}")
    return atom_map


def parse_gaussian_out_data(out_text: str) -> Tuple[Dict[int, dict], Dict[int, float]]:
    """
    Parse from a Gaussian .out/.log file:
    - Frequencies (mode -> freq, irrep) from repeated blocks containing "Frequencies --"
    - IR intensities (mode -> IR Inten) from the corresponding "IR Inten --" line

    Gaussian prints 3 modes per block. We assemble mode-indexed dicts.

    Note:
    - Gaussian logs may contain multiple frequency jobs (Link1, restarts).
      We select the last coherent run (mode numbering that increases, with resets starting a new run).
    """
    lines = out_text.splitlines()

    blocks = []  # list of (modes, irreps, freqs, intens)
    i = 0
    while i < len(lines):
        if "Frequencies --" in lines[i]:
            # Search backward for the mode-number line (e.g., "  1  2  3")
            mode_line = None
            irrep_line = ""
            for back in range(1, 8):
                if i - back < 0:
                    break
                if re.match(r"\s*\d+\s+\d+\s+\d+\s*$", lines[i - back]):
                    mode_line = lines[i - back]
                    irrep_line = lines[i - back + 1] if (i - back + 1) < len(lines) else ""
                    break

            # Search forward for IR Inten line
            inten_line = None
            for fwd in range(1, 12):
                if i + fwd >= len(lines):
                    break
                if "IR Inten" in lines[i + fwd]:
                    inten_line = lines[i + fwd]
                    break

            if mode_line:
                modes = [int(x) for x in mode_line.split()]
                irreps = irrep_line.split()
                while len(irreps) < len(modes):
                    irreps.append("")

                freqs = []
                try:
                    freqs = [float(x) for x in lines[i].split("--", 1)[1].split()]
                except Exception:
                    freqs = []
                while len(freqs) < len(modes):
                    freqs.append(float("nan"))

                intens = []
                if inten_line:
                    try:
                        intens = [float(x) for x in inten_line.split("--", 1)[1].split()]
                    except Exception:
                        intens = []
                while len(intens) < len(modes):
                    intens.append(float("nan"))

                blocks.append((modes, irreps, freqs, intens))
        i += 1

    if not blocks:
        return {}, {}

    # Split into "runs" by mode reset/backwards.
    runs = []
    current = []
    last_mode = 0
    for b in blocks:
        modes = b[0]
        if current and (modes[0] <= last_mode or modes[0] == 1):
            runs.append(current)
            current = []
        current.append(b)
        last_mode = modes[-1]
    if current:
        runs.append(current)

    # Choose run that reaches highest mode number; tie-break: last.
    best = max(runs, key=lambda r: (r[-1][0][-1], runs.index(r)))

    freq_data: Dict[int, dict] = {}
    intensities: Dict[int, float] = {}
    for modes, irreps, freqs, intens in best:
        for m, ir, fr, it in zip(modes, irreps, freqs, intens):
            if fr == fr:  # not NaN
                freq_data[m] = {"freq": float(fr), "irrep": (ir or "").strip()}
            if it == it:
                intensities[m] = float(it)

    return freq_data, intensities


def parse_qchem_output(out_text: str) -> Tuple[str, Dict[int, dict], Dict[int, float], Dict[int, str]]:
    """
    Unified parser for quantum-chemistry vibrational outputs.

    Returns:
        engine, freq_data, intensities, atom_map

    engine: "ORCA" or "Gaussian"
    """
    if is_gaussian_output(out_text):
        freq_data, intensities = parse_gaussian_out_data(out_text)
        atom_map = parse_atom_map_from_gaussian_out(out_text)
        return "Gaussian", freq_data, intensities, atom_map

    # Default: ORCA
    freq_data, intensities = parse_orca_out_data(out_text)
    atom_map = parse_atom_map_from_orca_out(out_text)
    return "ORCA", freq_data, intensities, atom_map

# ------------------------------------------------------------
# DD2 parser and lookup CSV export
# ------------------------------------------------------------

def parse_dd2(dd2_path: str) -> dict:
    """Parse a VEDA .dd2 file."""
    try:
        text = Path(dd2_path).read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        log_caution(f"Failed to read dd2: {dd2_path}")
        log_error("parse_dd2", e)
        return {"coords": []}

    lines = [ln.rstrip("\n") for ln in text.splitlines()]

    coord_rows: List[dict] = []
    # Example: "s 1 1.0 STRE  3  8  ... "
    table_re = re.compile(
        r"^\s*([A-Za-z])\s+(\d+)\s+([+-]?\d+(?:\.\d+)?(?:[EeDd][+-]?\d+)?)\s+([A-Za-z0-9_]+)\s+(.*)$"
    )

    for ln in lines:
        m = table_re.match(ln)
        if not m:
            continue

        code = m.group(1)

        try:
            coord_id = int(m.group(2))
        except Exception as e:
            log_caution(f"dd2 parse: invalid coord_id line skipped: {ln.strip()}")
            log_error("parse_dd2 coord_id", e)
            continue

        try:
            weight = safe_float(m.group(3))
        except Exception as e:
            log_caution(f"dd2 parse: invalid weight line skipped: {ln.strip()}")
            log_error("parse_dd2 weight", e)
            continue

        group = m.group(4)
        rest = m.group(5).strip()

        toks = rest.split()
        atoms: List[int] = []
        i = 0
        while i < len(toks) and re.fullmatch(r"[+-]?\d+", toks[i]):
            try:
                atoms.append(int(toks[i]))
            except Exception:
                break
            i += 1

        if i >= len(toks):
            continue

        label = toks[i]
        i += 1

        pop = None
        if i < len(toks):
            try:
                pop = safe_float(toks[i])
                i += 1
            except Exception:
                pop = None

        terms: List[Tuple[str, float]] = []
        while i + 1 < len(toks):
            freq_tag = toks[i]
            val = toks[i + 1]
            i += 2
            try:
                pct = safe_float(val)
            except Exception:
                continue
            terms.append((freq_tag, pct))

        coord_rows.append({
            "coord_id": coord_id,
            "coord_code": code,
            "weight": weight,
            "coord_group": group,
            "atoms": atoms,
            "coord_label_raw": label,
            "population": pop,
            "terms": terms,
            "source_line": ln.strip(),
        })

    return {"coords": coord_rows}


def export_internal_coordinate_lookup_csv(dd2_path: str, out_csv_path: str, fmu_path: Optional[str] = None, atom_map: Optional[Dict[int, str]] = None) -> None:
    """
    Export an internal-coordinate lookup CSV.

    - If FMU is provided and readable, it is used for element labeling.
    - Otherwise, the caller may pass atom_map from QC output (ORCA/Gaussian).
    - If neither is available, the CSV is still generated but element labels may degrade.
    """
    try:
        dd2 = parse_dd2(dd2_path)
        coords = dd2.get("coords", []) or []
        if not coords:
            raise ValueError("dd2 coords empty")

        # Build atom map
        amap: Dict[int, str] = {}
        if atom_map:
            try:
                amap = dict(atom_map)
            except Exception:
                amap = {}
        if (not amap) and fmu_path:
            try:
                amap = parse_atom_map_from_fmu(fmu_path)
            except Exception:
                amap = {}

        def atom_desc(idx: int) -> str:
            el = amap.get(idx, f"#{idx}")
            return f"{el}{idx}"

        rows: List[dict] = []
        for c in coords:
            coord_id = c.get("coord_id")
            group = c.get("coord_group", "")
            atoms = c.get("atoms", []) or []
            coord_code = c.get("coord_code", "") or ""
            raw = c.get("coord_label_raw", "") or ""

            atom_label = "-".join(atom_desc(a) for a in atoms) if atoms else ""
            group_u = (group or "").upper()

            # Human-friendly short description
            if group_u.startswith("STRE") and len(atoms) == 2:
                desc = f"str({atom_label})"
            elif group_u.startswith("BEND") and len(atoms) == 3:
                desc = f"bend({atom_label})"
            elif group_u.startswith("TORS") and len(atoms) == 4:
                desc = f"tors({atom_label})"
            else:
                desc = f"{group_u}({atom_label})" if atom_label else group_u

            if raw:
                desc += f"[{raw}]"

            # The dd2 parser may include an optional map of mode contributions (already summarized)
            top_terms = c.get("top_mode_terms", "")

            rows.append({
                "coord_id": coord_id,
                "coord_code": coord_code,
                "coord_group": group,
                "atoms": " ".join(str(a) for a in atoms),
                "atom_label": atom_label,
                "label": desc,
                "top_mode_terms": top_terms,
                "source_line": c.get("source_line", ""),
            })

        df = pd.DataFrame(rows)
        df.to_csv(out_csv_path, index=False, encoding="utf-8-sig")
        log_message(f"Saved coordinate lookup CSV: {out_csv_path}")

    except Exception as e:
        log_error(f"Failed to export coordinate lookup CSV: {e}")
        raise



# ------------------------------------------------------------
# ORCA .out parser (tolerant of formatting variations)
# ------------------------------------------------------------

def parse_orca_out_data(out_text: str):
    """
    Parse from an QC output file:
    - Frequencies (mode -> freq, irrep) from the "VIBRATIONAL FREQUENCIES" table
    - IR intensities (mode -> Int[km/mol]) from the "IR SPECTRUM" table

    Notes:
    - ORCA mode indices typically include translational/rotational near-zero modes.
      The IR table usually starts at the first vibrational mode (often 6, but not always).
      Downstream mapping uses the IR-start index when available.
    """
    lines = out_text.splitlines()
    n_lines = len(lines)

    freq_data: Dict[int, dict] = {}
    intensities: Dict[int, float] = {}

    re_freq_line = re.compile(
        r"^\s*(\d+)\s*:\s*([+-]?(?:\d*\.\d+|\d+\.\d*|\d+)(?:[EeDd][+-]?\d+)?)\s+cm(?:\*\*)?-1(?:\s+(.*))?$",
        re.IGNORECASE
    )

    # Captures: mode, freq, eps, Int (km/mol)
    re_ir_line = re.compile(
        r"^\s*(\d+)\s*:\s*([+-]?(?:\d*\.\d+|\d+\.\d*|\d+)(?:[EeDd][+-]?\d+)?)\s+"
        r"([+-]?(?:\d*\.\d+|\d+\.\d*|\d+)(?:[EeDd][+-]?\d+)?)\s+"
        r"([+-]?(?:\d*\.\d+|\d+\.\d*|\d+)(?:[EeDd][+-]?\d+)?)",
        re.IGNORECASE
    )

    i = 0
    while i < n_lines:
        line = lines[i].strip()

        if line.upper() == "VIBRATIONAL FREQUENCIES":
            i += 1
            while i < n_lines:
                sub = lines[i].strip()
                if sub.upper().startswith("NORMAL MODES") or sub.upper() == "IR SPECTRUM" or sub.upper().startswith("THERMOCHEMISTRY"):
                    break
                m = re_freq_line.match(lines[i])
                if m:
                    try:
                        mode = int(m.group(1))
                        freq = float(safe_float(m.group(2)))
                        raw_irrep = (m.group(3) or "").strip()
                        irrep = re.sub(r"^\d+\s*-\s*", "", raw_irrep)
                        freq_data[mode] = {"freq": freq, "irrep": irrep}
                    except Exception as e:
                        log_caution(f"ORCA frequency parse failed on line: {lines[i].strip()}")
                        log_error("parse_orca_out_data freq", e)
                i += 1
            continue

        if line.upper() == "IR SPECTRUM":
            i += 1
            while i < n_lines and not re_ir_line.match(lines[i]):
                i += 1
            while i < n_lines:
                sub = lines[i].strip()
                if not sub:
                    break
                m = re_ir_line.match(lines[i])
                if m:
                    try:
                        mode = int(m.group(1))
                        intensities[mode] = float(safe_float(m.group(4)))
                    except Exception as e:
                        log_caution(f"ORCA intensity parse failed on line: {lines[i].strip()}")
                        log_error("parse_orca_out_data intensity", e)
                i += 1
            continue

        i += 1

    return freq_data, intensities



# ------------------------------------------------------------
# VEDA (.ved) parser
# ------------------------------------------------------------

_INT_RE = re.compile(r"^\d+$")

def _is_plausible_ved_header_ints(ints: List[int]) -> bool:
    """Heuristic to distinguish VEDA header rows from data rows.
    True for sequences like: 1 2 3 ... or 17 18 19 ... (strictly increasing, positive, mostly step=1).
    False for data rows like: 1 50 50 0 ... (not increasing).
    """
    if not ints or len(ints) < 2:
        return False
    if min(ints) <= 0:
        return False
    for a, b in zip(ints, ints[1:]):
        if b <= a:
            return False
    steps = [b - a for a, b in zip(ints, ints[1:])]
    n1 = sum(1 for d in steps if d == 1)
    return n1 >= max(1, int(0.6 * len(steps)))



def parse_ved_matrix_stitched(lines: List[str], label: str) -> Tuple[int, int, List[List[float]], List[int]]:
    """
    Parse a VEDA matrix block (.ved), joining stitched sub-blocks if needed.

    Returns:
        n_modes, n_cols, matrix, col_ids

    col_ids:
        - If the VEDA block contains header rows listing column IDs, those are used.
        - If no column headers are found, col_ids is [1..n_cols] (legacy behavior).
    """
    lab = label.strip().upper()
    start_idx = None
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s:
            continue
        if re.match(rf"^{re.escape(lab)}\s*:?", s, flags=re.IGNORECASE):
            start_idx = i
            break
    if start_idx is None:
        raise ValueError(f"{label} header not found")

    # If headers are found, we build by column-ID (safer than assuming sequential columns).
    has_headers = False
    current_cols: List[int] = []
    col_ids_order: List[int] = []
    col_ids_seen: set = set()

    mode_to_colvals: Dict[int, Dict[int, float]] = {}
    mode_to_listvals: Dict[int, List[float]] = {}

    i = start_idx + 1
    while i < len(lines):
        s = lines[i].strip()
        if not s:
            i += 1
            continue

        # End at the next block header
        if s.upper().startswith("PED:") and lab != "PED":
            break
        if s.upper().startswith("TED:") and lab != "TED":
            break
        if re.match(r"^-+\s*$", s) and (mode_to_colvals or mode_to_listvals):
            break

        toks = s.split()

        # Header row: column indices like 1 2 3 ... (but avoid misclassifying integer-only data rows)
        if toks and all(_INT_RE.fullmatch(t) for t in toks):
            try:
                int_toks = [int(t) for t in toks]
            except Exception:
                int_toks = []
            if _is_plausible_ved_header_ints(int_toks):
                has_headers = True
                try:
                    current_cols = [int(t) for t in toks]
                except Exception as e:
                    log_caution(f"{label} header row parse failed: {s}")
                    log_error("parse_ved_matrix_stitched header", e)
                    current_cols = []
                for cid in current_cols:
                    if cid not in col_ids_seen:
                        col_ids_seen.add(cid)
                        col_ids_order.append(cid)
                i += 1
                continue

        # Data row: leading mode index
        if toks and toks[0].lstrip("+-").isdigit():
            try:
                mode = int(toks[0])
            except Exception:
                i += 1
                continue

            vals: List[float] = []
            for t in toks[1:]:
                try:
                    vals.append(safe_float(t))
                except Exception:
                    # ignore stray tokens
                    continue

            # VEDA quirk: sometimes the last numeric token repeats the mode index
            if vals and float(vals[-1]).is_integer() and int(vals[-1]) == mode:
                vals = vals[:-1]

            if not vals:
                i += 1
                continue

            if has_headers:
                if not current_cols:
                    log_caution(f"{label} matrix row seen before a valid header row (mode={mode}). Line: {s}")
                    i += 1
                    continue
                n = min(len(vals), len(current_cols))
                if len(vals) != len(current_cols):
                    log_caution(
                        f"{label} row length mismatch: mode={mode} values={len(vals)} header_cols={len(current_cols)} "
                        f"(using first {n})."
                    )
                d = mode_to_colvals.setdefault(mode, {})
                for k in range(n):
                    d[current_cols[k]] = vals[k]
            else:
                # Legacy stitching: just append values as they appear
                mode_to_listvals.setdefault(mode, []).extend(vals)

        i += 1

    if not (mode_to_colvals or mode_to_listvals):
        raise ValueError(f"{label} matrix empty")

    if has_headers:
        n_modes = max(mode_to_colvals.keys()) if mode_to_colvals else 0
        n_cols = len(col_ids_order)
        matrix: List[List[float]] = []
        for mode in range(1, n_modes + 1):
            d = mode_to_colvals.get(mode, {})
            matrix.append([float(d.get(cid, 0.0)) for cid in col_ids_order])
        return n_modes, n_cols, matrix, col_ids_order

    # Legacy path (no headers found)
    n_modes = max(mode_to_listvals.keys())
    n_cols = max((len(v) for v in mode_to_listvals.values()), default=0)
    matrix2: List[List[float]] = []
    for mode in range(1, n_modes + 1):
        row = list(mode_to_listvals.get(mode, []))
        if len(row) < n_cols:
            row += [0.0] * (n_cols - len(row))
        elif len(row) > n_cols:
            row = row[:n_cols]
        matrix2.append(row)
    col_ids_legacy = list(range(1, n_cols + 1))
    return n_modes, n_cols, matrix2, col_ids_legacy


def _extract_ved_frequencies(lines: List[str], n_modes_hint: Optional[int]) -> List[float]:
    """
    Extract VEDA frequencies in mode order.

    Strategy (strict-to-loose, but always *section-aware*):
    1) Prefer lines that explicitly include "cm-1"/"cm**-1" AND a leading mode number.
    2) If not found, look for a "FREQ"/"FREQUENCIES" section and parse mode+freq lines in that section.
    3) If still not found, as a guarded fallback, extract numeric frequency values (even without mode numbers)
       *only inside the detected frequency section*.

    We intentionally avoid "scan all floats in the header", because that tends to pick up unrelated numbers.

    Returns:
        freqs_ved (length == n_modes_hint if successfully extracted), else [].
    """
    if not lines:
        return []

    # Avoid scanning into the PED/TED matrices.
    stop = None
    for idx, ln in enumerate(lines):
        s = ln.strip().upper()
        if s.startswith("PED:") or s.startswith("TED:"):
            stop = idx
            break
    header_region = lines[:stop] if stop is not None else lines

    
    # Pass 0: VEDA often prints plain numeric frequency lists (no units) before PED/TED.
    # Extract the best "numeric-only" block from the header region.
    float_re = re.compile(r"[+-]?(?:\d*\.\d+|\d+\.\d*|\d+)(?:[EeDd][+-]?\d+)?")
    numline_re = re.compile(r"^\s*[+-]?(?:\d*\.\d+|\d+\.\d*|\d+)(?:[EeDd][+-]?\d+)?(?:\s+[+-]?(?:\d*\.\d+|\d+\.\d*|\d+)(?:[EeDd][+-]?\d+)?)*\s*$")
    blocks: List[List[float]] = []
    current: List[float] = []
    for ln in header_region:
        s = ln.strip()
        if not s:
            if current:
                blocks.append(current)
                current = []
            continue
        if numline_re.fullmatch(s):
            nums = [safe_float(x) for x in float_re.findall(s)]
            if len(nums) >= 2:
                current.extend(nums)
                continue
        if current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)

    if blocks:
        best = None
        if n_modes_hint:
            exact = [b for b in blocks if len(b) == n_modes_hint]
            if exact:
                best = max(exact, key=len)
            else:
                above = [b for b in blocks if len(b) > n_modes_hint]
                below = [b for b in blocks if len(b) < n_modes_hint]
                if above:
                    best = min(above, key=lambda b: len(b) - n_modes_hint)
                elif below:
                    best = max(below, key=len)
        if best is None:
            best = max(blocks, key=len)

        if n_modes_hint and len(best) >= n_modes_hint:
            return [float(x) for x in best[:n_modes_hint]]
        if not n_modes_hint and len(best) >= 6:
            return [float(x) for x in best]
# Pass 1: explicit unit lines (most reliable)
    unit_re = re.compile(
        r"^\s*(\d+)\s*[:\)]?\s*([+-]?(?:\d*\.\d+|\d+\.\d*|\d+)(?:[EeDd][+-]?\d+)?)\s*cm(?:\*\*)?-1\b",
        re.IGNORECASE
    )
    freq_by_mode: Dict[int, float] = {}
    for ln in header_region:
        m = unit_re.match(ln)
        if not m:
            continue
        try:
            mode = int(m.group(1))
            freq = safe_float(m.group(2))
        except Exception:
            continue
        if mode not in freq_by_mode:
            freq_by_mode[mode] = float(freq)

    if n_modes_hint and freq_by_mode:
        # Require a complete 1..n set (strict; avoids accidental partial matches)
        if all((k in freq_by_mode) for k in range(1, n_modes_hint + 1)):
            return [float(freq_by_mode[k]) for k in range(1, n_modes_hint + 1)]

    # Pass 2: look for a "FREQUENCIES" section
    # Heuristic: once we see a line that includes "FREQ", parse subsequent lines until blank/next header.
    start_idxs: List[int] = []
    for idx, ln in enumerate(header_region):
        u = ln.upper()
        if "FREQUENCIES" in u or re.search(r"\bFREQ\b", u):
            start_idxs.append(idx)

    # mode + freq (no unit required)
    modefreq_re = re.compile(
        r"^\s*(\d+)\s*[:\)]?\s*([+-]?(?:\d*\.\d+|\d+\.\d*|\d+)(?:[EeDd][+-]?\d+)?)\b"
    )

    for sidx in start_idxs:
        freq_by_mode2: Dict[int, float] = {}
        section_lines: List[str] = []
        for ln in header_region[sidx:sidx + 500]:  # hard cap to avoid runaway
            section_lines.append(ln)
            if not ln.strip():
                # a blank line tends to end the table
                if freq_by_mode2:
                    break
                continue
            # Stop if it looks like we hit another section header
            if re.match(r"^[A-Z][A-Z0-9 _-]{4,}:?$", ln.strip().upper()) and freq_by_mode2:
                break

            m = modefreq_re.match(ln)
            if not m:
                continue
            try:
                mode = int(m.group(1))
                freq = safe_float(m.group(2))
            except Exception:
                continue
            if mode not in freq_by_mode2:
                freq_by_mode2[mode] = float(freq)

        if n_modes_hint and freq_by_mode2:
            if all((k in freq_by_mode2) for k in range(1, n_modes_hint + 1)):
                return [float(freq_by_mode2[k]) for k in range(1, n_modes_hint + 1)]

        # Pass 3 (guarded): mode-less numeric list inside the section only
        if n_modes_hint:
            float_re = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.\d*|\d+)(?:[EeDd][+-]?\d+)?")
            nums: List[float] = []
            for ln in section_lines:
                s = ln.strip()
                if not s:
                    continue
                # Extract all numeric tokens
                toks = float_re.findall(s)
                if not toks:
                    continue

                vals = []
                for t in toks:
                    try:
                        vals.append(float(safe_float(t)))
                    except Exception:
                        continue

                if not vals:
                    continue

                # If the line starts with an integer mode number, drop the first number (likely the mode index)
                if re.match(r"^\s*\d+\s", ln) and len(vals) >= 2 and float(vals[0]).is_integer():
                    vals = vals[1:]

                # Plausibility filter (very loose)
                for v in vals:
                    if abs(v) <= 10000.0:
                        nums.append(v)

                if len(nums) >= n_modes_hint:
                    return nums[:n_modes_hint]

    return []



def parse_ved_freqs_and_matrices(ved_input: Any):
    """Extract VEDA frequencies and TED/PED matrices from a .ved file."""
    try:
        if isinstance(ved_input, (str, os.PathLike)):
            text = Path(ved_input).read_text(encoding="utf-8", errors="ignore")
        elif hasattr(ved_input, "read_text"):
            text = ved_input.read_text(encoding="utf-8", errors="ignore")
        else:
            text = str(ved_input)
    except Exception as e:
        log_caution(f"Failed to read .ved: {ved_input}")
        log_error("parse_ved_freqs_and_matrices read", e)
        return [], None, None

    lines = text.splitlines()

    ted_block = None
    ped_block = None

    try:
        n_m, n_c, ted_m, ted_cols = parse_ved_matrix_stitched(lines, "TED")
        ted_block = {"n_modes": n_m, "n_cols": n_c, "matrix": ted_m, "col_ids": ted_cols}
    except Exception as e:
        log_message(f"TED matrix not available: {e}")

    try:
        n_m, n_c, ped_m, ped_cols = parse_ved_matrix_stitched(lines, "PED")
        ped_block = {"n_modes": n_m, "n_cols": n_c, "matrix": ped_m, "col_ids": ped_cols}
    except Exception as e:
        log_caution(f"PED matrix parse failed: {e}")
        log_error("parse_ved_freqs_and_matrices PED", e)

    n_modes_hint = None
    if ped_block and isinstance(ped_block.get("n_modes"), int):
        n_modes_hint = int(ped_block["n_modes"])
    elif ted_block and isinstance(ted_block.get("n_modes"), int):
        n_modes_hint = int(ted_block["n_modes"])

    freqs_ved = _extract_ved_frequencies(lines, n_modes_hint)

    if n_modes_hint and not freqs_ved:
        log_caution(
            f"VEDA frequency extraction failed (expected {n_modes_hint} modes). "
            f"ORCA↔VEDA mapping will be skipped."
        )

    return freqs_ved, ted_block, ped_block


# ------------------------------------------------------------
# ORCA ↔ VEDA mode mapping (core: 1:1 minimum-cost ordered alignment)
# ------------------------------------------------------------

def _align_ordered_by_frequency(shorter: List[Tuple[int, float]], longer: List[Tuple[int, float]]):
    """
    shorter/longer are sorted by frequency ascending: [(mode, freq), ...]
    Select len(shorter) items from longer while preserving order, minimizing total |Δfreq| (1:1 mapping).

    Returns:
        pairs: list of (idx_shorter, idx_longer)
        total_cost: float
    """
    S = len(shorter)
    L = len(longer)
    if S == 0 or L == 0 or L < S:
        return [], math.inf

    freqs_s = [f for _, f in shorter]
    freqs_l = [f for _, f in longer]

    INF = 1e60
    prev = [0.0] * (L + 1)
    choices = [bytearray(L + 1) for _ in range(S + 1)]

    for i in range(1, S + 1):
        curr = [INF] * (L + 1)
        curr[0] = INF
        dec = choices[i]
        fi = freqs_s[i - 1]
        for j in range(1, L + 1):
            skip = curr[j - 1]
            match = prev[j - 1] + abs(fi - freqs_l[j - 1])
            if match <= skip:
                curr[j] = match
                dec[j] = 1
            else:
                curr[j] = skip
                dec[j] = 0
        prev = curr

    total_cost = prev[L]

    pairs: List[Tuple[int, int]] = []
    i = S
    j = L
    while i > 0 and j > 0:
        if choices[i][j] == 1:
            pairs.append((i - 1, j - 1))
            i -= 1
            j -= 1
        else:
            j -= 1
    pairs.reverse()
    return pairs, total_cost


def build_veda_orca_mode_maps(freqs_ved: List[float], orca_freq_data: Dict[int, dict], orca_intensities: Optional[Dict[int, float]] = None, tol_cm1: float = 5.0):
    """
    Map VEDA modes to ORCA modes (frequency-based 1:1 ordered alignment).
    """
    stats = {
        "n_veda": len(freqs_ved) if freqs_ved else 0,
        "n_orca": len(orca_freq_data) if orca_freq_data else 0,
        "n_matched": 0,
        "max_abs_diff": None,
        "mean_abs_diff": None,
    }

    if not freqs_ved:
        log_caution("VEDA frequencies are empty: ORCA mapping skipped.")
        return {}, {}, stats

    if not orca_freq_data:
        log_caution("ORCA frequency data is empty: ORCA mapping skipped.")
        return {}, {}, stats

    veda_items = [(i + 1, float(f)) for i, f in enumerate(freqs_ved)]

    orca_items: List[Tuple[int, float]] = []
    for k, data in orca_freq_data.items():
        try:
            orca_items.append((int(k), float(data.get("freq", 0.0))))
        except Exception:
            continue

    if not orca_items:
        log_caution("ORCA frequency data exists but no valid (mode,freq) pairs parsed.")
        return {}, {}, stats


    # If IR spectrum data exists, use its starting mode index to drop translational/rotational modes.
    if orca_intensities:
        try:
            min_ir_mode = min(int(k) for k in orca_intensities.keys())
        except Exception:
            min_ir_mode = None
        if min_ir_mode is not None:
            orca_items = [(m, f) for (m, f) in orca_items if m >= min_ir_mode]
            stats["n_orca"] = len(orca_items)
            log_message(f"ORCA mapping: using modes >= {min_ir_mode} based on IR spectrum table.")
    veda_sorted = sorted(veda_items, key=lambda x: x[1])
    orca_sorted = sorted(orca_items, key=lambda x: x[1])

    V = len(veda_sorted)
    O = len(orca_sorted)

    swapped = False
    if O >= V:
        shorter = veda_sorted
        longer = orca_sorted
    else:
        swapped = True
        shorter = orca_sorted
        longer = veda_sorted
        log_caution(f"ORCA modes ({O}) < VEDA modes ({V}). Some VEDA modes will remain unmapped.")

    pairs, _ = _align_ordered_by_frequency(shorter, longer)
    if not pairs:
        log_caution("Failed to align VEDA↔ORCA by frequency (no pairs).")
        return {}, {}, stats

    veda_to_orca: Dict[int, int] = {}
    diffs: List[float] = []

    if not swapped:
        for i_s, j_l in pairs:
            v_mode, v_f = shorter[i_s]
            o_mode, o_f = longer[j_l]
            veda_to_orca[v_mode] = o_mode
            diffs.append(abs(v_f - o_f))
    else:
        orca_to_veda_tmp: Dict[int, int] = {}
        for i_s, j_l in pairs:
            o_mode, o_f = shorter[i_s]
            v_mode, v_f = longer[j_l]
            orca_to_veda_tmp[o_mode] = v_mode
            diffs.append(abs(o_f - v_f))
        veda_to_orca = {v: o for o, v in orca_to_veda_tmp.items()}

    orca_to_veda = {o: v for v, o in veda_to_orca.items()}

    stats["n_matched"] = len(veda_to_orca)
    if diffs:
        stats["max_abs_diff"] = max(diffs)
        stats["mean_abs_diff"] = sum(diffs) / len(diffs)

    if stats["max_abs_diff"] is not None and stats["max_abs_diff"] > tol_cm1:
        # Absolute tolerance is useful for catching "totally wrong file" cases when frequencies are similar-scale.
        # However, some workflows produce systematic shifts (e.g., scaling or different reference), where the
        # mapping can still be correct by rank-order. In that case, judge by *relative* deviation as well.
        try:
            vmax = max(abs(float(f)) for f in freqs_ved) if freqs_ved else 0.0
            omax = max(abs(float(d.get("freq", 0.0))) for d in orca_freq_data.values()) if orca_freq_data else 0.0
            denom = max(vmax, omax, 1.0)
        except Exception:
            denom = 1.0
        rel = float(stats["max_abs_diff"]) / denom
        if rel >= 0.05:
            log_caution(
                f"ORCA↔VEDA mapping has large frequency diffs: max |Δ|={stats['max_abs_diff']:.2f} cm^-1 "
                f"(tol={tol_cm1}, rel={rel:.3f}). Check files / ordering."
            )
        else:
            log_message(
                f"ORCA↔VEDA mapping: max |Δ|={stats['max_abs_diff']:.2f} cm^-1 exceeds tol={tol_cm1}, "
                f"but relative deviation is small (rel={rel:.3f}); mapping is likely still OK."
            )

    if not swapped and O > V:
        log_message(f"ORCA modes ({O}) > VEDA modes ({V}): extra ORCA modes were skipped by alignment.")

    return veda_to_orca, orca_to_veda, stats


# ------------------------------------------------------------
# PED row normalization check
# ------------------------------------------------------------

def _ped_percent_matrix_with_check(mat: List[List[float]], target: float = 100.0, tol: float = 1.0):
    """
    If a PED row sum deviates from target (=100), take abs values and renormalize the row.
    """
    if not mat:
        return mat, [], []
    out: List[List[float]] = []
    sums: List[float] = []
    notes: List[str] = []
    for r in mat:
        ar = [abs(float(v)) for v in r]
        s = sum(ar)
        sums.append(s)
        if s > 1e-12 and abs(s - target) > tol:
            scale = target / s
            out.append([v * scale for v in ar])
            notes.append(f"renorm_from_{s:.3f}")
        else:
            out.append(ar)
            notes.append("")
    return out, sums, notes


# ------------------------------------------------------------
# PED columns ↔ dd2 coordinates (use VEDA column IDs when available)
# ------------------------------------------------------------

def build_ped_column_coord_map(ped_col_ids: List[int], dd2_coords: List[dict]):
    """
    Map PED column POSITION (1-based) to dd2 coordinate objects.

    Mapping key:
        VEDA column ID (from PED header rows)  -> dd2 coord_id

    dd2 nuance:
        Many .dd2 files contain multiple "coordinate tables" distinguished by coord_code
        (e.g., primary coordinates + alternative coordinates). In that situation, the same
        coord_id can appear multiple times. For PED labeling we *prefer* coord_code == 's'
        when available, and fall back to the first occurrence otherwise.

    Returns:
        colpos_to_info: dict[int, dict]
            colpos -> {"ped_col":int, "coord_id":int, "coord_code":str, "coord":dict|None}
        cautions: list[str]
    """
    cautions: List[str] = []

    if not ped_col_ids:
        cautions.append("PED column IDs are empty: cannot label PED columns.")
        return {}, cautions

    if not dd2_coords:
        cautions.append("dd2 coords are empty: cannot label PED columns.")
        return {}, cautions

    # Group dd2 rows by coord_id
    from collections import defaultdict
    rows_by_id: Dict[int, List[dict]] = defaultdict(list)
    missing_id = 0
    for c in dd2_coords:
        cid = c.get("coord_id")
        if isinstance(cid, int):
            rows_by_id[cid].append(c)
        else:
            missing_id += 1
    if missing_id:
        cautions.append(f"dd2 coords missing coord_id: {missing_id} rows")

    # Detect duplicates that are *actually problematic* (duplicates within the preferred code 's')
    dup_any = [cid for cid, lst in rows_by_id.items() if len(lst) > 1]
    if dup_any:
        dup_s = []
        for cid, lst in rows_by_id.items():
            s_count = sum(1 for r in lst if (r.get("coord_code") or "").lower() == "s")
            if s_count > 1:
                dup_s.append(cid)

        if dup_s:
            cautions.append(f"dd2 has duplicate coord_id entries within coord_code='s' (first few): {sorted(dup_s)[:10]}")
        else:
            # This is common (alternative-coordinate tables). Log as INFO only.
            log_message("dd2 contains multiple rows per coord_id (likely alternative coordinates). Using coord_code='s' when available.")

    # Build a "best" representative per coord_id: prefer coord_code == 's'
    best_by_id: Dict[int, dict] = {}
    best_code_by_id: Dict[int, str] = {}
    for cid, lst in rows_by_id.items():
        chosen = None
        for r in lst:
            if (r.get("coord_code") or "").lower() == "s":
                chosen = r
                break
        if chosen is None:
            chosen = lst[0]
        best_by_id[cid] = chosen
        best_code_by_id[cid] = (chosen.get("coord_code") or "")

    # PED header checks
    if len(set(ped_col_ids)) != len(ped_col_ids):
        cautions.append("PED column IDs contain duplicates (VEDA header may be malformed).")

    missing_ids: List[int] = []
    colpos_to_info: Dict[int, dict] = {}
    for pos, cid in enumerate(ped_col_ids, start=1):
        c_obj = best_by_id.get(cid)
        if c_obj is None:
            missing_ids.append(cid)
        colpos_to_info[pos] = {
            "ped_col": pos,
            "coord_id": cid,
            "coord_code": best_code_by_id.get(cid, ""),
            "coord": c_obj,
        }

    if missing_ids:
        preview = ", ".join(map(str, missing_ids[:12]))
        more = "" if len(missing_ids) <= 12 else f" ... (+{len(missing_ids) - 12})"
        cautions.append(f"dd2 coord_id not found for some PED column IDs: {preview}{more}")

    return colpos_to_info, cautions



# ------------------------------------------------------------
# GUI text
# ------------------------------------------------------------

MAIN_DESCRIPTION = """This tool cross-references the PED (Potential Energy Distribution) matrix in a VEDA (.ved) file
with internal-coordinate definitions from DD2 + FMU, then exports the top contributing internal coordinates
for each vibrational mode to CSV.

Required input files:
- .ved (VEDA output; PED matrix is required)
- .dd2 (VEDA dd2 internal-coordinate table)
- .fmu (atom → element mapping)
- .out (ORCA output; required for ORCA↔VEDA mode mapping and IR data)

Quick steps:
1) Click [Select .ved] (same-stem .dd2/.fmu/.out in the same folder will be auto-filled when present)
2) Review or override the auto-filled file paths if needed
3) Click [RUN ANALYSIS]
4) Inspect the generated CSV files (see the "User Guide" tab for details)
"""

USAGE_MANUAL = """OUTPUT FILES
1) <stem>_PED_table.csv
   - A table of the top PED contributors (up to 6 internal coordinates) for each VEDA mode.
2) <stem>_coordinates_lookup.csv
   - A lookup table for dd2 internal coordinates with atom indices (and additional metadata where available).
   - Includes coord_code (e.g., 's' primary / 'k','v' alternative tables) to help disambiguate.

KEY COLUMNS IN PED_table.csv
- mode_veda      : VEDA mode index (1-based)
- mode_orca      : Matched ORCA mode index (blank if not matched)
- freq_veda      : VEDA frequency [cm^-1] (0 if unavailable)
- freq_orca      : ORCA frequency [cm^-1] (0 if unavailable)
- delta_freq     : freq_orca - freq_veda (blank if not matched)
- abs_delta_freq : |delta_freq| (blank if not matched)
- irrep          : ORCA irrep (blank if unavailable)
- IR_intensity  : IR intensity (ORCA/Gaussian; 0 if unavailable)
- ped_sum        : Sum of absolute PED contributions in the row (typically ~100)
- note           : Renormalization note if PED row sum deviates from ~100 (e.g., renorm_from_XXX)
- caution        : Per-mode caution messages (see below)

TOP CONTRIBUTION FIELDS (up to 6)
- PED1_col / PED1_coord_id / PED1_coord_code / PED1_label / PED1_val ... PED6_*
  - PED*_col      : PED matrix column position (1-based)
  - PED*_coord_id : Coordinate ID taken from the VEDA PED header rows (falls back to col position if missing)
  - PED*_coord_code: dd2 coord_code used for labeling (helps disambiguate duplicates in the lookup CSV)
  - PED*_label    : Simplified label (element symbols only; check lookup CSV for atom indices)
  - PED*_val      : Contribution [%] (very small contributions may be omitted)

IMPORTANT: CONSISTENCY CHECKS (CAUTION)
- PED labeling uses the VEDA PED header column IDs when present.
  If dd2 does not contain those coord_id values, labels become UNKNOWN and CAUTION messages are recorded.
- ORCA↔VEDA mapping is done via frequency-based 1:1 ordered alignment.
  Large |Δfreq| often indicates mismatched files, different geometries, or missing/extra modes.

LOG FILE
- A .log file is created next to the script (or in your home folder if that is not writable).
  When results look suspicious, check CAUTION/ERROR messages in the log first.
"""


# ------------------------------------------------------------
# GUI app
# ------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title(f"{APP_NAME} (public v9)")
        self.geometry("860x660")

        self.ved_path: Optional[str] = None
        self.dd2_path: Optional[str] = None
        self.fmu_path: Optional[str] = None
        self.out_path: Optional[str] = None

        self._cfg = load_config()

        self._build_gui()
        self._apply_config_on_startup()

    def _build_gui(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        self.tab_main = ttk.Frame(nb)
        self.tab_usage = ttk.Frame(nb)

        nb.add(self.tab_main, text="Analysis")
        nb.add(self.tab_usage, text="User Guide")

        # --- Main tab ---
        main = self.tab_main
        main.columnconfigure(0, weight=1)

        desc = tk.Label(main, text=MAIN_DESCRIPTION, justify="left", anchor="w", wraplength=820)
        desc.pack(fill="x", padx=12, pady=(12, 6))

        frame = tk.Frame(main, padx=12, pady=8)
        frame.pack(fill="both", expand=False)

        self._labels: Dict[str, tk.Label] = {}

        def make_row(lbl_text: str, attr_name: str, file_types):
            row = tk.Frame(frame, pady=4)
            row.pack(fill="x")
            btn = tk.Button(row, text=lbl_text, width=16,
                            command=lambda: self._select_file(attr_name, file_types))
            btn.pack(side="left")
            lbl = tk.Label(row, text="(Not selected)", fg="gray", anchor="w")
            lbl.pack(side="left", padx=10, fill="x", expand=True)
            self._labels[attr_name] = lbl

        make_row("Select .ved", "ved_path", [("VEDA files", "*.ved"), ("All files", "*.*")])
        make_row("Select .dd2", "dd2_path", [("DD2 files", "*.dd2"), ("All files", "*.*")])
        make_row("Select .fmu", "fmu_path", [("FMU files", "*.fmu"), ("All files", "*.*")])
        make_row("Select QC output (.out/.log)", "out_path", [("ORCA/Gaussian output", "*.out *.log"), ("ORCA out", "*.out"), ("Gaussian log", "*.log"), ("All files", "*.*")])

        btn_run = tk.Button(main, text="RUN ANALYSIS", font=("Arial", 12, "bold"),
                            bg="#dddddd", command=self.run)
        btn_run.pack(padx=12, pady=14, fill="x")

        self.status_lbl = tk.Label(main, text="Ready", fg="blue", anchor="w")
        self.status_lbl.pack(fill="x", padx=12, pady=(0, 8))

        # --- Usage tab ---
        usage = self.tab_usage
        usage.columnconfigure(0, weight=1)
        usage.rowconfigure(0, weight=1)

        st = scrolledtext.ScrolledText(usage, wrap="word", font=("TkDefaultFont", 10))
        st.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        st.insert("1.0", USAGE_MANUAL)
        st.configure(state="disabled")

    def _apply_config_on_startup(self):
        # Restore from config (existing files only)
        for attr in ("ved_path", "dd2_path", "fmu_path", "out_path"):
            p = self._cfg.get(attr)
            if p and Path(p).is_file():
                self._set_path(attr, p, save=False)

        # If .ved exists, auto-fill same-stem companion files that are missing
        if self.ved_path and Path(self.ved_path).is_file():
            self._auto_fill_related_files(self.ved_path, only_if_missing=True, save=False)

        # Save back (dropping non-existing paths)
        self._save_current_config()

    def _save_current_config(self):
        cfg = dict(self._cfg) if isinstance(self._cfg, dict) else {}
        cfg["ved_path"] = self.ved_path or ""
        cfg["dd2_path"] = self.dd2_path or ""
        cfg["fmu_path"] = self.fmu_path or ""
        cfg["out_path"] = self.out_path or ""

        last_dir = ""
        for p in (self.ved_path, self.dd2_path, self.fmu_path, self.out_path):
            if p and Path(p).exists():
                last_dir = str(Path(p).resolve().parent)
                break
        if last_dir:
            cfg["last_dir"] = last_dir

        self._cfg = cfg
        save_config(cfg)

    def _set_path(self, attr: str, path: Optional[str], save: bool = True):
        setattr(self, attr, path)
        lbl = self._labels.get(attr)
        if lbl:
            if path and Path(path).exists():
                lbl.config(text=path, fg="black")
            else:
                lbl.config(text="(Not selected)", fg="gray")
        if save:
            self._save_current_config()

    def _select_file(self, attr: str, types):
        initdir = None
        current = getattr(self, attr, None)
        if current and Path(current).exists():
            initdir = str(Path(current).resolve().parent)
        else:
            last_dir = self._cfg.get("last_dir")
            if last_dir and Path(last_dir).exists():
                initdir = last_dir

        path = filedialog.askopenfilename(initialdir=initdir, filetypes=types)
        if not path:
            return

        self._set_path(attr, path, save=False)

        # When selecting a .ved, auto-fill same-stem files in the same folder.
        if attr == "ved_path":
            self._auto_fill_related_files(path, only_if_missing=False, save=False)

        self._save_current_config()

    def _auto_fill_related_files(self, ved_path: str, only_if_missing: bool, save: bool):
        """
        Auto-fill dd2/fmu/out with the same stem in the same directory as the selected .ved.

        Noise policy (v9):
        - Missing candidates are logged as INFO (log_message), not CAUTION.
        Safety policy:
        - When selecting a new .ved (only_if_missing=False), missing companion files clear previous selections
          to avoid accidental cross-file analysis.
        """
        p = Path(ved_path)
        if not p.exists():
            return

        cand = {
            "dd2_path": p.with_suffix(".dd2"),
            "fmu_path": p.with_suffix(".fmu"),
            "out_path": None,  # handled below (.out or .log)
        }

        # Prefer same-stem .out; fallback to .log (Gaussian) when .out is absent.
        out_cand = p.with_suffix(".out")
        log_cand = p.with_suffix(".log")
        if out_cand.exists():
            cand["out_path"] = out_cand
        elif log_cand.exists():
            cand["out_path"] = log_cand
        else:
            cand["out_path"] = out_cand  # keep .out as the canonical name for messages

        missing: List[str] = []
        filled: List[str] = []

        for attr, fp in cand.items():
            if only_if_missing and getattr(self, attr, None):
                continue

            if fp.is_file():
                self._set_path(attr, str(fp), save=False)
                filled.append(fp.name)
            else:
                missing.append(fp.name)
                if not only_if_missing:
                    # Clear to avoid accidentally reusing old companion files.
                    self._set_path(attr, None, save=False)

        if filled:
            log_message(f"Auto-fill: filled {', '.join(filled)}")
        if missing:
            log_message(f"Auto-fill: not found {', '.join(missing)} in {p.parent}")

        if save:
            self._save_current_config()

    def run(self):
        if not (self.ved_path and self.dd2_path and self.out_path):
            messagebox.showwarning("Missing Files", "Required files: .ved, .dd2, QC output (.out/.log). FMU is optional; if omitted, atom labels are taken from the QC output when possible.")
            return

        cautions_for_gui: List[str] = []

        try:
            self.status_lbl.config(text="Processing...", fg="blue")
            self.update()

            # 1) Parse .ved (PED is required)
            freqs_ved, ted_blk, ped_blk = parse_ved_freqs_and_matrices(Path(self.ved_path))
            if not ped_blk:
                raise ValueError("No PED matrix found in .ved file (see log for details).")

            if not freqs_ved:
                cautions_for_gui.append("VEDA frequencies could not be extracted (ORCA↔VEDA mapping skipped).")

            # 2) Parse dd2
            dd2_data = parse_dd2(self.dd2_path)
            coords = dd2_data.get("coords", []) or []
            if not coords:
                log_caution("dd2 coords are empty. PED labels may become UNKNOWN.")
                cautions_for_gui.append("dd2 contains no coordinates (PED labels may become UNKNOWN).")

            # 3) Atom map (for lookup CSV + simplified labels)
            atom_map: Dict[int, str] = {}
            if self.fmu_path:
                atom_map = parse_atom_map_from_fmu(self.fmu_path)
            if not atom_map:
                log_caution("Atom map could not be built from FMU. Will try QC output geometry for labeling.")

            # 4) QC parse (ORCA or Gaussian; required)
            try:
                out_text = Path(self.out_path).read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                log_caution(f"Failed to read ORCA .out: {self.out_path}")
                log_error("run read out", e)
                out_text = ""

            if not out_text:
                raise ValueError("QC output file could not be read (empty).")

            engine, orca_freq_data, orca_intensities, qc_atom_map = parse_qchem_output(out_text)
            log_message(f"QC engine detected: {engine}")
            if not orca_freq_data:
                raise ValueError(f"No vibrational frequency data parsed from QC output (engine={engine}).")

            if not atom_map:
                atom_map = parse_atom_map_from_orca_out(out_text)


            # 5) Mode mapping (frequency-based 1:1 alignment)
            tol_map = 5.0
            veda_to_orca, _, map_stats = build_veda_orca_mode_maps(freqs_ved, orca_freq_data, orca_intensities=orca_intensities, tol_cm1=tol_map)
            if map_stats.get("max_abs_diff") is not None and map_stats["max_abs_diff"] > tol_map:
                cautions_for_gui.append(f"Some ORCA↔VEDA matches have large |Δfreq| (max={map_stats['max_abs_diff']:.2f})")
            if freqs_ved and map_stats.get("n_matched", 0) == 0:
                cautions_for_gui.append("Failed to match ORCA↔VEDA modes (mode_orca etc. will be blank).")

            # 6) PED row renormalization
            ped_mat_norm, sums, notes = _ped_percent_matrix_with_check(ped_blk["matrix"])

            # 7) PED columns ↔ dd2 mapping (use VEDA column IDs if present)
            ped_col_ids: List[int] = ped_blk.get("col_ids", []) or []
            if not ped_col_ids:
                # Defensive fallback
                ped_col_ids = list(range(1, int(ped_blk.get("n_cols", 0)) + 1))
                log_caution("PED column IDs missing; falling back to sequential numbering.")

            colpos_to_info, colmap_cautions = build_ped_column_coord_map(ped_col_ids, coords)
            for c in colmap_cautions:
                log_caution(c)
            if colmap_cautions:
                cautions_for_gui.append("Potential PED column ↔ dd2(coord_id) mismatch detected (see log).")

            # 8) Build DataFrame
            rows: List[dict] = []
            for i, row in enumerate(ped_mat_norm):
                v_mode = i + 1

                v_freq = 0.0
                if freqs_ved and i < len(freqs_ved):
                    try:
                        v_freq = float(freqs_ved[i])
                    except Exception:
                        v_freq = 0.0

                o_mode = veda_to_orca.get(v_mode) if veda_to_orca else None

                o_freq = 0.0
                o_irrep = ""
                o_int = 0.0

                caution_msgs: List[str] = []
                if not freqs_ved:
                    caution_msgs.append("VEDA frequency unavailable")

                if o_mode is None:
                    caution_msgs.append("ORCA mode not matched")
                else:
                    fd = orca_freq_data.get(o_mode)
                    if fd:
                        try:
                            o_freq = float(fd.get("freq", 0.0))
                        except Exception:
                            o_freq = 0.0
                        o_irrep = fd.get("irrep", "") or ""
                    else:
                        caution_msgs.append("ORCA frequency unavailable")

                    try:
                        o_int = float(orca_intensities.get(o_mode, 0.0))
                    except Exception:
                        o_int = 0.0

                    if v_freq and o_freq:
                        absd = abs(o_freq - v_freq)
                        if absd > tol_map:
                            caution_msgs.append(f"|Δfreq|={absd:.2f}>tol({tol_map:.2f})")

                contribs: List[Tuple[float, int]] = []
                for col_idx_0, val in enumerate(row):
                    col_pos = col_idx_0 + 1
                    contribs.append((float(val), col_pos))
                contribs.sort(key=lambda x: x[0], reverse=True)

                delta_freq = None
                abs_delta_freq = None
                if o_mode is not None and v_freq and o_freq:
                    delta_freq = o_freq - v_freq
                    abs_delta_freq = abs(delta_freq)

                entry = {
                    "mode_veda": v_mode,
                    "mode_orca": o_mode if o_mode else "",
                    "freq_veda": v_freq,
                    "freq_orca": o_freq,
                    "delta_freq": delta_freq,
                    "abs_delta_freq": abs_delta_freq,
                    "irrep": o_irrep,
                    "IR_intensity": o_int,
                    "ped_sum": sums[i] if i < len(sums) else "",
                    "note": notes[i] if i < len(notes) else "",
                }

                rank_out = 0
                unknown_in_top = 0
                for val, col_pos in contribs:
                    if rank_out >= 6:
                        break
                    if val < 0.1:
                        break

                    info = colpos_to_info.get(col_pos, {"ped_col": col_pos, "coord_id": col_pos, "coord_code": "", "coord": None})
                    coord_id = info.get("coord_id", col_pos)
                    coord_code = info.get("coord_code", "") or ""
                    c_obj = info.get("coord")

                    if c_obj is None:
                        unknown_in_top += 1
                        lbl_body = "UNKNOWN"
                    else:
                        grp = c_obj.get("coord_group", "") or ""
                        grp_u = grp.upper()
                        ats = c_obj.get("atoms", []) or []
                        raw = c_obj.get("coord_label_raw", "") or ""

                        at_syms = [atom_map.get(a, f"{a}") for a in ats]

                        if grp_u.startswith("STRE") and len(ats) == 2:
                            lbl_body = f"str({at_syms[0]}-{at_syms[1]})"
                        elif grp_u.startswith("BEND") and len(ats) == 3:
                            lbl_body = f"bend({at_syms[0]}-{at_syms[1]}-{at_syms[2]})"
                        elif grp_u.startswith("TORS") and len(ats) == 4:
                            lbl_body = f"tors({at_syms[0]}-{at_syms[1]}-{at_syms[2]}-{at_syms[3]})"
                        else:
                            lbl_body = f"{grp_u}({'-'.join(at_syms)})"

                        if raw:
                            lbl_body += f"[{raw}]"

                    entry[f"PED{rank_out + 1}_col"] = int(col_pos)
                    entry[f"PED{rank_out + 1}_coord_id"] = int(coord_id) if isinstance(coord_id, int) else coord_id
                    entry[f"PED{rank_out + 1}_coord_code"] = coord_code
                    entry[f"PED{rank_out + 1}_label"] = lbl_body
                    entry[f"PED{rank_out + 1}_val"] = round(val, 1)

                    rank_out += 1

                if unknown_in_top:
                    caution_msgs.append(f"UNKNOWN in top contributions({unknown_in_top})")

                if entry.get("note"):
                    caution_msgs.append("PED renormalized")

                entry["caution"] = "; ".join(caution_msgs)

                rows.append(entry)

            df_ped = pd.DataFrame(rows)

            cols = [
                "mode_veda", "mode_orca",
                "freq_veda", "freq_orca", "delta_freq", "abs_delta_freq",
                "irrep", "IR_intensity",
                "ped_sum", "note", "caution",
            ]
            for r in range(1, 7):
                cols.extend([f"PED{r}_col", f"PED{r}_coord_id", f"PED{r}_coord_code", f"PED{r}_label", f"PED{r}_val"])
            cols = [c for c in cols if c in df_ped.columns]
            df_ped = df_ped[cols]

            # Save paths
            base = Path(self.ved_path)
            save_path = str(base.with_name(base.stem + "_PED_table.csv"))
            lookup_path = str(base.with_name(base.stem + "_coordinates_lookup.csv"))

            df_ped.to_csv(save_path, index=False, encoding="utf-8-sig")
            log_message(f"Saved PED CSV: {save_path}")

            export_internal_coordinate_lookup_csv(self.dd2_path, lookup_path, fmu_path=self.fmu_path, atom_map=atom_map)

            # Save config
            self._save_current_config()

            self.status_lbl.config(text=f"Done! Saved: {Path(save_path).name}", fg="green")

            msg = f"Analysis complete.\n\nSaved:\n1. {save_path}\n2. {lookup_path}\n\nLog:\n{_ensure_log_path()}"
            messagebox.showinfo("Success", msg)

            if cautions_for_gui:
                messagebox.showwarning(
                    "Caution",
                    "Analysis completed, but there are cautions:\n\n- " + "\n- ".join(cautions_for_gui) +
                    "\n\nSee the log (.log) for details."
                )

        except Exception as e:
            self.status_lbl.config(text="Error occurred", fg="red")
            log_caution("Run Analysis failed (see ERROR detail below).")
            log_error("Run Analysis", e)
            messagebox.showerror("Error", f"An error occurred:\n{str(e)}\n\nSee log:\n{_ensure_log_path()}")


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()