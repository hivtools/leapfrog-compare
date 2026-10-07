"""
Fingerprints of the R packages the EPPASM tabs shell out to, for cache keys —
so reinstalling a package, or editing a local checkout, never serves results
computed by the previous build.

An installed package is identified by its version plus a hash of its installed
DESCRIPTION, whose `Built:` field changes on every (re)install even when the
version number doesn't. A local checkout (loaded via pkgload::load_all) is
identified by a hash of its sources. eppasm.lf's results also depend on the
installed `leapfrog` package, so that's folded into its fingerprint.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import hashlib
import shutil
import subprocess

import leapfrog_compare.config as config

_PACKAGE_DIRS = {
    "eppasm": config.EPPASM_DIR,
    "eppasm.lf": config.EPPASM_LEAPFROG_DIR,
}
_USE_LOCAL_CHECKOUT = {
    "eppasm": config.EPPASM_USE_LOCAL_CHECKOUT,
    "eppasm.lf": config.EPPASM_LF_USE_LOCAL_CHECKOUT,
}
# Installed R packages whose results feed into each package's output.
_DEPENDENCIES = {
    "eppasm": (),
    "eppasm.lf": ("leapfrog",),
}
_SOURCE_GLOBS = ("DESCRIPTION", "NAMESPACE", "R/*.R", "src/*.c", "src/*.cpp", "src/*.h", "src/*.hpp")


@lru_cache(maxsize=None)
def _installed_path(package: str) -> Path:
    """Where R finds the installed package. Cached for the app's lifetime — a
    reinstall to the same library is still picked up, since DESCRIPTION is
    re-read on every fingerprint."""
    exe = shutil.which(config.R_EXECUTABLE) or config.R_EXECUTABLE
    try:
        out = subprocess.run(
            [exe, "-e", f'cat(find.package("{package}"))'],
            capture_output=True, text=True, timeout=60, check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"R package '{package}' is not installed:\n{exc.stderr}") from exc
    return Path(out.stdout.strip().splitlines()[-1])


def _description_version(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("Version:"):
            return line.split(":", 1)[1].strip()
    return "unknown"


def _installed(package: str) -> tuple[str, bytes]:
    desc = (_installed_path(package) / "DESCRIPTION").read_bytes()
    return _description_version(desc.decode(errors="replace")), desc


def _local_checkout(path: Path) -> tuple[str, bytes]:
    digest = hashlib.sha1()
    for pattern in _SOURCE_GLOBS:
        for f in sorted(path.glob(pattern)):
            digest.update(f.relative_to(path).as_posix().encode())
            digest.update(f.read_bytes())
    desc = path / "DESCRIPTION"
    version = _description_version(desc.read_text(errors="replace")) if desc.exists() else "unknown"
    return f"local{version}", digest.digest()


def package_fingerprint(package: str) -> str:
    """Short, filename-safe id for the build of `package` the R scripts will
    load (per config.py), e.g. "0.8.6-3fa94c1e"."""
    if _USE_LOCAL_CHECKOUT.get(package, False):
        version, content = _local_checkout(Path(_PACKAGE_DIRS[package]).expanduser())
    else:
        version, content = _installed(package)
    digest = hashlib.sha1(content)
    for dep in _DEPENDENCIES.get(package, ()):
        digest.update(_installed(dep)[1])
    return f"{version}-{digest.hexdigest()[:8]}"
