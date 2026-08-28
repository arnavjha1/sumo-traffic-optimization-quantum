#!/usr/bin/env python3
"""
Run every traffic controller for both experiment families.

Expected folder layout (runner sits beside grid_2x2/ and grid_3x3/):

    run_all_traffic_experiments.py
    grid_2x2/
        0_fixed/a7.py
        0_fixed/data.py
        1_classical/a7.py
        1_classical/data.py
        2_classical_global/a7.py
        2_classical_global/data.py
        3_quantum/a7.py
        3_quantum/data.py
        4_RL/co_light/a7.py
        4_RL/co_light/data.py
        4_RL/mp_light/a7.py
        4_RL/mp_light/data.py
        4_RL/press_light/a7.py
        4_RL/press_light/data.py
        4_RL/max_pressure/a7.py
        4_RL/max_pressure/data.py
        5_SCOOT/a7.py
        5_SCOOT/data.py
    grid_3x3/
        ...same controller subfolders...

Default behavior:
1. Saturated alpha sweep:
      2 grids x 9 controllers x 11 alpha values = 198 runs
      Calls each a7.py with alpha 0..10.
      Saves/checkpoints everything to:
          all_alpha_results.json

2. Seattle experiment:
      2 grids x 9 controllers = 18 runs
      Calls each data.py once.
      Saves/checkpoints everything to:
          all_seattle_results.json

Important compatibility behavior:
- Current 2x2 a7.py files may ignore sys.argv and hard-code sim2x2_a7.sumocfg.
  This runner still passes the alpha argument, but also launches a TEMPORARY copy
  of the script with SUMO_CONFIG pointed at the requested alpha config.
- If sim{grid}_aX.sumocfg does not exist, the runner can create a TEMPORARY
  alpha-specific config from the a7 config by replacing the a7 route reference.
  Original source/config files are never overwritten.
- SUMO_CONFIG, ROUTE_FILE, and MODEL_PATH are rewritten only in the temporary
  launch copy to absolute paths when resolvable. This avoids working-directory
  problems caused by the nested controller folders.
- sumo-gui is changed to sumo in the temporary copy by default for unattended
  batch execution. Use --keep-gui to disable that behavior.
- Results are checkpointed atomically after EVERY run.
- Successful runs are skipped automatically on restart. Failed runs are retried.
- Full stdout and stderr are retained in the JSON files, in addition to parsed
  graph-ready metrics.

Run:
    python run_all_traffic_experiments.py

Useful:
    python run_all_traffic_experiments.py --dry-run
    python run_all_traffic_experiments.py --skip-seattle
    python run_all_traffic_experiments.py --skip-saturated
    python run_all_traffic_experiments.py --only-grid 2x2
    python run_all_traffic_experiments.py --only-controller quantum
    python run_all_traffic_experiments.py --alpha 7
    python run_all_traffic_experiments.py --no-resume
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


# ============================================================
# EXPERIMENT DEFINITION
# ============================================================

RUNNER_VERSION = "1.1"

BASE_DIR = Path(__file__).resolve().parent

ALPHA_OUTPUT_FILE = BASE_DIR / "all_alpha_results.json"
SEATTLE_OUTPUT_FILE = BASE_DIR / "all_seattle_results.json"

DEFAULT_SATURATED_TIMEOUT_SECONDS = 6 * 60 * 60
DEFAULT_SEATTLE_TIMEOUT_SECONDS = 12 * 60 * 60

ALPHA_VALUES = list(range(11))

CONTROLLERS = [
    ("fixed", "0_fixed"),
    ("classical_local", "1_classical"),
    ("classical_global", "2_classical_global"),
    ("colight", "4_RL/co_light"),
    ("mplight", "4_RL/mp_light"),
    ("presslight", "4_RL/press_light"),
    ("max_pressure", "4_RL/max_pressure"),
    ("scoot", "5_SCOOT"),
]

GRID_SPECS = {
    "2x2": {
        "folder": "grid_2x2",
        "config_prefix": "sim2x2",
    },
    "3x3": {
        "folder": "grid_3x3",
        "config_prefix": "sim3x3",
    },
}


# ============================================================
# GENERAL HELPERS
# ============================================================

NUMBER_RE = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"


def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def ensure_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def load_json_if_present(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None

    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else None
    except Exception:
        print(
            f"WARNING: Could not load existing checkpoint {path}. "
            f"A new result structure will be created.",
            flush=True,
        )
        return None


def relative_display(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(BASE_DIR.resolve()))
    except Exception:
        return str(path.resolve())


def build_subprocess_environment(
    controller_dir: Path,
    grid_dir: Path,
) -> Dict[str, str]:
    """
    Keep the user's normal environment and make all likely Python module
    locations importable. This helps agent.py / annealer_*.py resolve without
    forcing a particular working directory.
    """
    env = os.environ.copy()

    python_paths = [
        str(controller_dir.resolve()),
        str(controller_dir.parent.resolve()),
        str(grid_dir.resolve()),
        str(BASE_DIR.resolve()),
    ]

    existing = env.get("PYTHONPATH")
    if existing:
        python_paths.append(existing)

    # Preserve order while removing duplicates.
    seen = set()
    deduped = []
    for item in python_paths:
        if item not in seen:
            seen.add(item)
            deduped.append(item)

    env["PYTHONPATH"] = os.pathsep.join(deduped)
    return env


# ============================================================
# SOURCE / PATH RESOLUTION
# ============================================================

_ASSIGNMENT_PATTERN_CACHE: Dict[str, re.Pattern[str]] = {}


def assignment_pattern(variable: str) -> re.Pattern[str]:
    pattern = _ASSIGNMENT_PATTERN_CACHE.get(variable)
    if pattern is None:
        pattern = re.compile(
            rf"(?m)^(?P<indent>[ \t]*){re.escape(variable)}[ \t]*=.*$"
        )
        _ASSIGNMENT_PATTERN_CACHE[variable] = pattern
    return pattern


def replace_assignment(
    source: str,
    variable: str,
    python_value_literal: str,
    *,
    replace_all: bool = True,
) -> Tuple[str, int]:
    """
    Replace top-level/simple assignment lines such as:
        MODEL_PATH = "foo.pt"
        SUMO_CONFIG = f"..."
    """
    pattern = assignment_pattern(variable)
    matches = list(pattern.finditer(source))
    if not matches:
        return source, 0

    count = 0 if replace_all else 1

    def repl(match: re.Match[str]) -> str:
        return f"{match.group('indent')}{variable} = {python_value_literal}"

    new_source, num = pattern.subn(
        repl,
        source,
        count=count,
    )
    return new_source, num


_SIMPLE_STRING_ASSIGNMENT = re.compile(
    r"""(?m)^[ \t]*(?P<var>[A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*
        (?P<f>f)?(?P<quote>["'])(?P<value>.*?)(?P=quote)[ \t]*(?:\#.*)?$
    """,
    re.VERBOSE,
)


def get_last_simple_string_assignment(
    source: str,
    variable: str,
) -> Optional[str]:
    values = []
    for match in _SIMPLE_STRING_ASSIGNMENT.finditer(source):
        if match.group("var") == variable:
            values.append(match.group("value"))
    return values[-1] if values else None


def substitute_alpha_tokens(value: str, alpha: int) -> str:
    replacements = {
        "{ALPHA_INDEX}": str(alpha),
        "{alpha_index}": str(alpha),
        "{ALPHA}": str(alpha),
        "{alpha}": str(alpha),
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    return value


def find_existing_file(
    filename_or_relative: str,
    *,
    controller_dir: Path,
    grid_dir: Path,
) -> Optional[Path]:
    """
    Resolve a path from the most likely locations without changing user files.
    """
    raw = Path(filename_or_relative)

    if raw.is_absolute() and raw.is_file():
        return raw.resolve()

    candidates = [
        controller_dir / raw,
        controller_dir.parent / raw,
        grid_dir / raw,
        BASE_DIR / raw,
    ]

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    # Last resort: search by basename inside the grid tree.
    basename = raw.name
    if basename:
        matches = list(grid_dir.rglob(basename))
        if len(matches) == 1 and matches[0].is_file():
            return matches[0].resolve()

        # Prefer a hit under this controller if multiple copies exist.
        controller_matches = [
            p for p in matches
            if p.is_file() and controller_dir in p.parents
        ]
        if len(controller_matches) == 1:
            return controller_matches[0].resolve()

    return None


def expected_config_path(
    grid_key: str,
    mode: str,
    alpha: Optional[int] = None,
) -> Path:
    spec = GRID_SPECS[grid_key]
    prefix = spec["config_prefix"]

    if mode == "saturated":
        if alpha is None:
            raise ValueError("alpha is required for saturated config lookup")

        return BASE_DIR / f"{prefix}_a{alpha}.sumocfg"

    if mode == "seattle":
        return BASE_DIR / f"{prefix}_data.sumocfg"

    raise ValueError(f"Unknown mode: {mode}")


def parse_route_files_from_sumocfg(config_path: Path) -> List[str]:
    """
    Best-effort extraction of <route-files value="...">.
    """
    try:
        tree = ET.parse(config_path)
        root = tree.getroot()
    except Exception:
        return []

    values: List[str] = []

    for element in root.iter():
        tag = element.tag.split("}")[-1]
        if tag == "route-files":
            raw = element.attrib.get("value", "")
            values.extend(
                item.strip()
                for item in raw.split(",")
                if item.strip()
            )

    return values


def validate_config_route_files(config_path: Path) -> Tuple[bool, List[str]]:
    """
    Validate route files when the SUMO config exposes them directly.
    If there is no route-files element, return success because the config may
    reference routes through another mechanism.
    """
    route_values = parse_route_files_from_sumocfg(config_path)
    if not route_values:
        return True, []

    missing = []
    for raw in route_values:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = config_path.parent / candidate
        if not candidate.is_file():
            missing.append(str(candidate))

    return len(missing) == 0, missing


def make_alpha_config_from_a7_template(
    *,
    grid_key: str,
    alpha: int,
) -> Optional[Path]:
    """
    Compatibility fallback for legacy 2x2-style setups where only the a7
    SUMO config exists and a7.py itself ignores the alpha command-line value.

    A temporary config is written BESIDE the original a7 config so its relative
    route-file paths keep the same meaning. The caller must delete it.
    """
    spec = GRID_SPECS[grid_key]
    grid_dir = BASE_DIR / spec["folder"]
    prefix = spec["config_prefix"]

    template = grid_dir / f"{prefix}_a7.sumocfg"
    if not template.is_file():
        return None

    text = template.read_text(encoding="utf-8")

    # Replace alpha token a7 only when it is not embedded in a larger number.
    # Examples handled:
    #   routes_a7.rou.xml
    #   routes3x3_a7.rou.xml
    #   /a7/
    replaced = re.sub(
        r"(?i)(?<![A-Za-z0-9])a7(?!\d)",
        f"a{alpha}",
        text,
    )

    # Also catch the common "_a7" case because the previous boundary rule sees
    # the underscore as a word-ish separator in some naming conventions.
    replaced = replaced.replace("_a7", f"_a{alpha}")

    if replaced == text and alpha != 7:
        # We cannot safely infer how the route is selected.
        return None

    fd, temp_name = tempfile.mkstemp(
        prefix=f".__runner_{prefix}_a{alpha}_",
        suffix=".sumocfg",
        dir=str(grid_dir),
        text=True,
    )
    os.close(fd)

    temp_path = Path(temp_name)
    temp_path.write_text(replaced, encoding="utf-8")

    ok, missing = validate_config_route_files(temp_path)
    if not ok:
        temp_path.unlink(missing_ok=True)
        return None

    return temp_path


def resolve_config_for_run(
    *,
    grid_key: str,
    mode: str,
    alpha: Optional[int],
) -> Tuple[Path, Optional[Path]]:
    """
    Returns:
        config_path,
        temporary_config_to_cleanup (or None)
    """
    expected = expected_config_path(grid_key, mode, alpha)

    if expected.is_file():
        return expected.resolve(), None

    # Search recursively for the exact expected basename.
    
    matches = list(BASE_DIR.rglob(expected.name))
    if len(matches) == 1:
        return matches[0].resolve(), None

    if mode == "saturated" and alpha is not None:
        temp = make_alpha_config_from_a7_template(
            grid_key=grid_key,
            alpha=alpha,
        )
        if temp is not None:
            return temp.resolve(), temp

    raise FileNotFoundError(
        f"Could not resolve SUMO config for grid={grid_key}, "
        f"mode={mode}, alpha={alpha}. Expected: {expected}"
    )


def resolve_explicit_route_file(
    *,
    source: str,
    alpha: int,
    controller_dir: Path,
    grid_dir: Path,
) -> Optional[Path]:
    raw = get_last_simple_string_assignment(source, "ROUTE_FILE")
    if raw is None:
        return None

    substituted = substitute_alpha_tokens(raw, alpha)
    resolved = find_existing_file(
        substituted,
        controller_dir=controller_dir,
        grid_dir=grid_dir,
    )
    return resolved


def resolve_model_file(
    *,
    source: str,
    controller_dir: Path,
    grid_dir: Path,
) -> Optional[Path]:
    raw = get_last_simple_string_assignment(source, "MODEL_PATH")
    if raw is None:
        return None

    return find_existing_file(
        raw,
        controller_dir=controller_dir,
        grid_dir=grid_dir,
    )


def build_temporary_launch_script(
    *,
    script_path: Path,
    grid_key: str,
    mode: str,
    alpha: Optional[int],
    config_path: Path,
    force_headless: bool,
) -> Tuple[Path, List[str]]:
    """
    Create a temporary copy in the same controller directory.

    Only path/execution-environment assignments are adjusted. Controller logic
    is left untouched.
    """
    controller_dir = script_path.parent
    grid_dir = BASE_DIR / GRID_SPECS[grid_key]["folder"]

    source = script_path.read_text(encoding="utf-8")
    notes: List[str] = []

    # Absolute config path eliminates cwd ambiguity.
    source, n = replace_assignment(
        source,
        "SUMO_CONFIG",
        repr(str(config_path.resolve())),
    )
    if n:
        notes.append(
            f"SUMO_CONFIG -> {config_path.resolve()}"
        )

    # If the controller separately passes a route file, resolve it for alpha.
    if mode == "saturated" and alpha is not None:
        route_file = resolve_explicit_route_file(
            source=script_path.read_text(encoding="utf-8"),
            alpha=alpha,
            controller_dir=controller_dir,
            grid_dir=grid_dir,
        )

        if get_last_simple_string_assignment(
            script_path.read_text(encoding="utf-8"),
            "ROUTE_FILE",
        ) is not None:
            if route_file is None:
                raise FileNotFoundError(
                    f"{relative_display(script_path)} defines ROUTE_FILE, "
                    f"but the alpha={alpha} route file could not be resolved."
                )

            source, n = replace_assignment(
                source,
                "ROUTE_FILE",
                repr(str(route_file.resolve())),
            )
            if n:
                notes.append(
                    f"ROUTE_FILE -> {route_file.resolve()}"
                )

    # Resolve frozen RL model paths without requiring a special cwd.
    original_source = script_path.read_text(encoding="utf-8")
    model_literal = get_last_simple_string_assignment(
        original_source,
        "MODEL_PATH",
    )
    if model_literal is not None:
        model_path = resolve_model_file(
            source=original_source,
            controller_dir=controller_dir,
            grid_dir=grid_dir,
        )

        if model_path is not None:
            source, n = replace_assignment(
                source,
                "MODEL_PATH",
                repr(str(model_path.resolve())),
            )
            if n:
                notes.append(
                    f"MODEL_PATH -> {model_path.resolve()}"
                )
        else:
            notes.append(
                f"WARNING: MODEL_PATH '{model_literal}' was not pre-resolved; "
                f"script will use its original relative path."
            )

    if force_headless:
        source, n = replace_assignment(
            source,
            "SUMO_BINARY",
            repr("sumo"),
        )
        if n:
            notes.append("SUMO_BINARY -> sumo (headless batch mode)")

    fd, temp_name = tempfile.mkstemp(
        prefix=".__runner_",
        suffix=".py",
        dir=str(controller_dir),
        text=True,
    )
    os.close(fd)

    temp_path = Path(temp_name)
    temp_path.write_text(source, encoding="utf-8")

    # Fail early if our temporary source is syntactically invalid.
    compile(source, str(temp_path), "exec")

    return temp_path, notes


# ============================================================
# OUTPUT PARSING
# ============================================================

def parse_optional_float(value: str) -> Optional[float]:
    if value.strip().upper() == "N/A":
        return None
    return float(value)


def extract_tagged_json_blocks(output: str) -> Dict[str, Any]:
    """
    Capture machine-readable lines already emitted by QAOA/global controllers,
    e.g. ENERGY_JSON, HOURLY_ENERGY_JSON, HOURLY_QAOA_PARAMS_JSON.
    """
    parsed: Dict[str, Any] = {}

    pattern = re.compile(
        r"(?m)^(?P<key>[A-Z][A-Z0-9_]*JSON):\s*(?P<value>.+?)\s*$"
    )

    for match in pattern.finditer(output):
        key = match.group("key")
        raw = match.group("value")
        try:
            parsed[key] = json.loads(raw)
        except json.JSONDecodeError:
            parsed[key] = {
                "_parse_error": True,
                "_raw": raw,
            }

    return parsed


def find_section_overall(
    output: str,
    heading: str,
    *,
    integer: bool = False,
) -> Optional[float]:
    lines = output.splitlines()

    heading_norm = heading.strip().lower()

    for i, line in enumerate(lines):
        if line.strip().lower() != heading_norm:
            continue

        for candidate in lines[i + 1 : i + 20]:
            stripped = candidate.strip()

            if stripped.lower().startswith("overall:"):
                raw = stripped.split(":", 1)[1].strip()
                match = re.search(NUMBER_RE, raw)
                if not match:
                    return None
                value = float(match.group(0))
                return int(round(value)) if integer else value

            # Stop if another major metric section begins before Overall.
            if stripped.lower() in {
                "average travel time:",
                "average waiting time:",
                "throughput:",
            }:
                break

    return None


def parse_saturated_traffic(output: str) -> Dict[str, Any]:
    """
    Supports both families currently present in the project:

    3x3/direct style:
        Average Travel Time: 182.23 s
        Average Waiting Time: 44.21 s
        Throughput: 944

    legacy 2x2 route-category style:
        Average Travel Time:
          Two Turns: ...
          ...
          Overall: 123.45 s
    """
    result: Dict[str, Any] = {}

    direct_tt = re.findall(
        rf"(?mi)^[ \t]*Average Travel Time:[ \t]*(?P<v>{NUMBER_RE})[ \t]*s?[ \t]*$",
        output,
    )
    direct_wt = re.findall(
        rf"(?mi)^[ \t]*Average Waiting Time:[ \t]*(?P<v>{NUMBER_RE})[ \t]*s?[ \t]*$",
        output,
    )
    direct_thr = re.findall(
        r"(?mi)^[ \t]*(?:Throughput|Measured completed vehicles):[ \t]*(\d+)[ \t]*$",
        output,
    )

    tt = float(direct_tt[-1]) if direct_tt else None
    wt = float(direct_wt[-1]) if direct_wt else None
    throughput = int(direct_thr[-1]) if direct_thr else None

    if tt is None:
        tt = find_section_overall(
            output,
            "Average Travel Time:",
        )

    if wt is None:
        wt = find_section_overall(
            output,
            "Average Waiting Time:",
        )

    if throughput is None:
        throughput_value = find_section_overall(
            output,
            "Throughput:",
            integer=True,
        )
        throughput = (
            int(throughput_value)
            if throughput_value is not None
            else None
        )

    result["average_travel_time"] = tt
    result["average_waiting_time"] = wt
    result["throughput"] = throughput

    # Useful accounting values when emitted by the newer 3x3 controllers.
    inserted_match = re.findall(
        r"(?mi)^[ \t]*Vehicles inserted:[ \t]*(\d+)[ \t]*$",
        output,
    )
    still_match = re.findall(
        r"(?mi)^[ \t]*Vehicles still in network.*?:[ \t]*(\d+)[ \t]*$",
        output,
    )

    result["vehicles_inserted"] = (
        int(inserted_match[-1]) if inserted_match else None
    )
    result["vehicles_still_in_network"] = (
        int(still_match[-1]) if still_match else None
    )

    return result


HOURLY_SEATTLE_PATTERN = re.compile(
    rf"(?mi)^[ \t]*Hour[ \t]+(?P<hour>\d{{2}}):[ \t]*"
    rf"TT=(?P<tt>N/A|{NUMBER_RE})(?:[ \t]*s)?[ \t]*,[ \t]*"
    rf"WT=(?P<wt>N/A|{NUMBER_RE})(?:[ \t]*s)?[ \t]*,[ \t]*"
    rf"n=(?P<n>\d+)"
    rf"(?P<rest>[^\n]*)$"
)


def parse_optional_named_int(rest: str, key: str) -> Optional[int]:
    match = re.search(
        rf"(?i)\b{re.escape(key)}[ \t]*=[ \t]*(\d+)",
        rest,
    )
    return int(match.group(1)) if match else None


def parse_seattle_traffic(output: str) -> Dict[str, Any]:
    hourly_by_hour: Dict[int, Dict[str, Any]] = {}

    for match in HOURLY_SEATTLE_PATTERN.finditer(output):
        hour = int(match.group("hour"))
        if not 0 <= hour <= 23:
            continue

        rest = match.group("rest") or ""

        hourly_by_hour[hour] = {
            "hour": hour,
            "average_travel_time": parse_optional_float(
                match.group("tt")
            ),
            "average_waiting_time": parse_optional_float(
                match.group("wt")
            ),
            "completed_vehicles": int(match.group("n")),
            "measured_departures": parse_optional_named_int(
                rest,
                "departed",
            ),
            "unfinished": parse_optional_named_int(
                rest,
                "unfinished",
            ),
        }

    hourly = [
        hourly_by_hour[h]
        for h in sorted(hourly_by_hour)
    ]

    overall_match = re.search(
        rf"(?mis)Post-warm-up Overall:[ \t]*\n"
        rf".*?Average Travel Time:[ \t]*(?P<tt>{NUMBER_RE})[ \t]*s"
        rf".*?Average Waiting Time:[ \t]*(?P<wt>{NUMBER_RE})[ \t]*s"
        rf".*?Measured completed vehicles:[ \t]*(?P<n>\d+)",
        output,
    )

    overall = None
    if overall_match:
        overall = {
            "average_travel_time": float(
                overall_match.group("tt")
            ),
            "average_waiting_time": float(
                overall_match.group("wt")
            ),
            "completed_vehicles": int(
                overall_match.group("n")
            ),
        }

        measured_departures_match = re.search(
            r"(?mi)^[ \t]*Measured departures:[ \t]*(\d+)[ \t]*$",
            output,
        )
        unfinished_match = re.search(
            r"(?mi)^[ \t]*Measured unfinished.*?:[ \t]*(\d+)[ \t]*$",
            output,
        )

        overall["measured_departures"] = (
            int(measured_departures_match.group(1))
            if measured_departures_match
            else None
        )
        overall["unfinished"] = (
            int(unfinished_match.group(1))
            if unfinished_match
            else None
        )

    return {
        "hourly": hourly,
        "hours_parsed": len(hourly),
        "missing_hours": sorted(
            set(range(24)) - set(hourly_by_hour)
        ),
        "overall": overall,
    }


def parse_output(
    *,
    mode: str,
    output: str,
) -> Dict[str, Any]:
    parsed: Dict[str, Any] = {
        "tagged_json": extract_tagged_json_blocks(output),
    }

    if mode == "saturated":
        parsed["traffic"] = parse_saturated_traffic(output)
    elif mode == "seattle":
        parsed["traffic"] = parse_seattle_traffic(output)
    else:
        raise ValueError(f"Unknown parse mode: {mode}")

    return parsed


# ============================================================
# RESULT STRUCTURES / GRAPH-READY SUMMARIES
# ============================================================

def saturated_run_key(run: Dict[str, Any]) -> Tuple[str, str, int]:
    return (
        str(run["grid"]),
        str(run["controller"]),
        int(run["alpha_index"]),
    )


def seattle_run_key(run: Dict[str, Any]) -> Tuple[str, str]:
    return (
        str(run["grid"]),
        str(run["controller"]),
    )


def upsert_run(
    runs: List[Dict[str, Any]],
    record: Dict[str, Any],
    *,
    mode: str,
) -> None:
    key_func = (
        saturated_run_key
        if mode == "saturated"
        else seattle_run_key
    )
    key = key_func(record)

    for i, existing in enumerate(runs):
        try:
            if key_func(existing) == key:
                runs[i] = record
                return
        except Exception:
            continue

    runs.append(record)


def successful_keys(
    runs: Iterable[Dict[str, Any]],
    *,
    mode: str,
) -> set:
    key_func = (
        saturated_run_key
        if mode == "saturated"
        else seattle_run_key
    )

    result = set()
    for run in runs:
        if run.get("status") == "success":
            try:
                result.add(key_func(run))
            except Exception:
                pass
    return result


def build_alpha_graph_data(
    runs: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Convenient structure for reconstructing alpha-sweep graphs without
    reparsing raw stdout.
    """
    result: Dict[str, Any] = {}

    successful = [
        r for r in runs
        if r.get("status") == "success"
    ]

    for grid_key in GRID_SPECS:
        result[grid_key] = {}

        for controller_name, _ in CONTROLLERS:
            points = []

            matching = sorted(
                (
                    r for r in successful
                    if r.get("grid") == grid_key
                    and r.get("controller") == controller_name
                ),
                key=lambda r: int(r.get("alpha_index", -1)),
            )

            for run in matching:
                traffic = (
                    run.get("parsed", {})
                    .get("traffic", {})
                )

                points.append({
                    "alpha_index": run.get("alpha_index"),
                    "alpha": run.get("alpha"),
                    "average_travel_time":
                        traffic.get("average_travel_time"),
                    "average_waiting_time":
                        traffic.get("average_waiting_time"),
                    "throughput":
                        traffic.get("throughput"),
                    "vehicles_inserted":
                        traffic.get("vehicles_inserted"),
                    "vehicles_still_in_network":
                        traffic.get("vehicles_still_in_network"),
                })

            result[grid_key][controller_name] = points

    return result


def build_seattle_graph_data(
    runs: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {}

    successful = [
        r for r in runs
        if r.get("status") == "success"
    ]

    for grid_key in GRID_SPECS:
        result[grid_key] = {}

        for controller_name, _ in CONTROLLERS:
            matching = [
                r for r in successful
                if r.get("grid") == grid_key
                and r.get("controller") == controller_name
            ]

            if not matching:
                result[grid_key][controller_name] = None
                continue

            run = matching[-1]
            traffic = (
                run.get("parsed", {})
                .get("traffic", {})
            )

            result[grid_key][controller_name] = {
                "hourly": traffic.get("hourly", []),
                "overall": traffic.get("overall"),
                "hours_parsed": traffic.get("hours_parsed"),
                "missing_hours": traffic.get("missing_hours", []),
            }

    return result


def create_result_document(mode: str) -> Dict[str, Any]:
    if mode == "saturated":
        planned = (
            len(GRID_SPECS)
            * len(CONTROLLERS)
            * len(ALPHA_VALUES)
        )
        description = (
            "2 grids x 9 controllers x 11 alpha values"
        )
    else:
        planned = (
            len(GRID_SPECS)
            * len(CONTROLLERS)
        )
        description = (
            "2 grids x 9 controllers"
        )

    return {
        "runner_version": RUNNER_VERSION,
        "mode": mode,
        "created_at": now_iso(),
        "last_updated_at": now_iso(),
        "base_directory": str(BASE_DIR),
        "planned_runs_full_suite": planned,
        "planned_runs_description": description,
        "controllers": [
            {
                "name": name,
                "subfolder": subfolder,
            }
            for name, subfolder in CONTROLLERS
        ],
        "grids": GRID_SPECS,
        "runs": [],
        "graph_data": {},
        "summary": {},
    }


def refresh_result_document(
    document: Dict[str, Any],
    *,
    mode: str,
) -> None:
    runs = document.setdefault("runs", [])

    success_count = sum(
        r.get("status") == "success"
        for r in runs
    )
    failure_count = sum(
        r.get("status") == "failed"
        for r in runs
    )
    timeout_count = sum(
        r.get("status") == "timeout"
        for r in runs
    )

    parse_warning_count = sum(
        bool(r.get("parse_warnings"))
        for r in runs
    )

    document["last_updated_at"] = now_iso()
    document["summary"] = {
        "records_in_file": len(runs),
        "successful": success_count,
        "failed": failure_count,
        "timed_out": timeout_count,
        "with_parse_warnings": parse_warning_count,
    }

    if mode == "saturated":
        document["graph_data"] = build_alpha_graph_data(runs)
    else:
        document["graph_data"] = build_seattle_graph_data(runs)


# ============================================================
# PREFLIGHT
# ============================================================

def selected_grids(args: argparse.Namespace) -> List[str]:
    if args.only_grid:
        return [args.only_grid]
    return list(GRID_SPECS.keys())


def selected_controllers(
    args: argparse.Namespace,
) -> List[Tuple[str, str]]:
    if args.only_controller:
        return [
            item for item in CONTROLLERS
            if item[0] == args.only_controller
        ]
    return CONTROLLERS.copy()


def selected_alphas(args: argparse.Namespace) -> List[int]:
    if args.alpha is not None:
        values = sorted(set(args.alpha))
        for value in values:
            if not 0 <= value <= 10:
                raise ValueError(
                    f"Alpha index must be 0..10, got {value}"
                )
        return values
    return ALPHA_VALUES.copy()


def controller_script(
    grid_key: str,
    subfolder: str,
    filename: str,
) -> Path:
    return (
        BASE_DIR
        / GRID_SPECS[grid_key]["folder"]
        / Path(subfolder)
        / filename
    )


def preflight(
    args: argparse.Namespace,
) -> List[str]:
    errors: List[str] = []

    grids = selected_grids(args)
    controllers = selected_controllers(args)
    alphas = selected_alphas(args)

    if not args.skip_saturated:
        for grid_key in grids:
            for controller_name, subfolder in controllers:
                script = controller_script(
                    grid_key,
                    subfolder,
                    "a7.py",
                )
                if not script.is_file():
                    errors.append(
                        f"Missing a7.py: {relative_display(script)}"
                    )

            # Validate alpha configs or compatibility fallback.
            for alpha in alphas:
                expected = expected_config_path(
                    grid_key,
                    "saturated",
                    alpha,
                )

                if expected.is_file():
                    continue

                grid_dir = (
                    BASE_DIR
                    / GRID_SPECS[grid_key]["folder"]
                )
                if list(grid_dir.rglob(expected.name)):
                    continue

                template = (
                    grid_dir
                    / f"{GRID_SPECS[grid_key]['config_prefix']}_a7.sumocfg"
                )
                if not template.is_file():
                    errors.append(
                        f"Missing alpha config {expected.name} "
                        f"and no a7 template exists in "
                        f"{relative_display(grid_dir)}"
                    )

    if not args.skip_seattle:
        for grid_key in grids:
            for controller_name, subfolder in controllers:
                script = controller_script(
                    grid_key,
                    subfolder,
                    "data.py",
                )
                if not script.is_file():
                    errors.append(
                        f"Missing data.py: {relative_display(script)}"
                    )

            expected = expected_config_path(
                grid_key,
                "seattle",
            )
            if not expected.is_file():
                grid_dir = (
                    BASE_DIR
                    / GRID_SPECS[grid_key]["folder"]
                )
                matches = list(grid_dir.rglob(expected.name))
                if not matches:
                    errors.append(
                        f"Missing Seattle config: "
                        f"{relative_display(expected)}"
                    )

    if shutil.which("sumo") is None and not args.keep_gui:
        errors.append(
            "Could not find the 'sumo' executable on PATH. "
            "Either fix SUMO PATH or use --keep-gui if your "
            "scripts intentionally use sumo-gui."
        )

    return errors


def print_plan(args: argparse.Namespace) -> None:
    grids = selected_grids(args)
    controllers = selected_controllers(args)
    alphas = selected_alphas(args)

    print("\n===== BATCH PLAN =====")

    if not args.skip_saturated:
        saturated_count = (
            len(grids)
            * len(controllers)
            * len(alphas)
        )
        print(
            f"Saturated: {saturated_count} runs "
            f"({len(grids)} grids x "
            f"{len(controllers)} controllers x "
            f"{len(alphas)} alphas)"
        )
        print(
            f"Alpha JSON: {ALPHA_OUTPUT_FILE}"
        )

    if not args.skip_seattle:
        seattle_count = (
            len(grids)
            * len(controllers)
        )
        print(
            f"Seattle:   {seattle_count} runs "
            f"({len(grids)} grids x "
            f"{len(controllers)} controllers)"
        )
        print(
            f"Seattle JSON: {SEATTLE_OUTPUT_FILE}"
        )

    print(
        f"Resume successful runs: "
        f"{'NO' if args.no_resume else 'YES'}"
    )
    print(
        f"SUMO mode: "
        f"{'keep script setting' if args.keep_gui else 'headless sumo'}"
    )
    print("======================\n")


# ============================================================
# ONE RUN
# ============================================================

def build_parse_warnings(
    *,
    mode: str,
    parsed: Dict[str, Any],
) -> List[str]:
    warnings: List[str] = []

    traffic = parsed.get("traffic", {})

    if mode == "saturated":
        for field in (
            "average_travel_time",
            "average_waiting_time",
            "throughput",
        ):
            if traffic.get(field) is None:
                warnings.append(
                    f"Could not parse saturated {field}"
                )

    else:
        if traffic.get("overall") is None:
            warnings.append(
                "Could not parse Seattle overall traffic metrics"
            )

        missing = traffic.get("missing_hours", [])
        if missing:
            warnings.append(
                f"Seattle hourly parser missing hours: {missing}"
            )

    return warnings


def run_one(
    *,
    grid_key: str,
    controller_name: str,
    subfolder: str,
    mode: str,
    alpha: Optional[int],
    timeout_seconds: int,
    force_headless: bool,
) -> Dict[str, Any]:
    filename = (
        "a7.py"
        if mode == "saturated"
        else "data.py"
    )

    script_path = controller_script(
        grid_key,
        subfolder,
        filename,
    )

    controller_dir = script_path.parent
    grid_dir = (
        BASE_DIR
        / GRID_SPECS[grid_key]["folder"]
    )

    started_at = now_iso()
    start_perf = time.perf_counter()

    temp_script: Optional[Path] = None
    temp_config: Optional[Path] = None

    record: Dict[str, Any] = {
        "grid": grid_key,
        "controller": controller_name,
        "mode": mode,
        "source_script": relative_display(script_path),
        "started_at": started_at,
    }

    if alpha is not None:
        record["alpha_index"] = alpha
        record["alpha"] = alpha / 10.0

    try:
        config_path, temp_config = resolve_config_for_run(
            grid_key=grid_key,
            mode=mode,
            alpha=alpha,
        )

        temp_script, rewrite_notes = (
            build_temporary_launch_script(
                script_path=script_path,
                grid_key=grid_key,
                mode=mode,
                alpha=alpha,
                config_path=config_path,
                force_headless=force_headless,
            )
        )

        cmd = [
            sys.executable,
            str(temp_script),
        ]

        # ALWAYS pass alpha 0..10 as requested. Legacy 2x2 scripts that ignore
        # argv are still made alpha-correct by the temporary SUMO_CONFIG rewrite.
        if mode == "saturated":
            if alpha is None:
                raise ValueError(
                    "Saturated run requires alpha"
                )
            cmd.append(str(alpha))

        record["resolved_config"] = (
            str(config_path.resolve())
        )
        record["temporary_config_used"] = (
            temp_config is not None
        )
        record["launch_rewrites"] = rewrite_notes
        record["command"] = cmd
        # Run from the PROJECT ROOT, not grid_2x2/grid_3x3.
        #
        # The SUMO .sumocfg files in this project contain paths such as:
        #     grid_2x2/grid2x2_tls.net.xml
        #     grid_3x3/grid3x3_tls.net.xml
        #
        # Therefore their relative paths are authored relative to BASE_DIR.
        # Running with cwd=grid_dir would incorrectly resolve, for example:
        #     grid_2x2/grid_2x2/grid2x2_tls.net.xml
        #
        # MODEL_PATH / SUMO_CONFIG / explicit ROUTE_FILE assignments are made
        # absolute in the temporary launch copy whenever resolvable.
        record["working_directory"] = (
            str(BASE_DIR.resolve())
        )
        record["timeout_seconds"] = timeout_seconds

        completed = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            env=build_subprocess_environment(
                controller_dir,
                grid_dir,
            ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )

        stdout = completed.stdout or ""
        stderr = completed.stderr or ""

        record["return_code"] = completed.returncode
        record["stdout"] = stdout
        record["stderr"] = stderr

        if completed.returncode != 0:
            record["status"] = "failed"
            record["error"] = (
                f"Simulation returned exit code "
                f"{completed.returncode}"
            )
        else:
            parsed = parse_output(
                mode=mode,
                output=stdout,
            )
            record["parsed"] = parsed
            record["parse_warnings"] = (
                build_parse_warnings(
                    mode=mode,
                    parsed=parsed,
                )
            )
            record["status"] = "success"

    except subprocess.TimeoutExpired as error:
        record["status"] = "timeout"
        record["error"] = (
            f"Timed out after {timeout_seconds} seconds"
        )
        record["stdout"] = ensure_text(error.stdout)
        record["stderr"] = ensure_text(error.stderr)

    except Exception as error:
        record["status"] = "failed"
        record["error"] = (
            f"{type(error).__name__}: {error}"
        )
        record["traceback"] = traceback.format_exc()

    finally:
        if temp_script is not None:
            temp_script.unlink(missing_ok=True)

        if temp_config is not None:
            temp_config.unlink(missing_ok=True)

        record["finished_at"] = now_iso()
        record["duration_seconds"] = round(
            time.perf_counter() - start_perf,
            3,
        )

    return record


# ============================================================
# RUN LOOPS
# ============================================================

def load_or_create_document(
    path: Path,
    *,
    mode: str,
    resume: bool,
) -> Dict[str, Any]:
    if resume:
        existing = load_json_if_present(path)
        if (
            existing
            and existing.get("mode") == mode
        ):
            existing.setdefault("runs", [])
            return existing

    return create_result_document(mode)


def save_checkpoint(
    document: Dict[str, Any],
    *,
    mode: str,
    path: Path,
) -> None:
    refresh_result_document(
        document,
        mode=mode,
    )
    atomic_write_json(path, document)


def print_run_result(record: Dict[str, Any]) -> None:
    status = record.get("status", "unknown").upper()
    duration = record.get("duration_seconds", 0)

    prefix = (
        f"{record.get('grid')} | "
        f"{record.get('controller')}"
    )

    if record.get("mode") == "saturated":
        prefix += (
            f" | a{record.get('alpha_index')}"
        )

    if record.get("status") == "success":
        traffic = (
            record.get("parsed", {})
            .get("traffic", {})
        )

        if record.get("mode") == "saturated":
            print(
                f"{status}: {prefix} | "
                f"TT={traffic.get('average_travel_time')} | "
                f"WT={traffic.get('average_waiting_time')} | "
                f"throughput={traffic.get('throughput')} | "
                f"{duration:.1f}s",
                flush=True,
            )
        else:
            overall = traffic.get("overall") or {}
            print(
                f"{status}: {prefix} | "
                f"hours={traffic.get('hours_parsed')} | "
                f"TT={overall.get('average_travel_time')} | "
                f"WT={overall.get('average_waiting_time')} | "
                f"completed={overall.get('completed_vehicles')} | "
                f"{duration:.1f}s",
                flush=True,
            )

        warnings = record.get("parse_warnings") or []
        for warning in warnings:
            print(
                f"  PARSE WARNING: {warning}",
                flush=True,
            )
    else:
        print(
            f"{status}: {prefix} | "
            f"{record.get('error')} | "
            f"{duration:.1f}s",
            flush=True,
        )

        stderr = ensure_text(record.get("stderr"))
        if stderr.strip():
            tail = "\n".join(
                stderr.strip().splitlines()[-12:]
            )
            print(
                "  stderr tail:\n"
                + "\n".join(
                    f"    {line}"
                    for line in tail.splitlines()
                ),
                flush=True,
            )


def run_saturated_suite(
    args: argparse.Namespace,
) -> Dict[str, Any]:
    document = load_or_create_document(
        ALPHA_OUTPUT_FILE,
        mode="saturated",
        resume=not args.no_resume,
    )

    runs = document.setdefault("runs", [])
    already_successful = successful_keys(
        runs,
        mode="saturated",
    )

    grids = selected_grids(args)
    controllers = selected_controllers(args)
    alphas = selected_alphas(args)

    planned = (
        len(grids)
        * len(controllers)
        * len(alphas)
    )
    completed_counter = 0

    print(
        f"\n===== SATURATED ALPHA SWEEP "
        f"({planned} selected runs) =====\n",
        flush=True,
    )

    for grid_key in grids:
        for controller_name, subfolder in controllers:
            for alpha in alphas:
                completed_counter += 1
                key = (
                    grid_key,
                    controller_name,
                    alpha,
                )

                if (
                    not args.no_resume
                    and key in already_successful
                ):
                    print(
                        f"SKIP success "
                        f"[{completed_counter}/{planned}]: "
                        f"{grid_key} | {controller_name} | a{alpha}",
                        flush=True,
                    )
                    continue

                print(
                    f"RUN [{completed_counter}/{planned}]: "
                    f"{grid_key} | {controller_name} | a{alpha}",
                    flush=True,
                )

                record = run_one(
                    grid_key=grid_key,
                    controller_name=controller_name,
                    subfolder=subfolder,
                    mode="saturated",
                    alpha=alpha,
                    timeout_seconds=args.saturated_timeout,
                    force_headless=not args.keep_gui,
                )

                upsert_run(
                    runs,
                    record,
                    mode="saturated",
                )
                save_checkpoint(
                    document,
                    mode="saturated",
                    path=ALPHA_OUTPUT_FILE,
                )
                print_run_result(record)

                if record.get("status") == "success":
                    already_successful.add(key)

    save_checkpoint(
        document,
        mode="saturated",
        path=ALPHA_OUTPUT_FILE,
    )
    return document


def run_seattle_suite(
    args: argparse.Namespace,
) -> Dict[str, Any]:
    document = load_or_create_document(
        SEATTLE_OUTPUT_FILE,
        mode="seattle",
        resume=not args.no_resume,
    )

    runs = document.setdefault("runs", [])
    already_successful = successful_keys(
        runs,
        mode="seattle",
    )

    grids = selected_grids(args)
    controllers = selected_controllers(args)

    planned = (
        len(grids)
        * len(controllers)
    )
    completed_counter = 0

    print(
        f"\n===== SEATTLE SUITE "
        f"({planned} selected runs) =====\n",
        flush=True,
    )

    for grid_key in grids:
        for controller_name, subfolder in controllers:
            completed_counter += 1
            key = (
                grid_key,
                controller_name,
            )

            if (
                not args.no_resume
                and key in already_successful
            ):
                print(
                    f"SKIP success "
                    f"[{completed_counter}/{planned}]: "
                    f"{grid_key} | {controller_name}",
                    flush=True,
                )
                continue

            print(
                f"RUN [{completed_counter}/{planned}]: "
                f"{grid_key} | {controller_name}",
                flush=True,
            )

            record = run_one(
                grid_key=grid_key,
                controller_name=controller_name,
                subfolder=subfolder,
                mode="seattle",
                alpha=None,
                timeout_seconds=args.seattle_timeout,
                force_headless=not args.keep_gui,
            )

            upsert_run(
                runs,
                record,
                mode="seattle",
            )
            save_checkpoint(
                document,
                mode="seattle",
                path=SEATTLE_OUTPUT_FILE,
            )
            print_run_result(record)

            if record.get("status") == "success":
                already_successful.add(key)

    save_checkpoint(
        document,
        mode="seattle",
        path=SEATTLE_OUTPUT_FILE,
    )
    return document


# ============================================================
# CLI
# ============================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run all 2x2/3x3 saturated alpha sweeps and "
            "Seattle controller evaluations."
        )
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate layout and print plan without running SUMO.",
    )
    parser.add_argument(
        "--skip-saturated",
        action="store_true",
        help="Do not run the 198-run saturated alpha sweep.",
    )
    parser.add_argument(
        "--skip-seattle",
        action="store_true",
        help="Do not run the 18 Seattle data.py evaluations.",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help=(
            "Ignore successful checkpoints and rerun selected work. "
            "Existing JSON records with the same keys are replaced."
        ),
    )
    parser.add_argument(
        "--only-grid",
        choices=sorted(GRID_SPECS.keys()),
        help="Restrict run to one grid.",
    )
    parser.add_argument(
        "--only-controller",
        choices=[name for name, _ in CONTROLLERS],
        help="Restrict run to one controller.",
    )
    parser.add_argument(
        "--alpha",
        type=int,
        action="append",
        help=(
            "Restrict saturated sweep to one or more alpha indices. "
            "Can be repeated, e.g. --alpha 0 --alpha 7."
        ),
    )
    parser.add_argument(
        "--keep-gui",
        action="store_true",
        help=(
            "Do not rewrite SUMO_BINARY to 'sumo'. "
            "Normally batch runs are forced headless."
        ),
    )
    parser.add_argument(
        "--saturated-timeout",
        type=int,
        default=DEFAULT_SATURATED_TIMEOUT_SECONDS,
        help=(
            "Per-run saturated timeout in seconds "
            f"(default {DEFAULT_SATURATED_TIMEOUT_SECONDS})."
        ),
    )
    parser.add_argument(
        "--seattle-timeout",
        type=int,
        default=DEFAULT_SEATTLE_TIMEOUT_SECONDS,
        help=(
            "Per-run Seattle timeout in seconds "
            f"(default {DEFAULT_SEATTLE_TIMEOUT_SECONDS})."
        ),
    )

    args = parser.parse_args()

    if args.skip_saturated and args.skip_seattle:
        parser.error(
            "Both --skip-saturated and --skip-seattle were supplied; "
            "there would be nothing to run."
        )

    return args


def print_final_summary(
    alpha_document: Optional[Dict[str, Any]],
    seattle_document: Optional[Dict[str, Any]],
) -> None:
    print("\n===== BATCH COMPLETE =====")

    if alpha_document is not None:
        summary = alpha_document.get("summary", {})
        print(
            "Alpha sweep: "
            f"success={summary.get('successful', 0)}, "
            f"failed={summary.get('failed', 0)}, "
            f"timeout={summary.get('timed_out', 0)}"
        )
        print(
            f"  JSON: {ALPHA_OUTPUT_FILE}"
        )

    if seattle_document is not None:
        summary = seattle_document.get("summary", {})
        print(
            "Seattle: "
            f"success={summary.get('successful', 0)}, "
            f"failed={summary.get('failed', 0)}, "
            f"timeout={summary.get('timed_out', 0)}"
        )
        print(
            f"  JSON: {SEATTLE_OUTPUT_FILE}"
        )

    print("==========================\n")


def main() -> int:
    args = parse_args()

    print_plan(args)

    errors = preflight(args)
    if errors:
        print("===== PREFLIGHT FAILED =====")
        for error in errors:
            print(f"- {error}")
        print("============================")
        return 2

    print("Preflight passed.", flush=True)

    if args.dry_run:
        print(
            "Dry run requested: no simulations were started."
        )
        return 0

    alpha_document = None
    seattle_document = None

    if not args.skip_saturated:
        alpha_document = run_saturated_suite(args)

    if not args.skip_seattle:
        seattle_document = run_seattle_suite(args)

    print_final_summary(
        alpha_document,
        seattle_document,
    )

    any_problem = False

    for document in (
        alpha_document,
        seattle_document,
    ):
        if document is None:
            continue

        summary = document.get("summary", {})
        if (
            summary.get("failed", 0)
            or summary.get("timed_out", 0)
        ):
            any_problem = True

    return 1 if any_problem else 0


if __name__ == "__main__":
    raise SystemExit(main())
