# Shared tidy-long-format emitter for a `simmod()` result (class "spec" `mod`
# array plus its `hivpop`/`artpop`/`infections`/`hivdeaths`/`prev15to49`/
# `incid15to49` attributes), used by both run_simmod.R (mod straight from
# `prepare_directincid()`) and run_fitmod.R (mod refit at a fitted theta).
#
# tidy_mod_output(fp, mod) -> data.frame(indicator, age_group, sex, year, value)

tidy_mod_output <- function(fp, mod) {
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

  rbind(
    to_long_fine_age("total_population", total_population_by_age),
    to_long_hivpop_age("hiv_population", attr(mod, "hivpop")),
    to_long_artpop_age("art_population", attr(mod, "artpop")),
    to_long_fine_age("new_infections", attr(mod, "infections")),
    to_long_fine_age("aids_deaths", attr(mod, "hivdeaths")),
    emit_scalar("prevalence_15to49", attr(mod, "prev15to49") * 100),
    emit_scalar("incidence_15to49", attr(mod, "incid15to49") * 100)
  )
}

# Tidy long-format emitter for an `ll(theta, fp, likdat)` result (normally a
# named numeric vector of log-likelihood components: anc, ancrt, hhs, incid,
# artcov, rprior), used by both run_ll.R and run_fitmod.R's
# likelihood-at-fitted-theta output. Adds a `total` row (sum of components,
# i.e. what `likelihood(theta, fp, likdat, log=TRUE)` returns). `ll()` can
# short-circuit to a bare unnamed `-Inf` for a theta whose r-vector is out of
# bounds (see run_ll.R) — handled here as a single "total" row so a pathological
# input still produces a valid (if uninformative) comparison row rather than
# an error.
#
# tidy_ll_output(ll_result) -> data.frame(component, value)
tidy_ll_output <- function(ll_result) {
  if (is.null(names(ll_result))) {
    return(data.frame(component = "total", value = sum(ll_result)))
  }
  data.frame(
    component = c(names(ll_result), "total"),
    value = c(as.numeric(ll_result), sum(ll_result))
  )
}
