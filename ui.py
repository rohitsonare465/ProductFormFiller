"""PyQt6 user interface for Product Form Filler."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QObject, QThread, Qt, pyqtSlot
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSpinBox,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from csv_loader import CsvLoadResult, load_product_csv, row_to_form_values
from filler import FAST_PROFILE, NORMAL_PROFILE, FillStatus, FormFillerWorker, timing_profile_to_delays
from settings import (
    LOG_PATH,
    AppSettings,
    append_fill_log,
    load_progress,
    load_settings,
    save_progress,
    save_settings,
)


DARK_STYLESHEET = """
QWidget { background: #16181d; color: #f2f4f8; font-size: 13px; }
QGroupBox { border: 1px solid #343946; border-radius: 8px; margin-top: 10px; padding: 10px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QPushButton { background: #2b303b; border: 1px solid #4b5567; border-radius: 6px; padding: 7px 10px; }
QPushButton:hover { background: #363d4a; }
QPushButton:disabled { color: #7b8494; background: #20242c; }
QSpinBox, QTableView { background: #20242c; border: 1px solid #3a4050; border-radius: 6px; }
QHeaderView::section { background: #2b303b; color: #f2f4f8; padding: 5px; border: 0; }
QProgressBar { border: 1px solid #3a4050; border-radius: 6px; text-align: center; background: #20242c; }
QProgressBar::chunk { background: #4f8cff; border-radius: 5px; }
"""


class PandasTableModel(QAbstractTableModel):
    def __init__(self, dataframe: pd.DataFrame | None = None) -> None:
        super().__init__()
        self._dataframe = dataframe if dataframe is not None else pd.DataFrame()

    def set_dataframe(self, dataframe: pd.DataFrame) -> None:
        self.beginResetModel()
        self._dataframe = dataframe
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._dataframe.index)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._dataframe.columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> str | None:
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        return str(self._dataframe.iat[index.row(), index.column()])

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> str | int | None:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return str(self._dataframe.columns[section])
        return section + 1


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings: AppSettings = load_settings()
        self.csv_result: CsvLoadResult | None = None
        self.table_model = PandasTableModel()
        self.worker: FormFillerWorker | None = None
        self.worker_thread: QThread | None = None

        self.setWindowTitle("Product Form Filler")
        self.resize(1280, 760)

        self._build_ui()
        self._connect_actions()
        self._apply_dark_mode(self.settings.dark_mode)
        self._restore_last_csv()
        self._update_controls()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.worker is not None:
            self.worker.stop()
        self._persist_settings()
        super().closeEvent(event)

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        self.status_label = QLabel("Load a CSV to begin.")
        self.file_label = QLabel("No CSV loaded")
        self.file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        top_group = QGroupBox("CSV")
        top_layout = QGridLayout(top_group)
        self.load_button = QPushButton("Load CSV")
        self.export_log_button = QPushButton("Show Log Location")
        self.dark_mode_checkbox = QCheckBox("Dark Mode")
        self.dark_mode_checkbox.setChecked(self.settings.dark_mode)
        top_layout.addWidget(self.load_button, 0, 0)
        top_layout.addWidget(self.export_log_button, 0, 1)
        top_layout.addWidget(self.dark_mode_checkbox, 0, 2)
        top_layout.addWidget(QLabel("File:"), 1, 0)
        top_layout.addWidget(self.file_label, 1, 1, 1, 2)

        row_group = QGroupBox("Row")
        row_layout = QGridLayout(row_group)
        self.row_selector = QSpinBox()
        self.row_selector.setMinimum(1)
        self.row_selector.setMaximum(1)
        self.prev_button = QPushButton("Previous Row")
        self.next_button = QPushButton("Next Row")
        self.goto_button = QPushButton("Go To Row")
        self.auto_advance_checkbox = QCheckBox("Auto Advance")
        self.auto_advance_checkbox.setChecked(self.settings.auto_advance)
        row_layout.addWidget(QLabel("Selected row"), 0, 0)
        row_layout.addWidget(self.row_selector, 0, 1)
        row_layout.addWidget(self.goto_button, 0, 2)
        row_layout.addWidget(self.prev_button, 0, 3)
        row_layout.addWidget(self.next_button, 0, 4)
        row_layout.addWidget(self.auto_advance_checkbox, 0, 5)

        fill_group = QGroupBox("Filling")
        fill_layout = QGridLayout(fill_group)
        self.fill_button = QPushButton("Fill Current Form")
        self.pause_button = QPushButton("Pause")
        self.resume_button = QPushButton("Resume")
        self.stop_button = QPushButton("Stop")
        self.profile_combo = QComboBox()
        self.profile_combo.addItem("Normal Mode (4-5 min)", NORMAL_PROFILE)
        self.profile_combo.addItem("Fast Mode (3-3.5 min)", FAST_PROFILE)
        profile_index = self.profile_combo.findData(self.settings.typing_profile)
        self.profile_combo.setCurrentIndex(max(0, profile_index))
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 41)
        self.progress_bar.setValue(0)
        fill_layout.addWidget(self.fill_button, 0, 0)
        fill_layout.addWidget(self.pause_button, 0, 1)
        fill_layout.addWidget(self.resume_button, 0, 2)
        fill_layout.addWidget(self.stop_button, 0, 3)
        fill_layout.addWidget(QLabel("Typing Profile"), 1, 0)
        fill_layout.addWidget(self.profile_combo, 1, 1, 1, 3)
        fill_layout.addWidget(self.progress_bar, 2, 0, 1, 4)

        self.table = QTableView()
        self.table.setModel(self.table_model)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        root.addWidget(top_group)
        root.addWidget(row_group)
        root.addWidget(fill_group)
        root.addWidget(self.status_label)
        root.addWidget(self.table, 1)
        self.setCentralWidget(central)

        self.open_log_action = QAction("Open Log Folder", self)
        self.menuBar().addAction(self.open_log_action)

    def _connect_actions(self) -> None:
        self.load_button.clicked.connect(self._choose_csv)
        self.prev_button.clicked.connect(self._previous_row)
        self.next_button.clicked.connect(self._next_row)
        self.goto_button.clicked.connect(self._go_to_row)
        self.fill_button.clicked.connect(self._fill_current_form)
        self.pause_button.clicked.connect(self._pause_fill)
        self.resume_button.clicked.connect(self._resume_fill)
        self.stop_button.clicked.connect(self._stop_fill)
        self.profile_combo.currentIndexChanged.connect(self._typing_profile_changed)
        self.auto_advance_checkbox.toggled.connect(self._auto_advance_changed)
        self.dark_mode_checkbox.toggled.connect(self._dark_mode_changed)
        self.export_log_button.clicked.connect(self._show_log_location)
        self.open_log_action.triggered.connect(self._show_log_location)

    def _restore_last_csv(self) -> None:
        progress = load_progress()
        last_csv = self.settings.last_csv_path or str(progress.get("csv_path", ""))
        if not last_csv:
            return
        path = Path(last_csv)
        if path.exists():
            self._load_csv(path, silent=True)
            last_completed = int(progress.get("last_completed_row", self.settings.last_completed_row))
            if self.csv_result and last_completed + 1 < len(self.csv_result.dataframe.index):
                self.row_selector.setValue(last_completed + 2)

    @pyqtSlot()
    def _choose_csv(self) -> None:
        start_dir = str(Path(self.settings.last_csv_path).parent) if self.settings.last_csv_path else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Load product CSV", start_dir, "CSV Files (*.csv)")
        if path:
            self._load_csv(Path(path), silent=False)

    def _load_csv(self, path: Path, silent: bool) -> None:
        try:
            result = load_product_csv(path)
        except Exception as exc:  # noqa: BLE001 - user-facing error.
            if not silent:
                QMessageBox.critical(self, "CSV Load Failed", str(exc))
            return

        self.csv_result = result
        self.settings.last_csv_path = str(result.path)
        self.file_label.setText(str(result.path))

        if not result.is_valid:
            self.table_model.set_dataframe(result.dataframe)
            self.status_label.setText("CSV is missing required columns.")
            self._update_controls()
            QMessageBox.critical(
                self,
                "Missing CSV Columns",
                "The CSV is missing required columns:\n\n" + "\n".join(result.missing_columns),
            )
            return

        self.table_model.set_dataframe(result.dataframe)
        self.row_selector.setMaximum(max(1, len(result.dataframe.index)))
        self.row_selector.setValue(1)
        self.progress_bar.setRange(0, 41)
        self.progress_bar.setValue(0)

        extras = f" Extra columns ignored: {', '.join(result.extra_columns)}" if result.extra_columns else ""
        self.status_label.setText(f"Loaded {len(result.dataframe.index)} rows.{extras}")
        self._persist_settings()
        self._update_controls()

    @pyqtSlot()
    def _previous_row(self) -> None:
        self.row_selector.setValue(max(1, self.row_selector.value() - 1))
        self._go_to_row()

    @pyqtSlot()
    def _next_row(self) -> None:
        self.row_selector.setValue(min(self.row_selector.maximum(), self.row_selector.value() + 1))
        self._go_to_row()

    @pyqtSlot()
    def _go_to_row(self) -> None:
        row = self.row_selector.value() - 1
        self.table.selectRow(row)
        self.table.scrollTo(self.table_model.index(row, 0))
        self.status_label.setText(f"Selected row {row + 1}. Click the SKU field in Chrome before filling.")

    @pyqtSlot()
    def _fill_current_form(self) -> None:
        if self.csv_result is None or not self.csv_result.is_valid:
            QMessageBox.warning(self, "No Valid CSV", "Load a valid CSV before filling.")
            return
        if self.worker is not None:
            QMessageBox.information(self, "Fill In Progress", "A fill operation is already running.")
            return

        row_index = self.row_selector.value() - 1
        try:
            values = row_to_form_values(self.csv_result.dataframe, row_index)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Row Error", str(exc))
            return

        response = QMessageBox.question(
            self,
            "Ready To Fill",
            "After clicking Yes, manually focus Chrome and click inside the SKU field.\n\n"
            "The app will type all fields and press Tab between fields only. It will not press Enter or submit.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if response != QMessageBox.StandardButton.Yes:
            return

        self.progress_bar.setRange(0, len(values))
        self.progress_bar.setValue(0)
        self.worker_thread = QThread(self)
        self.worker = FormFillerWorker(
            values=values,
            delays=timing_profile_to_delays(str(self.profile_combo.currentData())),
            startup_delay=5.0,
        )
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._fill_progress)
        self.worker.field_started.connect(self._field_started)
        self.worker.paused_changed.connect(self._paused_changed)
        self.worker.finished.connect(self._fill_finished)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self._thread_finished)
        self.worker_thread.start()
        self.status_label.setText("Filling starts in 5 seconds. Focus Chrome and click the SKU field now.")
        self._update_controls()

    @pyqtSlot()
    def _pause_fill(self) -> None:
        if self.worker:
            self.worker.pause()

    @pyqtSlot()
    def _resume_fill(self) -> None:
        if self.worker:
            self.worker.resume()

    @pyqtSlot()
    def _stop_fill(self) -> None:
        if self.worker:
            self.worker.stop()
            self.status_label.setText("Stopping after the current safe typing step.")

    @pyqtSlot(int, int, str)
    def _fill_progress(self, completed: int, total: int, form_field: str) -> None:
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(completed)
        self.status_label.setText(f"Filled {completed}/{total}: {form_field}")

    @pyqtSlot(int, str)
    def _field_started(self, index: int, form_field: str) -> None:
        self.status_label.setText(f"Typing field {index + 1}: {form_field}")

    @pyqtSlot(bool)
    def _paused_changed(self, paused: bool) -> None:
        self.status_label.setText("Paused." if paused else "Resumed.")
        self._update_controls()

    @pyqtSlot(str, str)
    def _fill_finished(self, status: str, message: str) -> None:
        if self.csv_result is None:
            return
        row_index = self.row_selector.value() - 1
        if status == FillStatus.COMPLETED.value:
            sku = str(self.csv_result.dataframe.iloc[row_index].get("SKU", ""))
            self.settings.last_completed_row = row_index
            save_progress(str(self.csv_result.path), row_index)
            append_fill_log(str(self.csv_result.path), row_index, sku)
            if self.auto_advance_checkbox.isChecked() and row_index + 1 < len(self.csv_result.dataframe.index):
                self.row_selector.setValue(row_index + 2)
                self.table.selectRow(row_index + 1)
                self.table.scrollTo(self.table_model.index(row_index + 1, 0))
                self.status_label.setText(
                    f"Completed row {row_index + 1}. Stopped after Barcode. "
                    f"Review and submit manually. Row {row_index + 2} is selected."
                )
            else:
                self.status_label.setText(
                    f"Completed row {row_index + 1}. Stopped after Barcode. Review and submit manually."
                )
        elif status == FillStatus.STOPPED.value:
            self.status_label.setText(message)
        else:
            QMessageBox.critical(self, "Fill Failed", message)
            self.status_label.setText("Fill failed.")
        self._persist_settings()

    @pyqtSlot()
    def _thread_finished(self) -> None:
        if self.worker_thread:
            self.worker_thread.deleteLater()
        self.worker = None
        self.worker_thread = None
        self._update_controls()

    @pyqtSlot(int)
    def _typing_profile_changed(self, _index: int) -> None:
        self.settings.typing_profile = str(self.profile_combo.currentData())
        profile_name = self.profile_combo.currentText()
        self.status_label.setText(f"Selected {profile_name}. Timing remains randomized.")
        self._persist_settings()

    @pyqtSlot(bool)
    def _auto_advance_changed(self, checked: bool) -> None:
        self.settings.auto_advance = checked
        self._persist_settings()

    @pyqtSlot(bool)
    def _dark_mode_changed(self, checked: bool) -> None:
        self.settings.dark_mode = checked
        self._apply_dark_mode(checked)
        self._persist_settings()

    def _apply_dark_mode(self, enabled: bool) -> None:
        QApplication.instance().setStyleSheet(DARK_STYLESHEET if enabled else "")

    @pyqtSlot()
    def _show_log_location(self) -> None:
        QMessageBox.information(
            self,
            "Log File",
            f"Filled row history is saved here:\n\n{LOG_PATH}",
        )

    def _update_controls(self) -> None:
        has_valid_csv = self.csv_result is not None and self.csv_result.is_valid
        is_running = self.worker is not None
        self.fill_button.setEnabled(has_valid_csv and not is_running)
        self.prev_button.setEnabled(has_valid_csv and not is_running)
        self.next_button.setEnabled(has_valid_csv and not is_running)
        self.goto_button.setEnabled(has_valid_csv and not is_running)
        self.row_selector.setEnabled(has_valid_csv and not is_running)
        self.load_button.setEnabled(not is_running)
        self.profile_combo.setEnabled(not is_running)
        self.pause_button.setEnabled(is_running)
        self.resume_button.setEnabled(is_running)
        self.stop_button.setEnabled(is_running)

    def _persist_settings(self) -> None:
        save_settings(self.settings)
