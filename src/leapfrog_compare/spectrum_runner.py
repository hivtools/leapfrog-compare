"""
Load a PJNZ file and run leapfrog-py's `run_model` with the "Spectrum" configuration.

This is a DP/AIM-only engine run (no Goals wrapper) — a direct mirror of
`pjnz_runner.run_pjnz`, swapping `leapfrog_goals.run_goals` for
`leapfrog_py.run_model(..., "Spectrum", ...)`. The output dict uses the same key
names as `run_goals()`'s DP/AIM-derived keys (both packages share the same
generated C++ adapter code), so `indicator_map.py`'s "dp_aim"/"spectrum" disagg
functions work unchanged against it.
"""
from pathlib import Path
import time

import numpy as np

from leapfrog_py import get_leapfrog_ss, run_model
from SpectrumCommon.Util.ConvertNumpy import modvars_to_numpy
from SpectrumCommon.Util.LeapfrogDataMapping import modvars_to_leapfrog
from Tools.ImportPJNZ.Importer import GB_ImportProjectionFromFile
from SpectrumCommon.Const.PJ.PJNTags import PJN_FirstYearTag, PJN_FinalYearTag


def run_spectrum(pjnz_path: Path) -> tuple[dict, dict[str, np.ndarray], range]:
    """
    Load a PJNZ file and run leapfrog-py's "Spectrum"-configuration model.

    Returns
    -------
    (modvars, leapfrog_output, output_years)
        modvars          : raw Spectrum modvars dict (list values converted to numpy arrays)
        leapfrog_output  : dict of numpy arrays from run_model(..., "Spectrum", ...)
        output_years     : range(first_year, final_year + 1)
    """
    raw_modvars, _, _, _ = GB_ImportProjectionFromFile(str(pjnz_path))
    modvars = modvars_to_numpy(raw_modvars)

    ss = get_leapfrog_ss("Spectrum")
    params = modvars_to_leapfrog(modvars, ss)  # model_variant defaults to "Spectrum"

    first_year = int(modvars[PJN_FirstYearTag])
    final_year = int(modvars[PJN_FinalYearTag])
    output_years = range(first_year, final_year + 1)

    start = time.time()
    leapfrog_output = run_model(params, "Spectrum", output_years)
    end = time.time()

    elapsed_ms = (end - start) * 1000
    print(f"AIM model fit took: {elapsed_ms} ms")

    return modvars, leapfrog_output, output_years
