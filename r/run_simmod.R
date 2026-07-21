# Run `simmod()` from either the `eppasm` or `eppasm.lf` (eppasm-leapfrog) R
# package against a PJNZ file, and write a small set of derived comparison
# series to a tidy long-format CSV (indicator, age_group, sex, year, value).
#
# Usage:
#   Rscript run_simmod.R <package> <pjnz_path> <out_csv> <pkg_dir> <use_local:0|1>
#
#   package    "eppasm" or "eppasm.lf"
#   pjnz_path  path to the input .PJNZ file
#   out_csv    output CSV path (written atomically via a .tmp + rename)
#   pkg_dir    root directory of the package's source checkout (only used
#              when use_local is 1)
#   use_local  1 to load the package from `pkg_dir` via pkgload::load_all()
#              (development / not-yet-installed checkout), 0 to use the
#              regular installed copy via library(). No auto-detection —
#              this flag is the single source of truth for which copy runs.
#
# Each package's own default `simmod()` VERSION is used (eppasm: "C", the
# compiled legacy engine; eppasm.lf: "leapfrog", the new leapfrog-backed
# engine) — that default-vs-default comparison is the whole point of this
# tab. `eppmod = "rtrend"` is not supported by the leapfrog engine, but is
# irrelevant here since `prepare_directincid()` always uses direct incidence.

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 5) {
  stop("Usage: Rscript run_simmod.R <package> <pjnz_path> <out_csv> <pkg_dir> <use_local:0|1>")
}
pkg <- args[[1]]
pjnz_path <- args[[2]]
out_csv <- args[[3]]
pkg_dir <- args[[4]]
use_local <- as.logical(as.integer(args[[5]]))

invisible(if (use_local) {
  suppressMessages(pkgload::load_all(pkg_dir, quiet = TRUE))
} else {
  suppressMessages(library(pkg, character.only = TRUE))
})

this_file <- sub("--file=", "", grep("--file=", commandArgs(trailingOnly = FALSE), value = TRUE))
source(file.path(dirname(this_file), "eppasm_tidy_output.R"))

fp <- prepare_directincid(pjnz_path)

start_time <- Sys.time()
mod <- simmod(fp)
elapsed_ms <- as.numeric(difftime(Sys.time(), start_time, units = "secs")) * 1000
cat(sprintf("%s simmod() fit took: %.1f ms\n", pkg, elapsed_ms))

out <- tidy_mod_output(fp, mod)

tmp_path <- paste0(out_csv, ".tmp")
write.csv(out, tmp_path, row.names = FALSE)
file.rename(tmp_path, out_csv)

cat(sprintf("Wrote %d rows to %s\n", nrow(out), out_csv))
