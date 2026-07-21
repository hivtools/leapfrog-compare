# Run `ll(theta, fp, likdat)` from either the `eppasm` or `eppasm.lf`
# (eppasm-leapfrog) R package against a PJNZ file, and write the named
# log-likelihood components to a tidy CSV.
#
# Usage:
#   Rscript run_ll.R <package> <pjnz_path> <region> <out_csv> <pkg_dir> <use_local:0|1>
#
#   package    "eppasm" or "eppasm.lf"
#   pjnz_path  path to the input .PJNZ file
#   region     name of the region to use, as returned by list_eppasm_regions.R
#              (e.g. "National", or "Urban"/"Rural" for a multi-region file)
#   out_csv    output CSV path for the ll() components (written atomically)
#   pkg_dir    root directory of the package's source checkout (only used
#              when use_local is 1)
#   use_local  1 to load the package from `pkg_dir` via pkgload::load_all(),
#              0 to use the regular installed copy via library()
#
# `ll()` is identical (same signature, same component names) in both
# packages, and internally calls `simmod(fp)` — so, like the simmod tab, this
# already dispatches to each package's own default engine on identical
# inputs. `theta` is not otherwise available for an arbitrary PJNZ (no fit
# has been run), so we take the highest-prior-density draw out of a batch of
# prior samples with a fixed seed — computing `lprior()` over a batch is
# effectively free (no simmod() calls, unlike the full `likelihood()` used to
# pick fitmod()'s own optfit starting point), and picking the modal-ish draw
# avoids landing on a theta whose r-vector is out of bounds, which makes
# ll() short-circuit to a bare (unnamed) -Inf instead of returning its usual
# named-component breakdown. Since both packages independently derive fp's
# prior specification from the same PJNZ, a fixed seed should produce a
# matching theta in both packages' runs. `theta` is written alongside the
# ll() result (out_csv with a "_theta" suffix) so the caller can verify the
# two packages' draws actually matched rather than silently comparing ll()
# values computed on different theta. Individual *components* can still
# legitimately be -Inf (e.g. a poorly-fitting ANC term) — that's a valid,
# comparable outcome, not an error.

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 6) {
  stop("Usage: Rscript run_ll.R <package> <pjnz_path> <region> <out_csv> <pkg_dir> <use_local:0|1>")
}
pkg <- args[[1]]
pjnz_path <- args[[2]]
region <- args[[3]]
out_csv <- args[[4]]
pkg_dir <- args[[5]]
use_local <- as.logical(as.integer(args[[6]]))

# Fixed so both packages' independent prior draws use the same RNG state.
LL_THETA_SEED <- 20240101
# Number of prior draws to search for a highest-prior-density theta.
LL_THETA_BATCH <- 200

invisible(if (use_local) {
  suppressMessages(pkgload::load_all(pkg_dir, quiet = TRUE))
} else {
  suppressMessages(library(pkg, character.only = TRUE))
})

this_file <- sub("--file=", "", grep("--file=", commandArgs(trailingOnly = FALSE), value = TRUE))
script_dir <- dirname(this_file)
source(file.path(script_dir, "eppasm_tidy_output.R"))
source(file.path(script_dir, "eppasm_fit_prep.R"))

# Derive proj.end from prepare_directincid()'s own projection years, same as
# run_simmod.R already uses — no extra user input needed.
fp0 <- prepare_directincid(pjnz_path)
proj_end <- fp0$ss$proj_start + fp0$ss$PROJ_YEARS - 1

obj_list <- prepare_spec_fit(pjnz_path, proj.end = proj_end)
if (!region %in% names(obj_list)) {
  stop(sprintf("Region '%s' not found; available regions: %s", region, paste(names(obj_list), collapse = ", ")))
}
obj <- obj_list[[region]]

built <- build_fp_likdat(pkg, obj)
fp <- built$fp
likdat <- built$likdat

set.seed(LL_THETA_SEED)
theta_candidates <- getFromNamespace("sample.prior", pkg)(LL_THETA_BATCH, fp)
lpriors <- vapply(seq_len(nrow(theta_candidates)),
                   function(i) lprior(theta_candidates[i, ], fp), numeric(1))
theta <- as.numeric(theta_candidates[which.max(lpriors), ])

start_time <- Sys.time()
ll_result <- ll(theta, fp, likdat)
elapsed_ms <- as.numeric(difftime(Sys.time(), start_time, units = "secs")) * 1000
cat(sprintf("%s ll() took: %.1f ms\n", pkg, elapsed_ms))

out <- tidy_ll_output(ll_result)

tmp_path <- paste0(out_csv, ".tmp")
write.csv(out, tmp_path, row.names = FALSE)
file.rename(tmp_path, out_csv)

theta_csv <- sub("\\.csv$", "_theta.csv", out_csv)
theta_tmp <- paste0(theta_csv, ".tmp")
write.csv(data.frame(param = seq_along(theta), value = theta), theta_tmp, row.names = FALSE)
file.rename(theta_tmp, theta_csv)

cat(sprintf("Wrote %d component rows to %s (theta: %s)\n", nrow(out), out_csv, theta_csv))
