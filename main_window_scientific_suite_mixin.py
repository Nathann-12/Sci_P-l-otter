"""Integrated scientific-suite workflows: recipes, statistics, fits, and batch."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
import logging
from pathlib import Path
import uuid
import weakref
from typing import Any, Mapping

import pandas as pd
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QMessageBox, QProgressDialog

from analysis.batch import (
    dataframe_checksum,
    export_batch_report,
    load_scientific_dataframe,
)
from analysis.scientific_operations import register_scientific_operations
from core.analysis_recipe import (
    AnalysisRecipe,
    AnalysisRecipeEngine,
    OperationRegistry,
    RecipeInput,
    RecipeNode,
    RecipeOutput,
    RecalculationMode,
)


logger = logging.getLogger(__name__)
_BINDING_VERSION = 2


@dataclass(frozen=True)
class _RecipeComputation:
    engine: AnalysisRecipeEngine
    outputs: Mapping[str, Any]
    source_checksum: str
    error: str = ""
    cancelled: bool = False

    @property
    def ok(self) -> bool:
        return not self.error and not self.cancelled


@dataclass
class _ScientificRecipeBinding:
    recipe: AnalysisRecipe
    source_book: str
    result_book: str = ""
    curves_book: str = ""
    graph_tab_id: str = ""
    graph_name: str = ""
    graph_key: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = "Dirty"
    error: str = ""
    last_run: str = "Never"
    source_checksum: str = ""
    running: bool = False
    pending: bool = False
    pending_force: bool = False
    pending_auto_only: bool = False
    generation: int = 0
    running_generation: int = 0
    worker: Any = field(default=None, repr=False)
    engine: Any = field(default=None, repr=False)

    @property
    def recipe_id(self) -> str:
        return self.recipe.recipe_id

    @property
    def operation(self) -> str:
        return self.recipe.nodes[-1].operation if self.recipe.nodes else ""

    @property
    def mode(self) -> str:
        modes = {node.recalculation_mode.value for node in self.recipe.nodes}
        return next(iter(modes)).title() if len(modes) == 1 else "Mixed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "binding_version": _BINDING_VERSION,
            "recipe": self.recipe.to_dict(),
            "source_book": self.source_book,
            "result_book": self.result_book,
            "curves_book": self.curves_book,
            "graph_name": self.graph_name,
            "graph_key": self.graph_key,
            "status": self.status,
            "error": self.error,
            "last_run": self.last_run,
            "source_checksum": self.source_checksum,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "_ScientificRecipeBinding":
        version = int(raw.get("binding_version", 0))
        if version not in {1, _BINDING_VERSION}:
            raise ValueError("Unsupported scientific recipe binding version.")
        recipe = AnalysisRecipe.from_dict(raw["recipe"])
        return cls(
            recipe=recipe,
            source_book=str(raw.get("source_book", "")),
            result_book=str(raw.get("result_book", "")),
            curves_book=str(raw.get("curves_book", "")),
            graph_name=str(raw.get("graph_name", "")),
            graph_key=str(raw.get("graph_key", "")) or recipe.recipe_id,
            status=str(raw.get("status", "Dirty")),
            error=str(raw.get("error", "")),
            last_run=str(raw.get("last_run", "Never")),
            source_checksum=str(raw.get("source_checksum", "")),
        )


class MainWindowScientificSuiteMixin:
    """Connect the pure scientific cores to Books, Graphs, projects, and batch."""

    def init_scientific_suite(self) -> None:
        self._scientific_registry = OperationRegistry()
        register_scientific_operations(self._scientific_registry)
        self._scientific_recipes: dict[str, _ScientificRecipeBinding] = {}
        self._scientific_batch_workers: set[Any] = set()
        self._scientific_batch_dialogs: set[Any] = set()
        self._scientific_epoch = uuid.uuid4().hex

        initial = getattr(self, "workbook", None)
        if initial is not None:
            self._connect_analysis_recipe_book(initial)
        for widget, _subwindow in getattr(getattr(self, "mdi", None), "_books", {}).values():
            self._connect_analysis_recipe_book(widget)

    def closeEvent(self, event) -> None:
        """Cooperatively stop analysis workers before Qt destroys the window."""
        for binding in list(getattr(self, "_scientific_recipes", {}).values()):
            worker = getattr(binding, "worker", None)
            if worker is not None:
                try:
                    worker.cancel()
                except Exception:
                    pass
        for worker in list(getattr(self, "_scientific_batch_workers", set())):
            try:
                worker.cancel()
            except Exception:
                pass
        for dialog in list(getattr(self, "_scientific_batch_dialogs", set())):
            try:
                dialog.close()
            except Exception:
                pass
        super().closeEvent(event)

    # -------------------------------------------------------------- UI flows
    def scientific_open_statistics(self, default_operation: str | None = None) -> None:
        frame = self._scientific_active_frame()
        if frame is None:
            return
        source_book = self._active_book_label()
        from dialogs.statistics_dialog import OPERATION_LABELS, StatisticsDialog

        numeric = [str(c) for c in frame.columns if pd.api.types.is_numeric_dtype(frame[c])]
        if not numeric:
            self.inform("Statistics", "The active Book has no numeric columns.")
            return
        dialog = StatisticsDialog(
            [str(c) for c in frame.columns], numeric,
            default_operation=default_operation, parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        operation, params = values["operation"], values["params"]
        label = OPERATION_LABELS.get(operation, "Statistical Analysis")
        self._create_and_run_recipe(label, operation, params, source_book, frame)

    def scientific_open_global_fit(self) -> None:
        frame = self._scientific_active_frame()
        if frame is None:
            return
        source_book = self._active_book_label()
        numeric = [str(c) for c in frame.columns if pd.api.types.is_numeric_dtype(frame[c])]
        if len(numeric) < 3:
            self.inform(
                "Global Fit",
                "Global Fit needs one numeric X column and at least two numeric Y columns.",
            )
            return
        from dialogs.global_fit_dialog import GlobalFitDialog

        dialog = GlobalFitDialog(numeric, self)
        if dialog.exec() != QDialog.Accepted:
            return
        self._create_and_run_recipe(
            "Global Fit", "global_fit", dialog.values(), source_book, frame,
            background=True,
        )

    def scientific_open_peak_analyzer(self) -> None:
        frame = self._scientific_active_frame()
        if frame is None:
            return
        source_book = self._active_book_label()
        numeric = [str(c) for c in frame.columns if pd.api.types.is_numeric_dtype(frame[c])]
        if len(numeric) < 2:
            self.inform("Peak Analyzer", "Peak analysis needs numeric X and Y columns.")
            return
        from dialogs.peak_analyzer_dialog import PeakAnalyzerDialog

        dialog = PeakAnalyzerDialog(numeric, self)
        if dialog.exec() != QDialog.Accepted:
            return
        self._create_and_run_recipe(
            "Peak Analyzer", "peak_analysis", dialog.values(), source_book, frame,
            background=True,
        )

    def scientific_manage_recipes(self) -> None:
        from dialogs.recipe_manager_dialog import RecipeManagerDialog

        dialog = RecipeManagerDialog(self.analysis_recipe_summaries(), self)

        def refresh(*_args):
            dialog.set_recipes(self.analysis_recipe_summaries())

        dialog.run_requested.connect(
            lambda recipe_id: (self._start_recipe_recalculation(recipe_id, force=True), refresh())
        )
        dialog.mode_requested.connect(
            lambda recipe_id, mode: (self._set_recipe_mode(recipe_id, mode), refresh())
        )
        dialog.duplicate_requested.connect(
            lambda recipe_id: (self._duplicate_recipe(recipe_id), refresh())
        )
        dialog.export_requested.connect(self._export_recipe)
        dialog.delete_requested.connect(
            lambda recipe_id: (self._delete_recipe(recipe_id), refresh())
        )
        dialog.exec()

    def scientific_recalculate_all(self) -> None:
        runnable = [
            binding for binding in self._scientific_recipes.values()
            if any(
                node.recalculation_mode != RecalculationMode.FROZEN
                for node in binding.recipe.nodes
            )
        ]
        if not runnable:
            self.inform("Recalculate", "There are no runnable Analysis Recipes.")
            return
        for binding in runnable:
            self._start_recipe_recalculation(binding.recipe_id, force=False, auto_only=False)
        self.notify(f"Recalculating {len(runnable)} analysis recipe(s)...")

    def scientific_import_recipe(self) -> None:
        path = self.ask_open_path(
            "Import Analysis Recipe", "Analysis Recipe (*.scirecipe.json *.json);;All Files (*.*)"
        )
        if not path:
            return
        try:
            recipe = AnalysisRecipe.load(path)
            unknown = sorted({n.operation for n in recipe.nodes if n.operation not in self._scientific_registry})
            if unknown:
                raise ValueError(f"Unsupported operation(s): {', '.join(unknown)}")
            source_ids = self._recipe_source_ids(recipe)
            if len(source_ids) != 1:
                raise ValueError("The desktop importer currently requires exactly one external data source.")
            names = self._scientific_source_book_names()
            if not names:
                raise ValueError("Open a data Book before importing a recipe.")
            source_book, ok = self.ask_choice(
                "Map Recipe Source", "Use this Book as the recipe input:", names
            )
            if not ok:
                return
            if recipe.recipe_id in self._scientific_recipes:
                recipe = AnalysisRecipe.create(
                    f"{recipe.name} (Imported)", nodes=list(recipe.nodes),
                    description=recipe.description, metadata=dict(recipe.metadata),
                )
            frame = self._scientific_frame_for_book(source_book)
            if frame is None:
                raise ValueError(f"Source Book is unavailable: {source_book}")
            binding = _ScientificRecipeBinding(recipe=recipe, source_book=source_book)
            outputs, updated, checksum = self._compute_recipe(binding.recipe, frame)
            binding.recipe, binding.source_checksum = updated, checksum
            self._scientific_recipes[binding.recipe_id] = binding
            self._publish_recipe_outputs(binding, outputs, create=True)
            binding.status, binding.error = "Clean", ""
            binding.last_run = datetime.now().isoformat(timespec="seconds")
            self.notify(f"Imported and ran recipe: {binding.recipe.name}")
        except Exception as exc:
            self.error_box("Import Recipe Failed", f"Reason: {exc}")

    def scientific_batch_analysis(self) -> None:
        from dialogs.batch_analysis_dialog import BatchAnalysisDialog

        summaries = self.analysis_recipe_summaries()
        if not summaries:
            self.inform(
                "Batch Analysis",
                "Run an analysis once to create a Recipe, or import a Recipe first.",
            )
            return
        dialog = BatchAnalysisDialog(summaries, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        binding = self._scientific_recipes.get(str(values["recipe_id"]))
        if binding is None:
            self.error_box("Batch Analysis", "The selected recipe no longer exists.")
            return

        from widgets.batch_analysis_worker import BatchAnalysisWorker

        recipe_document = binding.recipe.to_dict()
        registry = self._scientific_registry

        def analyzer(frame, _context):
            recipe = AnalysisRecipe.from_dict(recipe_document)
            engine = AnalysisRecipeEngine(recipe, registry)
            for source_id in self._recipe_source_ids(recipe):
                engine.set_source(source_id, frame, auto_run=False)
            target = engine.topological_order[-1]
            report = engine.run(target, force=True)
            if not report.ok:
                reason = next(iter(report.failed.values()), None) or next(
                    iter(report.blocked.values()), "Recipe did not produce a result."
                )
                raise RuntimeError(reason)
            return engine.get_result(target, "result")

        worker = BatchAnalysisWorker(
            values["files"], loader=load_scientific_dataframe, analyzer=analyzer,
            recipe_name=binding.recipe.name, recipe_version=binding.recipe.version,
        )
        progress = QProgressDialog(
            "Preparing batch analysis...", "Cancel", 0, len(values["files"]), self
        )
        progress.setWindowTitle("Batch Analysis")
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.canceled.connect(worker.cancel)
        worker.signals.progress.connect(
            lambda done, total, source: self._update_batch_progress(progress, done, total, source)
        )

        def finished(result):
            try:
                report_path = export_batch_report(result, values["report_path"])
                summary_name = self._open_analysis_book(
                    f"{binding.recipe.name} Batch Summary", result.summary_frame(),
                    provenance={
                        "recipe_id": binding.recipe_id,
                        "operation": "batch_analysis",
                        "report_path": str(report_path),
                    },
                )
                self.notify(
                    f"Batch complete: {result.success_count} succeeded, "
                    f"{result.failure_count} failed -> {Path(report_path).name}; {summary_name}"
                )
            except Exception as exc:
                self.error_box("Batch Report Failed", f"Reason: {exc}")
            finally:
                progress.close()
                self._scientific_batch_workers.discard(worker)
                self._scientific_batch_dialogs.discard(progress)

        def failed(traceback_text):
            progress.close()
            self._scientific_batch_workers.discard(worker)
            self._scientific_batch_dialogs.discard(progress)
            self.error_box("Batch Analysis Failed", traceback_text.splitlines()[-1])

        worker.signals.finished.connect(finished)
        worker.signals.failed.connect(failed)
        self._scientific_batch_workers.add(worker)
        self._scientific_batch_dialogs.add(progress)
        worker.start()

    # ------------------------------------------------------- recipe lifecycle
    def _create_and_run_recipe(
        self, name: str, operation: str, params: Mapping[str, Any],
        source_book: str, frame: pd.DataFrame,
        *, background: bool = False,
    ) -> _ScientificRecipeBinding | None:
        self._ensure_recipe_source_dataset(source_book, frame)
        outputs_spec = [RecipeOutput("result", "dataframe", "Analysis report")]
        if operation in {"global_fit", "peak_analysis"}:
            outputs_spec.append(RecipeOutput("curves", "dataframe", "Fit curves and residuals"))
        node = RecipeNode(
            node_id="analysis",
            operation=operation,
            inputs=(RecipeInput.source("data", "source"),),
            outputs=tuple(outputs_spec),
            parameters=dict(params),
            recalculation_mode=RecalculationMode.AUTO,
            label=name,
        )
        recipe = AnalysisRecipe.create(
            name,
            nodes=[node],
            description=f"Reusable SciPlotter {name} analysis",
            metadata={"source_book": source_book, "target_node": "analysis"},
        )
        binding = _ScientificRecipeBinding(recipe=recipe, source_book=source_book)
        binding.engine = AnalysisRecipeEngine(recipe, self._scientific_registry)
        self._scientific_recipes[binding.recipe_id] = binding
        record = getattr(self, "_record_op", None)
        if callable(record):
            record(operation, recipe_id=binding.recipe_id, source_book=source_book, **dict(params))
        if background:
            self._start_recipe_recalculation(binding.recipe_id, force=True)
            self.notify(f"{name} started in the background; the source Book remains usable.")
            return binding
        try:
            computation = self._compute_recipe(binding.engine, frame, force=True)
            if not computation.ok:
                binding.engine = computation.engine
                binding.recipe = computation.engine.recipe
                binding.source_checksum = computation.source_checksum
                raise RuntimeError(computation.error or "Execution was cancelled.")
            self._commit_recipe_computation(binding, computation, create=True)
            if binding.status == "Warning":
                self.notify(f"{name} completed with warning: {binding.error}", error=True)
            else:
                self.notify(f"{name} complete; saved as an Auto Analysis Recipe.")
            return binding
        except Exception as exc:
            binding.status = "Error"
            binding.error = str(exc)
            self.error_box(f"{name} Failed", f"Reason: {exc}")
            return None

    def _compute_recipe(
        self,
        engine: AnalysisRecipeEngine,
        frame: pd.DataFrame,
        cancel_check=None,
        *,
        force: bool = False,
        auto_only: bool = False,
    ) -> _RecipeComputation:
        source_ids = self._recipe_source_ids(engine.recipe)
        if not source_ids:
            raise ValueError("Recipe has no external DataFrame source.")
        for source_id in source_ids:
            engine.set_source(source_id, frame, auto_run=False)
        target = str(engine.recipe.metadata.get("target_node") or engine.topological_order[-1])
        report = (
            engine.run_auto(target, cancel_check=cancel_check)
            if auto_only
            else engine.run(target, force=force, cancel_check=cancel_check)
        )
        checksum = dataframe_checksum(frame)
        if report.cancelled:
            return _RecipeComputation(engine, {}, checksum, cancelled=True)
        if not report.ok:
            reason = next(iter(report.failed.values()), None) or next(
                iter(report.blocked.values()), None
            ) or "Recipe produced no result."
            return _RecipeComputation(engine, {}, checksum, error=str(reason))
        try:
            outputs = {
                output.name: engine.get_result(target, output.name)
                for output in engine.recipe.node(target).outputs
            }
        except Exception as exc:
            return _RecipeComputation(engine, {}, checksum, error=str(exc))
        return _RecipeComputation(engine, outputs, checksum)

    def _start_recipe_recalculation(
        self,
        recipe_id: str,
        *,
        force: bool = False,
        auto_only: bool = False,
    ) -> None:
        binding = self._scientific_recipes.get(str(recipe_id))
        if binding is None:
            return
        if binding.mode == "Frozen" and not force:
            binding.status = "Frozen"
            return
        frame = self._scientific_frame_for_book(binding.source_book)
        if frame is None:
            binding.status = "Missing source"
            binding.error = f"Source Book is unavailable: {binding.source_book}"
            return
        if binding.running:
            binding.generation += 1
            binding.pending = True
            binding.pending_force = binding.pending_force or force
            binding.pending_auto_only = binding.pending_auto_only or auto_only
            if binding.worker is not None:
                binding.worker.cancel()
            return

        from widgets.heavy_plot_worker import HeavyPlotWorker

        if binding.engine is None:
            binding.engine = AnalysisRecipeEngine(binding.recipe, self._scientific_registry)
        worker_engine = binding.engine.fork()
        binding.generation += 1
        generation = binding.generation
        epoch = self._scientific_epoch
        binding.running = True
        binding.running_generation = generation
        binding.pending = False
        binding.pending_force = False
        binding.pending_auto_only = False
        binding.status = "Running"

        def prepare(source_frame, token):
            return self._compute_recipe(
                worker_engine,
                source_frame,
                cancel_check=lambda: token.cancelled,
                force=force,
                auto_only=auto_only,
            )

        worker = HeavyPlotWorker(prepare, frame.copy(deep=True))
        binding.worker = worker
        worker.signals.finished.connect(
            lambda payload, rid=binding.recipe_id, gen=generation, ep=epoch, job=worker:
                self._recipe_recalculation_finished(rid, payload, gen, ep, job)
        )
        worker.signals.failed.connect(
            lambda trace, rid=binding.recipe_id, gen=generation, ep=epoch, job=worker:
                self._recipe_recalculation_failed(rid, trace, gen, ep, job)
        )
        worker.signals.cancelled.connect(
            lambda rid=binding.recipe_id, gen=generation, ep=epoch, job=worker:
                self._recipe_recalculation_cancelled(rid, gen, ep, job)
        )
        worker.start()

    def _recipe_recalculation_finished(
        self, recipe_id: str, payload, generation=None, epoch=None, worker=None
    ) -> None:
        binding = self._scientific_recipes.get(recipe_id)
        if binding is None:
            return
        if not self._recipe_job_is_current(binding, generation, epoch, worker):
            self._finish_recipe_job(binding, worker)
            return
        binding.running = False
        binding.worker = None
        if not isinstance(payload, _RecipeComputation):
            self._recipe_recalculation_failed(
                recipe_id, "RuntimeError: invalid recipe worker result"
            )
            return
        binding.engine = payload.engine
        binding.recipe = payload.engine.recipe
        binding.source_checksum = payload.source_checksum
        if payload.cancelled:
            binding.status = "Dirty"
        elif payload.error:
            binding.status = "Error - last good result kept" if binding.result_book else "Error"
            binding.error = payload.error
            self._mark_result_stale(binding)
            self.notify(
                f"Recipe '{binding.recipe.name}' failed; last good result was kept.",
                error=True,
            )
        else:
            self._commit_recipe_computation(binding, payload)
            if binding.status == "Warning":
                self.notify(
                    f"Recipe '{binding.recipe.name}' completed with warning: {binding.error}",
                    error=True,
                )
        self._run_pending_recipe_job(binding)

    def _recipe_recalculation_failed(
        self, recipe_id: str, traceback_text: str,
        generation=None, epoch=None, worker=None,
    ) -> None:
        binding = self._scientific_recipes.get(recipe_id)
        if binding is None:
            return
        if not self._recipe_job_is_current(binding, generation, epoch, worker):
            self._finish_recipe_job(binding, worker)
            return
        binding.running = False
        binding.worker = None
        binding.status = "Error - last good result kept" if binding.result_book else "Error"
        binding.error = traceback_text.splitlines()[-1] if traceback_text else "Unknown error"
        self._mark_result_stale(binding)
        self.notify(f"Recipe '{binding.recipe.name}' failed; last good result was kept.", error=True)
        self._run_pending_recipe_job(binding)

    def _recipe_recalculation_cancelled(
        self, recipe_id: str, generation=None, epoch=None, worker=None
    ) -> None:
        binding = self._scientific_recipes.get(recipe_id)
        if binding is None:
            return
        if not self._recipe_job_is_current(binding, generation, epoch, worker):
            self._finish_recipe_job(binding, worker)
            return
        binding.running = False
        binding.worker = None
        binding.status = "Dirty"
        self._run_pending_recipe_job(binding)

    def _recipe_job_is_current(self, binding, generation, epoch, worker) -> bool:
        return (
            (generation is None or generation == binding.generation)
            and (epoch is None or epoch == getattr(self, "_scientific_epoch", None))
            and (worker is None or worker is binding.worker)
        )

    def _finish_recipe_job(self, binding, worker) -> None:
        if worker is not None and binding.worker is not worker:
            return
        binding.running = False
        binding.worker = None
        self._run_pending_recipe_job(binding)

    def _run_pending_recipe_job(self, binding) -> None:
        if not binding.pending:
            return
        force = binding.pending_force
        auto_only = binding.pending_auto_only
        binding.pending = False
        binding.pending_force = False
        binding.pending_auto_only = False
        if auto_only and not any(
            node.recalculation_mode == RecalculationMode.AUTO
            for node in binding.recipe.nodes
        ):
            return
        self._start_recipe_recalculation(
            binding.recipe_id, force=force, auto_only=auto_only
        )

    def _commit_recipe_computation(self, binding, computation, *, create=False) -> None:
        binding.engine = computation.engine
        binding.recipe = computation.engine.recipe
        binding.source_checksum = computation.source_checksum
        binding.last_run = datetime.now().isoformat(timespec="seconds")
        warning = self._output_warning(computation.outputs)
        binding.status = "Warning" if warning else "Clean"
        binding.error = warning
        self._publish_recipe_outputs(binding, computation.outputs, create=create)

    @staticmethod
    def _output_warning(outputs) -> str:
        """Return a human-readable warning if an analysis did not fully converge.

        A curve fit that hit ``max_nfev`` (or otherwise failed to converge) is
        still returned as a result object with best-effort parameters; without
        this check the recipe would be marked ``Clean`` and the questionable fit
        would be persisted to the Book/Graph/project as if it were trustworthy.
        The fit report tables carry an explicit convergence marker (peak: a
        ``success`` column, global fit: a ``Convergence``/``success`` row) which
        we surface here so UI, batch and AI all report the same status.
        """

        result = outputs.get("result") if isinstance(outputs, Mapping) else outputs
        if not isinstance(result, pd.DataFrame) or result.empty:
            return ""
        columns = set(result.columns)

        # Peak analyzer: one boolean ``success`` per fitted peak.
        if "success" in columns and "section" not in columns:
            try:
                converged = result["success"].astype(bool)
            except (TypeError, ValueError):
                return ""
            if not converged.all():
                return "Peak fit did not converge (optimiser stopped early)."
            return ""

        # Global fit: a ``Convergence`` section carries success + message rows.
        if {"section", "metric"}.issubset(columns):
            convergence = result[result["section"] == "Convergence"]
            if not convergence.empty:
                success_rows = convergence[convergence["metric"] == "success"]
                if not success_rows.empty and not bool(success_rows["value"].iloc[0]):
                    message = ""
                    if "detail" in convergence.columns:
                        message_rows = convergence[convergence["metric"] == "message"]
                        if not message_rows.empty:
                            message = str(message_rows["detail"].iloc[0])
                    detail = f" ({message})" if message and message != "nan" else ""
                    return f"Global fit did not converge{detail}."
        return ""

    # ----------------------------------------------------------- Book + Graph
    def _publish_recipe_outputs(self, binding, outputs, *, create: bool) -> None:
        report = self._as_dataframe(outputs.get("result"))
        provenance = self._binding_provenance(binding)
        if create or not binding.result_book:
            binding.result_book = self._open_analysis_book(
                f"{binding.recipe.name} Results", report, provenance=provenance
            )
        else:
            self._update_analysis_book(binding.result_book, report, provenance)

        curves = outputs.get("curves")
        if curves is not None:
            curves_frame = self._as_dataframe(curves)
            if create or not binding.curves_book:
                binding.curves_book = self._open_analysis_book(
                    f"{binding.recipe.name} Curves", curves_frame, provenance=provenance
                )
            else:
                self._update_analysis_book(binding.curves_book, curves_frame, provenance)
            self._render_recipe_graph(binding, curves_frame)
        self._refresh_project_explorer()

    def _open_analysis_book(self, name: str, frame: pd.DataFrame, *, provenance: Mapping[str, Any]):
        book_name = self._open_signal_result_book(name, frame)
        payload = getattr(self, "_datasets", {}).get(book_name)
        if isinstance(payload, dict):
            payload["analysis_provenance"] = dict(provenance)
        return book_name

    def _update_analysis_book(self, name: str, frame: pd.DataFrame, provenance) -> None:
        payload = getattr(self, "_datasets", {}).get(name)
        if isinstance(payload, dict):
            payload["df"] = frame
            payload["analysis_provenance"] = dict(provenance)
        workbook = getattr(getattr(self, "mdi", None), "book_widget", lambda *_: None)(name)
        if workbook is not None and hasattr(workbook, "set_dataframe"):
            workbook.set_dataframe(frame)

    def _render_recipe_graph(self, binding, curves: pd.DataFrame) -> None:
        tabs = getattr(self, "tabs", None)
        if tabs is None or curves.empty:
            return
        tab_id = binding.graph_tab_id
        if (not tab_id or tab_id not in getattr(tabs, "tabs", {})) and binding.graph_name:
            for candidate_id, title in getattr(tabs, "get_open_tabs", lambda: [])():
                if title == binding.graph_name:
                    tab_id = candidate_id
                    binding.graph_tab_id = candidate_id
                    break
        if not tab_id or tab_id not in getattr(tabs, "tabs", {}):
            binding.graph_name = binding.graph_name or f"{binding.recipe.name} Fit"
            tab_id = tabs.add_tab(binding.graph_name)
            binding.graph_tab_id = tab_id
        tab = tabs.tabs.get(tab_id)
        if tab is None:
            return
        try:
            tab.clear_layers()
            tab.get_axes().clear()
            series: list[tuple[Any, Any, str, dict]] = []
            if "dataset" in curves.columns:
                colors = ("#4F9CF9", "#e29b52", "#56b4a7", "#c77dff", "#e76f51")
                for index, (dataset, part) in enumerate(curves.groupby("dataset", sort=False)):
                    color = colors[index % len(colors)]
                    series.append((part.x, part.observed, f"{dataset} observed", {"color": color, "alpha": .45}))
                    series.append((part.x, part.fitted, f"{dataset} fit", {"color": color, "linewidth": 2.0}))
            else:
                series = [
                    (curves.x, curves.observed, "Observed", {"color": "#aab0b6", "alpha": .75}),
                    (curves.x, curves.baseline, "Baseline", {"color": "#e29b52", "linestyle": "--"}),
                    (curves.x, curves.fitted, "Peak fit", {"color": "#4F9CF9", "linewidth": 2.1}),
                ]
            for x, y, label, options in series:
                tabs.add_series_to_tabs(
                    [tab_id], x, y, label=label, style="line",
                    meta={"recipe_id": binding.recipe_id, "analysis_fit": True},
                    defer_draw=True, **options,
                )
            ax = tab.get_axes()
            ax.legend(loc="best")
            ax.set_title(binding.recipe.name)
            tab.canvas.draw_idle()
        except Exception:
            logger.debug("analysis graph rendering failed", exc_info=True)

    def _mark_result_stale(self, binding) -> None:
        for name in (binding.result_book, binding.curves_book):
            payload = getattr(self, "_datasets", {}).get(name)
            if isinstance(payload, dict):
                provenance = dict(payload.get("analysis_provenance") or {})
                provenance.update({"status": binding.status, "error": binding.error, "stale": True})
                payload["analysis_provenance"] = provenance

    # ------------------------------------------------------- source watching
    def _connect_analysis_recipe_book(self, workbook) -> None:
        if workbook is None or getattr(workbook, "_scientific_recipe_connected", False):
            return
        table = getattr(workbook, "table", None)
        if table is None:
            return
        workbook._scientific_recipe_connected = True
        timer = QTimer(workbook)
        timer.setSingleShot(True)
        timer.setInterval(450)
        reference = weakref.ref(workbook)
        timer.timeout.connect(lambda: self._recalculate_recipes_for_book(reference()))
        workbook._scientific_recipe_timer = timer
        table.itemChanged.connect(lambda _item, ref=reference: self._analysis_source_edited(ref()))

    def _analysis_source_edited(self, workbook) -> None:
        if workbook is None:
            return
        name = str(getattr(workbook, "dataset_name", "") or "")
        affected = [b for b in self._scientific_recipes.values() if b.source_book == name]
        if not affected:
            return
        for binding in affected:
            if binding.running:
                binding.pending = True
            if binding.mode == "Frozen":
                binding.status = "Frozen"
            else:
                binding.status = "Dirty"
                self._mark_result_stale(binding)
        timer = getattr(workbook, "_scientific_recipe_timer", None)
        if timer is not None:
            timer.start()

    def _recalculate_recipes_for_book(self, workbook) -> None:
        if workbook is None:
            return
        name = str(getattr(workbook, "dataset_name", "") or "")
        for binding in self._scientific_recipes.values():
            if binding.source_book == name and binding.mode == "Auto":
                self._start_recipe_recalculation(binding.recipe_id)

    # ------------------------------------------------ manager + persistence
    def analysis_recipe_summaries(self) -> list[dict[str, Any]]:
        return [
            {
                "id": binding.recipe_id,
                "name": binding.recipe.name,
                "mode": binding.mode,
                "status": binding.status,
                "source": binding.source_book,
                "result": binding.result_book or "Not calculated",
                "last_run": binding.last_run,
                "operation": binding.operation,
                "source_checksum": binding.source_checksum,
                "error": binding.error,
            }
            for binding in self._scientific_recipes.values()
        ]

    def serialize_analysis_recipes(self) -> list[dict[str, Any]]:
        return [binding.to_dict() for binding in self._scientific_recipes.values()]

    def prepare_analysis_recipe_persistence(self) -> None:
        """Snapshot visible source sheets before ``core.session`` builds staging."""
        for source_book in {b.source_book for b in self._scientific_recipes.values()}:
            frame = self._scientific_frame_for_book(source_book)
            if frame is not None:
                self._ensure_recipe_source_dataset(source_book, frame)

    def restore_analysis_recipes(self, payload) -> None:
        if not hasattr(self, "_scientific_recipes"):
            self.init_scientific_suite()
        restored: dict[str, _ScientificRecipeBinding] = {}
        for raw in payload or []:
            try:
                binding = _ScientificRecipeBinding.from_dict(raw)
                if any(node.operation not in self._scientific_registry for node in binding.recipe.nodes):
                    binding.status = "Unavailable operation"
                restored[binding.recipe_id] = binding
            except Exception:
                logger.warning("invalid analysis recipe skipped during project restore", exc_info=True)
        self._scientific_recipes = restored
        for widget, _subwindow in getattr(getattr(self, "mdi", None), "_books", {}).values():
            self._connect_analysis_recipe_book(widget)
        self._refresh_project_explorer()

    def _set_recipe_mode(self, recipe_id: str, mode: str) -> None:
        binding = self._scientific_recipes.get(recipe_id)
        if binding is None:
            return
        parsed = RecalculationMode.parse(mode)
        binding.recipe.nodes = [replace(node, recalculation_mode=parsed) for node in binding.recipe.nodes]
        binding.recipe.updated_at = datetime.now().astimezone().isoformat()
        binding.status = "Frozen" if parsed == RecalculationMode.FROZEN else "Dirty"
        if parsed == RecalculationMode.AUTO:
            self._start_recipe_recalculation(recipe_id)

    def _duplicate_recipe(self, recipe_id: str) -> None:
        original = self._scientific_recipes.get(recipe_id)
        if original is None:
            return
        recipe = AnalysisRecipe.create(
            f"{original.recipe.name} Copy",
            nodes=list(original.recipe.nodes),
            description=original.recipe.description,
            metadata=dict(original.recipe.metadata),
        )
        duplicate = _ScientificRecipeBinding(recipe=recipe, source_book=original.source_book)
        self._scientific_recipes[duplicate.recipe_id] = duplicate
        self._start_recipe_recalculation(duplicate.recipe_id, force=True)

    def _export_recipe(self, recipe_id: str) -> None:
        binding = self._scientific_recipes.get(recipe_id)
        if binding is None:
            return
        safe_name = "_".join(binding.recipe.name.split()) or "analysis_recipe"
        path = self.ask_save_path(
            "Export Analysis Recipe", f"{safe_name}.scirecipe.json",
            "Analysis Recipe (*.scirecipe.json *.json)",
        )
        if not path:
            return
        try:
            binding.recipe.save(path)
            self.notify(f"Recipe exported: {Path(path).name}")
        except Exception as exc:
            self.error_box("Export Recipe Failed", f"Reason: {exc}")

    def _delete_recipe(self, recipe_id: str) -> None:
        binding = self._scientific_recipes.get(recipe_id)
        if binding is None:
            return
        answer = QMessageBox.question(
            self, "Delete Analysis Recipe",
            f"Delete '{binding.recipe.name}'? Existing result Books will be kept as ordinary data.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        if binding.worker is not None:
            try:
                binding.worker.cancel()
            except Exception:
                pass
        self._scientific_recipes.pop(recipe_id, None)
        for name in (binding.result_book, binding.curves_book):
            payload = getattr(self, "_datasets", {}).get(name)
            if isinstance(payload, dict):
                payload.pop("analysis_provenance", None)

    # -------------------------------------------------------------- utilities
    def _scientific_active_frame(self) -> pd.DataFrame | None:
        workbook = getattr(self, "workbook", None)
        frame = None
        if workbook is not None and hasattr(workbook, "dataframe"):
            try:
                visible = workbook.dataframe()
                if isinstance(visible, pd.DataFrame) and not visible.empty:
                    frame = visible
            except Exception:
                logger.debug("active worksheet read failed", exc_info=True)
        if frame is None:
            frame = getattr(self, "_df", None)
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            self.inform("No Data", "Open or select a non-empty data Book first.")
            return None
        return frame.copy(deep=True)

    def _scientific_frame_for_book(self, name: str) -> pd.DataFrame | None:
        workbook = getattr(getattr(self, "mdi", None), "book_widget", lambda *_: None)(name)
        if workbook is not None:
            try:
                frame = workbook.dataframe()
                if isinstance(frame, pd.DataFrame) and not frame.empty:
                    return frame
            except Exception:
                logger.debug("could not read recipe source worksheet", exc_info=True)
        payload = getattr(self, "_datasets", {}).get(name)
        frame = payload.get("df") if isinstance(payload, dict) else None
        return frame.copy(deep=True) if isinstance(frame, pd.DataFrame) and not frame.empty else None

    def _scientific_source_book_names(self) -> list[str]:
        return [
            str(name) for name, payload in getattr(self, "_datasets", {}).items()
            if isinstance(payload, dict) and isinstance(payload.get("df"), pd.DataFrame)
        ]

    def _ensure_recipe_source_dataset(self, name: str, frame: pd.DataFrame) -> None:
        datasets = getattr(self, "_datasets", None)
        if not isinstance(datasets, dict):
            return
        payload = datasets.get(name)
        if isinstance(payload, dict):
            payload["df"] = frame.copy(deep=True)
        else:
            datasets[name] = {"df": frame.copy(deep=True), "path": None}

    @staticmethod
    def _recipe_source_ids(recipe: AnalysisRecipe) -> tuple[str, ...]:
        return tuple(dict.fromkeys(
            binding.source_id
            for node in recipe.nodes for binding in node.inputs
            if binding.kind == "source"
        ))

    @staticmethod
    def _as_dataframe(value) -> pd.DataFrame:
        if isinstance(value, pd.DataFrame):
            return value.copy(deep=True)
        if isinstance(value, Mapping):
            return pd.DataFrame([dict(value)])
        return pd.DataFrame({"result": [value]})

    def _binding_provenance(self, binding) -> dict[str, Any]:
        return {
            "recipe_id": binding.recipe_id,
            "recipe_name": binding.recipe.name,
            "operation": binding.operation,
            "source_book": binding.source_book,
            "source_checksum": binding.source_checksum,
            "mode": binding.mode,
            "status": binding.status,
            "last_run": binding.last_run,
            "stale": False,
        }

    @staticmethod
    def _update_batch_progress(dialog, done: int, total: int, source: str) -> None:
        dialog.setMaximum(max(1, int(total)))
        dialog.setValue(int(done))
        if source:
            dialog.setLabelText(f"Processed {done} of {total}: {Path(source).name}")

    def _refresh_project_explorer(self) -> None:
        explorer = getattr(self, "project_explorer", None)
        if explorer is not None and hasattr(explorer, "refresh"):
            try:
                explorer.refresh()
            except Exception:
                logger.debug("project explorer recipe refresh skipped", exc_info=True)


__all__ = ["MainWindowScientificSuiteMixin"]
