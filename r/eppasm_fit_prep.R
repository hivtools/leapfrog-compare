# Shared "build fp + likdat ready for ll()/fitmod()" helpers, used by
# run_ll.R and fit_theta.R.
#
# load_region_obj(pjnz_path, region) -> one region's prepare_spec_fit() object,
# projected to the same end year prepare_directincid() uses (as the simmod
# tab does), so no extra user input is needed.
load_region_obj <- function(pjnz_path, region) {
  fp0 <- prepare_directincid(pjnz_path)
  proj_end <- fp0$ss$proj_start + fp0$ss$PROJ_YEARS - 1
  obj_list <- prepare_spec_fit(pjnz_path, proj.end = proj_end)
  if (!region %in% names(obj_list)) {
    stop(sprintf("Region '%s' not found; available regions: %s", region, paste(names(obj_list), collapse = ", ")))
  }
  obj_list[[region]]
}

# theta_param_names(fp) -> a readable name per theta element, following the
# positional layout fnCreateParam() reads theta in: the EPP-model parameters,
# then iota (transformed), then whichever ANC / ANC-RT likelihood parameters
# this fp's data switches on. Falls back to "theta[i]" for anything unrecognised.
theta_param_names <- function(fp, n_param) {
  epp <- switch(
    fp$eppmod,
    rspline = sprintf("spline_u[%d]", seq_len(fp$numKnots)),
    logrw = sprintf("logrw_beta[%d]", seq_len(fp$numKnots)),
    rlogistic = sprintf("rlogistic[%d]", 1:4),
    rhybrid = c(sprintf("rlogistic[%d]", 1:4), sprintf("rw[%d]", seq_len(fp$rt$n_rw))),
    character(0)
  )
  nms <- c(epp, "iota (transformed)")
  if (isTRUE(fp$ancsitedata)) {
    nms <- c(nms, "ancbias")
    if (!exists("v.infl", where = fp)) nms <- c(nms, "log v.infl")
  }
  if (exists("ancrt", fp) && fp$ancrt %in% c("census", "both")) {
    nms <- c(nms, "log_frr_adjust")
    if (!exists("ancrtcens.vinfl", fp)) nms <- c(nms, "log ancrtcens.vinfl")
  }
  if (exists("ancrt", fp) && fp$ancrt %in% c("site", "both")) {
    nms <- c(nms, "ancrtsite.beta")
  }
  if (length(nms) != n_param) {
    return(sprintf("theta[%d]", seq_len(n_param)))
  }
  nms
}

# This replicates the prep block inlined at the top of `eppasm::fitmod()`
# (fit-model.R, between updating `fp` from `attr(obj, "specfp")` and the
# "Fit using optimization" section) — the same logic eppasm.lf already
# extracts as its own exported `prep_fp_fitmod()`. eppasm doesn't export the
# per-eppmod prep helpers it calls (`prepare_rspline_model` etc. are
# unexported), so we reach them via `getFromNamespace(name, pkg)` — `pkg` is
# a runtime string here, so the literal `pkg:::name` form doesn't work; this
# mirrors how `fitmod()` itself already defaults to `eppasm:::sample.prior`
# internally, i.e. relying on these internals is consistent with the
# packages' own conventions, not new fragility.
#
# build_fp_likdat(pkg, obj, eppmod) -> list(fp = ..., likdat = ...)
#
# `eppmod` selects the EPP transmission-curve model ("rspline", "rhybrid",
# "logrw", "rlogistic", "rtrend"). It's not derived from the PJNZ — eppasm's
# own fitmod() requires the caller to supply it via `...` — so callers pass
# it through from the UI's EPP model selector (default "rhybrid"; note
# eppasm-leapfrog explicitly rejects "rtrend", see leapfrog.R).
build_fp_likdat <- function(pkg, obj, eppmod = "rhybrid") {
  get_pkg_fn <- function(name) getFromNamespace(name, pkg)

  fp <- stats::update(attr(obj, "specfp"), eppmod = eppmod)
  eppd <- attr(obj, "eppd")

  has_ancrtsite <- exists("ancsitedat", eppd) && any(eppd$ancsitedat$type == "ancrt")
  has_ancrtcens <- !is.null(eppd$ancrtcens) && nrow(eppd$ancrtcens)

  if (!has_ancrtsite) {
    fp$ancrtsite.beta <- 0
  }

  if (has_ancrtsite & has_ancrtcens) {
    fp$ancrt <- "both"
  } else if (has_ancrtsite & !has_ancrtcens) {
    fp$ancrt <- "site"
  } else if (!has_ancrtsite & has_ancrtcens) {
    fp$ancrt <- "census"
  } else {
    fp$ancrt <- "none"
  }

  likdat <- get_pkg_fn("prepare_likdat")(eppd, fp)
  fp$ancsitedata <- as.logical(nrow(likdat$ancsite.dat$df))

  if (fp$eppmod %in% c("logrw", "rhybrid")) {
    fp$SIM_YEARS <- as.integer(max(likdat$ancsite.dat$df$yidx,
                                    likdat$hhs.dat$yidx,
                                    likdat$ancrtcens.dat$yidx,
                                    likdat$hhsincid.dat$idx))
    fp$proj.steps <- seq(fp$ss$proj_start + 0.5, fp$ss$proj_start - 1 + fp$SIM_YEARS + 0.5, by = 1 / fp$ss$hiv_steps_per_year)
  } else {
    fp$SIM_YEARS <- fp$ss$PROJ_YEARS
  }

  tsEpidemicStart <- fp$ss$time_epi_start + 0.5
  if (fp$eppmod == "rspline") {
    fp <- get_pkg_fn("prepare_rspline_model")(fp, tsEpidemicStart = tsEpidemicStart)
  } else if (fp$eppmod == "rtrend") {
    fp <- get_pkg_fn("prepare_rtrend_model")(fp)
  } else if (fp$eppmod == "logrw") {
    fp <- get_pkg_fn("prepare_logrw")(fp)
  } else if (fp$eppmod == "rhybrid") {
    fp <- get_pkg_fn("prepare_rhybrid")(fp)
  } else if (fp$eppmod == "rlogistic") {
    fp$tsEpidemicStart <- fp$proj.steps[which.min(abs(fp$proj.steps - fp$ss$time_epi_start + 0.5))]
  }

  fp$logitiota <- TRUE
  fp$incidmod <- "eppspectrum"

  list(fp = fp, likdat = likdat)
}
