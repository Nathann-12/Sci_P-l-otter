# Scientific Workflows

SciPlotter's sale-facing analysis path is built around one contract:

`Book data → Analysis Recipe → Result Book / Fit Curves / Graph → Batch report`

Changing a source worksheet marks every dependent result as dirty. Recipes can
use one of three recalculation modes:

- **Auto** recalculates after a short edit debounce.
- **Manual** keeps the last result visible and waits for Run/Recalculate.
- **Frozen** deliberately preserves the saved result until its mode is changed
  (an explicit forced batch run is still allowed).

If a recalculation fails, SciPlotter never replaces a valid result with a
partial or empty table. The existing Book is marked stale, the error is retained,
and the last-good result remains available.

## Statistics

Open **Analysis → Statistics**. The dynamic dialog explains and validates the
selected test before running it.

Implemented analyses:

- one-sample, independent Welch/pooled, and paired t-tests;
- one-way and Type II/III two-way ANOVA;
- Mann-Whitney U, Wilcoxon signed-rank, and Kruskal-Wallis tests;
- Shapiro-Wilk and Levene checks;
- effect sizes and confidence intervals;
- Holm, Bonferroni, Sidak, Benjamini-Hochberg, and Benjamini-Yekutieli p-value
  corrections;
- multiple linear regression with coefficient CIs, VIF, Durbin-Watson,
  Shapiro-Wilk residual check, Breusch-Pagan, leverage, and Cook's distance.

Group comparisons accept both wide data (one group per numeric column) and long
data (one response column plus one grouping column). Every result is a normal
Book, so it can be plotted, exported, or used by a downstream recipe.

## Global Fit

Open **Analysis → Fitting → Global Fit (Shared Parameters)**. Map one X column
and at least two Y columns, then select a model and the shared parameters.

Built-in models are Gaussian, Lorentzian, Voigt, exponential, and exponential
decay. The dialog supports:

- shared versus dataset-local parameters;
- automatic or explicit initial values;
- fixed values and lower/upper bounds;
- a sigma column with absolute-uncertainty semantics;
- ordinary or robust loss;
- parameter covariance/correlation, standard errors, confidence intervals,
  prediction bands, residuals, R², RMSE, AIC, BIC, and reduced chi-square.

The workflow creates a summary Book, a tidy curves/residual Book, and a linked
fit graph. Recalculation updates the existing outputs instead of creating an
unbounded sequence of new result windows.

## Peak Analyzer

Open **Analysis → Peaks and Baseline → Peak Analyzer**. The operation executes
baseline estimation, candidate detection, simultaneous multi-peak fitting, and
reporting as one auditable recipe.

Available baselines are none, constant, linear, and asymmetric least squares
(ALS). Peak models are Gaussian, Lorentzian, and Voigt; positive, negative, and
two-direction detection are supported. Reports contain center, absolute height,
amplitude above baseline, FWHM, analytic area, confidence intervals, fit
metrics, baseline/fitted arrays, prediction bands, and residuals.

## Recipe Manager and project files

Run an analysis once and SciPlotter creates an Auto recipe. Use
**Analysis → Analysis Recipes → Manage Recipes** to run it, change mode,
duplicate it, export it, or remove only the recipe while retaining its result
Books as ordinary data. Recipes also appear in Project Explorer.

`.sciproj` schema version 2 stores recipes, mappings, modes, compact provenance,
and result metadata. Project writes are atomic. Full source/result tables remain
embedded by the existing project mechanism; recipe JSON stores configuration
and bounded audit summaries rather than duplicating large arrays.

Standalone recipes use `*.scirecipe.json`. Import asks which open Book should be
mapped to the recipe's external source. The current desktop importer accepts one
external source per imported recipe; the headless recipe engine itself supports
multiple source IDs and arbitrary acyclic node graphs.

## Batch Analysis

Use **Analysis → Analysis Recipes → Batch Analysis** and select a recipe, files,
and report path. Supported inputs match SciPlotter's normal data loaders. The
computation runs off the UI thread and can be cancelled between files.

Each input has its own SHA-256 checksum and isolated success/error record. A bad
file does not discard successful files. Report formats:

- XLSX: summary plus one output sheet per successful DataFrame result;
- HTML: self-contained human-readable summary;
- CSV: flat summary;
- JSON: versioned manifest and audit metadata.

All numerical computation uses the full input DataFrame. Plot rendering LOD and
decimation never alter statistics or fit inputs.

## Numerical and architecture contracts

- Pure computation lives in `analysis/`; Qt never runs inside numerical cores.
- `core/analysis_recipe.py` owns DAG validation, operation allow-listing,
  parameter schemas, deterministic execution, checksums, provenance, and
  last-good cache semantics.
- `analysis/scientific_operations.py` is the single DataFrame/column-mapping
  adapter used by UI, recipe, and batch paths.
- Background workers perform loading and computation only. Books, Graphs, and
  dialogs are updated on the Qt GUI thread.
- Missing/stale column mappings fail clearly; they are never guessed silently.

The suite does not yet implement post-hoc pairwise ANOVA comparisons, repeated-
measures ANOVA, mixed-effects models, survival analysis, PCA/PLS, or power/sample
size planning. Those remain separate roadmap items rather than being implied by
the current Statistics menu.
