"""
Shell out to eppasm / eppasm-leapfrog's `ll(theta, fp, likdat)` (via
r/run_ll.R), comparing the named log-likelihood components each package
computes on an identical (theta, fp, likdat) triple. Unlike the simmod tab,
`ll()` needs `prepare_spec_fit()` (survey/ANC data), which returns results
keyed by region for multi-region PJNZ files — so results are additionally
keyed by region, and a small region-listing script backs the region selector.
"""
from __future__ import annotations

from pathlib import Path
import json
import shutil
import subprocess

import pandas as pd

import leapfrog_compare.config as config

_R_DIR = Path(__file__).resolve().parent.parent.parent / "r"
_RUN_LL_SCRIPT = _R_DIR / "run_ll.R"
_LIST_REGIONS_SCRIPT = _R_DIR / "list_eppasm_regions.R"

_PACKAGE_DIRS = {
    "eppasm": config.EPPASM_DIR,
    "eppasm.lf": config.EPPASM_LEAPFROG_DIR,
}
_USE_LOCAL_CHECKOUT = {
    "eppasm": config.EPPASM_USE_LOCAL_CHECKOUT,
    "eppasm.lf": config.EPPASM_LF_USE_LOCAL_CHECKOUT,
}


def _safe(name: str) -> str:
    return name.replace(".", "_").replace("/", "_")


def _regions_cache_path(pjnz_path: Path) -> Path:
    return config.EPPASM_LL_CACHE_DIR / f"{pjnz_path.stem}__regions.json"


def list_eppasm_regions(pjnz_path: Path, *, force: bool = False, timeout: int = 600) -> list[str]:
    """Runs (or reads cached) region names for a PJNZ, via prepare_spec_fit(). Only
    needs eppasm (region names are data-derived, not engine-derived)."""
    cache_file = _regions_cache_path(pjnz_path)
    if cache_file.exists() and not force:
        return json.loads(cache_file.read_text())

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    exe = shutil.which(config.R_EXECUTABLE) or config.R_EXECUTABLE
    args = [
        exe, str(_LIST_REGIONS_SCRIPT), str(pjnz_path.resolve()), str(cache_file.resolve()),
        str(config.EPPASM_DIR), "1" if config.EPPASM_USE_LOCAL_CHECKOUT else "0",
    ]
    try:
        subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"listing eppasm regions failed:\n{exc.stderr}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"listing eppasm regions timed out after {timeout}s") from exc
    return json.loads(cache_file.read_text())


def _cache_path(pjnz_path: Path, region: str, package: str) -> Path:
    return config.EPPASM_LL_CACHE_DIR / f"{pjnz_path.stem}__{_safe(region)}__{_safe(package)}.csv"


def run_ll(
    pjnz_path: Path, package: str, region: str, *, force: bool = False, timeout: int = 600,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run (or read cached) ll() components + sampled theta for one package.
    Returns (components_df, theta_df)."""
    cache_file = _cache_path(pjnz_path, region, package)
    theta_file = cache_file.with_name(cache_file.stem + "_theta.csv")
    if cache_file.exists() and theta_file.exists() and not force:
        return pd.read_csv(cache_file), pd.read_csv(theta_file)

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    exe = shutil.which(config.R_EXECUTABLE) or config.R_EXECUTABLE
    use_local = _USE_LOCAL_CHECKOUT[package]
    args = [
        exe, str(_RUN_LL_SCRIPT), package, str(pjnz_path.resolve()), region,
        str(cache_file.resolve()), str(_PACKAGE_DIRS[package]), "1" if use_local else "0",
    ]
    try:
        subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"eppasm ll() ({package}) R subprocess failed:\n{exc.stderr}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"eppasm ll() ({package}) R subprocess timed out after {timeout}s") from exc
    return pd.read_csv(cache_file), pd.read_csv(theta_file)


def run_ll_both(pjnz_path: Path, region: str, *, force: bool = False) -> dict:
    """Runs both packages' ll() for one region. Returns a dict with:
      - "components": DataFrame(component, eppasm, eppasm_lf) wide by package
      - "theta_match": True if both packages' independently-sampled theta matched
        exactly (they should, given the same fixed seed + PJNZ — a mismatch means
        the two packages' prior specifications actually differ, so the ll()
        comparison below isn't apples-to-apples)
    Raises RuntimeError (mirroring run_eppasm_both) if either package fails."""
    results: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}
    errors: list[str] = []
    for pkg in ("eppasm", "eppasm.lf"):
        try:
            results[pkg] = run_ll(pjnz_path, pkg, region, force=force)
        except Exception as exc:
            print(f"[ll_runner] {pkg} failed for {pjnz_path.stem} ({region}): {exc}")
            errors.append(f"--- {pkg} ---\n{exc}")
    if errors:
        raise RuntimeError(
            "The ll tab compares the 'eppasm' and 'eppasm.lf' R packages, so both "
            "must run successfully. The following failed (is the R package "
            "installed?):\n\n" + "\n\n".join(errors)
        )

    comp_eppasm = results["eppasm"][0].set_index("component")["value"]
    comp_lf = results["eppasm.lf"][0].set_index("component")["value"]
    components = pd.DataFrame({"eppasm": comp_eppasm, "eppasm_lf": comp_lf}).reset_index()

    theta_eppasm = results["eppasm"][1]["value"].to_numpy()
    theta_lf = results["eppasm.lf"][1]["value"].to_numpy()
    theta_match = (
        theta_eppasm.shape == theta_lf.shape
        and bool((abs(theta_eppasm - theta_lf) < 1e-9).all())
    )

    return {"components": components, "theta_match": theta_match}
