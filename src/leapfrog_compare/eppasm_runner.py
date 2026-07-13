"""
Shell out to eppasm / eppasm-leapfrog's `simmod()` (via r/run_simmod.R),
caching results to disk as tidy CSVs — one per (PJNZ, package) — since the R
subprocess is much slower than the in-process Python model calls the other
tabs use. Results are computed on first request and cached; pass force=True
(wired to a "Re-run" button in the UI) to recompute.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import numpy as np
import pandas as pd

import leapfrog_compare.config as config

_R_SCRIPT = Path(__file__).resolve().parent.parent.parent / "r" / "run_simmod.R"

_PACKAGE_DIRS = {
    "eppasm": config.EPPASM_DIR,
    "eppasm.lf": config.EPPASM_LEAPFROG_DIR,
}
_USE_LOCAL_CHECKOUT = {
    "eppasm": config.EPPASM_USE_LOCAL_CHECKOUT,
    "eppasm.lf": config.EPPASM_LF_USE_LOCAL_CHECKOUT,
}


def _cache_path(pjnz_path: Path, package: str) -> Path:
    safe_package = package.replace(".", "_")
    return config.EPPASM_CACHE_DIR / f"{pjnz_path.stem}__{safe_package}.csv"


def run_eppasm(pjnz_path: Path, package: str, *, force: bool = False, timeout: int = 600) -> pd.DataFrame:
    """Run (or read cached) simmod() tidy output for one package."""
    cache_file = _cache_path(pjnz_path, package)
    if cache_file.exists() and not force:
        return pd.read_csv(cache_file)

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    exe = shutil.which(config.R_EXECUTABLE) or config.R_EXECUTABLE
    use_local = _USE_LOCAL_CHECKOUT[package]
    args = [
        exe, str(_R_SCRIPT), package, str(pjnz_path.resolve()),
        str(cache_file.resolve()), str(_PACKAGE_DIRS[package]), "1" if use_local else "0",
    ]
    try:
        subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"eppasm ({package}) R subprocess failed:\n{exc.stderr}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"eppasm ({package}) R subprocess timed out after {timeout}s") from exc
    return pd.read_csv(cache_file)


def _pivot_to_arrays(df: pd.DataFrame, output_years: range) -> dict[str, dict[str, dict[str, np.ndarray]]]:
    """Reindex each (indicator, age_group, sex) group onto `output_years`, NaN-padding
    missing years. Returns dict[indicator][age_group][sex] -> aligned ndarray."""
    years_arr = np.array(list(output_years))
    result: dict[str, dict[str, dict[str, np.ndarray]]] = {}
    for (indicator, age_group, sex), group in df.groupby(["indicator", "age_group", "sex"]):
        series = group.set_index("year")["value"]
        aligned = series.reindex(years_arr).to_numpy(dtype=float)
        result.setdefault(indicator, {}).setdefault(age_group, {})[sex] = aligned
    return result


def run_eppasm_both(pjnz_path: Path, *, force: bool = False) -> tuple[dict, range]:
    """Runs both packages and returns (data_by_source, output_years), matching the
    comparison module's run_fn contract. If one package fails (e.g. a missing R
    dependency), the other's results still render — only raises if both fail."""
    dfs: dict[str, pd.DataFrame] = {}
    for pkg in ("eppasm", "eppasm.lf"):
        try:
            dfs[pkg] = run_eppasm(pjnz_path, pkg, force=force)
        except Exception as exc:
            print(f"[eppasm_runner] {pkg} failed for {pjnz_path.stem}: {exc}")
    if not dfs:
        raise RuntimeError("Both eppasm and eppasm.lf failed to run — see server logs for details.")

    all_years = pd.concat(dfs.values())["year"]
    output_years = range(int(all_years.min()), int(all_years.max()) + 1)
    data_by_source = {
        ("eppasm_lf" if pkg == "eppasm.lf" else pkg): _pivot_to_arrays(df, output_years)
        for pkg, df in dfs.items()
    }
    return data_by_source, output_years
