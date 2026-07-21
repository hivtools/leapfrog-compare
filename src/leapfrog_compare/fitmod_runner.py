"""
Shell out to eppasm / eppasm-leapfrog's `fitmod()` (via r/run_fitmod.R) — a
reduced-but-real IMIS Bayesian fit (see run_fitmod.R's header comment for why
eppasm's own defaults aren't used: they'd take hours). Produces both a
refit `simmod()` time series at the posterior mean theta (reusing the same
tidy shape as the simmod tab) and an `ll()` component breakdown at that
theta (reusing the same shape as the ll tab), plus fit diagnostics.

This is the slow tab: results are always cached and only recomputed on an
explicit "Re-run" click, same as the simmod tab, but with a much longer
subprocess timeout.
"""
from __future__ import annotations

from pathlib import Path
import json
import shutil
import subprocess

import pandas as pd

import leapfrog_compare.config as config
from leapfrog_compare.eppasm_runner import _pivot_to_arrays

_R_SCRIPT = Path(__file__).resolve().parent.parent.parent / "r" / "run_fitmod.R"

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


def _cache_paths(pjnz_path: Path, region: str, package: str) -> tuple[Path, Path, Path]:
    stem = f"{pjnz_path.stem}__{_safe(region)}__{_safe(package)}"
    base = config.EPPASM_FITMOD_CACHE_DIR
    return base / f"{stem}__mod.csv", base / f"{stem}__ll.csv", base / f"{stem}__meta.json"


def run_fitmod(
    pjnz_path: Path, package: str, region: str, *, force: bool = False,
    timeout: int = config.EPPASM_FITMOD_TIMEOUT,
) -> dict:
    """Run (or read cached) fitmod() for one package. Returns
    {"mod_df": ..., "ll_df": ..., "meta": ...}."""
    mod_file, ll_file, meta_file = _cache_paths(pjnz_path, region, package)
    if mod_file.exists() and ll_file.exists() and meta_file.exists() and not force:
        return {
            "mod_df": pd.read_csv(mod_file), "ll_df": pd.read_csv(ll_file),
            "meta": json.loads(meta_file.read_text()),
        }

    mod_file.parent.mkdir(parents=True, exist_ok=True)
    exe = shutil.which(config.R_EXECUTABLE) or config.R_EXECUTABLE
    use_local = _USE_LOCAL_CHECKOUT[package]
    args = [
        exe, str(_R_SCRIPT), package, str(pjnz_path.resolve()), region,
        str(mod_file.resolve()), str(ll_file.resolve()), str(meta_file.resolve()),
        str(_PACKAGE_DIRS[package]), "1" if use_local else "0",
    ]
    try:
        subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"eppasm fitmod() ({package}) R subprocess failed:\n{exc.stderr}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"eppasm fitmod() ({package}) R subprocess timed out after {timeout}s"
        ) from exc
    return {
        "mod_df": pd.read_csv(mod_file), "ll_df": pd.read_csv(ll_file),
        "meta": json.loads(meta_file.read_text()),
    }


def run_fitmod_both(pjnz_path: Path, region: str, *, force: bool = False) -> dict:
    """Runs both packages' fitmod(). Returns a dict with:
      - "mod": (data_by_source, output_years) — same shape plot_panel_server expects
      - "ll": {"components": DataFrame(component, eppasm, eppasm_lf)} — same shape
        ll_result_panel_server expects (no "theta_match": each package fits its own
        posterior mean independently, so the thetas are expected to differ)
      - "meta": {"eppasm": {...}, "eppasm_lf": {...}} fit diagnostics per package
    Raises RuntimeError if either package fails."""
    results: dict[str, dict] = {}
    errors: list[str] = []
    for pkg in ("eppasm", "eppasm.lf"):
        try:
            results[pkg] = run_fitmod(pjnz_path, pkg, region, force=force)
        except Exception as exc:
            print(f"[fitmod_runner] {pkg} failed for {pjnz_path.stem} ({region}): {exc}")
            errors.append(f"--- {pkg} ---\n{exc}")
    if errors:
        raise RuntimeError(
            "The fitmod tab compares the 'eppasm' and 'eppasm.lf' R packages, so both "
            "must run successfully. The following failed (is the R package "
            "installed?):\n\n" + "\n\n".join(errors)
        )

    mod_dfs = {pkg: r["mod_df"] for pkg, r in results.items()}
    all_years = pd.concat(mod_dfs.values())["year"]
    output_years = range(int(all_years.min()), int(all_years.max()) + 1)
    data_by_source = {
        ("eppasm_lf" if pkg == "eppasm.lf" else pkg): _pivot_to_arrays(df, output_years)
        for pkg, df in mod_dfs.items()
    }

    comp_eppasm = results["eppasm"]["ll_df"].set_index("component")["value"]
    comp_lf = results["eppasm.lf"]["ll_df"].set_index("component")["value"]
    components = pd.DataFrame({"eppasm": comp_eppasm, "eppasm_lf": comp_lf}).reset_index()

    return {
        "mod": (data_by_source, output_years),
        "ll": {"components": components},
        "meta": {pkg: r["meta"] for pkg, r in results.items()},
    }
