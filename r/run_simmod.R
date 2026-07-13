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

fp <- prepare_directincid(pjnz_path)

start_time <- Sys.time()
mod <- simmod(fp)
elapsed_ms <- as.numeric(difftime(Sys.time(), start_time, units = "secs")) * 1000
cat(sprintf("%s simmod() fit took: %.1f ms\n", pkg, elapsed_ms))

years <- fp$ss$proj_start + seq_len(fp$ss$PROJ_YEARS) - 1L

sex_labels <- character(fp$ss$NG)
sex_labels[fp$ss$m.idx] <- "male"
sex_labels[fp$ss$f.idx] <- "female"

# EPPASM's own coarse age-group scheme (ages 15-80), from fp$ss$h.ag.span —
# group widths c(2,3,5,5,5,5,5,5,31) starting at AGE_START=15, i.e. "15-16",
# "17-19", "20-24", ..., "45-49", "50+". Used for the age-faceted view.
age_group_bounds <- cumsum(c(0, fp$ss$h.ag.span))
age_group_labels <- c("15-16", "17-19", "20-24", "25-29", "30-34",
                       "35-39", "40-44", "45-49", "50+")

# `mat` is a (sex, year) matrix; as.vector() traverses it column-major (all
# sexes for year 1, then all sexes for year 2, ...), which is what the
# rep(..., times=)/rep(..., each=) calls below are built to match.
emit <- function(indicator, age_group, mat) {
  data.frame(
    indicator = indicator, age_group = age_group,
    sex = rep(sex_labels, times = ncol(mat)),
    year = rep(years, each = nrow(mat)),
    value = as.vector(mat)
  )
}

emit_scalar <- function(indicator, vec) {
  data.frame(indicator = indicator, age_group = "Total", sex = "both", year = years, value = as.vector(vec))
}

# arr: (age=66, sex, year) single-year-age array -> "Total" row plus one row
# per coarse age group, summing the single-year ages within each group's span.
to_long_fine_age <- function(indicator, arr) {
  rows <- list(emit(indicator, "Total", apply(arr, c(2, 3), sum)))
  for (i in seq_along(age_group_labels)) {
    lo <- age_group_bounds[i] + 1
    hi <- age_group_bounds[i + 1]
    rows[[length(rows) + 1]] <- emit(indicator, age_group_labels[i],
                                      apply(arr[lo:hi, , , drop = FALSE], c(2, 3), sum))
  }
  do.call(rbind, rows)
}

# arr: (cd4stage, hAG=9, sex, year) -> "Total" row plus one row per hAG group
# (already at coarse-age granularity, so just slice+sum over cd4stage).
to_long_hivpop_age <- function(indicator, arr) {
  rows <- list(emit(indicator, "Total", apply(arr, c(3, 4), sum)))
  for (i in seq_along(age_group_labels)) {
    rows[[length(rows) + 1]] <- emit(indicator, age_group_labels[i],
                                      apply(arr[, i, , , drop = FALSE], c(3, 4), sum))
  }
  do.call(rbind, rows)
}

# arr: (artdur, cd4stage, hAG=9, sex, year) -> same idea as hivpop, one more dim.
to_long_artpop_age <- function(indicator, arr) {
  rows <- list(emit(indicator, "Total", apply(arr, c(4, 5), sum)))
  for (i in seq_along(age_group_labels)) {
    rows[[length(rows) + 1]] <- emit(indicator, age_group_labels[i],
                                      apply(arr[, , i, , , drop = FALSE], c(4, 5), sum))
  }
  do.call(rbind, rows)
}

# mod: (age, sex, hivstatus, year) -> collapse hivstatus first, then age-bin as above
total_population_by_age <- apply(mod, c(1, 2, 4), sum)  # (age, sex, year)

out <- rbind(
  to_long_fine_age("total_population", total_population_by_age),
  to_long_hivpop_age("hiv_population", attr(mod, "hivpop")),
  to_long_artpop_age("art_population", attr(mod, "artpop")),
  to_long_fine_age("new_infections", attr(mod, "infections")),
  to_long_fine_age("aids_deaths", attr(mod, "hivdeaths")),
  emit_scalar("prevalence_15to49", attr(mod, "prev15to49") * 100),
  emit_scalar("incidence_15to49", attr(mod, "incid15to49") * 100)
)

tmp_path <- paste0(out_csv, ".tmp")
write.csv(out, tmp_path, row.names = FALSE)
file.rename(tmp_path, out_csv)

cat(sprintf("Wrote %d rows to %s\n", nrow(out), out_csv))
