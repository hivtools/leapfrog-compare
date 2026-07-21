# Run `fitmod()` (IMIS Bayesian fit) from either the `eppasm` or `eppasm.lf`
# (eppasm-leapfrog) R package against a PJNZ file. `fitmod()` internally
# calls `simmod(fp)`/`ll(fp)` many times over the course of the fit, so —
# like `ll`, and unlike the direct-incidence `simmod` comparison — it
# dispatches to each package's own default engine, but this is SLOW.
#
# eppasm's own defaults (B0=1e5 initial draws, up to number_k=500 IMIS
# iterations) are not used here: benchmarked against the installed package on
# a small test PJNZ, IMIS costs roughly 0.01s/draw, so B0=1e5 alone is
# ~15-20 minutes before any iterations even start, with total runtime
# realistically reaching multiple hours — impractical to trigger from an
# interactive button click. IMIS_B0/IMIS_B/IMIS_NUMBER_K below are reduced
# to target a ~10-20 minute run while still exercising the real IMIS
# algorithm end-to-end (not a shortcut like optfit=TRUE) — this is a
# deliberate, documented approximation of the production fit, not the
# genuine article; the UI surfaces this. Tune these constants if your PJNZ
# files need more/less budget (bigger/more complex countries will need
# larger B0 to find enough high-likelihood draws).
#
# Writes three outputs:
#   - out_mod_csv:  tidy time series of `simmod()` refit at the posterior
#                   mean theta (same shape as run_simmod.R's output, so it
#                   can reuse the existing time-series comparison UI)
#   - out_ll_csv:   ll() component breakdown at that same posterior mean
#                   theta (same shape as run_ll.R's output)
#   - out_meta_json: fit timing + IMIS diagnostics (resample size, iterations)
#
# Usage:
#   Rscript run_fitmod.R <package> <pjnz_path> <region> <out_mod_csv> <out_ll_csv> <out_meta_json> <pkg_dir> <use_local:0|1>

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 8) {
  stop("Usage: Rscript run_fitmod.R <package> <pjnz_path> <region> <out_mod_csv> <out_ll_csv> <out_meta_json> <pkg_dir> <use_local:0|1>")
}
pkg <- args[[1]]
pjnz_path <- args[[2]]
region <- args[[3]]
out_mod_csv <- args[[4]]
out_ll_csv <- args[[5]]
out_meta_json <- args[[6]]
pkg_dir <- args[[7]]
use_local <- as.logical(as.integer(args[[8]]))

# Same eppmod choice as run_ll.R/eppasm_fit_prep.R's default — "rspline" is
# supported by both engines (unlike "rtrend", which the leapfrog engine
# rejects outright).
FITMOD_EPPMOD <- "rspline"

# Reduced-but-real IMIS budget — see header comment. eppasm's own defaults
# are B0=1e5, B=1e4, B.re=3000, number_k=500.
IMIS_B0 <- 20000
IMIS_B <- 2000
IMIS_B_RE <- 1000
IMIS_NUMBER_K <- 30

invisible(if (use_local) {
  suppressMessages(pkgload::load_all(pkg_dir, quiet = TRUE))
} else {
  suppressMessages(library(pkg, character.only = TRUE))
})

this_file <- sub("--file=", "", grep("--file=", commandArgs(trailingOnly = FALSE), value = TRUE))
script_dir <- dirname(this_file)
source(file.path(script_dir, "eppasm_tidy_output.R"))

fp0 <- prepare_directincid(pjnz_path)
proj_end <- fp0$ss$proj_start + fp0$ss$PROJ_YEARS - 1

obj_list <- prepare_spec_fit(pjnz_path, proj.end = proj_end)
if (!region %in% names(obj_list)) {
  stop(sprintf("Region '%s' not found; available regions: %s", region, paste(names(obj_list), collapse = ", ")))
}
obj <- obj_list[[region]]

start_time <- Sys.time()
fit <- fitmod(
  obj, eppmod = FITMOD_EPPMOD,
  B0 = IMIS_B0, B = IMIS_B, B.re = IMIS_B_RE, number_k = IMIS_NUMBER_K
)
elapsed_s <- as.numeric(difftime(Sys.time(), start_time, units = "secs"))
cat(sprintf("%s fitmod() took: %.1f s\n", pkg, elapsed_s))

theta_mean <- colMeans(fit$resample)

mod <- simmod(stats::update(fit$fp, list = fnCreateParam(theta_mean, fit$fp)))
mod_df <- tidy_mod_output(fit$fp, mod)

ll_at_mean <- ll(theta_mean, fit$fp, fit$likdat)
ll_df <- tidy_ll_output(ll_at_mean)

write_atomic_csv <- function(df, path) {
  tmp_path <- paste0(path, ".tmp")
  write.csv(df, tmp_path, row.names = FALSE)
  file.rename(tmp_path, path)
}

write_atomic_csv(mod_df, out_mod_csv)
write_atomic_csv(ll_df, out_ll_csv)

meta <- list(
  package = pkg, region = region, eppmod = FITMOD_EPPMOD,
  fit_time_s = elapsed_s, n_resample = nrow(fit$resample), n_iterations = nrow(fit$stat)
)
meta_tmp <- paste0(out_meta_json, ".tmp")
writeLines(jsonlite::toJSON(meta, auto_unbox = TRUE), meta_tmp)
file.rename(meta_tmp, out_meta_json)

cat(sprintf(
  "Wrote %d mod rows to %s, %d ll rows to %s, meta to %s\n",
  nrow(mod_df), out_mod_csv, nrow(ll_df), out_ll_csv, out_meta_json
))
