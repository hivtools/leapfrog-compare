# Fit theta for one PJNZ region with eppasm (the known-working reference
# package), for the ll tab to evaluate both packages' ll() at.
#
# Usage:
#   Rscript fit_theta.R <pjnz_path> <region> <eppmod> <out_csv> <out_meta_json> <pkg_dir> <use_local:0|1>
#
#   out_csv        theta, one row per parameter (columns index, name, value)
#   out_meta_json  how it was fitted: optimiser result + timing
#
# Uses `eppasm::fitmod(optfit = TRUE)` — the optimisation route already built
# into fitmod(): take the highest-posterior draw out of B0 prior samples as a
# starting point, then BFGS on log prior + sum(ll()) to the posterior mode
# (MAP). THETA_B0 is reduced from fitmod()'s default 1e5 (≈15-20 minutes of
# likelihood evaluations just to pick a starting point) to keep this to a
# minute or two; the optimiser does the rest. The Hessian / Laplace resample
# step is skipped (opthess = FALSE) since only the point estimate is used.

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 7) {
  stop("Usage: Rscript fit_theta.R <pjnz_path> <region> <eppmod> <out_csv> <out_meta_json> <pkg_dir> <use_local:0|1>")
}
pjnz_path <- args[[1]]
region <- args[[2]]
eppmod <- args[[3]]
out_csv <- args[[4]]
out_meta_json <- args[[5]]
pkg_dir <- args[[6]]
use_local <- as.logical(as.integer(args[[7]]))

THETA_B0 <- 1000
THETA_SEED <- 20240101

invisible(if (use_local) {
  suppressMessages(pkgload::load_all(pkg_dir, quiet = TRUE))
} else {
  suppressMessages(library(eppasm))
})

this_file <- sub("--file=", "", grep("--file=", commandArgs(trailingOnly = FALSE), value = TRUE))
source(file.path(dirname(this_file), "eppasm_fit_prep.R"))

obj <- load_region_obj(pjnz_path, region)

set.seed(THETA_SEED)
start_time <- Sys.time()
opt <- fitmod(obj, eppmod = eppmod, optfit = TRUE, B0 = THETA_B0, opthess = FALSE)
elapsed_s <- as.numeric(difftime(Sys.time(), start_time, units = "secs"))
cat(sprintf("eppasm fitmod(optfit) took: %.1f s\n", elapsed_s))

theta <- as.numeric(opt$par)
theta_df <- data.frame(
  index = seq_along(theta),
  name = theta_param_names(opt$fp, length(theta)),
  value = theta
)

tmp_path <- paste0(out_csv, ".tmp")
write.csv(theta_df, tmp_path, row.names = FALSE)
invisible(file.rename(tmp_path, out_csv))

meta <- list(
  package = "eppasm",
  package_version = as.character(packageVersion("eppasm")),
  method = "fitmod(optfit = TRUE) posterior mode",
  eppmod = eppmod,
  region = region,
  b0 = THETA_B0,
  seed = THETA_SEED,
  log_posterior = opt$value,
  convergence = opt$convergence,
  optim_message = if (is.null(opt$message)) "" else opt$message,
  fn_evaluations = unname(opt$counts[["function"]]),
  fit_time_s = elapsed_s,
  generated_at = format(Sys.time(), "%Y-%m-%d %H:%M:%S")
)
meta_tmp <- paste0(out_meta_json, ".tmp")
writeLines(jsonlite::toJSON(meta, auto_unbox = TRUE), meta_tmp)
invisible(file.rename(meta_tmp, out_meta_json))

cat(sprintf("Wrote %d theta values to %s\n", length(theta), out_csv))
