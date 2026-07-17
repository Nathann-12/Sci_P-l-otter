"""Model-pack UI for verified downloads and air-gapped installations."""
from __future__ import annotations

from threading import Event

from PySide6.QtCore import QThread, Qt, Signal
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ai.llama_cpp_client import resolve_llama_server
from ai.model_manager import ModelManager, system_ram_gb
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
    ) -> None:
        super().__init__(parent)
        self.manager = manager or ModelManager()
        self.active_pack_id = str(active_pack_id or "")
        self.runtime_path = str(runtime_path or "")
        self._worker: QThread | None = None
        self.runtime_manager = RuntimeManager()
        self.setWindowTitle("Local AI Models")
        self.resize(760, 430)

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

        ram = system_ram_gb()
        recommended = self.manager.recommended_pack(ram)
        runtime = resolve_llama_server(self.runtime_path)
        runtime_text = "runtime ready" if runtime else "llama.cpp runtime not found"
        self.hardware_label = QLabel(
            f"System RAM: {ram:.1f} GB  ·  Recommended: {recommended.display_name}  ·  {runtime_text}",
            self,
        )
        self.hardware_label.setWordWrap(True)
        layout.addWidget(self.hardware_label)

        self.table = QTableWidget(0, 4, self)
        self.table.setObjectName("AiModelTable")
        self.table.setHorizontalHeaderLabels(("Model", "Size", "Recommended RAM", "Status"))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        self.license_label = QLabel(self)
        self.license_label.setOpenExternalLinks(True)
        self.license_label.setTextFormat(Qt.RichText)
        layout.addWidget(self.license_label)

        self.progress = QProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.hide()
        layout.addWidget(self.progress)

        primary_actions = QHBoxLayout()
        self.download_button = QPushButton("Download & verify", self)
        self.runtime_button = QPushButton("Install AI runtime", self)
        self.import_button = QPushButton("Install offline pack…", self)
        self.export_button = QPushButton("Export offline pack…", self)
        self.folder_button = QPushButton("Open model folder", self)
        self.use_button = QPushButton("Use selected model", self)
        self.close_button = QPushButton("Close", self)
        for button in (
            self.download_button,
            self.runtime_button,
            self.import_button,
            self.export_button,
            self.folder_button,
            self.use_button,
        ):
            if button not in {self.export_button, self.folder_button}:
                primary_actions.addWidget(button)
        primary_actions.addStretch(1)
        layout.addLayout(primary_actions)
        secondary_actions = QHBoxLayout()
        secondary_actions.addWidget(self.export_button)
        secondary_actions.addWidget(self.folder_button)
        secondary_actions.addStretch(1)
        secondary_actions.addWidget(self.close_button)
        layout.addLayout(secondary_actions)

        self.table.itemSelectionChanged.connect(self._sync_selection)
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

    def _refresh_table(self) -> None:
        packs = self.manager.packs()
        self.table.setRowCount(len(packs))
        selected_row = 0
        for row, pack in enumerate(packs):
            name = QTableWidgetItem(pack.display_name)
            name.setData(Qt.UserRole, pack.pack_id)
            self.table.setItem(row, 0, name)
            self.table.setItem(row, 1, QTableWidgetItem(f"{pack.size_bytes / 1024**2:.0f} MB"))
            self.table.setItem(row, 2, QTableWidgetItem(f"{pack.recommended_ram_gb:g} GB"))
            installed = self.manager.is_installed(pack.pack_id)
            status = "Installed"
            if pack.pack_id == self.active_pack_id and installed:
                status = "Active"
            elif not installed:
                status = "Not installed"
            self.table.setItem(row, 3, QTableWidgetItem(status))
            if pack.pack_id == self.active_pack_id:
                selected_row = row
        self.table.resizeColumnsToContents()
        if packs:
            self.table.selectRow(selected_row)
        self._sync_selection()

    def _sync_selection(self) -> None:
        pack_id = self.selected_pack_id()
        if not pack_id:
            return
        pack = next(pack for pack in self.manager.packs() if pack.pack_id == pack_id)
        installed = self.manager.is_installed(pack_id)
        self.download_button.setEnabled(not installed and self._worker is None)
        self.export_button.setEnabled(installed and self._worker is None)
        self.use_button.setEnabled(installed and self._worker is None)
        runtime = resolve_llama_server(self.runtime_path)
        self.runtime_button.setEnabled(runtime is None and self._worker is None)
        self.runtime_button.setText("Runtime ready" if runtime else "Install AI runtime")
        self.license_label.setText(
            f'{pack.description} · License: <a href="{pack.license_url}">{pack.license_name}</a> · '
            f'<a href="{pack.source_url}">model card</a>'
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
            f"License: {pack.license_name}\nSource: {pack.source_url}\n\n"
            "The model is allowed for commercial use under its own license. "
            "SciPlotter will verify its SHA-256 before installation.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
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
        worker = _RuntimeDownloadThread(self.runtime_manager, self)
        worker.progress_changed.connect(self._on_progress)
        worker.installed.connect(self._on_runtime_installed)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._worker_finished)
        self._worker = worker
        self._set_working(True)
        worker.start()

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
        if self.manager.is_installed(pack_id):
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
        if self._worker is not None:
            self._worker.cancel()

    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setValue(int(100 * done / max(1, total)))
        self.progress.setFormat(f"{done / 1024**2:.0f} / {total / 1024**2:.0f} MB")

    def _on_installed(self, pack_id: str) -> None:
        self.active_pack_id = pack_id
        self._refresh_table()

    def _on_runtime_installed(self, path: str) -> None:
        self.runtime_path = path
        self.hardware_label.setText(
            self.hardware_label.text().replace("llama.cpp runtime not found", "runtime ready")
        )

    def _on_exported(self, path: str) -> None:
        QMessageBox.information(self, "Offline pack created", path)

    def _on_failed(self, message: str) -> None:
        if "cancel" not in message.casefold():
            QMessageBox.critical(self, "Model download failed", message)

    def _worker_finished(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        self._set_working(False)
        self._refresh_table()

    def reject(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            return
        super().reject()
