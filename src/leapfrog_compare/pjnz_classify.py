"""
Classify a PJNZ file as "Goals" or "AIM" by peeking at its zip contents — a
PJNZ is a zip archive of per-module files named "<name>.<MODULE>" (.DP, .HV,
.PJN, .RN, ...). A ".HV" member means the file carries Goals/HIV-projection
data; PJNZ files exported without ever running Spectrum's AIM/HIV module lack
it entirely. This is a cheap, read-only check — no need to run the full
PJNZ importer just to decide which comparison tabs a file belongs on.
"""
from pathlib import Path
import zipfile


def is_goals_pjnz(pjnz_path: Path) -> bool:
    with zipfile.ZipFile(pjnz_path) as z:
        return any(name.upper().endswith(".HV") for name in z.namelist())
