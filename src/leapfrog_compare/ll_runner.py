"""
Shell out to eppasm / eppasm-leapfrog's `ll(theta, fp, likdat)` (via
r/run_ll.R), comparing the named log-likelihood components each package
computes on an identical (theta, fp, likdat) triple. Unlike the simmod tab,
`ll()` needs `prepare_spec_fit()` (survey/ANC data), which returns results
keyed by region for multi-region PJNZ files — so results are additionally
keyed by region, and a small region-listing script backs the region selector.

theta is fitted once per (PJNZ, region, eppmod) with eppasm — the
known-working reference — via r/fit_theta.R, cached, and then shared by both
packages' ll() runs.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import time

import pandas as pd

import leapfrog_compare.config as config
from leapfrog_compare.r_packages import package_fingerprint

_R_DIR = Path(__file__).resolve().parent.parent.parent / "r"
_RUN_LL_SCRIPT = _R_DIR / "run_ll.R"
_FIT_THETA_SCRIPT = _R_DIR / "fit_theta.R"
_LIST_REGIONS_SCRIPT = _R_DIR / "list_eppasm_regions.R"

# Fitting theta is a full (if shortened) optimisation, so allow much longer
# than a single ll() call.
THETA_TIMEOUT = 1800

# EPP transmission-curve models selectable in the ll/fitmod tabs. "rtrend" is
# left out: the leapfrog engine rejects it.
EPPMOD_CHOICES = ["rhybrid", "rspline", "logrw", "rlogistic"]
DEFAULT_EPPMOD = "rhybrid"

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
    return (
        config.EPPASM_LL_CACHE_DIR
        / f"{pjnz_path.stem}__regions__eppasm_{package_fingerprint('eppasm')}.json"
    )


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


@dataclass(frozen=True)
class Theta:
    """A theta fitted by eppasm (r/fit_theta.R) for one (PJNZ, region, eppmod)."""
    pjnz_stem: str
    region: str
    eppmod: str
    path: Path
    df: pd.DataFrame  # index, name, value
    meta: dict
    digest: str  # short hash of the values, so ll() results are cached per theta


def _theta_paths(pjnz_path: Path, region: str, eppmod: str) -> tuple[Path, Path]:
    # Fitted with eppasm, so keyed by its build.
    stem = f"{pjnz_path.stem}__{_safe(region)}__{eppmod}__eppasm_{package_fingerprint('eppasm')}"
    base = config.EPPASM_LL_CACHE_DIR / "theta"
    return base / f"{stem}__theta.csv", base / f"{stem}__theta_meta.json"


def theta_cached(pjnz_path: Path, region: str, eppmod: str) -> bool:
    return all(p.exists() for p in _theta_paths(pjnz_path, region, eppmod))


def get_theta(
    pjnz_path: Path, region: str, eppmod: str, *, force: bool = False,
    timeout: int = THETA_TIMEOUT,
) -> Theta:
    """Read the cached eppasm-fitted theta, or fit it (slow: a minute or two via
    eppasm's fitmod(optfit=TRUE)) when missing or `force`d."""
    theta_file, meta_file = _theta_paths(pjnz_path, region, eppmod)
    if force or not theta_cached(pjnz_path, region, eppmod):
        label = f"{pjnz_path.stem} ({region}, {eppmod})"
        reason = "regenerating" if theta_cached(pjnz_path, region, eppmod) else "no cached theta"
        print(f"[ll_runner] Fitting theta with eppasm for {label}: {reason}")
        started = time.monotonic()
        theta_file.parent.mkdir(parents=True, exist_ok=True)
        exe = shutil.which(config.R_EXECUTABLE) or config.R_EXECUTABLE
        args = [
            exe, str(_FIT_THETA_SCRIPT), str(pjnz_path.resolve()), region, eppmod,
            str(theta_file.resolve()), str(meta_file.resolve()),
            str(config.EPPASM_DIR), "1" if config.EPPASM_USE_LOCAL_CHECKOUT else "0",
        ]
        try:
            subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=True)
        except subprocess.CalledProcessError as exc:
            print(f"[ll_runner] Fitting theta for {label} failed")
            raise RuntimeError(f"fitting theta with eppasm failed:\n{exc.stderr}") from exc
        except subprocess.TimeoutExpired as exc:
            print(f"[ll_runner] Fitting theta for {label} timed out after {timeout}s")
            raise RuntimeError(f"fitting theta with eppasm timed out after {timeout}s") from exc
        print(f"[ll_runner] Fitted theta for {label} in {time.monotonic() - started:.1f}s -> {theta_file}")

    df = pd.read_csv(theta_file)
    digest = hashlib.sha1(df["value"].to_numpy().tobytes()).hexdigest()[:10]
    return Theta(
        pjnz_stem=pjnz_path.stem, region=region, eppmod=eppmod, path=theta_file,
        df=df, meta=json.loads(meta_file.read_text()), digest=digest,
    )


def _cache_path(pjnz_path: Path, theta: Theta, package: str) -> Path:
    return (
        config.EPPASM_LL_CACHE_DIR
        / (
            f"{pjnz_path.stem}__{_safe(theta.region)}__{theta.eppmod}__{theta.digest}"
            f"__{_safe(package)}_{package_fingerprint(package)}.csv"
        )
    )


def run_ll(
    pjnz_path: Path, package: str, theta: Theta, *, force: bool = False, timeout: int = 600,
) -> pd.DataFrame:
    """Run (or read cached) one package's ll() components at `theta`."""
    cache_file = _cache_path(pjnz_path, theta, package)
    if cache_file.exists() and not force:
        return pd.read_csv(cache_file)

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    exe = shutil.which(config.R_EXECUTABLE) or config.R_EXECUTABLE
    use_local = _USE_LOCAL_CHECKOUT[package]
    args = [
        exe, str(_RUN_LL_SCRIPT), package, str(pjnz_path.resolve()), theta.region, theta.eppmod,
        str(theta.path.resolve()), str(cache_file.resolve()), str(_PACKAGE_DIRS[package]),
        "1" if use_local else "0",
    ]
    try:
        subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"eppasm ll() ({package}) R subprocess failed:\n{exc.stderr}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"eppasm ll() ({package}) R subprocess timed out after {timeout}s") from exc
    return pd.read_csv(cache_file)


def run_ll_both(pjnz_path: Path, theta: Theta, *, force: bool = False) -> dict:
    """Runs both packages' ll() at the same eppasm-fitted `theta`. Returns a dict with:
      - "components": DataFrame(component, eppasm, eppasm_lf) wide by package
      - "eppmod", "theta_source": for display
    Raises RuntimeError (mirroring run_eppasm_both) if either package fails."""
    results: dict[str, pd.DataFrame] = {}
    errors: list[str] = []
    for pkg in ("eppasm", "eppasm.lf"):
        try:
            results[pkg] = run_ll(pjnz_path, pkg, theta, force=force)
        except Exception as exc:
            print(f"[ll_runner] {pkg} failed for {pjnz_path.stem} ({theta.region}): {exc}")
            errors.append(f"--- {pkg} ---\n{exc}")
    if errors:
        raise RuntimeError(
            "The ll tab compares the 'eppasm' and 'eppasm.lf' R packages, so both "
            "must run successfully. The following failed (is the R package "
            "installed?):\n\n" + "\n\n".join(errors)
        )

    comp_eppasm = results["eppasm"].set_index("component")["value"]
    comp_lf = results["eppasm.lf"].set_index("component")["value"]
    components = pd.DataFrame({"eppasm": comp_eppasm, "eppasm_lf": comp_lf}).reset_index()

    return {
        "components": components,
        "eppmod": theta.eppmod,
        "theta_source": (
            f"eppasm posterior mode (log posterior {theta.meta['log_posterior']:.2f}, "
            f"generated {theta.meta['generated_at']})"
        ),
    }
