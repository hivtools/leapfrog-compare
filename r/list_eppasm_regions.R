# List the regions `prepare_spec_fit()` finds in a PJNZ file (e.g. "National",
# or "Urban"/"Rural" for a multi-region file) — used to populate the region
# selector on the ll/fitmod tabs. Region names are data-derived (from the
# PJNZ's own EPP survey/ANC data), not engine-derived, so this only needs to
# load one package (eppasm) regardless of which package(s) the caller will
# later compare.
#
# Usage:
#   Rscript list_eppasm_regions.R <pjnz_path> <out_json> <pkg_dir> <use_local:0|1>

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 4) {
  stop("Usage: Rscript list_eppasm_regions.R <pjnz_path> <out_json> <pkg_dir> <use_local:0|1>")
}
pjnz_path <- args[[1]]
out_json <- args[[2]]
pkg_dir <- args[[3]]
use_local <- as.logical(as.integer(args[[4]]))

invisible(if (use_local) {
  suppressMessages(pkgload::load_all(pkg_dir, quiet = TRUE))
} else {
  suppressMessages(library(eppasm))
})

# Same proj.end derivation as run_ll.R/run_fitmod.R: derive from
# prepare_directincid()'s own projection years rather than asking the user.
fp0 <- prepare_directincid(pjnz_path)
proj_end <- fp0$ss$proj_start + fp0$ss$PROJ_YEARS - 1

obj_list <- prepare_spec_fit(pjnz_path, proj.end = proj_end)
regions <- names(obj_list)

tmp_path <- paste0(out_json, ".tmp")
writeLines(jsonlite::toJSON(regions), tmp_path)
file.rename(tmp_path, out_json)

cat(sprintf("Found %d region(s): %s\n", length(regions), paste(regions, collapse = ", ")))
