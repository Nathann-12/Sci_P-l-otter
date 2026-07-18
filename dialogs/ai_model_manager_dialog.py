"""Model-pack UI for verified downloads and air-gapped installations."""
from __future__ import annotations

from threading import Event
from typing import Callable

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ai.llama_cpp_client import resolve_llama_server
from ai.model_manager import ModelManager, system_ram_gb
from ai.readiness import AIReadiness, inspect_bundled_ai
from ai.runtime_manager import RuntimeManager


class _ModelDownloadThread(QThread):
    progress_changed = Signal(int, int)
    installed = Signal(str)
    failed = Signal(str)

    def __init__(self, manager: ModelManager, pack_id: str, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.pack_id = pack_id
        self._cancelled = Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def run(self) -> None:
        try:
            self.manager.download(
                self.pack_id,
                progress=lambda done, total: self.progress_changed.emit(done, total),
                cancelled=self._cancelled.is_set,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.installed.emit(self.pack_id)


class _RuntimeDownloadThread(QThread):
    progress_changed = Signal(int, int)
    installed = Signal(str)
    failed = Signal(str)

    def __init__(self, manager: RuntimeManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._cancelled = Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def run(self) -> None:
        try:
            path = self.manager.download_and_install(
                progress=lambda done, total: self.progress_changed.emit(done, total),
                cancelled=self._cancelled.is_set,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.installed.emit(str(path))


class _OfflineInstallThread(QThread):
    progress_changed = Signal(int, int)
    installed = Signal(str)
    failed = Signal(str)

    def __init__(self, manager: ModelManager, bundle: str, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.bundle = bundle
        self._cancelled = Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def run(self) -> None:
        try:
            path = self.manager.install_offline_bundle(
                self.bundle,
                progress=lambda done, total: self.progress_changed.emit(done, total),
                cancelled=self._cancelled.is_set,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.installed.emit(path.parent.name)


class _OfflineExportThread(QThread):
    progress_changed = Signal(int, int)
    exported = Signal(str)
    failed = Signal(str)

    def __init__(self, manager: ModelManager, pack_id: str, destination: str, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.pack_id = pack_id
        self.destination = destination
        self._cancelled = Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def run(self) -> None:
        try:
            path = self.manager.create_offline_bundle(
                self.pack_id,
                self.destination,
                progress=lambda done, total: self.progress_changed.emit(done, total),
                cancelled=self._cancelled.is_set,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.exported.emit(str(path))


class AiModelManagerDialog(QDialog):
    """Manage optional models without sending research data to a cloud."""

    def __init__(
        self,
        parent=None,
        *,
        manager: ModelManager | None = None,
        active_pack_id: str = "",
        runtime_path: str = "",
        runtime_manager: RuntimeManager | None = None,
        ram_gb: float | None = None,
        runtime_resolver: Callable | None = None,
    ) -> None:
        super().__init__(parent)
        self.manager = manager or ModelManager()
        self.active_pack_id = str(active_pack_id or "")
        self.runtime_path = str(runtime_path or "")
        self._worker: QThread | None = None
        self._setup_target_pack_id = ""
        self.runtime_manager = runtime_manager or RuntimeManager()
        self.runtime_resolver = runtime_resolver or resolve_llama_server
        self.ram_gb = system_ram_gb() if ram_gb is None else max(0.0, float(ram_gb))
        self.setWindowTitle("Local AI Models")
        self.resize(820, 480)

        layout = QVBoxLayout(self)
        title = QLabel("Private local AI", self)
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(title)
        privacy = QLabel(
            "Prompts and research data stay on this computer. Only the selected "
            "public model file is downloaded; model files are SHA-256 verified.",
            self,
        )
        privacy.setWordWrap(True)
        layout.addWidget(privacy)

        self.hardware_label = QLabel(self)
        self.hardware_label.setWordWrap(True)
        layout.addWidget(self.hardware_label)

        self.table = QTableWidget(0, 4, self)
        self.table.setObjectName("AiModelTable")
        self.table.setHorizontalHeaderLabels(("Model", "Size", "Recommended RAM", "Status"))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        layout.addWidget(self.table, 1)

        self.license_label = QLabel(self)
        self.license_label.setOpenExternalLinks(True)
        self.license_label.setTextFormat(Qt.RichText)
        self.license_label.setWordWrap(True)
        layout.addWidget(self.license_label)

        self.progress = QProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.hide()
        layout.addWidget(self.progress)

        primary_actions = QHBoxLayout()
        self.setup_button = QPushButton("Install & use selected", self)
        self.download_button = QPushButton("Download & verify", self)
        self.runtime_button = QPushButton("Install AI runtime", self)
        self.import_button = QPushButton("Install offline pack…", self)
        self.export_button = QPushButton("Export offline pack…", self)
        self.folder_button = QPushButton("Open model folder", self)
        self.use_button = QPushButton("Use selected model", self)
        self.close_button = QPushButton("Close", self)
        primary_actions.addWidget(self.setup_button)
        primary_actions.addWidget(self.use_button)
        primary_actions.addStretch(1)
        layout.addLayout(primary_actions)

        component_actions = QHBoxLayout()
        component_actions.addWidget(self.download_button)
        component_actions.addWidget(self.runtime_button)
        component_actions.addWidget(self.import_button)
        component_actions.addStretch(1)
        layout.addLayout(component_actions)

        secondary_actions = QHBoxLayout()
        secondary_actions.addWidget(self.export_button)
        secondary_actions.addWidget(self.folder_button)
        secondary_actions.addStretch(1)
        secondary_actions.addWidget(self.close_button)
        layout.addLayout(secondary_actions)

        self.table.itemSelectionChanged.connect(self._sync_selection)
        self.setup_button.clicked.connect(self._install_and_use_selected)
        self.download_button.clicked.connect(self._download_selected)
        self.runtime_button.clicked.connect(self._download_runtime)
        self.import_button.clicked.connect(self._import_offline)
        self.export_button.clicked.connect(self._export_offline)
        self.folder_button.clicked.connect(self._open_folder)
        self.use_button.clicked.connect(self._use_selected)
        self.close_button.clicked.connect(self.reject)
        self._refresh_table()

    def selected_pack_id(self) -> str:
        row = self.table.currentRow()
        if row < 0:
            return ""
        item = self.table.item(row, 0)
        return str(item.data(Qt.UserRole) or "") if item else ""

    def _readiness(self, pack_id: str) -> AIReadiness:
        return inspect_bundled_ai(
            pack_id,
            self.runtime_path,
            manager=self.manager,
            runtime_manager=self.runtime_manager,
            ram_gb=self.ram_gb,
            runtime_resolver=self.runtime_resolver,
        )

    def _refresh_hardware_status(self) -> None:
        recommended = self.manager.recommended_pack(self.ram_gb)
        runtime_ready = self.runtime_manager.is_installed()
        runtime_text = "runtime ready" if runtime_ready else "runtime needs setup"
        self.hardware_label.setText(
            f"System RAM: {self.ram_gb:.1f} GB  ·  "
            f"Recommended: {recommended.display_name}  ·  {runtime_text}"
        )

    def _refresh_table(self) -> None:
        packs = self.manager.packs()
        current_id = self._setup_target_pack_id or self.selected_pack_id()
        self.table.setRowCount(len(packs))
        recommended_id = self.manager.recommended_pack(self.ram_gb).pack_id
        preferred_id = (
            self.active_pack_id
            if self.active_pack_id and self.manager.is_installed(self.active_pack_id)
            else current_id or recommended_id
        )
        selected_row = 0
        for row, pack in enumerate(packs):
            name = QTableWidgetItem(pack.display_name)
            name.setData(Qt.UserRole, pack.pack_id)
            self.table.setItem(row, 0, name)
            self.table.setItem(row, 1, QTableWidgetItem(f"{pack.size_bytes / 1024**2:.0f} MB"))
            self.table.setItem(row, 2, QTableWidgetItem(f"{pack.recommended_ram_gb:g} GB"))
            installed = self.manager.is_installed(pack.pack_id)
            preview = str(getattr(pack, "release_status", "preview")) != "release"
            status = "Installed · Preview" if preview else "Installed"
            readiness = self._readiness(pack.pack_id)
            if pack.pack_id == self.active_pack_id and readiness.ready:
                status = "Active · Preview" if preview else "Active"
            elif installed and readiness.state in {"runtime_missing", "unverified_runtime"}:
                status = "Installed · runtime needed"
            elif not installed:
                status = "Not installed"
            self.table.setItem(row, 3, QTableWidgetItem(status))
            if pack.pack_id == preferred_id:
                selected_row = row
        if packs:
            self.table.selectRow(selected_row)
        self._refresh_hardware_status()
        self._sync_selection()

    def _sync_selection(self) -> None:
        pack_id = self.selected_pack_id()
        if not pack_id:
            return
        pack = next(pack for pack in self.manager.packs() if pack.pack_id == pack_id)
        installed = self.manager.is_installed(pack_id)
        readiness = self._readiness(pack_id)
        idle = self._worker is None
        self.download_button.setEnabled(not installed and self._worker is None)
        self.export_button.setEnabled(installed and self._worker is None)
        self.use_button.setEnabled(readiness.ready and idle)
        self.setup_button.setEnabled(
            idle
            and readiness.state
            not in {"ready", "insufficient_memory", "unknown_model", "incompatible_model"}
        )
        if readiness.ready:
            self.setup_button.setText("Ready to use")
        elif readiness.state == "model_missing":
            self.setup_button.setText("Install model & use")
        elif readiness.state == "runtime_missing":
            self.setup_button.setText("Install runtime & use")
        elif readiness.state == "unverified_runtime":
            self.setup_button.setText("Replace runtime & use")
        else:
            self.setup_button.setText("Install & use selected")
        runtime_ready = self.runtime_manager.is_installed()
        self.runtime_button.setEnabled(not runtime_ready and idle)
        self.runtime_button.setText("Runtime ready" if runtime_ready else "Install AI runtime")
        self.license_label.setText(
            f'{pack.description} · License: <a href="{pack.license_url}">{pack.license_name}</a> · '
            f'<a href="{pack.source_url}">model card</a> · '
            f'Channel: {str(getattr(pack, "release_status", "preview")).title()}'
            f'<br>{readiness.detail}'
        )

    def _download_selected(self) -> None:
        pack_id = self.selected_pack_id()
        if not pack_id:
            return
        pack = next(pack for pack in self.manager.packs() if pack.pack_id == pack_id)
        answer = QMessageBox.question(
            self,
            "Download local AI model",
            f"Download {pack.display_name} ({pack.size_bytes / 1024**2:.0f} MB)?\n\n"
            f"Channel: {str(getattr(pack, 'release_status', 'preview')).title()}\n"
            f"License: {pack.license_name}\nSource: {pack.source_url}\n\n"
            "The model is allowed for commercial use under its own license. "
            "SciPlotter will verify its SHA-256 before installation.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._start_model_download(pack_id)

    def _start_model_download(self, pack_id: str) -> None:
        worker = _ModelDownloadThread(self.manager, pack_id, self)
        worker.progress_changed.connect(self._on_progress)
        worker.installed.connect(self._on_installed)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._worker_finished)
        self._worker = worker
        self._set_working(True)
        worker.start()

    def _download_runtime(self) -> None:
        package = self.runtime_manager.package
        answer = QMessageBox.question(
            self,
            "Install local AI runtime",
            f"Download the pinned llama.cpp {package.version} runtime "
            f"({package.size_bytes / 1024**2:.0f} MB)?\n\n"
            f"License: {package.license_name}\nSource: {package.source_url}\n\n"
            "The archive is SHA-256 verified and the server listens only on 127.0.0.1.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._start_runtime_download()

    def _start_runtime_download(self) -> None:
        worker = _RuntimeDownloadThread(self.runtime_manager, self)
        worker.progress_changed.connect(self._on_progress)
        worker.installed.connect(self._on_runtime_installed)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._worker_finished)
        self._worker = worker
        self._set_working(True)
        worker.start()

    def _install_and_use_selected(self) -> None:
        """Install every missing component in dependency order, then activate."""
        pack_id = self.selected_pack_id()
        if not pack_id or self._worker is not None:
            return
        readiness = self._readiness(pack_id)
        if readiness.ready:
            self.active_pack_id = pack_id
            self.accept()
            return
        if readiness.state in {"insufficient_memory", "incompatible_model", "unknown_model"}:
            QMessageBox.warning(self, "AI setup unavailable", readiness.detail)
            return

        pack = next(pack for pack in self.manager.packs() if pack.pack_id == pack_id)
        missing_size = 0
        components: list[str] = []
        if "runtime" in readiness.missing:
            missing_size += self.runtime_manager.package.size_bytes
            components.append(f"llama.cpp {self.runtime_manager.package.version}")
        if "model" in readiness.missing:
            missing_size += pack.size_bytes
            components.append(pack.display_name)
        answer = QMessageBox.question(
            self,
            "Set up private local AI",
            f"Install {' and '.join(components)} "
            f"({missing_size / 1024**2:.0f} MB total)?\n\n"
            f"Model channel: {readiness.release_status.title()}\n\n"
            "SciPlotter downloads only public AI components, verifies their "
            "pinned SHA-256 values, and runs inference on this computer.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._setup_target_pack_id = pack_id
        self._continue_setup()

    def _continue_setup(self) -> None:
        if self._worker is not None or not self._setup_target_pack_id:
            return
        readiness = self._readiness(self._setup_target_pack_id)
        if readiness.ready:
            self.active_pack_id = self._setup_target_pack_id
            self._setup_target_pack_id = ""
            self._refresh_table()
            self.accept()
        elif readiness.state in {
            "model_and_runtime_missing",
            "runtime_missing",
            "unverified_runtime",
        }:
            self._start_runtime_download()
        elif readiness.state == "model_missing":
            self._start_model_download(self._setup_target_pack_id)
        else:
            self._setup_target_pack_id = ""
            QMessageBox.critical(self, "AI setup could not continue", readiness.detail)

    def _import_offline(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Install offline AI model", "", "SciPlotter model (*.scimodel)"
        )
        if not path:
            return
        worker = _OfflineInstallThread(self.manager, path, self)
        worker.progress_changed.connect(self._on_progress)
        worker.installed.connect(self._on_installed)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._worker_finished)
        self._worker = worker
        self._set_working(True)
        worker.start()

    def _export_offline(self) -> None:
        pack_id = self.selected_pack_id()
        if not pack_id:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export offline AI model", f"{pack_id}.scimodel", "SciPlotter model (*.scimodel)"
        )
        if not path:
            return
        worker = _OfflineExportThread(self.manager, pack_id, path, self)
        worker.progress_changed.connect(self._on_progress)
        worker.exported.connect(self._on_exported)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._worker_finished)
        self._worker = worker
        self._set_working(True)
        worker.start()

    def _open_folder(self) -> None:
        self.manager.root.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.manager.root.resolve())))

    def _use_selected(self) -> None:
        pack_id = self.selected_pack_id()
        if self._readiness(pack_id).ready:
            self.active_pack_id = pack_id
            self._refresh_table()
            self.accept()

    def _set_working(self, working: bool) -> None:
        self.progress.setVisible(working)
        self.table.setEnabled(not working)
        self.import_button.setEnabled(not working)
        self.folder_button.setEnabled(not working)
        self.close_button.setText("Cancel" if working else "Close")
        if working:
            self.close_button.clicked.disconnect()
            self.close_button.clicked.connect(self._cancel_download)
        else:
            self.close_button.clicked.disconnect()
            self.close_button.clicked.connect(self.reject)
        self._sync_selection()

    def _cancel_download(self) -> None:
        self._setup_target_pack_id = ""
        if self._worker is not None:
            self._worker.cancel()

    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setValue(int(100 * done / max(1, total)))
        self.progress.setFormat(f"{done / 1024**2:.0f} / {total / 1024**2:.0f} MB")

    def _on_installed(self, pack_id: str) -> None:
        self._refresh_table()

    def _on_runtime_installed(self, path: str) -> None:
        self.runtime_path = path
        self._refresh_hardware_status()

    def _on_exported(self, path: str) -> None:
        QMessageBox.information(self, "Offline pack created", path)

    def _on_failed(self, message: str) -> None:
        self._setup_target_pack_id = ""
        if "cancel" not in message.casefold():
            QMessageBox.critical(self, "Local AI setup failed", message)

    def _worker_finished(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        self._set_working(False)
        self._refresh_table()
        if self._setup_target_pack_id:
            QTimer.singleShot(0, self._continue_setup)

    def reject(self) -> None:
        if self._worker is not None:
            self._setup_target_pack_id = ""
            self._worker.cancel()
            return
        self._setup_target_pack_id = ""
        super().reject()
