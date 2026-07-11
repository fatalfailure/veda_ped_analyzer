#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
veda_ped_analyzer (public release v1.1.7 - Combined Target Matrix-Source Selection Fix)

Purpose
- Combine the PED (Potential Energy Distribution) matrix from a VEDA .ved file with
  internal-coordinate definitions from DD2 + (FMU or ORCA geometry).
- Export the top PED contributors (internal coordinate ID / simplified label / contribution %)
  for each vibrational mode to CSV.
- Parse an QC output file (required) to obtain ORCA frequencies / irreps / IR intensities and
  map ORCA modes to VEDA modes using a frequency-based 1:1 ordered alignment.
- Support multi-interpretation export (STANDARD 's', ALTERNATIVE 'k', ALTERNATIVE2 'v') 
  to fully ensure alternative coordinate sets are captured and accurately labeled.
- Add coordinate-centered target tracking for metal-ligand stretches and other selected internal coordinates.
- Export long PED tables, target hits, target summaries by mode/coordinate, and target matrices.
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
APP_VERSION = "1.1.9"
APP_RELEASE_DATE = "2026-07-11"
APP_VERSION_LABEL = f"{APP_NAME} v{APP_VERSION}"

COORDINATE_CODE_LABELS = {
    "s": "s - standard",
    "k": "k - alternative",
    "v": "v - alternative2",
}
COORDINATE_CODE_ORDER = ["s", "k", "v"]

COORDINATE_GROUP_LABELS = {
    "STRE": "STRE - Stretching",
    "BEND": "BEND - Bending",
    "TORS": "TORS - Torsion",
}
COORDINATE_GROUP_ORDER = ["STRE", "BEND", "TORS"]


def _code_display(code: str) -> str:
    c = (code or "").strip().lower()
    return COORDINATE_CODE_LABELS.get(c, c)


def _code_from_filter(value: str) -> str:
    v = (value or "").strip().lower()
    if not v or v == "(any)":
        return "(any)"
    # Accept both raw values such as "s" and display labels such as "s - standard".
    return v.split()[0]


def _group_display(group: str) -> str:
    g = (group or "").strip().upper()
    return COORDINATE_GROUP_LABELS.get(g, g)


def _group_from_filter(value: str) -> str:
    v = (value or "").strip()
    if not v or v == "(any)":
        return "(any)"
    # Accept both raw values such as "STRE" and display labels such as "STRE - Stretching".
    return v.split()[0].upper()


def _ordered_code_values(codes) -> list:
    codes_l = sorted({str(c).strip().lower() for c in codes if str(c).strip()})
    ordered = [c for c in COORDINATE_CODE_ORDER if c in codes_l]
    ordered += [c for c in codes_l if c not in ordered]
    return [_code_display(c) for c in ordered] + ["(any)"]


def _ordered_group_values(groups) -> list:
    groups_u = sorted({str(g).strip().upper() for g in groups if str(g).strip()})
    ordered = [g for g in COORDINATE_GROUP_ORDER if g in groups_u]
    ordered += [g for g in groups_u if g not in ordered]
    return [_group_display(g) for g in ordered] + ["(any)"]


try:
    BASE_PATH = Path(__file__).resolve()
except Exception:
    BASE_PATH = Path.cwd() / APP_NAME

LOG_PATHS = [
    BASE_PATH.with_suffix(".log"),
    Path.home() / f"{APP_NAME}.log",
]
CONFIG_PATHS = [
    BASE_PATH.with_suffix(".json"),
    Path.home() / f"{APP_NAME}.json",
]

LOG_PATH: Optional[Path] = None
CONFIG_PATH: Optional[Path] = None


def _first_writable_path(candidates: List[Path], default_name: str) -> Path:
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
    global LOG_PATH
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

    print(f"[{APP_NAME}] LOG WRITE FAILED: {last_exc}", file=sys.stderr)


def log_message(msg: str) -> None:
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    line = f"[{ts}] {msg}\n"
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
# Numeric parsing
# ------------------------------------------------------------

def safe_float(x) -> float:
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

    atom_map: Dict[int, str] = {}
    in_atomic = False
    idx = 1
    for ln in lines:
        if re.search(r"Atomic numbers", ln, re.IGNORECASE):
            in_atomic = True
            continue
        if in_atomic:
            if re.match(r"^[A-Za-z].*:", ln) and not re.search(r"Atomic numbers", ln, re.IGNORECASE):
                break
            for tok in ln.split():
                if re.fullmatch(r"\d+", tok):
                    z = int(tok)
                    atom_map[idx] = Z_TO_EL.get(z, f"Z{z}")
                    idx += 1
    return atom_map


def parse_atom_map_from_orca_out(out_text: str) -> Dict[int, str]:
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
    if not out_text:
        return False
    head = out_text[:6000]
    if "Entering Gaussian System" in head:
        return True
    if "Gaussian, Inc." in head:
        return True
    if "Normal termination of Gaussian" in out_text:
        return True
    return False


def parse_atom_map_from_gaussian_out(out_text: str) -> Dict[int, str]:
    if not out_text:
        return {}

    starts = [m.start() for m in re.finditer(r"\n\s*Standard orientation:\s*\n", out_text)]
    if not starts:
        starts = [m.start() for m in re.finditer(r"\n\s*Input orientation:\s*\n", out_text)]
    if not starts:
        return {}

    chunk = out_text[starts[-1]:]
    lines = chunk.splitlines()

    dash = [i for i, ln in enumerate(lines[:200]) if re.match(r"\s*-{5,}\s*$", ln)]
    if len(dash) < 2:
        return {}

    i0 = dash[1] + 1
    atom_map: Dict[int, str] = {}
    for ln in lines[i0:]:
        if re.match(r"\s*-{5,}\s*$", ln):
            break
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
    lines = out_text.splitlines()

    blocks = []
    i = 0
    while i < len(lines):
        if "Frequencies --" in lines[i]:
            mode_line = None
            irrep_line = ""
            for back in range(1, 8):
                if i - back < 0:
                    break
                if re.match(r"\s*\d+\s+\d+\s+\d+\s*$", lines[i - back]):
                    mode_line = lines[i - back]
                    irrep_line = lines[i - back + 1] if (i - back + 1) < len(lines) else ""
                    break

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

    best = max(runs, key=lambda r: (r[-1][0][-1], runs.index(r)))

    freq_data: Dict[int, dict] = {}
    intensities: Dict[int, float] = {}
    for modes, irreps, freqs, intens in best:
        for m, ir, fr, it in zip(modes, irreps, freqs, intens):
            if fr == fr:
                freq_data[m] = {"freq": float(fr), "irrep": (ir or "").strip()}
            if it == it:
                intensities[m] = float(it)

    return freq_data, intensities


def parse_qchem_output(out_text: str) -> Tuple[str, Dict[int, dict], Dict[int, float], Dict[int, str]]:
    if is_gaussian_output(out_text):
        freq_data, intensities = parse_gaussian_out_data(out_text)
        atom_map = parse_atom_map_from_gaussian_out(out_text)
        return "Gaussian", freq_data, intensities, atom_map

    freq_data, intensities = parse_orca_out_data(out_text)
    atom_map = parse_atom_map_from_orca_out(out_text)
    return "ORCA", freq_data, intensities, atom_map


# ------------------------------------------------------------
# DD2 parser and lookup CSV export
# ------------------------------------------------------------

def parse_dd2(dd2_path: str) -> dict:
    try:
        text = Path(dd2_path).read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        log_caution(f"Failed to read dd2: {dd2_path}")
        log_error("parse_dd2", e)
        return {"coords": []}

    lines = [ln.rstrip("\n") for ln in text.splitlines()]
    coord_rows: List[dict] = []
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
    try:
        dd2 = parse_dd2(dd2_path)
        coords = dd2.get("coords", []) or []
        if not coords:
            raise ValueError("dd2 coords empty")

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
        log_error("export_internal_coordinate_lookup_csv", e)
        raise


# ------------------------------------------------------------
# ORCA .out parser (Fixed Regex Patterns)
# ------------------------------------------------------------

def parse_orca_out_data(out_text: str):
    lines = out_text.splitlines()
    n_lines = len(lines)

    freq_data: Dict[int, dict] = {}
    intensities: Dict[int, float] = {}

    re_freq_line = re.compile(
        r"^\s*(\d+)\s*:\s*([+-]?(?:\d*\.\d+|\d+\.\d*|\d+)(?:[EeDd][+-]?\d+)?)\s+cm(?:\*\*)?-1(?:\s+(.*))?$",
        re.IGNORECASE
    )
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


def parse_ved_matrix_stitched(lines: List[str], label: str, start_from_idx: int = 0) -> Tuple[int, int, List[List[float]], List[int], int, str]:
    lab = label.strip().upper()
    start_idx = None
    matched_header = ""
    for i in range(start_from_idx, len(lines)):
        s = lines[i].strip()
        if not s:
            continue
        if re.match(rf"^{re.escape(lab)}\s*:?", s, flags=re.IGNORECASE):
            start_idx = i
            matched_header = s
            break
    if start_idx is None:
        raise ValueError(f"{label} header not found")

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

        if s.upper().startswith("PED:") and lab != "PED":
            break
        if s.upper().startswith("TED:") and lab != "TED":
            break
        if lab == "PED" and re.match(r"^PED\s*:", s, flags=re.IGNORECASE) and i > start_idx + 1:
            break
        if lab == "TED" and re.match(r"^TED\s*:", s, flags=re.IGNORECASE) and i > start_idx + 1:
            break
        if re.match(r"^-+\s*$", s) and (mode_to_colvals or mode_to_listvals):
            break

        toks = s.split()

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
                    continue

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
                    log_caution(f"{label} row length mismatch: mode={mode} values={len(vals)} header_cols={len(current_cols)}")
                d = mode_to_colvals.setdefault(mode, {})
                for k in range(n):
                    d[current_cols[k]] = vals[k]
            else:
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
        return n_modes, n_cols, matrix, col_ids_order, i, matched_header

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
    return n_modes, n_cols, matrix2, col_ids_legacy, i, matched_header


def _extract_ved_frequencies(lines: List[str], n_modes_hint: Optional[int]) -> List[float]:
    if not lines:
        return []

    stop = None
    for idx, ln in enumerate(lines):
        s = ln.strip().upper()
        if s.startswith("PED:") or s.startswith("TED:"):
            stop = idx
            break
    header_region = lines[:stop] if stop is not None else lines

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
        if all((k in freq_by_mode) for k in range(1, n_modes_hint + 1)):
            return [float(freq_by_mode[k]) for k in range(1, n_modes_hint + 1)]

    start_idxs: List[int] = []
    for idx, ln in enumerate(header_region):
        u = ln.upper()
        if "FREQUENCIES" in u or re.search(r"\bFREQ\b", u):
            start_idxs.append(idx)

    modefreq_re = re.compile(
        r"^\s*(\d+)\s*[:\)]?\s*([+-]?(?:\d*\.\d+|\d+\.\d*|\d+)(?:[EeDd][+-]?\d+)?)\b"
    )

    for sidx in start_idxs:
        freq_by_mode2: Dict[int, float] = {}
        section_lines: List[str] = []
        for ln in header_region[sidx:sidx + 500]:
            section_lines.append(ln)
            if not ln.strip():
                if freq_by_mode2:
                    break
                continue
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

        if n_modes_hint:
            float_re = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.\d*|\d+)(?:[EeDd][+-]?\d+)?")
            nums: List[float] = []
            for ln in section_lines:
                s = ln.strip()
                if not s:
                    continue
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

                if re.match(r"^\s*\d+\s", ln) and len(vals) >= 2 and float(vals[0]).is_integer():
                    vals = vals[1:]

                for v in vals:
                    if abs(v) <= 10000.0:
                        nums.append(v)

                if len(nums) >= n_modes_hint:
                    return nums[:n_modes_hint]

    return []


def parse_ved_freqs_and_matrices(ved_input: Any):
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
        return [], None, []

    lines = text.splitlines()
    ted_block = None
    ped_blocks = []

    try:
        n_m, n_c, ted_m, ted_cols, _, _ = parse_ved_matrix_stitched(lines, "TED")
        ted_block = {"n_modes": n_m, "n_cols": n_c, "matrix": ted_m, "col_ids": ted_cols}
    except Exception as e:
        log_message(f"TED matrix not available: {e}")

    curr_idx = 0
    while curr_idx < len(lines):
        try:
            n_m, n_c, ped_m, ped_cols, next_idx, header = parse_ved_matrix_stitched(lines, "PED", start_from_idx=curr_idx)
            
            target_code = "s"
            if "ALTERNATIVE" in header.upper():
                target_code = "k"
                if "ALTERNATIVE2" in header.upper():
                    target_code = "v"
            
            ped_blocks.append({
                "header": header,
                "target_code": target_code,
                "n_modes": n_m,
                "n_cols": n_c,
                "matrix": ped_m,
                "col_ids": ped_cols
            })
            curr_idx = next_idx
        except Exception:
            break

    n_modes_hint = None
    if ped_blocks and isinstance(ped_blocks[0].get("n_modes"), int):
        n_modes_hint = int(ped_blocks[0]["n_modes"])
    elif ted_block and isinstance(ted_block.get("n_modes"), int):
        n_modes_hint = int(ted_block["n_modes"])

    freqs_ved = _extract_ved_frequencies(lines, n_modes_hint)

    if n_modes_hint and not freqs_ved:
        log_caution(f"VEDA frequency extraction failed (expected {n_modes_hint} modes). ORCA↔VEDA mapping will be skipped.")

    return freqs_ved, ted_block, ped_blocks


# ------------------------------------------------------------
# ORCA ↔ VEDA mode mapping
# ------------------------------------------------------------

def _align_ordered_by_frequency(shorter: List[Tuple[int, float]], longer: List[Tuple[int, float]]):
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
    stats = {
        "n_veda": len(freqs_ved) if freqs_ved else 0,
        "n_orca": len(orca_freq_data) if orca_freq_data else 0,
        "n_matched": 0,
        "max_abs_diff": None,
        "mean_abs_diff": None,
    }

    if not freqs_ved or not orca_freq_data:
        log_caution("VEDA or ORCA frequency data is empty: mapping skipped.")
        return {}, {}, stats

    veda_items = [(i + 1, float(f)) for i, f in enumerate(freqs_ved)]
    orca_items: List[Tuple[int, float]] = []
    for k, data in orca_freq_data.items():
        try:
            orca_items.append((int(k), float(data.get("freq", 0.0))))
        except Exception:
            continue

    if not orca_items:
        log_caution("ORCA frequency data exists but no valid pairs parsed.")
        return {}, {}, stats

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
        log_caution("Failed to align VEDA↔ORCA by frequency.")
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
        try:
            vmax = max(abs(float(f)) for f in freqs_ved) if freqs_ved else 0.0
            omax = max(abs(float(d.get("freq", 0.0))) for d in orca_freq_data.values()) if orca_freq_data else 0.0
            denom = max(vmax, omax, 1.0)
        except Exception:
            denom = 1.0
        rel = float(stats["max_abs_diff"]) / denom
        if rel >= 0.05:
            log_caution(f"ORCA↔VEDA large frequency diffs: max |Δ|={stats['max_abs_diff']:.2f} cm^-1")
        else:
            log_message(f"ORCA↔VEDA: max |Δ|={stats['max_abs_diff']:.2f} cm^-1 exceeds tol, but relative diff is small.")

    return veda_to_orca, orca_to_veda, stats


# ------------------------------------------------------------
# PED row normalization check
# ------------------------------------------------------------

def _ped_percent_matrix_with_check(mat: List[List[float]], target: float = 100.0, tol: float = 1.0):
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
# PED columns ↔ dd2 coordinates
# ------------------------------------------------------------

def build_ped_column_coord_map(ped_col_ids: List[int], dd2_coords: List[dict], target_code: str = "s"):
    cautions: List[str] = []

    if not ped_col_ids or not dd2_coords:
        cautions.append("PED column IDs or dd2 coords are empty: cannot label PED columns.")
        return {}, cautions

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

    best_by_id: Dict[int, dict] = {}
    best_code_by_id: Dict[int, str] = {}
    for cid, lst in rows_by_id.items():
        chosen = None
        for r in lst:
            if (r.get("coord_code") or "").lower() == target_code.lower():
                chosen = r
                break
        if chosen is None and target_code.lower() != "s":
            for r in lst:
                if (r.get("coord_code") or "").lower() == "s":
                    chosen = r
                    break
        if chosen is None:
            chosen = lst[0]
            
        best_by_id[cid] = chosen
        best_code_by_id[cid] = (chosen.get("coord_code") or "")

    if len(set(ped_col_ids)) != len(ped_col_ids):
        cautions.append("PED column IDs contain duplicates (VEDA header may be malformed).")

    missing_ids: List[int] = []
    colpos_to_info: Dict[int, dict] = {}
    for pos, cid in enumerate(ped_col_ids, start=1):
        c_obj = best_by_id.get(cid)
        if c_obj is None:
            missing_ids.append(cid)
        all_candidates = rows_by_id.get(cid, []) or []
        code_candidates = [r for r in all_candidates if (r.get("coord_code") or "").lower() == target_code.lower()]
        if not code_candidates and target_code.lower() != "s":
            code_candidates = [r for r in all_candidates if (r.get("coord_code") or "").lower() == "s"]
        colpos_to_info[pos] = {
            "ped_col": pos,
            "coord_id": cid,
            "coord_code": best_code_by_id.get(cid, ""),
            "coord": c_obj,
            "coord_candidates": code_candidates or all_candidates,
        }

    if missing_ids:
        preview = ", ".join(map(str, missing_ids[:12]))
        more = "" if len(missing_ids) <= 12 else f" ... (+{len(missing_ids) - 12})"
        cautions.append(f"dd2 coord_id not found for some PED column IDs: {preview}{more}")

    return colpos_to_info, cautions



# ------------------------------------------------------------
# GUI text and target-tracking extension
# ------------------------------------------------------------

DEFAULT_TOP_N_TERMS = 6
DEFAULT_LONG_MIN_PED = 0.1
DEFAULT_TARGET_MIN_PED = 0.1
DEFAULT_TARGET_TOTAL_PED = 1.0

METAL_ELEMENTS = set("""
Li Be Na Mg Al K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Cs Ba
La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Fr Ra Ac Th Pa U
""".split())

MAIN_DESCRIPTION = f"""Target-tracking PED analyzer for VEDA/DD2/QC output files.
Version: {APP_VERSION} ({APP_RELEASE_DATE})

This program keeps the original mode-centered PED export, and adds coordinate-centered analysis:
- Long PED table: rank 7 and below are searchable.
- Target hits: selected internal coordinates are traced across all vibrational modes.
- Target summaries: selected internal coordinates can be tracked by total target PED, including mixed standard/alternative coordinates.
"""

USAGE_MANUAL = """Recommended workflow

1. Files / Precheck
   Select .ved, .dd2, optional .fmu, and QC output (.out/.log). Press Load / Precheck.

2. Coordinate Browser
   Filter DD2 internal coordinates. Filter DD2 internal coordinates. Use coordinate-set-qualified targets such as s:83, k:126, or v:76.
   For metal-ligand stretches, use group=STRE and metal atom index, or press Auto-detect metal-ligand stretches.

3. Target Definition
   Confirm the target coordinate references. Set a frequency range and PED thresholds.

4. Run Analysis
   Export the standard top-N table, long PED table, target hits, and target summaries.

Key output files

- *_PED_table_*.csv
  Original-style mode-centered table with top-N PED terms.

- *_PED_terms_long_*.csv
  Long-format PED table. Use this when an internal coordinate is hidden below rank 6.

- *_target_hits_*.csv
  Every selected coordinate detected in each mode, with PED value and rank.

- *_target_summary_by_mode_*.csv
  Main table for split metal-ligand stretches. Modes are ranked by total target PED.

- *_target_summary_by_coord_*.csv
  Coordinate-centered summary: where each target coordinate appears most strongly.

- *_target_matrix_*.csv
  Matrix format: rows are modes and columns are target coordinates. Useful for Excel heatmaps.
"""


def _parse_int_list(text: Any) -> List[int]:
    if text is None:
        return []
    out: List[int] = []
    for tok in re.findall(r"[+-]?\d+", str(text)):
        try:
            out.append(int(tok))
        except Exception:
            continue
    return out


def _parse_atom_filter_requirements(text: Any) -> List[set]:
    """Parse the Coordinate Browser atom filter.

    Semantics:
    - ``3`` shows coordinates containing atom 3.
    - ``3,12`` or ``3 12`` shows coordinates containing atom 3 OR atom 12
      (backward-compatible behaviour).
    - ``3-12`` / ``3–12`` / ``3－12`` shows coordinates containing BOTH
      atom 3 and atom 12. This is intended for bond/pair searches.
    - Multiple pair expressions are OR'ed, e.g. ``3-12; 4-11``.

    Return a list of required atom sets; a row matches if any set is a subset
    of that row's atom list.
    """
    if text is None:
        return []
    s = str(text).strip()
    if not s:
        return []
    # Normalize common dash variants used in Japanese/Windows input.
    s_norm = s.replace("–", "-").replace("—", "-").replace("−", "-").replace("－", "-")
    reqs: List[set] = []
    consumed = []

    # Treat a-b as a pair/bond query, not as a numeric range.
    pair_pat = re.compile(r"(?<!\d)(\d+)\s*-\s*(\d+)(?!\d)")
    for m in pair_pat.finditer(s_norm):
        try:
            a = int(m.group(1)); b = int(m.group(2))
        except Exception:
            continue
        req = {a, b}
        if req and req not in reqs:
            reqs.append(req)
        consumed.append((m.start(), m.end()))

    # Remove pair spans before parsing singleton OR terms.
    chars = list(s_norm)
    for a, b in consumed:
        for i in range(a, b):
            chars[i] = " "
    rest = "".join(chars)
    for tok in re.findall(r"\d+", rest):
        try:
            req = {int(tok)}
        except Exception:
            continue
        if req and req not in reqs:
            reqs.append(req)
    return reqs


def _normalize_coord_group(group: Any) -> str:
    g = str(group or "").strip().upper()
    if not g:
        return "*"
    if g.startswith("STRE"):
        return "STRE"
    if g.startswith("BEND"):
        return "BEND"
    if g.startswith("TORS"):
        return "TORS"
    return g


def _make_target_ref(code: Any, group: Any = None, coord_id: Any = None) -> str:
    """Return a group-qualified coordinate reference, e.g. k:STRE:126.

    The three-part reference is required because VEDA/DD2 may reuse the same
    code+coord_id for different coordinate groups such as STRE and BEND.
    For backward compatibility, two-argument calls produce code:*:coord_id.
    """
    if coord_id is None:
        coord_id = group
        group = "*"
    c = str(code or "s").strip().lower() or "s"
    g = _normalize_coord_group(group)
    try:
        cid = int(coord_id)
    except Exception:
        cid = str(coord_id).strip()
    return f"{c}:{g}:{cid}"


def _split_target_ref(ref: Any) -> Tuple[str, str, int]:
    parts = str(ref or "").strip().split(":")
    if len(parts) == 3:
        code, group, cid = parts
    elif len(parts) == 2:
        code, cid = parts
        group = "*"
    elif len(parts) == 1 and parts[0]:
        code, group, cid = "s", "*", parts[0]
    else:
        raise ValueError("empty target reference")
    return (str(code or "s").lower(), _normalize_coord_group(group), int(cid))


def _target_ref_matches(concrete_ref: Any, requested_refs: set) -> bool:
    """Return True when a concrete code:group:id ref is selected.

    Wildcard forms from older configs are accepted: k:*:126 or s:*:83.
    """
    try:
        c, g, cid = _split_target_ref(concrete_ref)
    except Exception:
        return False
    wanted = {str(r).lower() for r in requested_refs}
    g_l = str(g).lower()
    return (
        f"{c}:{g_l}:{cid}" in wanted or
        f"{c}:*:{cid}" in wanted or
        f"*:{g_l}:{cid}" in wanted or
        f"*:*:{cid}" in wanted
    )


def _parse_target_refs(text: Any, default_code: str = "s") -> List[str]:
    """Parse target references from free text.

    Preferred examples: ``s:STRE:83``, ``k:STRE:126``, ``v:BEND:81``.
    Backward-compatible examples: ``s:83`` -> ``s:*:83`` and ``83`` -> ``s:*:83``.
    """
    if text is None:
        return []
    s = str(text)
    refs: List[str] = []
    seen = set()

    # Preferred three-part refs.
    pat3 = r"(?i)\b([skv])\s*[:：]\s*([A-Za-z0-9_]+)\s*[:：]\s*([0-9]+)\b"
    for m in re.finditer(pat3, s):
        ref = _make_target_ref(m.group(1), m.group(2), m.group(3))
        if ref not in seen:
            seen.add(ref); refs.append(ref)

    stripped = re.sub(pat3, " ", s)
    # Legacy two-part refs.
    pat2 = r"(?i)\b([skv])\s*[:：]\s*([0-9]+)\b"
    for m in re.finditer(pat2, stripped):
        ref = _make_target_ref(m.group(1), "*", m.group(2))
        if ref not in seen:
            seen.add(ref); refs.append(ref)

    stripped = re.sub(pat2, " ", stripped)
    for tok in re.findall(r"\b[0-9]+\b", stripped):
        ref = _make_target_ref(default_code, "*", tok)
        if ref not in seen:
            seen.add(ref); refs.append(ref)
    return refs


def _sort_target_refs(refs) -> List[str]:
    order = {"s": 0, "k": 1, "v": 2, "*": 9}
    gorder = {"STRE": 0, "BEND": 1, "TORS": 2, "*": 9}
    def key(ref):
        try:
            code, group, cid = _split_target_ref(ref)
            return (order.get(code, 8), gorder.get(group, 8), int(cid))
        except Exception:
            return (9, 9, str(ref))
    return sorted(set(str(r) for r in refs if str(r).strip()), key=key)


def _parse_symbol_list(text: Any) -> List[str]:
    if text is None:
        return []
    vals: List[str] = []
    for tok in re.split(r"[,;\s]+", str(text).strip()):
        tok = tok.strip()
        if not tok:
            continue
        if re.fullmatch(r"[A-Za-z]{1,3}", tok):
            vals.append(tok.capitalize())
    return vals


def _parse_optional_float(text: Any) -> Optional[float]:
    s = "" if text is None else str(text).strip()
    if not s:
        return None
    try:
        return float(safe_float(s))
    except Exception:
        return None


def _code_output_label(code: str) -> str:
    c = (code or "").strip().lower()
    if c == "s":
        return "standard"
    if c == "k":
        return "alternative_k"
    if c == "v":
        return "alternative_v"
    return c or "unknown"


def _is_standard_ped_block(ped_block: Optional[dict]) -> bool:
    """Return True when a PED block is the standard VEDA PED block."""
    if not ped_block:
        return False
    code = str(ped_block.get("target_code", "s") or "s").strip().lower()
    header = str(ped_block.get("header", "") or "").upper()
    return code == "s" and "ALTERNATIVE" not in header


def _select_ped_block_for_coordinate_code(ped_blocks: List[dict], code: str) -> Tuple[Optional[dict], bool]:
    """Select the PED matrix to use for a requested coordinate-set code.

    VEDA/DD2 often contains alternative coordinate rows (k/v) even when the .ved
    file provides only a single PED matrix.  In that common case, alternative
    interpretation should mean: use the standard PED matrix columns and label
    those columns with the requested DD2 coordinate set.

    Returns (ped_block, reinterpreted_from_standard).  The flag is True when no
    PED block explicitly matching ``code`` was found and a standard/first block
    is used as a matrix source.
    """
    c = str(code or "s").strip().lower() or "s"
    blocks = list(ped_blocks or [])
    if not blocks:
        return None, True

    exact = [b for b in blocks if str(b.get("target_code", "s") or "s").strip().lower() == c]
    if exact:
        # For s, prefer a block whose header is not ALTERNATIVE.  For k/v, the
        # target_code assigned by parse_ved_freqs_and_matrices is already the
        # best available marker.
        if c == "s":
            for b in exact:
                if _is_standard_ped_block(b):
                    return b, False
        return exact[0], False

    for b in blocks:
        if _is_standard_ped_block(b):
            return b, True

    return blocks[0], True


def _format_atom(idx: int, atom_map: Optional[Dict[int, str]]) -> str:
    amap = atom_map or {}
    el = amap.get(idx, "")
    if el:
        return f"{el}{idx}"
    return f"#{idx}"


def _coord_atom_label(c_obj: Optional[dict], atom_map: Optional[Dict[int, str]]) -> str:
    if not c_obj:
        return ""
    atoms = c_obj.get("atoms", []) or []
    return "-".join(_format_atom(int(a), atom_map) for a in atoms)


def _coord_label(c_obj: Optional[dict], atom_map: Optional[Dict[int, str]], include_raw: bool = True) -> str:
    if not c_obj:
        return "UNKNOWN"
    group = (c_obj.get("coord_group", "") or "").upper()
    atoms = c_obj.get("atoms", []) or []
    atom_label = _coord_atom_label(c_obj, atom_map)
    if group.startswith("STRE") and len(atoms) == 2:
        body = f"str({atom_label})"
    elif group.startswith("BEND") and len(atoms) == 3:
        body = f"bend({atom_label})"
    elif group.startswith("TORS") and len(atoms) == 4:
        body = f"tors({atom_label})"
    else:
        body = f"{group}({atom_label})" if atom_label else group
    raw = c_obj.get("coord_label_raw", "") or ""
    if include_raw and raw:
        body += f"[{raw}]"
    return body


def _coord_group(c_obj: Optional[dict]) -> str:
    if not c_obj:
        return ""
    return (c_obj.get("coord_group", "") or "")


def _coord_code(c_obj: Optional[dict]) -> str:
    if not c_obj:
        return ""
    return (c_obj.get("coord_code", "") or "")


def _coord_id(c_obj: Optional[dict], fallback: Any = "") -> Any:
    if not c_obj:
        return fallback
    cid = c_obj.get("coord_id", fallback)
    return cid if cid is not None else fallback


def _freq_in_range(freq: float, fmin: Optional[float], fmax: Optional[float]) -> bool:
    try:
        f = float(freq)
    except Exception:
        return False
    if fmin is not None and f < fmin:
        return False
    if fmax is not None and f > fmax:
        return False
    return True


def _coord_matches_metal_ligand_stretch(
    c_obj: Optional[dict],
    atom_map: Optional[Dict[int, str]],
    metal_atoms: Optional[List[int]] = None,
    ligand_atoms: Optional[List[int]] = None,
    ligand_elements: Optional[List[str]] = None,
) -> bool:
    if not c_obj:
        return False
    group = (c_obj.get("coord_group", "") or "").upper()
    atoms = [int(a) for a in (c_obj.get("atoms", []) or [])]
    if not group.startswith("STRE") or len(atoms) != 2:
        return False

    metal_set = set(int(a) for a in (metal_atoms or []))
    ligand_atom_set = set(int(a) for a in (ligand_atoms or []))
    ligand_el_set = set(e.capitalize() for e in (ligand_elements or []))
    amap = atom_map or {}

    def is_metal_atom(a: int) -> bool:
        if metal_set:
            return a in metal_set
        return amap.get(a, "").capitalize() in METAL_ELEMENTS

    metal_side = [a for a in atoms if is_metal_atom(a)]
    if not metal_side:
        return False

    other_side = [a for a in atoms if a not in metal_side]
    if not other_side:
        return False

    if ligand_atom_set and not any(a in ligand_atom_set for a in other_side):
        return False

    if ligand_el_set:
        other_els = set((amap.get(a, "") or "").capitalize() for a in other_side)
        if not (other_els & ligand_el_set):
            return False

    return True


class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title(f"{APP_VERSION_LABEL} (Target Coordinate Tracking)")
        self.geometry("1120x780")

        self.ved_path: Optional[str] = None
        self.dd2_path: Optional[str] = None
        self.fmu_path: Optional[str] = None
        self.out_path: Optional[str] = None
        self.output_dir_path: Optional[str] = None

        self._cfg = load_config()
        self.analysis_ctx: Optional[dict] = None
        self.coordinate_rows: List[dict] = []
        self._preview_dfs: Dict[str, pd.DataFrame] = {}

        self._build_gui()
        self._apply_config_on_startup()

    # -----------------------------
    # GUI construction
    # -----------------------------

    def _build_gui(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        self.tab_files = ttk.Frame(nb)
        self.tab_coords = ttk.Frame(nb)
        self.tab_target = ttk.Frame(nb)
        self.tab_run = ttk.Frame(nb)
        self.tab_results = ttk.Frame(nb)
        self.tab_usage = ttk.Frame(nb)

        nb.add(self.tab_files, text="Files / Precheck")
        nb.add(self.tab_coords, text="Coordinate Browser")
        nb.add(self.tab_target, text="Target Definition")
        nb.add(self.tab_run, text="Run Analysis")
        nb.add(self.tab_results, text="Results Preview")
        nb.add(self.tab_usage, text="User Guide")

        self._build_files_tab()
        self._build_coordinate_tab()
        self._build_target_tab()
        self._build_run_tab()
        self._build_results_tab()
        self._build_usage_tab()

    def _build_files_tab(self):
        main = self.tab_files
        main.columnconfigure(0, weight=1)
        desc = tk.Label(main, text=MAIN_DESCRIPTION, justify="left", anchor="w", wraplength=1040)
        desc.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))

        frame = ttk.LabelFrame(main, text="Input files", padding=10)
        frame.grid(row=1, column=0, sticky="ew", padx=12, pady=6)
        frame.columnconfigure(1, weight=1)
        self._labels: Dict[str, tk.Label] = {}

        def make_row(r: int, lbl_text: str, attr_name: str, file_types):
            btn = tk.Button(frame, text=lbl_text, width=22,
                            command=lambda: self._select_file(attr_name, file_types))
            btn.grid(row=r, column=0, sticky="w", pady=3)
            lbl = tk.Label(frame, text="(Not selected)", fg="gray", anchor="w")
            lbl.grid(row=r, column=1, sticky="ew", padx=10, pady=3)
            self._labels[attr_name] = lbl

        make_row(0, "Select .ved", "ved_path", [("VEDA files", "*.ved"), ("All files", "*.*")])
        make_row(1, "Select .dd2", "dd2_path", [("DD2 files", "*.dd2"), ("All files", "*.*")])
        make_row(2, "Select .fmu", "fmu_path", [("FMU files", "*.fmu"), ("All files", "*.*")])
        make_row(3, "Select QC output", "out_path", [("QC output", "*.out *.log"), ("All files", "*.*")])

        btn_out = tk.Button(frame, text="Select output folder", width=22, command=self._select_output_dir)
        btn_out.grid(row=4, column=0, sticky="w", pady=3)
        lbl_out = tk.Label(frame, text="(Same folder as .ved)", fg="gray", anchor="w")
        lbl_out.grid(row=4, column=1, sticky="ew", padx=10, pady=3)
        self._labels["output_dir_path"] = lbl_out

        action = ttk.Frame(main)
        action.grid(row=2, column=0, sticky="ew", padx=12, pady=(8, 4))
        ttk.Button(action, text="Load / Precheck", command=self.precheck).pack(side="left")
        self.status_lbl = tk.Label(action, text="Ready", fg="blue", anchor="w")
        self.status_lbl.pack(side="left", padx=12, fill="x", expand=True)

        pre = ttk.LabelFrame(main, text="Precheck summary", padding=6)
        pre.grid(row=3, column=0, sticky="nsew", padx=12, pady=6)
        main.rowconfigure(3, weight=1)
        pre.rowconfigure(0, weight=1)
        pre.columnconfigure(0, weight=1)
        self.precheck_text = scrolledtext.ScrolledText(pre, wrap="word", height=16)
        self.precheck_text.grid(row=0, column=0, sticky="nsew")

    def _make_tree_with_scrollbars(self, parent, height: int = 15) -> ttk.Treeview:
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, show="headings", height=height, selectmode="extended")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return tree

    def _build_coordinate_tab(self):
        tab = self.tab_coords
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(2, weight=1)

        filters = ttk.LabelFrame(tab, text="Filters", padding=8)
        filters.grid(row=0, column=0, sticky="ew", padx=12, pady=8)

        self.filter_code_var = tk.StringVar(value=_code_display("s"))
        self.filter_group_var = tk.StringVar(value=_group_display("STRE"))
        self.filter_atom_var = tk.StringVar(value="")
        self.filter_element_var = tk.StringVar(value="")
        self.filter_label_var = tk.StringVar(value="")

        ttk.Label(filters, text="Coordinate set").grid(row=0, column=0, sticky="w")
        self.filter_code_combo = ttk.Combobox(filters, textvariable=self.filter_code_var, values=[_code_display("s"), _code_display("k"), _code_display("v"), "(any)"], width=18, state="readonly")
        self.filter_code_combo.grid(row=0, column=1, padx=4, sticky="w")

        ttk.Label(filters, text="Group").grid(row=0, column=2, sticky="w")
        self.filter_group_combo = ttk.Combobox(filters, textvariable=self.filter_group_var, values=[_group_display("STRE"), "(any)"], width=20, state="readonly")
        self.filter_group_combo.grid(row=0, column=3, padx=4, sticky="w")

        ttk.Label(filters, text="Atom filter").grid(row=0, column=4, sticky="w")
        ttk.Entry(filters, textvariable=self.filter_atom_var, width=18).grid(row=0, column=5, padx=4, sticky="w")

        ttk.Label(filters, text="Contains element").grid(row=1, column=0, sticky="w", pady=(5, 0))
        ttk.Entry(filters, textvariable=self.filter_element_var, width=14).grid(row=1, column=1, padx=4, sticky="w", pady=(5, 0))

        ttk.Label(filters, text="Text filter").grid(row=1, column=2, sticky="w", pady=(5, 0))
        ttk.Entry(filters, textvariable=self.filter_label_var, width=30).grid(row=1, column=3, columnspan=3, padx=4, sticky="ew", pady=(5, 0))
        filters.columnconfigure(3, weight=1)

        help_text = (
            "Atom filter: 3 = contains atom 3; 3,12 = contains atom 3 OR 12; "
            "3-12 = contains BOTH atoms 3 and 12.  "
            "Text filter: searches atom label / VEDA label / raw label, e.g. C4-C11, CC, ZnO, str."
        )
        ttk.Label(filters, text=help_text, foreground="#555555", wraplength=980, justify="left").grid(
            row=2, column=0, columnspan=6, sticky="w", pady=(6, 0)
        )

        buttons = ttk.Frame(tab)
        buttons.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))
        ttk.Button(buttons, text="Apply filter", command=self.refresh_coordinate_table).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Add selected to target", command=self.add_selected_coords_to_target).pack(side="left", padx=6)
        ttk.Button(buttons, text="Auto-detect metal-ligand stretches", command=self.auto_detect_target_coords).pack(side="left", padx=6)
        ttk.Button(buttons, text="Clear filter", command=self.clear_coordinate_filters).pack(side="left", padx=6)

        table_frame = ttk.LabelFrame(tab, text="DD2 internal coordinates", padding=6)
        table_frame.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.coord_tree = self._make_tree_with_scrollbars(table_frame, height=20)
        self._configure_coord_tree()

    def _configure_coord_tree(self):
        cols = ["coord_id", "code", "group", "atoms", "atom_label", "label", "raw_label"]
        self.coord_tree["columns"] = cols
        widths = {
            "coord_id": 80,
            "code": 50,
            "group": 90,
            "atoms": 120,
            "atom_label": 180,
            "label": 320,
            "raw_label": 160,
        }
        for c in cols:
            self.coord_tree.heading(c, text=c)
            self.coord_tree.column(c, width=widths.get(c, 120), anchor="w")

    def _build_target_tab(self):
        tab = self.tab_target
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(2, weight=1)

        settings = ttk.LabelFrame(tab, text="Target coordinate set", padding=8)
        settings.grid(row=0, column=0, sticky="ew", padx=12, pady=8)
        settings.columnconfigure(1, weight=1)

        self.target_name_var = tk.StringVar(value="target_coordinates")
        self.metal_atoms_var = tk.StringVar(value="")
        self.ligand_atoms_var = tk.StringVar(value="")
        self.ligand_elements_var = tk.StringVar(value="N O S P Cl Br I")
        self.use_rule_if_empty_var = tk.BooleanVar(value=True)

        ttk.Label(settings, text="Target set name").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(settings, textvariable=self.target_name_var, width=32).grid(row=0, column=1, sticky="w", pady=3)

        ttk.Label(settings, text="Metal atom index/indices").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(settings, textvariable=self.metal_atoms_var, width=32).grid(row=1, column=1, sticky="w", pady=3)
        ttk.Label(settings, text="Blank = auto-detect metallic elements").grid(row=1, column=2, sticky="w", padx=8)

        ttk.Label(settings, text="Ligand atom indices").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(settings, textvariable=self.ligand_atoms_var, width=32).grid(row=2, column=1, sticky="w", pady=3)
        ttk.Label(settings, text="Optional").grid(row=2, column=2, sticky="w", padx=8)

        ttk.Label(settings, text="Ligand elements").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Entry(settings, textvariable=self.ligand_elements_var, width=32).grid(row=3, column=1, sticky="w", pady=3)
        ttk.Label(settings, text="Example: N O S Cl").grid(row=3, column=2, sticky="w", padx=8)

        ttk.Checkbutton(settings, text="If target ID list is empty, use the metal-ligand stretch rule", variable=self.use_rule_if_empty_var).grid(row=4, column=0, columnspan=3, sticky="w", pady=3)

        ids_frame = ttk.LabelFrame(tab, text="Target coordinate references", padding=8)
        ids_frame.grid(row=1, column=0, sticky="ew", padx=12, pady=6)
        ids_frame.columnconfigure(0, weight=1)
        self.target_ids_text = tk.Text(ids_frame, height=4, wrap="word")
        self.target_ids_text.grid(row=0, column=0, sticky="ew")
        id_buttons = ttk.Frame(ids_frame)
        id_buttons.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(id_buttons, text="Sort / Deduplicate refs", command=self.normalize_target_ids_text).pack(side="left", padx=(0, 6))
        ttk.Button(id_buttons, text="Replace by auto-detect", command=self.auto_detect_target_coords).pack(side="left", padx=6)
        ttk.Button(id_buttons, text="Clear target refs", command=self.clear_target_ids).pack(side="left", padx=6)
        ttk.Button(id_buttons, text="Refresh target preview", command=self.refresh_target_preview).pack(side="left", padx=6)

        preview_frame = ttk.LabelFrame(tab, text="Target coordinate preview", padding=6)
        preview_frame.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)
        self.target_tree = self._make_tree_with_scrollbars(preview_frame, height=12)
        self._configure_generic_tree(self.target_tree, ["target_ref", "coord_id", "code", "group", "atom_label", "label"])

    def _build_run_tab(self):
        tab = self.tab_run
        tab.columnconfigure(0, weight=1)

        opt = ttk.LabelFrame(tab, text="Output options", padding=8)
        opt.grid(row=0, column=0, sticky="ew", padx=12, pady=8)
        opt.columnconfigure(1, weight=1)

        self.output_standard_var = tk.BooleanVar(value=True)
        self.output_long_var = tk.BooleanVar(value=True)
        self.output_target_hits_var = tk.BooleanVar(value=True)
        self.output_summary_mode_var = tk.BooleanVar(value=True)
        self.output_summary_coord_var = tk.BooleanVar(value=True)
        self.output_target_matrix_var = tk.BooleanVar(value=True)
        self.output_combined_target_var = tk.BooleanVar(value=True)
        self.include_alternative_var = tk.BooleanVar(value=False)
        self.include_all_target_modes_var = tk.BooleanVar(value=False)

        self.top_n_var = tk.StringVar(value=str(DEFAULT_TOP_N_TERMS))
        self.standard_min_ped_var = tk.StringVar(value=str(DEFAULT_LONG_MIN_PED))
        self.long_min_ped_var = tk.StringVar(value=str(DEFAULT_LONG_MIN_PED))
        self.target_min_ped_var = tk.StringVar(value=str(DEFAULT_TARGET_MIN_PED))
        self.target_total_min_ped_var = tk.StringVar(value=str(DEFAULT_TARGET_TOTAL_PED))
        self.freq_min_var = tk.StringVar(value="")
        self.freq_max_var = tk.StringVar(value="")

        ttk.Checkbutton(opt, text="Standard top-N PED table", variable=self.output_standard_var).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(opt, text="Long PED table", variable=self.output_long_var).grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(opt, text="Target hits", variable=self.output_target_hits_var).grid(row=0, column=2, sticky="w")
        ttk.Checkbutton(opt, text="Target summary by mode", variable=self.output_summary_mode_var).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(opt, text="Target summary by coordinate", variable=self.output_summary_coord_var).grid(row=1, column=1, sticky="w")
        ttk.Checkbutton(opt, text="Target matrix", variable=self.output_target_matrix_var).grid(row=1, column=2, sticky="w")
        ttk.Checkbutton(opt, text="Combined target outputs (allow mixed s/k/v targets)", variable=self.output_combined_target_var).grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Checkbutton(opt, text="Include alternative coordinate sets (k/v)", variable=self.include_alternative_var).grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Checkbutton(opt, text="Include target modes below total threshold", variable=self.include_all_target_modes_var).grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 0))

        thresh = ttk.LabelFrame(tab, text="Thresholds and frequency range", padding=8)
        thresh.grid(row=1, column=0, sticky="ew", padx=12, pady=8)

        fields = [
            ("Top N in standard table", self.top_n_var),
            ("Standard table min PED (%)", self.standard_min_ped_var),
            ("Long table min PED (%)", self.long_min_ped_var),
            ("Target hit min PED (%)", self.target_min_ped_var),
            ("Target total min PED per mode (%)", self.target_total_min_ped_var),
            ("Freq min (cm^-1)", self.freq_min_var),
            ("Freq max (cm^-1)", self.freq_max_var),
        ]
        for i, (lbl, var) in enumerate(fields):
            r = i // 2
            c = (i % 2) * 2
            ttk.Label(thresh, text=lbl).grid(row=r, column=c, sticky="w", pady=3, padx=(0, 6))
            ttk.Entry(thresh, textvariable=var, width=14).grid(row=r, column=c + 1, sticky="w", pady=3, padx=(0, 18))

        run_frame = ttk.Frame(tab)
        run_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=14)
        tk.Button(run_frame, text="RUN TARGET ANALYSIS", font=("Arial", 12, "bold"), bg="#dddddd", command=self.run).pack(fill="x")

        self.run_text = scrolledtext.ScrolledText(tab, wrap="word", height=18)
        self.run_text.grid(row=3, column=0, sticky="nsew", padx=12, pady=8)
        tab.rowconfigure(3, weight=1)

    def _build_results_tab(self):
        tab = self.tab_results
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)

        self.results_text = scrolledtext.ScrolledText(tab, wrap="word", height=7)
        self.results_text.grid(row=0, column=0, sticky="ew", padx=12, pady=8)

        nb = ttk.Notebook(tab)
        nb.grid(row=1, column=0, sticky="nsew", padx=12, pady=8)

        self.preview_summary_mode_frame = ttk.Frame(nb)
        self.preview_hits_frame = ttk.Frame(nb)
        self.preview_summary_coord_frame = ttk.Frame(nb)
        nb.add(self.preview_summary_mode_frame, text="Summary by mode")
        nb.add(self.preview_hits_frame, text="Target hits")
        nb.add(self.preview_summary_coord_frame, text="Summary by coordinate")

        self.summary_mode_tree = self._make_tree_with_scrollbars(self.preview_summary_mode_frame, height=18)
        self.hits_tree = self._make_tree_with_scrollbars(self.preview_hits_frame, height=18)
        self.summary_coord_tree = self._make_tree_with_scrollbars(self.preview_summary_coord_frame, height=18)

    def _build_usage_tab(self):
        usage = self.tab_usage
        usage.columnconfigure(0, weight=1)
        usage.rowconfigure(0, weight=1)
        st = scrolledtext.ScrolledText(usage, wrap="word", font=("TkDefaultFont", 10))
        st.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        st.insert("1.0", USAGE_MANUAL)
        st.configure(state="disabled")

    # -----------------------------
    # Config and path helpers
    # -----------------------------

    def _apply_config_on_startup(self):
        for attr in ("ved_path", "dd2_path", "fmu_path", "out_path"):
            p = self._cfg.get(attr)
            if p and Path(p).is_file():
                self._set_path(attr, p, save=False)

        p_out = self._cfg.get("output_dir_path")
        if p_out and Path(p_out).is_dir():
            self._set_path("output_dir_path", p_out, save=False)

        if self.ved_path and Path(self.ved_path).is_file():
            self._auto_fill_related_files(self.ved_path, only_if_missing=True, save=False)

        self.target_name_var.set(self._cfg.get("target_name", self.target_name_var.get()))
        self.metal_atoms_var.set(self._cfg.get("metal_atoms", self.metal_atoms_var.get()))
        self.ligand_atoms_var.set(self._cfg.get("ligand_atoms", self.ligand_atoms_var.get()))
        self.ligand_elements_var.set(self._cfg.get("ligand_elements", self.ligand_elements_var.get()))
        self.use_rule_if_empty_var.set(bool(self._cfg.get("use_rule_if_empty", self.use_rule_if_empty_var.get())))

        target_ids = self._cfg.get("target_coord_ids", "")
        if target_ids:
            self.target_ids_text.delete("1.0", "end")
            self.target_ids_text.insert("1.0", str(target_ids))

        self.top_n_var.set(str(self._cfg.get("top_n", self.top_n_var.get())))
        self.standard_min_ped_var.set(str(self._cfg.get("standard_min_ped", self.standard_min_ped_var.get())))
        self.long_min_ped_var.set(str(self._cfg.get("long_min_ped", self.long_min_ped_var.get())))
        self.target_min_ped_var.set(str(self._cfg.get("target_min_ped", self.target_min_ped_var.get())))
        self.target_total_min_ped_var.set(str(self._cfg.get("target_total_min_ped", self.target_total_min_ped_var.get())))
        self.freq_min_var.set(str(self._cfg.get("freq_min", self.freq_min_var.get())))
        self.freq_max_var.set(str(self._cfg.get("freq_max", self.freq_max_var.get())))

        self.output_standard_var.set(bool(self._cfg.get("output_standard", self.output_standard_var.get())))
        self.output_long_var.set(bool(self._cfg.get("output_long", self.output_long_var.get())))
        self.output_target_hits_var.set(bool(self._cfg.get("output_target_hits", self.output_target_hits_var.get())))
        self.output_summary_mode_var.set(bool(self._cfg.get("output_summary_mode", self.output_summary_mode_var.get())))
        self.output_summary_coord_var.set(bool(self._cfg.get("output_summary_coord", self.output_summary_coord_var.get())))
        self.output_target_matrix_var.set(bool(self._cfg.get("output_target_matrix", self.output_target_matrix_var.get())))
        self.output_combined_target_var.set(bool(self._cfg.get("output_combined_target", self.output_combined_target_var.get())))
        self.include_alternative_var.set(bool(self._cfg.get("include_alternative", self.include_alternative_var.get())))
        self.include_all_target_modes_var.set(bool(self._cfg.get("include_all_target_modes", self.include_all_target_modes_var.get())))

        self._save_current_config()

    def _save_current_config(self):
        cfg = dict(self._cfg) if isinstance(self._cfg, dict) else {}
        cfg["ved_path"] = self.ved_path or ""
        cfg["dd2_path"] = self.dd2_path or ""
        cfg["fmu_path"] = self.fmu_path or ""
        cfg["out_path"] = self.out_path or ""
        cfg["output_dir_path"] = self.output_dir_path or ""

        last_dir = ""
        for p in (self.ved_path, self.dd2_path, self.fmu_path, self.out_path):
            if p and Path(p).exists():
                last_dir = str(Path(p).resolve().parent)
                break
        if last_dir:
            cfg["last_dir"] = last_dir

        try:
            cfg["target_name"] = self.target_name_var.get()
            cfg["metal_atoms"] = self.metal_atoms_var.get()
            cfg["ligand_atoms"] = self.ligand_atoms_var.get()
            cfg["ligand_elements"] = self.ligand_elements_var.get()
            cfg["use_rule_if_empty"] = bool(self.use_rule_if_empty_var.get())
            cfg["target_coord_ids"] = self.target_ids_text.get("1.0", "end").strip()
            cfg["top_n"] = self.top_n_var.get()
            cfg["standard_min_ped"] = self.standard_min_ped_var.get()
            cfg["long_min_ped"] = self.long_min_ped_var.get()
            cfg["target_min_ped"] = self.target_min_ped_var.get()
            cfg["target_total_min_ped"] = self.target_total_min_ped_var.get()
            cfg["freq_min"] = self.freq_min_var.get()
            cfg["freq_max"] = self.freq_max_var.get()
            cfg["output_standard"] = bool(self.output_standard_var.get())
            cfg["output_long"] = bool(self.output_long_var.get())
            cfg["output_target_hits"] = bool(self.output_target_hits_var.get())
            cfg["output_summary_mode"] = bool(self.output_summary_mode_var.get())
            cfg["output_summary_coord"] = bool(self.output_summary_coord_var.get())
            cfg["output_target_matrix"] = bool(self.output_target_matrix_var.get())
            cfg["output_combined_target"] = bool(self.output_combined_target_var.get())
            cfg["include_alternative"] = bool(self.include_alternative_var.get())
            cfg["include_all_target_modes"] = bool(self.include_all_target_modes_var.get())
        except Exception:
            pass

        self._cfg = cfg
        save_config(cfg)

    def _set_path(self, attr: str, path: Optional[str], save: bool = True):
        setattr(self, attr, path)
        lbl = self._labels.get(attr)
        if lbl:
            if path and Path(path).exists():
                lbl.config(text=path, fg="black")
            else:
                if attr == "output_dir_path":
                    lbl.config(text="(Same folder as .ved)", fg="gray")
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
        if attr == "ved_path":
            self._auto_fill_related_files(path, only_if_missing=False, save=False)
        self.analysis_ctx = None
        self._save_current_config()

    def _select_output_dir(self):
        initdir = self.output_dir_path or self._cfg.get("last_dir") or None
        path = filedialog.askdirectory(initialdir=initdir)
        if not path:
            return
        self._set_path("output_dir_path", path, save=True)

    def _auto_fill_related_files(self, ved_path: str, only_if_missing: bool, save: bool):
        p = Path(ved_path)
        if not p.exists():
            return

        cand = {
            "dd2_path": p.with_suffix(".dd2"),
            "fmu_path": p.with_suffix(".fmu"),
            "out_path": None,
        }

        out_cand = p.with_suffix(".out")
        log_cand = p.with_suffix(".log")
        if out_cand.exists():
            cand["out_path"] = out_cand
        elif log_cand.exists():
            cand["out_path"] = log_cand
        else:
            cand["out_path"] = out_cand

        filled: List[str] = []
        missing: List[str] = []

        for attr, fp in cand.items():
            if only_if_missing and getattr(self, attr, None):
                continue
            if fp and fp.is_file():
                self._set_path(attr, str(fp), save=False)
                filled.append(fp.name)
            else:
                if fp:
                    missing.append(fp.name)
                if not only_if_missing:
                    self._set_path(attr, None, save=False)

        if filled:
            log_message(f"Auto-fill: filled {', '.join(filled)}")
        if missing:
            log_message(f"Auto-fill: not found {', '.join(missing)} in {p.parent}")

        if save:
            self._save_current_config()

    # -----------------------------
    # Precheck and coordinate table
    # -----------------------------

    def _set_text(self, widget, text: str):
        widget.delete("1.0", "end")
        widget.insert("1.0", text)

    def precheck(self):
        if not (self.ved_path and self.dd2_path and self.out_path):
            messagebox.showwarning("Missing Files", "Required files: .ved, .dd2, QC output (.out/.log).")
            return

        try:
            self.status_lbl.config(text="Prechecking...", fg="blue")
            self.update()

            freqs_ved, ted_blk, ped_blks = parse_ved_freqs_and_matrices(Path(self.ved_path))
            if not ped_blks:
                raise ValueError("No PED matrix found in .ved file.")

            dd2_data = parse_dd2(self.dd2_path)
            coords = dd2_data.get("coords", []) or []
            if not coords:
                log_caution("dd2 coords are empty. Coordinate labels may become UNKNOWN.")

            available_codes = sorted(list(set((c.get("coord_code") or "").lower() for c in coords if c.get("coord_code"))))
            if not available_codes:
                available_codes = ["s"]

            atom_map: Dict[int, str] = {}
            if self.fmu_path:
                atom_map = parse_atom_map_from_fmu(self.fmu_path)

            try:
                out_text = Path(self.out_path).read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                log_caution(f"Failed to read QC output: {self.out_path}")
                log_error("precheck read out", e)
                out_text = ""
            if not out_text:
                raise ValueError("QC output file could not be read or is empty.")

            engine, qc_freq_data, qc_intensities, qc_atom_map = parse_qchem_output(out_text)
            if not qc_freq_data:
                raise ValueError(f"No vibrational frequency data parsed from QC output (engine={engine}).")

            if not atom_map:
                atom_map = qc_atom_map or {}
            if not atom_map:
                log_caution("Atom map could not be built from FMU or QC output.")

            veda_to_qc, qc_to_veda, map_stats = build_veda_orca_mode_maps(freqs_ved, qc_freq_data, orca_intensities=qc_intensities, tol_cm1=5.0)

            self.analysis_ctx = {
                "freqs_ved": freqs_ved,
                "ted_block": ted_blk,
                "ped_blocks": ped_blks,
                "coords": coords,
                "available_codes": available_codes,
                "atom_map": atom_map,
                "engine": engine,
                "qc_freq_data": qc_freq_data,
                "qc_intensities": qc_intensities,
                "qc_atom_map": qc_atom_map,
                "veda_to_qc": veda_to_qc,
                "qc_to_veda": qc_to_veda,
                "map_stats": map_stats,
            }

            self.coordinate_rows = self._make_coordinate_rows(coords, atom_map)
            self._update_filter_choices()
            self.refresh_coordinate_table()
            self.refresh_target_preview()

            ped_headers = [str(b.get("header", "PED")) for b in ped_blks]
            lines = []
            lines.append("Precheck OK")
            lines.append(f"Program version      : {APP_VERSION} ({APP_RELEASE_DATE})")
            lines.append("")
            lines.append(f"VEDA modes           : {len(freqs_ved) if freqs_ved else 'not extracted'}")
            lines.append(f"PED blocks           : {len(ped_blks)}")
            for idx, h in enumerate(ped_headers, start=1):
                lines.append(f"  block {idx}           : {h}")
            lines.append(f"DD2 coordinates      : {len(coords)}")
            lines.append(f"Coordinate codes     : {', '.join(available_codes)}")
            lines.append(f"Atom map entries     : {len(atom_map)}")
            lines.append(f"QC engine            : {engine}")
            lines.append(f"QC modes             : {len(qc_freq_data)}")
            lines.append(f"Mode mapping matched : {map_stats.get('n_matched', 0)} / VEDA {map_stats.get('n_veda', 0)} / QC {map_stats.get('n_orca', 0)}")
            lines.append(f"Max abs freq diff    : {map_stats.get('max_abs_diff')}")
            lines.append(f"Mean abs freq diff   : {map_stats.get('mean_abs_diff')}")
            lines.append("")
            lines.append("Next step: use Coordinate Browser or Target Definition to select internal coordinates.")
            self._set_text(self.precheck_text, "\n".join(lines))
            self.status_lbl.config(text="Precheck OK", fg="green")
            self._save_current_config()

        except Exception as e:
            self.status_lbl.config(text="Precheck error", fg="red")
            log_caution("Precheck failed.")
            log_error("precheck", e)
            self._set_text(self.precheck_text, f"Precheck failed:\n{e}\n\nSee log: {_ensure_log_path()}")
            messagebox.showerror("Precheck error", f"An error occurred:\n{str(e)}\n\nSee log:\n{_ensure_log_path()}")

    def _make_coordinate_rows(self, coords: List[dict], atom_map: Dict[int, str]) -> List[dict]:
        rows: List[dict] = []
        for idx, c in enumerate(coords):
            atoms = c.get("atoms", []) or []
            rows.append({
                "row_index": idx,
                "coord_id": c.get("coord_id", ""),
                "code": c.get("coord_code", ""),
                "group": c.get("coord_group", ""),
                "atoms": " ".join(str(a) for a in atoms),
                "atom_label": _coord_atom_label(c, atom_map),
                "label": _coord_label(c, atom_map),
                "raw_label": c.get("coord_label_raw", "") or "",
                "source_line": c.get("source_line", "") or "",
                "coord": c,
            })
        return rows

    def _update_filter_choices(self):
        codes = sorted(set(str(r.get("code", "")).lower() for r in self.coordinate_rows if r.get("code")))
        groups = sorted(set(str(r.get("group", "")).upper() for r in self.coordinate_rows if r.get("group")))
        code_values = _ordered_code_values(codes)
        group_values = _ordered_group_values(groups)
        self.filter_code_combo.configure(values=code_values)
        self.filter_group_combo.configure(values=group_values)

        current_code = _code_from_filter(self.filter_code_var.get())
        current_group = _group_from_filter(self.filter_group_var.get())
        if current_code not in codes and current_code != "(any)":
            self.filter_code_var.set(_code_display("s") if "s" in codes else "(any)")
        elif self.filter_code_var.get() not in code_values:
            self.filter_code_var.set(_code_display(current_code) if current_code in codes else "(any)")

        if current_group not in groups and current_group != "(any)":
            self.filter_group_var.set(_group_display("STRE") if "STRE" in groups else "(any)")
        elif self.filter_group_var.get() not in group_values:
            self.filter_group_var.set(_group_display(current_group) if current_group in groups else "(any)")

    def clear_coordinate_filters(self):
        self.filter_code_var.set("(any)")
        self.filter_group_var.set("(any)")
        self.filter_atom_var.set("")
        self.filter_element_var.set("")
        self.filter_label_var.set("")
        self.refresh_coordinate_table()

    def refresh_coordinate_table(self):
        if not hasattr(self, "coord_tree"):
            return
        for item in self.coord_tree.get_children():
            self.coord_tree.delete(item)

        if not self.coordinate_rows:
            return

        code_filter = _code_from_filter(self.filter_code_var.get())
        group_filter = _group_from_filter(self.filter_group_var.get())
        atom_requirements = _parse_atom_filter_requirements(self.filter_atom_var.get())
        element_filter = set(_parse_symbol_list(self.filter_element_var.get()))
        label_filter = self.filter_label_var.get().strip().lower()
        atom_map = (self.analysis_ctx or {}).get("atom_map", {}) if self.analysis_ctx else {}

        n_show = 0
        for i, r in enumerate(self.coordinate_rows):
            if code_filter and code_filter != "(any)" and str(r.get("code", "")).lower() != code_filter:
                continue
            if group_filter and group_filter != "(any)" and str(r.get("group", "")).upper() != group_filter:
                continue
            atoms = _parse_int_list(r.get("atoms", ""))
            if atom_requirements and not any(req <= set(atoms) for req in atom_requirements):
                continue
            if element_filter:
                els = set((atom_map.get(a, "") or "").capitalize() for a in atoms)
                if not (els & element_filter):
                    continue
            if label_filter:
                hay = " ".join(str(r.get(k, "")) for k in ("atom_label", "label", "raw_label", "source_line")).lower()
                if label_filter not in hay:
                    continue

            vals = [r.get("coord_id", ""), r.get("code", ""), r.get("group", ""), r.get("atoms", ""), r.get("atom_label", ""), r.get("label", ""), r.get("raw_label", "")]
            self.coord_tree.insert("", "end", iid=str(i), values=vals)
            n_show += 1

        self.status_lbl.config(text=f"Coordinate rows shown: {n_show}", fg="blue")

    # -----------------------------
    # Target coordinate helpers
    # -----------------------------

    def _get_target_refs_from_text(self) -> set:
        return set(_parse_target_refs(self.target_ids_text.get("1.0", "end")))

    def _get_target_ids_from_text(self) -> set:
        """Backward-compatible helper: return numeric IDs only."""
        ids = set()
        for ref in self._get_target_refs_from_text():
            try:
                ids.add(_split_target_ref(ref)[2])
            except Exception:
                continue
        return ids

    def normalize_target_ids_text(self):
        refs = _sort_target_refs(self._get_target_refs_from_text())
        self.target_ids_text.delete("1.0", "end")
        self.target_ids_text.insert("1.0", ", ".join(refs))
        self.refresh_target_preview()
        self._save_current_config()

    def clear_target_ids(self):
        self.target_ids_text.delete("1.0", "end")
        self.refresh_target_preview()
        self._save_current_config()

    def add_selected_coords_to_target(self):
        if not self.coordinate_rows:
            messagebox.showwarning("No coordinates", "Run Load / Precheck first.")
            return
        selected = self.coord_tree.selection()
        if not selected:
            messagebox.showinfo("No selection", "Select rows in the coordinate table first.")
            return
        refs = self._get_target_refs_from_text()
        for iid in selected:
            try:
                row = self.coordinate_rows[int(iid)]
                cid = row.get("coord_id")
                code = row.get("code", row.get("coord_code", "s"))
                refs.add(_make_target_ref(code, row.get("group", row.get("coord_group", "")), cid))
            except Exception:
                continue
        refs = _sort_target_refs(refs)
        self.target_ids_text.delete("1.0", "end")
        self.target_ids_text.insert("1.0", ", ".join(refs))
        self.refresh_target_preview()
        self._save_current_config()

    def _detect_target_refs_by_rule(self) -> set:
        if not self.analysis_ctx:
            return set()
        atom_map = self.analysis_ctx.get("atom_map", {}) or {}
        metal_atoms = _parse_int_list(self.metal_atoms_var.get())
        ligand_atoms = _parse_int_list(self.ligand_atoms_var.get())
        ligand_elements = _parse_symbol_list(self.ligand_elements_var.get())
        refs = set()
        for c in self.analysis_ctx.get("coords", []) or []:
            if _coord_matches_metal_ligand_stretch(c, atom_map, metal_atoms, ligand_atoms, ligand_elements):
                cid = c.get("coord_id")
                if isinstance(cid, int):
                    refs.add(_make_target_ref(c.get("coord_code", "s"), c.get("coord_group", ""), cid))
        return refs

    def _detect_target_ids_by_rule(self) -> set:
        ids = set()
        for ref in self._detect_target_refs_by_rule():
            try:
                ids.add(_split_target_ref(ref)[2])
            except Exception:
                continue
        return ids

    def _get_effective_target_refs(self) -> set:
        refs = self._get_target_refs_from_text()
        if not refs and bool(self.use_rule_if_empty_var.get()):
            refs = self._detect_target_refs_by_rule()
        return refs

    def _get_effective_target_ids(self) -> set:
        ids = set()
        for ref in self._get_effective_target_refs():
            try:
                ids.add(_split_target_ref(ref)[2])
            except Exception:
                continue
        return ids

    def auto_detect_target_coords(self):
        if not self.analysis_ctx:
            self.precheck()
            if not self.analysis_ctx:
                return
        refs = _sort_target_refs(self._detect_target_refs_by_rule())
        self.target_ids_text.delete("1.0", "end")
        self.target_ids_text.insert("1.0", ", ".join(refs))
        self.refresh_target_preview()
        self._save_current_config()
        messagebox.showinfo("Auto-detect", f"Detected {len(refs)} target coordinate references.")

    def refresh_target_preview(self):
        if not hasattr(self, "target_tree"):
            return
        refs = self._get_effective_target_refs()
        rows = []
        for r in self.coordinate_rows:
            try:
                cid = int(r.get("coord_id"))
            except Exception:
                continue
            code = str(r.get("code", r.get("coord_code", "s")) or "s").lower()
            ref = _make_target_ref(code, r.get("group", r.get("coord_group", "")), cid)
            if _target_ref_matches(ref, refs):
                rows.append({
                    "target_ref": ref,
                    "coord_id": cid,
                    "code": r.get("code", ""),
                    "group": r.get("group", ""),
                    "atom_label": r.get("atom_label", ""),
                    "label": r.get("label", ""),
                })
        df = pd.DataFrame(rows)
        self._populate_tree(self.target_tree, df, max_rows=300)

    # -----------------------------
    # Analysis helpers
    # -----------------------------

    def _configure_generic_tree(self, tree: ttk.Treeview, cols: List[str]):
        tree["columns"] = cols
        tree["show"] = "headings"
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=max(80, min(260, 10 * len(c) + 60)), anchor="w")

    def _populate_tree(self, tree: ttk.Treeview, df: pd.DataFrame, max_rows: int = 300):
        for item in tree.get_children():
            tree.delete(item)
        if df is None or df.empty:
            self._configure_generic_tree(tree, [])
            return
        cols = list(df.columns)
        self._configure_generic_tree(tree, cols)
        for _, row in df.head(max_rows).iterrows():
            vals = []
            for c in cols:
                v = row.get(c, "")
                if isinstance(v, float):
                    if math.isnan(v):
                        vals.append("")
                    else:
                        vals.append(f"{v:.6g}")
                else:
                    vals.append("" if v is None else str(v))
            tree.insert("", "end", values=vals)

    def _output_path(self, base: Path, suffix: str) -> str:
        out_dir = Path(self.output_dir_path) if self.output_dir_path else base.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        return str(out_dir / (base.stem + suffix))

    def _get_options(self) -> dict:
        def int_opt(var, default):
            try:
                return max(1, int(float(str(var.get()).strip())))
            except Exception:
                return default

        def float_opt(var, default):
            try:
                return float(safe_float(str(var.get()).strip()))
            except Exception:
                return default

        return {
            "top_n": int_opt(self.top_n_var, DEFAULT_TOP_N_TERMS),
            "standard_min_ped": float_opt(self.standard_min_ped_var, DEFAULT_LONG_MIN_PED),
            "long_min_ped": float_opt(self.long_min_ped_var, DEFAULT_LONG_MIN_PED),
            "target_min_ped": float_opt(self.target_min_ped_var, DEFAULT_TARGET_MIN_PED),
            "target_total_min_ped": float_opt(self.target_total_min_ped_var, DEFAULT_TARGET_TOTAL_PED),
            "freq_min": _parse_optional_float(self.freq_min_var.get()),
            "freq_max": _parse_optional_float(self.freq_max_var.get()),
            "target_name": self.target_name_var.get().strip() or "target",
            "output_standard": bool(self.output_standard_var.get()),
            "output_long": bool(self.output_long_var.get()),
            "output_target_hits": bool(self.output_target_hits_var.get()),
            "output_summary_mode": bool(self.output_summary_mode_var.get()),
            "output_summary_coord": bool(self.output_summary_coord_var.get()),
            "output_target_matrix": bool(self.output_target_matrix_var.get()),
            "output_combined_target": bool(self.output_combined_target_var.get()),
            "include_alternative": bool(self.include_alternative_var.get()),
            "include_all_target_modes": bool(self.include_all_target_modes_var.get()),
        }

    def _mode_meta(self, ctx: dict, v_mode: int, row_index: int) -> Tuple[dict, List[str]]:
        freqs_ved = ctx.get("freqs_ved", []) or []
        qc_freq_data = ctx.get("qc_freq_data", {}) or {}
        qc_intensities = ctx.get("qc_intensities", {}) or {}
        veda_to_qc = ctx.get("veda_to_qc", {}) or {}
        caution_msgs: List[str] = []

        v_freq = 0.0
        if freqs_ved and row_index < len(freqs_ved):
            try:
                v_freq = float(freqs_ved[row_index])
            except Exception:
                v_freq = 0.0
        else:
            caution_msgs.append("VEDA frequency unavailable")

        q_mode = veda_to_qc.get(v_mode) if veda_to_qc else None
        q_freq = 0.0
        q_irrep = ""
        q_int = 0.0
        delta_freq = None
        abs_delta_freq = None

        if q_mode is None:
            caution_msgs.append("QC mode not matched")
        else:
            fd = qc_freq_data.get(q_mode)
            if fd:
                try:
                    q_freq = float(fd.get("freq", 0.0))
                except Exception:
                    q_freq = 0.0
                q_irrep = fd.get("irrep", "") or ""
            else:
                caution_msgs.append("QC frequency unavailable")
            try:
                q_int = float(qc_intensities.get(q_mode, 0.0))
            except Exception:
                q_int = 0.0
            if v_freq and q_freq:
                delta_freq = q_freq - v_freq
                abs_delta_freq = abs(delta_freq)
                if abs_delta_freq > 5.0:
                    caution_msgs.append(f"abs_freq_diff={abs_delta_freq:.2f}>5.00")

        meta = {
            "mode_veda": v_mode,
            "mode_qc": q_mode if q_mode else "",
            "freq_veda": v_freq,
            "freq_qc": q_freq,
            "delta_freq": delta_freq,
            "abs_delta_freq": abs_delta_freq,
            "irrep": q_irrep,
            "IR_intensity": q_int,
        }
        return meta, caution_msgs

    def _coord_info_from_col(self, colpos_to_info: Dict[int, dict], col_pos: int, atom_map: Dict[int, str], preferred_refs: Optional[set] = None) -> dict:
        info = colpos_to_info.get(col_pos, {"ped_col": col_pos, "coord_id": col_pos, "coord_code": "", "coord": None})
        c_obj = info.get("coord")
        cid = info.get("coord_id", col_pos)
        if preferred_refs:
            for cand in info.get("coord_candidates", []) or []:
                try:
                    cand_ref = _make_target_ref(cand.get("coord_code", "s"), cand.get("coord_group", ""), cid)
                    if _target_ref_matches(cand_ref, preferred_refs):
                        c_obj = cand
                        break
                except Exception:
                    continue
        return {
            "ped_col": col_pos,
            "coord_id": cid,
            "coord_code": info.get("coord_code", "") or _coord_code(c_obj),
            "target_ref": _make_target_ref(info.get("coord_code", "") or _coord_code(c_obj) or "s", _coord_group(c_obj), cid),
            "coord_group": _coord_group(c_obj),
            "atoms": " ".join(str(a) for a in ((c_obj or {}).get("atoms", []) or [])),
            "atom_label": _coord_atom_label(c_obj, atom_map),
            "label": _coord_label(c_obj, atom_map),
            "coord": c_obj,
        }

    def _generate_combined_target_outputs(self, base: Path, ctx: dict, ped_blocks: List[dict], coords: List[dict],
                                          atom_map: Dict[int, str], target_refs: set, opts: dict) -> Tuple[List[str], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Generate combined target outputs that may mix s/k/v target references.

        Per-coordinate-set outputs interpret all selected targets within one coordinate set.
        This combined output instead treats the target list literally as code-qualified
        references (for example s:83 plus k:126) and sums only those exact references.
        """
        saved_files: List[str] = []
        if not target_refs or not opts.get("output_combined_target", True):
            return saved_files, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        combined_hits: List[dict] = []
        mode_acc: Dict[Any, dict] = {}
        coord_acc: Dict[str, dict] = {}
        matrix_acc: Dict[Any, dict] = {}

        # Exact, code-qualified DD2 lookup.  Combined output must not let
        # the usual alternative->standard fallback relabel k/v targets as s
        # targets or vice versa.  For example, s:83 and k:126 are distinct
        # target coordinates even if their bare coord_id values overlap with
        # other coordinate sets.
        coord_by_ref: Dict[str, dict] = {}
        for c in coords:
            cid = c.get("coord_id")
            code0 = str(c.get("coord_code", "s") or "s").lower()
            if isinstance(cid, int):
                coord_by_ref[_make_target_ref(code0, c.get("coord_group", ""), cid).lower()] = c

        requested_refs = set(str(r).lower() for r in target_refs)
        found_refs = set()

        def _block_code(b: dict) -> str:
            return str(b.get("target_code", "s") or "s").strip().lower() or "s"

        def _block_has_coord_id(b: dict, cid: int) -> bool:
            cols = b.get("col_ids", []) or []
            if not cols:
                # If the .ved did not expose explicit column IDs, we cannot
                # prove absence here. Keep the block as a possible matrix source.
                return True
            try:
                return int(cid) in set(int(x) for x in cols)
            except Exception:
                return False

        standard_blocks = [b for b in ped_blocks if _is_standard_ped_block(b)]
        if not standard_blocks and ped_blocks:
            standard_blocks = [ped_blocks[0]]

        # Plan combined scans per target_ref, not just per coordinate code.
        # This is crucial when an explicit alternative PED block exists but does
        # not contain the requested alternative coord_id, while the standard PED
        # matrix can still be reinterpreted with the k/v DD2 mapping.  The older
        # code chose one block per code and therefore left cases like k:126 as
        # missing even though the standard PED matrix had column 126.
        view_map: Dict[Tuple[str, int], dict] = {}
        view_refs: Dict[Tuple[str, int], set] = {}
        view_reinterp: Dict[Tuple[str, int], bool] = {}

        for ref in _sort_target_refs(requested_refs):
            try:
                code_part, _group_part, cid_int = _split_target_ref(ref)
            except Exception:
                continue

            exact_blocks = [b for b in ped_blocks if _block_code(b) == code_part]
            candidates = [b for b in exact_blocks if _block_has_coord_id(b, cid_int)]
            reinterp = False

            if not candidates:
                candidates = [b for b in standard_blocks if _block_has_coord_id(b, cid_int)]
                reinterp = True

            if not candidates:
                candidates = exact_blocks or standard_blocks or list(ped_blocks or [])[:1]
                reinterp = bool(candidates and _block_code(candidates[0]) != code_part)

            if not candidates:
                continue

            ped_src = candidates[0]
            key = (code_part, id(ped_src))
            view_map[key] = ped_src
            view_refs.setdefault(key, set()).add(str(ref).lower())
            view_reinterp[key] = bool(reinterp or _block_code(ped_src) != code_part)

        combined_views: List[Tuple[str, dict, set, bool]] = [
            (code, view_map[(code, bid)], view_refs[(code, bid)], view_reinterp.get((code, bid), False))
            for code, bid in view_map.keys()
        ]

        for code, ped_blk, refs_for_code, view_reinterpreted in combined_views:
            header_str = ped_blk.get("header", "PED")
            code = str(code or "s").lower()
            code_label = _code_output_label(code)
            refs_for_code = set(str(r).lower() for r in refs_for_code)
            if not refs_for_code:
                continue

            if view_reinterpreted and code != str(ped_blk.get("target_code", "s") or "s").lower():
                log_message(f"[combined targets] Reinterpreting PED matrix '{header_str}' with DD2 coordinate set {code} ({code_label}).")

            ped_mat_norm, sums, notes = _ped_percent_matrix_with_check(ped_blk.get("matrix", []))
            ped_col_ids: List[int] = ped_blk.get("col_ids", []) or []
            if not ped_col_ids:
                ped_col_ids = list(range(1, int(ped_blk.get("n_cols", 0)) + 1))
                log_caution(f"[{header_str}] PED column IDs missing; combined output falls back to sequential numbering.")

            colpos_to_info, colmap_cautions = build_ped_column_coord_map(ped_col_ids, coords, target_code=code)
            for c in colmap_cautions:
                log_caution(f"[{header_str} - combined {code.upper()} targets] {c}")

            for row_index, row in enumerate(ped_mat_norm):
                v_mode = row_index + 1
                meta, base_cautions = self._mode_meta(ctx, v_mode, row_index)
                freq_for_filter = float(meta.get("freq_qc") or meta.get("freq_veda") or 0.0)
                mode_in_range = _freq_in_range(freq_for_filter, opts["freq_min"], opts["freq_max"])
                if not mode_in_range:
                    continue

                contribs: List[Tuple[float, int]] = []
                for col_idx_0, val in enumerate(row):
                    contribs.append((float(val), col_idx_0 + 1))
                contribs.sort(key=lambda x: x[0], reverse=True)

                mode_key = meta.get("mode_veda") or v_mode
                macc = mode_acc.setdefault(mode_key, {
                    "target_set_name": opts["target_name"],
                    "interpretation": "combined",
                    "ped_block": "mixed s/k/v",
                    **meta,
                    "total_target_PED": 0.0,
                    "max_target_PED": 0.0,
                    "best_target_rank": "",
                    "_terms": [],
                    "_detected": set(),
                    "_blocks": set(),
                })
                mat = matrix_acc.setdefault(mode_key, {
                    "target_set_name": opts["target_name"],
                    "interpretation": "combined",
                    "ped_block": "mixed s/k/v",
                    **meta,
                })

                cumulative = 0.0
                for rank, (val, col_pos) in enumerate(contribs, start=1):
                    cumulative += val
                    cinfo0 = self._coord_info_from_col(colpos_to_info, col_pos, atom_map, target_refs)
                    cid_raw = cinfo0.get("coord_id", "")
                    try:
                        cid_int = int(cid_raw)
                    except Exception:
                        cid_int = -1

                    # In combined mode, match by code+group+coord_id.  The same
                    # code+coord_id can be reused by DD2 for different groups
                    # (for example k:STRE:126 and k:BEND:126), so group is required.
                    matching_refs = []
                    for req in refs_for_code:
                        try:
                            req_code, req_group, req_cid = _split_target_ref(req)
                        except Exception:
                            continue
                        if req_code == code and int(req_cid) == int(cid_int):
                            matching_refs.append(f"{req_code}:{req_group}:{req_cid}")
                    if not matching_refs:
                        continue

                    for target_ref in matching_refs:
                        c_obj_exact = coord_by_ref.get(str(target_ref).lower())
                        if c_obj_exact is not None:
                            cinfo = {
                                "ped_col": col_pos,
                                "target_ref": target_ref,
                                "coord_id": cid_int,
                                "coord_code": code,
                                "coord_group": _coord_group(c_obj_exact),
                                "atoms": " ".join(str(a) for a in (c_obj_exact.get("atoms", []) or [])),
                                "atom_label": _coord_atom_label(c_obj_exact, atom_map),
                                "label": _coord_label(c_obj_exact, atom_map),
                            }
                        else:
                            cinfo = dict(cinfo0)
                            cinfo["target_ref"] = target_ref
                            cinfo["coord_code"] = code
                        found_refs.add(str(target_ref).lower())

                        macc["total_target_PED"] += val
                        macc["_blocks"].add(code_label)
                        if val > macc["max_target_PED"]:
                            macc["max_target_PED"] = val
                        if macc["best_target_rank"] == "":
                            macc["best_target_rank"] = rank
                        mat[f"coord_{str(target_ref).replace(':', '_')}"] = round(val, 6)

                        if val >= opts["target_min_ped"]:
                            macc["_detected"].add(target_ref)
                            macc["_terms"].append((val, rank, cinfo.get("label", ""), target_ref, code_label))
                            if opts["output_target_hits"]:
                                combined_hits.append({
                                    "target_set_name": opts["target_name"],
                                    "interpretation": "combined",
                                    "source_interpretation": code_label,
                                    "ped_block": header_str,
                                    **meta,
                                    "PED_rank": rank,
                                    "PED_value": round(val, 6),
                                    "cumulative_PED": round(cumulative, 6),
                                    **{k: cinfo.get(k, "") for k in ("ped_col", "target_ref", "coord_id", "coord_code", "coord_group", "atoms", "atom_label", "label")},
                                })

                            acc = coord_acc.setdefault(target_ref, {
                                "target_set_name": opts["target_name"],
                                "interpretation": "combined",
                                "source_interpretation": code_label,
                                "ped_block": header_str,
                                "target_ref": target_ref,
                                "coord_id": cid_int,
                                "coord_code": cinfo.get("coord_code", ""),
                                "coord_group": cinfo.get("coord_group", ""),
                                "atoms": cinfo.get("atoms", ""),
                                "atom_label": cinfo.get("atom_label", ""),
                                "label": cinfo.get("label", ""),
                                "sum_PED_in_range": 0.0,
                                "max_PED": 0.0,
                                "mode_qc_at_max": "",
                                "mode_veda_at_max": "",
                                "freq_qc_at_max": 0.0,
                                "freq_veda_at_max": 0.0,
                                "weight_freq_sum": 0.0,
                                "weight_sum": 0.0,
                                "mode_terms": [],
                            })
                            acc["sum_PED_in_range"] += val
                            acc["weight_freq_sum"] += val * freq_for_filter
                            acc["weight_sum"] += val
                            acc["mode_terms"].append((val, meta.get("mode_qc", ""), meta.get("mode_veda", ""), freq_for_filter, rank, code_label))
                            if val > acc["max_PED"]:
                                acc["max_PED"] = val
                                acc["mode_qc_at_max"] = meta.get("mode_qc", "")
                                acc["mode_veda_at_max"] = meta.get("mode_veda", "")
                                acc["freq_qc_at_max"] = meta.get("freq_qc", 0.0)
                                acc["freq_veda_at_max"] = meta.get("freq_veda", 0.0)

        # If a requested k/v target was not found in a parsed PED matrix, try the
        # coordinate-centered terms stored in DD2.  Some VEDA outputs contain
        # alternative coordinates in DD2 but do not provide separate alternative
        # PED matrices in the .ved file.  Without this fallback, a mixed target
        # such as s:83 + k:126 would report k:126 as missing even though DD2
        # contains its mode contributions.
        dd2_fallback_added = 0
        freqs_ved_for_terms = ctx.get("freqs_ved", []) or []

        def _term_tag_to_veda_mode(tag: Any) -> Optional[int]:
            raw = str(tag).strip()
            if not raw:
                return None
            # Direct mode labels such as 126, V126, F126, mode126.
            m_ints = re.findall(r"[+-]?\d+", raw)
            if m_ints:
                try:
                    cand = int(m_ints[-1])
                    if cand >= 1:
                        # If the value is a plausible mode index, use it.
                        n_hint = int((ctx.get("ped_blocks", [{}]) or [{}])[0].get("n_modes", 0) or len(freqs_ved_for_terms) or 0)
                        if n_hint <= 0 or cand <= n_hint:
                            return cand
                except Exception:
                    pass
            # Frequency labels such as 594.0: map to nearest VEDA frequency.
            try:
                fval = float(raw.replace("D", "E").replace("d", "e"))
                if freqs_ved_for_terms:
                    pairs = [(abs(float(f) - fval), i + 1) for i, f in enumerate(freqs_ved_for_terms)]
                    pairs.sort(key=lambda x: x[0])
                    if pairs and pairs[0][0] <= 5.0:
                        return pairs[0][1]
            except Exception:
                pass
            return None

        missing_before_dd2 = set(requested_refs - found_refs)
        for target_ref in _sort_target_refs(missing_before_dd2):
            c_obj = coord_by_ref.get(str(target_ref).lower())
            if not c_obj:
                continue
            terms_dd2 = c_obj.get("terms", []) or []
            if not terms_dd2:
                continue
            code = str(c_obj.get("coord_code", "s") or "s").lower()
            code_label = _code_output_label(code)
            source_label = f"dd2_terms_{code_label}"
            cinfo = {
                "ped_col": "DD2",
                "target_ref": str(target_ref).lower(),
                "coord_id": c_obj.get("coord_id", ""),
                "coord_code": code,
                "coord_group": _coord_group(c_obj),
                "atoms": " ".join(str(a) for a in (c_obj.get("atoms", []) or [])),
                "atom_label": _coord_atom_label(c_obj, atom_map),
                "label": _coord_label(c_obj, atom_map),
            }
            for tag, pct in terms_dd2:
                try:
                    val = abs(float(pct))
                except Exception:
                    continue
                v_mode = _term_tag_to_veda_mode(tag)
                if not v_mode:
                    continue
                meta, base_cautions = self._mode_meta(ctx, int(v_mode), int(v_mode) - 1)
                freq_for_filter = float(meta.get("freq_qc") or meta.get("freq_veda") or 0.0)
                if not _freq_in_range(freq_for_filter, opts["freq_min"], opts["freq_max"]):
                    continue

                mode_key = meta.get("mode_veda") or int(v_mode)
                macc = mode_acc.setdefault(mode_key, {
                    "target_set_name": opts["target_name"],
                    "interpretation": "combined",
                    "ped_block": "mixed s/k/v",
                    **meta,
                    "total_target_PED": 0.0,
                    "max_target_PED": 0.0,
                    "best_target_rank": "",
                    "_terms": [],
                    "_detected": set(),
                    "_blocks": set(),
                })
                mat = matrix_acc.setdefault(mode_key, {
                    "target_set_name": opts["target_name"],
                    "interpretation": "combined",
                    "ped_block": "mixed s/k/v",
                    **meta,
                })

                found_refs.add(str(target_ref).lower())
                macc["total_target_PED"] += val
                macc["_blocks"].add(source_label)
                if val > macc["max_target_PED"]:
                    macc["max_target_PED"] = val
                if macc["best_target_rank"] == "":
                    macc["best_target_rank"] = "DD2"
                mat[f"coord_{str(target_ref).replace(':', '_')}"] = round(val, 6)

                if val >= opts["target_min_ped"]:
                    macc["_detected"].add(str(target_ref).lower())
                    macc["_terms"].append((val, "DD2", cinfo.get("label", ""), str(target_ref).lower(), source_label))
                    if opts["output_target_hits"]:
                        combined_hits.append({
                            "target_set_name": opts["target_name"],
                            "interpretation": "combined",
                            "source_interpretation": source_label,
                            "ped_block": "DD2 terms",
                            **meta,
                            "PED_rank": "DD2",
                            "PED_value": round(val, 6),
                            "cumulative_PED": "",
                            **{k: cinfo.get(k, "") for k in ("ped_col", "target_ref", "coord_id", "coord_code", "coord_group", "atoms", "atom_label", "label")},
                        })

                    acc = coord_acc.setdefault(str(target_ref).lower(), {
                        "target_set_name": opts["target_name"],
                        "interpretation": "combined",
                        "source_interpretation": source_label,
                        "ped_block": "DD2 terms",
                        "target_ref": str(target_ref).lower(),
                        "coord_id": cinfo.get("coord_id", ""),
                        "coord_code": code,
                        "coord_group": cinfo.get("coord_group", ""),
                        "atoms": cinfo.get("atoms", ""),
                        "atom_label": cinfo.get("atom_label", ""),
                        "label": cinfo.get("label", ""),
                        "sum_PED_in_range": 0.0,
                        "max_PED": 0.0,
                        "mode_qc_at_max": "",
                        "mode_veda_at_max": "",
                        "freq_qc_at_max": 0.0,
                        "freq_veda_at_max": 0.0,
                        "weight_freq_sum": 0.0,
                        "weight_sum": 0.0,
                        "mode_terms": [],
                    })
                    acc["sum_PED_in_range"] += val
                    acc["weight_freq_sum"] += val * freq_for_filter
                    acc["weight_sum"] += val
                    acc["mode_terms"].append((val, meta.get("mode_qc", ""), meta.get("mode_veda", ""), freq_for_filter, "DD2", source_label))
                    if val > acc["max_PED"]:
                        acc["max_PED"] = val
                        acc["mode_qc_at_max"] = meta.get("mode_qc", "")
                        acc["mode_veda_at_max"] = meta.get("mode_veda", "")
                        acc["freq_qc_at_max"] = meta.get("freq_qc", 0.0)
                        acc["freq_veda_at_max"] = meta.get("freq_veda", 0.0)
                    dd2_fallback_added += 1

        if dd2_fallback_added:
            log_message(f"[combined targets] Added {dd2_fallback_added} contribution(s) from DD2 coordinate terms for targets not found in parsed PED blocks.")

        summary_mode_rows: List[dict] = []
        matrix_rows: List[dict] = []
        for mode_key, acc in mode_acc.items():
            total = acc.get("total_target_PED", 0.0)
            if not (opts["include_all_target_modes"] or total >= opts["target_total_min_ped"]):
                continue
            terms = sorted(acc.get("_terms", []), key=lambda x: x[0], reverse=True)
            top_terms = "; ".join(
                f"{tref}:{label}={val:.1f}% ({src}, rank {rank})" for val, rank, label, tref, src in terms[:8]
            )
            row = {k: v for k, v in acc.items() if not str(k).startswith("_")}
            row["ped_block"] = "+".join(sorted(acc.get("_blocks", []))) or "mixed s/k/v"
            row["requested_target_refs"] = ", ".join(_sort_target_refs(requested_refs))
            row["found_target_refs"] = ", ".join(_sort_target_refs(found_refs))
            row["missing_target_refs"] = ", ".join(_sort_target_refs(requested_refs - found_refs))
            row["total_target_PED"] = round(total, 6)
            row["max_target_PED"] = round(acc.get("max_target_PED", 0.0), 6)
            row["n_target_coords_detected"] = len(acc.get("_detected", set()))
            row["best_target_rank"] = acc.get("best_target_rank", "")
            row["top_target_terms"] = top_terms
            summary_mode_rows.append(row)

            mat = matrix_acc.get(mode_key, {}).copy()
            mat["requested_target_refs"] = row.get("requested_target_refs", "")
            mat["found_target_refs"] = row.get("found_target_refs", "")
            mat["missing_target_refs"] = row.get("missing_target_refs", "")
            mat["total_target_PED"] = row["total_target_PED"]
            mat["max_target_PED"] = row["max_target_PED"]
            mat["best_target_rank"] = row["best_target_rank"]
            matrix_rows.append(mat)

        summary_coord_rows: List[dict] = []
        for tref, acc in sorted(coord_acc.items(), key=lambda kv: str(kv[0])):
            terms = sorted(acc.get("mode_terms", []), key=lambda x: x[0], reverse=True)
            top_modes = "; ".join(
                f"QC{mq or ''}/V{mv}@{fr:.1f}:{val:.1f}% ({src}, rank {rk})" for val, mq, mv, fr, rk, src in terms[:10]
            )
            weight_sum = acc.get("weight_sum", 0.0) or 0.0
            weighted_mean_freq = (acc.get("weight_freq_sum", 0.0) / weight_sum) if weight_sum > 0 else ""
            summary_coord_rows.append({
                "target_set_name": acc.get("target_set_name", ""),
                "interpretation": "combined",
                "source_interpretation": acc.get("source_interpretation", ""),
                "ped_block": acc.get("ped_block", ""),
                "target_ref": acc.get("target_ref", ""),
                "coord_id": acc.get("coord_id", ""),
                "coord_code": acc.get("coord_code", ""),
                "coord_group": acc.get("coord_group", ""),
                "atoms": acc.get("atoms", ""),
                "atom_label": acc.get("atom_label", ""),
                "label": acc.get("label", ""),
                "max_PED": round(acc.get("max_PED", 0.0), 6),
                "mode_qc_at_max": acc.get("mode_qc_at_max", ""),
                "mode_veda_at_max": acc.get("mode_veda_at_max", ""),
                "freq_qc_at_max": acc.get("freq_qc_at_max", 0.0),
                "freq_veda_at_max": acc.get("freq_veda_at_max", 0.0),
                "sum_PED_in_range": round(acc.get("sum_PED_in_range", 0.0), 6),
                "weighted_mean_freq": weighted_mean_freq,
                "n_modes_detected": len(terms),
                "top_modes": top_modes,
            })

        df_hits = pd.DataFrame(combined_hits)
        df_sum_mode = pd.DataFrame(summary_mode_rows)
        df_sum_coord = pd.DataFrame(summary_coord_rows)
        df_matrix = pd.DataFrame(matrix_rows)

        if not df_sum_mode.empty:
            df_sum_mode = df_sum_mode.sort_values(["total_target_PED", "freq_qc"], ascending=[False, True])
        if not df_sum_coord.empty:
            df_sum_coord = df_sum_coord.sort_values(["sum_PED_in_range", "max_PED"], ascending=[False, False])

        if opts.get("output_target_hits"):
            save_path = self._output_path(base, "_target_hits_combined.csv")
            df_hits.to_csv(save_path, index=False, encoding="utf-8-sig")
            saved_files.append(save_path)
            log_message(f"Saved combined target hits: {save_path}")
        if opts.get("output_summary_mode"):
            save_path = self._output_path(base, "_target_summary_by_mode_combined.csv")
            df_sum_mode.to_csv(save_path, index=False, encoding="utf-8-sig")
            saved_files.append(save_path)
            log_message(f"Saved combined target summary by mode: {save_path}")
        if opts.get("output_summary_coord"):
            save_path = self._output_path(base, "_target_summary_by_coord_combined.csv")
            df_sum_coord.to_csv(save_path, index=False, encoding="utf-8-sig")
            saved_files.append(save_path)
            log_message(f"Saved combined target summary by coordinate: {save_path}")
        missing_refs = requested_refs - found_refs
        if missing_refs:
            log_caution("[combined targets] Requested target references not found in matching PED blocks: " + ", ".join(_sort_target_refs(missing_refs)))

        if opts.get("output_target_matrix"):
            save_path = self._output_path(base, "_target_matrix_combined.csv")
            df_matrix.to_csv(save_path, index=False, encoding="utf-8-sig")
            saved_files.append(save_path)
            log_message(f"Saved combined target matrix: {save_path}")

        return saved_files, df_sum_mode, df_hits, df_sum_coord

    # -----------------------------
    # Main run
    # -----------------------------

    def run(self):
        if not self.analysis_ctx:
            self.precheck()
            if not self.analysis_ctx:
                return

        ctx = self.analysis_ctx
        opts = self._get_options()
        if not any(opts[k] for k in ("output_standard", "output_long", "output_target_hits", "output_summary_mode", "output_summary_coord", "output_target_matrix")):
            messagebox.showwarning("No output", "Select at least one output option.")
            return

        target_refs = self._get_effective_target_refs()
        target_ids = self._get_effective_target_ids()
        if not target_refs and any(opts[k] for k in ("output_target_hits", "output_summary_mode", "output_summary_coord", "output_target_matrix")):
            messagebox.showwarning("No target coordinates", "No target coordinate IDs were selected or detected. Target outputs will be empty.")

        try:
            self.status_lbl.config(text="Running target analysis...", fg="blue")
            self.update()

            base = Path(self.ved_path)
            atom_map = ctx.get("atom_map", {}) or {}
            available_codes_all = ctx.get("available_codes", ["s"]) or ["s"]
            ped_blocks_all = ctx.get("ped_blocks", []) or []
            coords = ctx.get("coords", []) or []

            if opts.get("include_alternative"):
                output_codes = [str(c).lower() for c in available_codes_all]
            else:
                output_codes = [c for c in [str(x).lower() for x in available_codes_all] if c == "s"]
                if not output_codes:
                    output_codes = [str(available_codes_all[0]).lower()]
                    log_caution("Standard coordinate code 's' was not found; using the first available DD2 coordinate code.")

            ped_blocks = list(ped_blocks_all)
            if not ped_blocks:
                raise ValueError("No PED matrix found in prechecked context.")

            # Build coordinate-set interpretation views.  A view is a pair of a
            # coordinate-set code (s/k/v) and the PED matrix used as the numeric
            # source.  If the .ved file does not contain an explicit alternative
            # PED block, k/v are still interpreted by applying k/v DD2 labels to
            # the standard PED matrix.
            ped_views: List[Tuple[str, dict, bool]] = []
            for code in output_codes:
                ped_src, reinterp = _select_ped_block_for_coordinate_code(ped_blocks, code)
                if ped_src is None:
                    continue
                ped_views.append((str(code).lower(), ped_src, bool(reinterp)))

            saved_files: List[str] = []
            preview_summary_mode: List[pd.DataFrame] = []
            preview_hits: List[pd.DataFrame] = []
            preview_summary_coord: List[pd.DataFrame] = []

            for p_idx, (view_code, ped_blk, view_reinterpreted) in enumerate(ped_views):
                header_str = ped_blk.get("header", "PED")
                ped_mat_norm, sums, notes = _ped_percent_matrix_with_check(ped_blk.get("matrix", []))
                ped_col_ids: List[int] = ped_blk.get("col_ids", []) or []
                if not ped_col_ids:
                    ped_col_ids = list(range(1, int(ped_blk.get("n_cols", 0)) + 1))
                    log_caution(f"[{header_str}] PED column IDs missing; falling back to sequential numbering.")

                block_suffix = ""

                for code in [view_code]:
                    code_label = _code_output_label(code)
                    colpos_to_info, colmap_cautions = build_ped_column_coord_map(ped_col_ids, coords, target_code=code)
                    for c in colmap_cautions:
                        log_caution(f"[{header_str} - {code.upper()} interpretation] {c}")
                    if view_reinterpreted and code != str(ped_blk.get("target_code", "s") or "s").lower():
                        log_message(f"[{header_str}] Reinterpreting PED matrix with DD2 coordinate set {code} ({code_label}).")

                    standard_rows: List[dict] = []
                    long_rows: List[dict] = []
                    target_hits: List[dict] = []
                    summary_mode_rows: List[dict] = []
                    matrix_rows: List[dict] = []
                    coord_acc: Dict[int, dict] = {}

                    for row_index, row in enumerate(ped_mat_norm):
                        v_mode = row_index + 1
                        meta, base_cautions = self._mode_meta(ctx, v_mode, row_index)
                        freq_for_filter = float(meta.get("freq_qc") or meta.get("freq_veda") or 0.0)
                        mode_in_range = _freq_in_range(freq_for_filter, opts["freq_min"], opts["freq_max"])

                        contribs: List[Tuple[float, int]] = []
                        for col_idx_0, val in enumerate(row):
                            col_pos = col_idx_0 + 1
                            contribs.append((float(val), col_pos))
                        contribs.sort(key=lambda x: x[0], reverse=True)

                        cumulative = 0.0
                        target_total = 0.0
                        target_max = 0.0
                        best_target_rank = ""
                        target_terms_for_mode: List[Tuple[float, int, str, int]] = []
                        target_coords_detected = set()
                        matrix_entry = {
                            "target_set_name": opts["target_name"],
                            "interpretation": code_label,
                            "ped_block": header_str,
                            **meta,
                        }

                        standard_entry = {
                            **meta,
                            "interpretation": code_label,
                            "ped_block": header_str,
                            "ped_sum": sums[row_index] if row_index < len(sums) else "",
                            "note": notes[row_index] if row_index < len(notes) else "",
                        }

                        for rank, (val, col_pos) in enumerate(contribs, start=1):
                            cumulative += val
                            cinfo = self._coord_info_from_col(colpos_to_info, col_pos, atom_map, target_refs)
                            cid_raw = cinfo.get("coord_id", "")
                            try:
                                cid_int = int(cid_raw)
                            except Exception:
                                cid_int = -1
                            target_ref = cinfo.get("target_ref", _make_target_ref(cinfo.get("coord_code", "s"), cinfo.get("coord_group", ""), cid_int))
                            is_target = _target_ref_matches(target_ref, target_refs)

                            if opts["output_long"] and (val >= opts["long_min_ped"] or (is_target and val > 1.0e-12)):
                                long_rows.append({
                                    "interpretation": code_label,
                                    "ped_block": header_str,
                                    **meta,
                                    "PED_rank": rank,
                                    "PED_value": round(val, 6),
                                    "cumulative_PED": round(cumulative, 6),
                                    "is_target": bool(is_target),
                                    "target_set_name": opts["target_name"] if is_target else "",
                                    **{k: cinfo.get(k, "") for k in ("ped_col", "target_ref", "coord_id", "coord_code", "coord_group", "atoms", "atom_label", "label")},
                                })

                            if is_target:
                                target_total += val
                                if val > target_max:
                                    target_max = val
                                if best_target_rank == "":
                                    best_target_rank = rank
                                matrix_entry[f"coord_{str(target_ref).replace(':', '_')}"] = round(val, 6)
                                if val >= opts["target_min_ped"]:
                                    target_coords_detected.add(target_ref)
                                    target_terms_for_mode.append((val, rank, cinfo.get("label", ""), target_ref))
                                    if mode_in_range and opts["output_target_hits"]:
                                        target_hits.append({
                                            "target_set_name": opts["target_name"],
                                            "interpretation": code_label,
                                            "ped_block": header_str,
                                            **meta,
                                            "PED_rank": rank,
                                            "PED_value": round(val, 6),
                                            "cumulative_PED": round(cumulative, 6),
                                            **{k: cinfo.get(k, "") for k in ("ped_col", "target_ref", "coord_id", "coord_code", "coord_group", "atoms", "atom_label", "label")},
                                        })
                                    if mode_in_range:
                                        acc = coord_acc.setdefault(target_ref, {
                                            "target_set_name": opts["target_name"],
                                            "target_ref": target_ref,
                                            "interpretation": code_label,
                                            "ped_block": header_str,
                                            "coord_id": cid_int,
                                            "coord_code": cinfo.get("coord_code", ""),
                                            "coord_group": cinfo.get("coord_group", ""),
                                            "atoms": cinfo.get("atoms", ""),
                                            "atom_label": cinfo.get("atom_label", ""),
                                            "label": cinfo.get("label", ""),
                                            "sum_PED_in_range": 0.0,
                                            "max_PED": 0.0,
                                            "mode_qc_at_max": "",
                                            "mode_veda_at_max": "",
                                            "freq_qc_at_max": 0.0,
                                            "freq_veda_at_max": 0.0,
                                            "weight_freq_sum": 0.0,
                                            "weight_sum": 0.0,
                                            "mode_terms": [],
                                        })
                                        acc["sum_PED_in_range"] += val
                                        acc["weight_freq_sum"] += val * freq_for_filter
                                        acc["weight_sum"] += val
                                        acc["mode_terms"].append((val, meta.get("mode_qc", ""), meta.get("mode_veda", ""), freq_for_filter, rank))
                                        if val > acc["max_PED"]:
                                            acc["max_PED"] = val
                                            acc["mode_qc_at_max"] = meta.get("mode_qc", "")
                                            acc["mode_veda_at_max"] = meta.get("mode_veda", "")
                                            acc["freq_qc_at_max"] = meta.get("freq_qc", 0.0)
                                            acc["freq_veda_at_max"] = meta.get("freq_veda", 0.0)

                        target_terms_for_mode.sort(key=lambda x: x[0], reverse=True)
                        top_target_terms = "; ".join(
                            f"{cid}:{label}={val:.1f}% (rank {rank})" for val, rank, label, cid in target_terms_for_mode[:8]
                        )

                        standard_entry["target_set_name"] = opts["target_name"] if target_refs else ""
                        standard_entry["total_target_PED"] = round(target_total, 6) if target_refs else ""
                        standard_entry["max_target_PED"] = round(target_max, 6) if target_refs else ""
                        standard_entry["best_target_rank"] = best_target_rank
                        standard_entry["top_target_terms"] = top_target_terms

                        caution_msgs = list(base_cautions)
                        if standard_entry.get("note"):
                            caution_msgs.append("PED renormalized")

                        rank_out = 0
                        unknown_in_top = 0
                        for val, col_pos in contribs:
                            if rank_out >= opts["top_n"]:
                                break
                            if val < opts["standard_min_ped"]:
                                break
                            cinfo = self._coord_info_from_col(colpos_to_info, col_pos, atom_map, target_refs)
                            if cinfo.get("label") == "UNKNOWN":
                                unknown_in_top += 1
                            rnum = rank_out + 1
                            standard_entry[f"PED{rnum}_col"] = int(col_pos)
                            standard_entry[f"PED{rnum}_coord_id"] = cinfo.get("coord_id", "")
                            standard_entry[f"PED{rnum}_coord_code"] = cinfo.get("coord_code", "")
                            standard_entry[f"PED{rnum}_target_ref"] = cinfo.get("target_ref", "")
                            standard_entry[f"PED{rnum}_label"] = cinfo.get("label", "")
                            standard_entry[f"PED{rnum}_val"] = round(val, 1)
                            rank_out += 1

                        if unknown_in_top:
                            caution_msgs.append(f"UNKNOWN in top contributions({unknown_in_top})")
                        standard_entry["caution"] = "; ".join(caution_msgs)
                        standard_rows.append(standard_entry)

                        if target_refs and mode_in_range:
                            if opts["include_all_target_modes"] or target_total >= opts["target_total_min_ped"]:
                                summary_mode_rows.append({
                                    "target_set_name": opts["target_name"],
                                    "interpretation": code_label,
                                    "ped_block": header_str,
                                    **meta,
                                    "total_target_PED": round(target_total, 6),
                                    "max_target_PED": round(target_max, 6),
                                    "n_target_coords_detected": len(target_coords_detected),
                                    "best_target_rank": best_target_rank,
                                    "top_target_terms": top_target_terms,
                                })
                                if opts["output_target_matrix"]:
                                    matrix_entry["total_target_PED"] = round(target_total, 6)
                                    matrix_entry["max_target_PED"] = round(target_max, 6)
                                    matrix_entry["best_target_rank"] = best_target_rank
                                    matrix_rows.append(matrix_entry)

                    summary_coord_rows: List[dict] = []
                    for tref, acc in sorted(coord_acc.items(), key=lambda kv: str(kv[0])):
                        terms = sorted(acc.get("mode_terms", []), key=lambda x: x[0], reverse=True)
                        top_modes = "; ".join(
                            f"QC{mq or ''}/V{mv}@{fr:.1f}:{val:.1f}% (rank {rk})" for val, mq, mv, fr, rk in terms[:10]
                        )
                        weight_sum = acc.get("weight_sum", 0.0) or 0.0
                        weighted_mean_freq = (acc.get("weight_freq_sum", 0.0) / weight_sum) if weight_sum > 0 else ""
                        summary_coord_rows.append({
                            "target_set_name": acc.get("target_set_name", ""),
                            "interpretation": acc.get("interpretation", ""),
                            "ped_block": acc.get("ped_block", ""),
                            "target_ref": acc.get("target_ref", ""),
                            "coord_id": acc.get("coord_id", ""),
                            "coord_code": acc.get("coord_code", ""),
                            "coord_group": acc.get("coord_group", ""),
                            "atoms": acc.get("atoms", ""),
                            "atom_label": acc.get("atom_label", ""),
                            "label": acc.get("label", ""),
                            "max_PED": round(acc.get("max_PED", 0.0), 6),
                            "mode_qc_at_max": acc.get("mode_qc_at_max", ""),
                            "mode_veda_at_max": acc.get("mode_veda_at_max", ""),
                            "freq_qc_at_max": acc.get("freq_qc_at_max", 0.0),
                            "freq_veda_at_max": acc.get("freq_veda_at_max", 0.0),
                            "sum_PED_in_range": round(acc.get("sum_PED_in_range", 0.0), 6),
                            "weighted_mean_freq": weighted_mean_freq,
                            "n_modes_detected": len(terms),
                            "top_modes": top_modes,
                        })

                    # Standard table column order
                    if opts["output_standard"]:
                        df_standard = pd.DataFrame(standard_rows)
                        core_cols = [
                            "interpretation", "ped_block", "mode_veda", "mode_qc", "freq_veda", "freq_qc",
                            "delta_freq", "abs_delta_freq", "irrep", "IR_intensity", "ped_sum", "note",
                            "target_set_name", "total_target_PED", "max_target_PED", "best_target_rank", "top_target_terms", "caution",
                        ]
                        top_cols: List[str] = []
                        for r in range(1, opts["top_n"] + 1):
                            top_cols.extend([f"PED{r}_col", f"PED{r}_coord_id", f"PED{r}_coord_code", f"PED{r}_target_ref", f"PED{r}_label", f"PED{r}_val"])
                        ordered = [c for c in core_cols + top_cols if c in df_standard.columns]
                        df_standard = df_standard[ordered]
                        save_path = self._output_path(base, f"_PED_table_{code_label}{block_suffix}.csv")
                        df_standard.to_csv(save_path, index=False, encoding="utf-8-sig")
                        saved_files.append(save_path)
                        log_message(f"Saved standard PED table: {save_path}")

                    if opts["output_long"]:
                        df_long = pd.DataFrame(long_rows)
                        save_path = self._output_path(base, f"_PED_terms_long_{code_label}{block_suffix}.csv")
                        df_long.to_csv(save_path, index=False, encoding="utf-8-sig")
                        saved_files.append(save_path)
                        log_message(f"Saved long PED table: {save_path}")

                    if opts["output_target_hits"]:
                        df_hits = pd.DataFrame(target_hits)
                        save_path = self._output_path(base, f"_target_hits_{code_label}{block_suffix}.csv")
                        df_hits.to_csv(save_path, index=False, encoding="utf-8-sig")
                        saved_files.append(save_path)
                        log_message(f"Saved target hits: {save_path}")
                        preview_hits.append(df_hits)

                    if opts["output_summary_mode"]:
                        df_sum_mode = pd.DataFrame(summary_mode_rows)
                        if not df_sum_mode.empty:
                            df_sum_mode = df_sum_mode.sort_values(["total_target_PED", "freq_qc"], ascending=[False, True])
                        save_path = self._output_path(base, f"_target_summary_by_mode_{code_label}{block_suffix}.csv")
                        df_sum_mode.to_csv(save_path, index=False, encoding="utf-8-sig")
                        saved_files.append(save_path)
                        log_message(f"Saved target summary by mode: {save_path}")
                        preview_summary_mode.append(df_sum_mode)

                    if opts["output_summary_coord"]:
                        df_sum_coord = pd.DataFrame(summary_coord_rows)
                        if not df_sum_coord.empty:
                            df_sum_coord = df_sum_coord.sort_values(["sum_PED_in_range", "max_PED"], ascending=[False, False])
                        save_path = self._output_path(base, f"_target_summary_by_coord_{code_label}{block_suffix}.csv")
                        df_sum_coord.to_csv(save_path, index=False, encoding="utf-8-sig")
                        saved_files.append(save_path)
                        log_message(f"Saved target summary by coordinate: {save_path}")
                        preview_summary_coord.append(df_sum_coord)

                    if opts["output_target_matrix"]:
                        df_matrix = pd.DataFrame(matrix_rows)
                        save_path = self._output_path(base, f"_target_matrix_{code_label}{block_suffix}.csv")
                        df_matrix.to_csv(save_path, index=False, encoding="utf-8-sig")
                        saved_files.append(save_path)
                        log_message(f"Saved target matrix: {save_path}")

            if opts.get("output_combined_target") and target_refs:
                combined_files, df_csum_mode, df_chits, df_csum_coord = self._generate_combined_target_outputs(
                    base, ctx, ped_blocks, coords, atom_map, target_refs, opts
                )
                saved_files.extend(combined_files)
                if df_csum_mode is not None and not df_csum_mode.empty:
                    preview_summary_mode.append(df_csum_mode)
                if df_chits is not None and not df_chits.empty:
                    preview_hits.append(df_chits)
                if df_csum_coord is not None and not df_csum_coord.empty:
                    preview_summary_coord.append(df_csum_coord)

            lookup_path = self._output_path(base, "_coordinates_lookup.csv")
            export_internal_coordinate_lookup_csv(self.dd2_path, lookup_path, fmu_path=self.fmu_path, atom_map=atom_map)
            saved_files.append(lookup_path)

            self._save_current_config()
            self.status_lbl.config(text="Done", fg="green")

            if preview_summary_mode:
                self._preview_dfs["summary_by_mode"] = pd.concat(preview_summary_mode, ignore_index=True)
            else:
                self._preview_dfs["summary_by_mode"] = pd.DataFrame()
            if preview_hits:
                self._preview_dfs["hits"] = pd.concat(preview_hits, ignore_index=True)
            else:
                self._preview_dfs["hits"] = pd.DataFrame()
            if preview_summary_coord:
                self._preview_dfs["summary_by_coord"] = pd.concat(preview_summary_coord, ignore_index=True)
            else:
                self._preview_dfs["summary_by_coord"] = pd.DataFrame()

            self._populate_tree(self.summary_mode_tree, self._preview_dfs["summary_by_mode"], max_rows=300)
            self._populate_tree(self.hits_tree, self._preview_dfs["hits"], max_rows=300)
            self._populate_tree(self.summary_coord_tree, self._preview_dfs["summary_by_coord"], max_rows=300)

            msg_lines = ["Analysis complete.", "", "Saved files:"]
            msg_lines.extend(f"- {Path(f).name}" for f in saved_files)
            msg_lines.append("")
            msg_lines.append(f"Log: {_ensure_log_path()}")
            msg = "\n".join(msg_lines)
            self._set_text(self.run_text, msg)
            self._set_text(self.results_text, msg)
            messagebox.showinfo("Success", msg)

        except Exception as e:
            self.status_lbl.config(text="Error occurred", fg="red")
            log_caution("Run Target Analysis failed.")
            log_error("Run Target Analysis", e)
            self._set_text(self.run_text, f"Run failed:\n{e}\n\nSee log: {_ensure_log_path()}")
            messagebox.showerror("Error", f"An error occurred:\n{str(e)}\n\nSee log:\n{_ensure_log_path()}")


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
