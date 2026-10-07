# Run `ll(theta, fp, likdat)` from either the `eppasm` or `eppasm.lf`
# (eppasm-leapfrog) R package against a PJNZ file, and write the named
# log-likelihood components to a tidy CSV.
#
# Usage:
#   Rscript run_ll.R <package> <pjnz_path> <region> <eppmod> <theta_csv> <out_csv> <pkg_dir> <use_local:0|1>
#
#   package    "eppasm" or "eppasm.lf"
#   pjnz_path  path to the input .PJNZ file
#   region     name of the region to use, as returned by list_eppasm_regions.R
#              (e.g. "National", or "Urban"/"Rural" for a multi-region file)
#   eppmod     EPP transmission-curve model: "rhybrid", "rspline", "logrw"
#              or "rlogistic" ("rtrend" is rejected by the leapfrog engine)
#   theta_csv  theta to evaluate ll() at, as written by fit_theta.R (columns
#              index, name, value) — fitted once with eppasm and shared by
#              both packages' runs, so they're scored on an identical theta
#   out_csv    output CSV path for the ll() components (written atomically)
#   pkg_dir    root directory of the package's source checkout (only used
#              when use_local is 1)
#   use_local  1 to load the package from `pkg_dir` via pkgload::load_all(),
#              0 to use the regular installed copy via library()
#
# `ll()` is identical (same signature, same component names) in both
# packages, and internally calls `simmod(fp)` — so, like the simmod tab, this
# already dispatches to each package's own default engine on identical
# inputs. Individual *components* can legitimately be -Inf (e.g. a
# poorly-fitting ANC term) — that's a valid, comparable outcome, not an error.

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 8) {
  stop("Usage: Rscript run_ll.R <package> <pjnz_path> <region> <eppmod> <theta_csv> <out_csv> <pkg_dir> <use_local:0|1>")
}
pkg <- args[[1]]
pjnz_path <- args[[2]]
region <- args[[3]]
eppmod <- args[[4]]
theta_csv <- args[[5]]
out_csv <- args[[6]]
pkg_dir <- args[[7]]
use_local <- as.logical(as.integer(args[[8]]))

invisible(if (use_local) {
  suppressMessages(pkgload::load_all(pkg_dir, quiet = TRUE))
} else {
  suppressMessages(library(pkg, character.only = TRUE))
})

this_file <- sub("--file=", "", grep("--file=", commandArgs(trailingOnly = FALSE), value = TRUE))
script_dir <- dirname(this_file)
source(file.path(script_dir, "eppasm_tidy_output.R"))
source(file.path(script_dir, "eppasm_fit_prep.R"))

obj <- load_region_obj(pjnz_path, region)
built <- build_fp_likdat(pkg, obj, eppmod = eppmod)
fp <- built$fp
likdat <- built$likdat

theta <- read.csv(theta_csv)$value
# fnCreateParam() indexes theta by position without checking its length, so a
# theta fitted for a different PJNZ/region/eppmod would be silently misread.
n_param <- ncol(getFromNamespace("sample.prior", pkg)(1, fp))
if (length(theta) != n_param) {
  stop(sprintf(
    "theta has %d parameters but %s/%s with eppmod '%s' needs %d — regenerate theta",
    length(theta), basename(pjnz_path), region, eppmod, n_param
  ))
}

start_time <- Sys.time()
ll_result <- ll(theta, fp, likdat)
elapsed_ms <- as.numeric(difftime(Sys.time(), start_time, units = "secs")) * 1000
cat(sprintf("%s ll() took: %.1f ms\n", pkg, elapsed_ms))

out <- tidy_ll_output(ll_result)

tmp_path <- paste0(out_csv, ".tmp")
write.csv(out, tmp_path, row.names = FALSE)
invisible(file.rename(tmp_path, out_csv))

cat(sprintf("Wrote %d component rows to %s\n", nrow(out), out_csv))
