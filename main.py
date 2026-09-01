"""
main.py
-------
Grafische Oberfläche des Datei-Duplikatfinders, auf Basis von PySide6 (Qt) -
strukturell an den Datei-Umbenenner angelehnt (gleiche Bausteine aus
qt_widgets.py, gleiches Muster für Quellordner-Auswahl/Standardordner).

Die eigentliche Vergleichs-/Verschiebe-Logik ist unabhängig von der
Oberfläche in duplicate_engine.py.

Starten mit:  python3 main.py
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

import duplicate_engine as engine
from qt_widgets import FlowLayout, InfoIcon, TitledFrame

RECURSIVE_HELP = (
    "Bezieht beim Scannen auch alle Unterordner der gewählten Quelle(n) mit ein - "
    "abschalten, um wirklich nur die Dateien direkt im gewählten Ordner zu "
    "vergleichen (ohne dessen Unterordner)."
)

COMPARE_HELP = (
    "Zwei Dateien gelten als Duplikat, wenn sie exakt denselben Inhalt haben - "
    "geprüft über Dateigröße und einen SHA-256-Prüfsummen-Vergleich (nicht über "
    "den Dateinamen: 'Foto.jpg' und 'IMG_0231.jpg' mit identischem Inhalt werden "
    "erkannt). Innerhalb jeder Gruppe gilt die älteste Datei als Vorschlag fürs "
    "Original (Häkchen davor deshalb standardmäßig leer) - das lässt sich pro "
    "Datei per Häkchen anpassen."
)

COL_CHECK, COL_NAME, COL_FOLDER, COL_SIZE, COL_MODIFIED = range(5)


def _flow(parent_layout=None) -> QWidget:
    """Erzeugt ein Widget mit FlowLayout (umbrechende Zeile), hängt es
    optional direkt an ein übergeordnetes Layout und gibt es zurück."""
    row = QWidget()
    row.setLayout(FlowLayout())
    if parent_layout is not None:
        parent_layout.addWidget(row)
    return row


class DropZone(QFrame):
    """Fläche zum Hineinziehen von Dateien/Ordnern (Drag & Drop) - Klick
    öffnet alternativ den klassischen Ordner-Auswahldialog. Zeigt normalerweise
    einen Hinweistext an, nach Auswahl stattdessen eine Zusammenfassung der
    geladenen Quelle(n) (siehe set_summary)."""

    DEFAULT_TEXT = "📂 Ordner (oder Dateien) hierher ziehen  –  oder hier klicken zum Auswählen"

    def __init__(self, on_drop, on_click, parent=None):
        super().__init__(parent)
        self._on_drop = on_drop
        self._on_click = on_click
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumHeight(64)
        self.setStyleSheet(
            "DropZone { border: 2px dashed palette(mid); border-radius: 10px; }"
        )

        layout = QVBoxLayout(self)
        self.label = QLabel(self.DEFAULT_TEXT)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)

    def set_summary(self, text: str | None) -> None:
        self.label.setText(text if text else self.DEFAULT_TEXT)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self._on_drop(paths)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._on_click()


class ScanWorker(QThread):
    """Führt scan_for_duplicates() in einem Hintergrund-Thread aus, damit die
    Oberfläche bei großen Ordnern nicht einfriert. progress meldet den
    Fortschritt (siehe duplicate_engine.scan_for_duplicates), finished liefert
    die fertigen Gruppen."""

    progress = Signal(int, int, str)
    finished_ok = Signal(list)
    failed = Signal(str)

    def __init__(self, sources: list[Path], recursive: bool, parent=None):
        super().__init__(parent)
        self._sources = sources
        self._recursive = recursive

    def run(self):
        try:
            groups = engine.scan_for_duplicates(
                self._sources,
                recursive=self._recursive,
                progress_callback=lambda done, total, phase: self.progress.emit(done, total, phase),
            )
        except OSError as exc:
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(groups)


class DuplicateFinderApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Datei-Duplikatfinder")
        self.resize(900, 760)
        self.setMinimumSize(360, 300)

        # self.sources kann mehrere Ordner/Dateien enthalten (z.B. per Drag &
        # Drop mehrfach hereingezogen).
        self.sources: list[Path] = []
        self.groups: list[engine.DuplicateGroup] = []
        self._worker: ScanWorker | None = None

        self._build_ui()
        self._update_undo_button()
        self._load_default_folder_if_set()

    # ------------------------------------------------------------------
    # UI-Aufbau
    # ------------------------------------------------------------------
    def _build_ui(self):
        outer = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body_widget = QWidget()
        body = QVBoxLayout(body_widget)
        scroll.setWidget(body_widget)
        outer.addWidget(scroll, 1)

        self._build_source_section(body)
        self._build_result_section(body)

        hint = QLabel(
            "Tipp: Häkchen markiert eine Datei zum Verschieben - je Gruppe ist die älteste "
            "Datei standardmäßig abgewählt (Original). Verschobene Dateien landen im "
            "Unterordner 'Duplikate' der jeweiligen Quelle und lassen sich per "
            "'Verschieben rückgängig machen' wiederherstellen."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid);")
        body.addWidget(hint)

        bottom = _flow(outer)
        self.move_button = QPushButton("🗂 Ausgewählte in 'Duplikate'-Ordner verschieben")
        self.move_button.setEnabled(False)
        self.move_button.setToolTip("Verschiebt alle angehakten Dateien in einen 'Duplikate'-Unterordner ihrer jeweiligen Quelle.")
        self.move_button.clicked.connect(self.move_selected)
        bottom.layout().addWidget(self.move_button)
        self.undo_button = QPushButton("↺ Verschieben rückgängig machen")
        self.undo_button.setToolTip("Macht die zuletzt durchgeführte Verschiebe-Aktion wieder rückgängig.")
        self.undo_button.clicked.connect(self.undo_last)
        bottom.layout().addWidget(self.undo_button)

    def _build_source_section(self, body: QVBoxLayout) -> None:
        source_frame = TitledFrame("Quellordner")
        body.addWidget(source_frame)

        drop_row = QWidget()
        drop_row_layout = QHBoxLayout(drop_row)
        drop_row_layout.setContentsMargins(0, 0, 0, 0)
        self.drop_zone = DropZone(on_drop=self._load_paths, on_click=self.choose_folder)
        self.drop_zone.setToolTip("Ordner/Dateien hierher ziehen oder klicken, um sie über den Ordner-Auswahldialog zu laden.")
        drop_row_layout.addWidget(self.drop_zone, 1)

        button_stack = QVBoxLayout()
        button_stack.setSpacing(4)
        reset_selection_btn = QPushButton("↺")
        reset_selection_btn.setFixedWidth(36)
        reset_selection_btn.setToolTip(
            "Setzt die aktuelle Quellauswahl zurück. Ist bereits nichts geladen, wird "
            "stattdessen der feste Standardordner (sofern festgelegt) erneut geladen."
        )
        reset_selection_btn.clicked.connect(self._reset_source_selection)
        button_stack.addWidget(reset_selection_btn)
        set_default_btn = QPushButton("📌")
        set_default_btn.setFixedWidth(36)
        set_default_btn.setToolTip("Merkt sich den aktuell geladenen Ordner dauerhaft als Standard - wird künftig bei jedem App-Start automatisch geladen.")
        set_default_btn.clicked.connect(self._set_default_folder)
        button_stack.addWidget(set_default_btn)
        clear_default_btn = QPushButton("✕")
        clear_default_btn.setFixedWidth(36)
        clear_default_btn.setToolTip("Entfernt den festgelegten Standardordner - beim nächsten Start wird kein Ordner mehr automatisch geladen.")
        clear_default_btn.clicked.connect(self._clear_default_folder)
        button_stack.addWidget(clear_default_btn)
        button_stack.addStretch(1)
        drop_row_layout.addLayout(button_stack)
        source_frame.body_layout.addWidget(drop_row)

        self.default_folder_label = QLabel("Kein Standardordner festgelegt")
        self.default_folder_label.setWordWrap(True)
        source_frame.body_layout.addWidget(self.default_folder_label)
        self._refresh_default_folder_label()

        options_row = _flow(None)
        self.recursive_check = QCheckBox("Unterordner einbeziehen (rekursiv)")
        self.recursive_check.setChecked(engine.load_settings().get("recursive", True))
        self.recursive_check.toggled.connect(self._on_recursive_toggled)
        options_row.layout().addWidget(self.recursive_check)
        options_row.layout().addWidget(InfoIcon(RECURSIVE_HELP))
        options_row.layout().addWidget(InfoIcon(COMPARE_HELP, title="Vergleichskriterium"))
        source_frame.body_layout.addWidget(options_row)

        scan_row = _flow(None)
        self.scan_button = QPushButton("🔍 Auf Duplikate prüfen")
        self.scan_button.clicked.connect(self.start_scan)
        scan_row.layout().addWidget(self.scan_button)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedWidth(220)
        scan_row.layout().addWidget(self.progress_bar)
        self.status_label = QLabel("")
        scan_row.layout().addWidget(self.status_label)
        source_frame.body_layout.addWidget(scan_row)

    def _build_result_section(self, body: QVBoxLayout) -> None:
        result_frame = TitledFrame("Ergebnis")
        result_frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        body.addWidget(result_frame, 1)

        self.summary_label = QLabel("Noch nicht gescannt.")
        result_frame.body_layout.addWidget(self.summary_label)

        check_row = _flow(None)
        select_all_btn = QPushButton("☑ Alle auswählen")
        select_all_btn.setToolTip("Hakt alle gefundenen Duplikate an - sie werden dann beim Verschieben berücksichtigt.")
        select_all_btn.clicked.connect(lambda: self._set_all_checked(True))
        check_row.layout().addWidget(select_all_btn)
        select_none_btn = QPushButton("☐ Alle abwählen")
        select_none_btn.clicked.connect(lambda: self._set_all_checked(False))
        check_row.layout().addWidget(select_none_btn)
        reset_selection_btn = QPushButton("↺ Auswahl zurücksetzen (Original behalten)")
        reset_selection_btn.setToolTip("Stellt je Gruppe die Vorauswahl wieder her: älteste Datei abgewählt (Original), restliche angehakt.")
        reset_selection_btn.clicked.connect(self._reset_check_selection)
        check_row.layout().addWidget(reset_selection_btn)
        result_frame.body_layout.addWidget(check_row)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels(["", "Datei", "Ordner", "Größe", "Geändert am"])
        header = self.tree.header()
        header.setSectionResizeMode(COL_CHECK, QHeaderView.Fixed)
        header.setSectionResizeMode(COL_NAME, QHeaderView.Interactive)
        header.setSectionResizeMode(COL_FOLDER, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_SIZE, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_MODIFIED, QHeaderView.ResizeToContents)
        self.tree.setColumnWidth(COL_CHECK, 28)
        self.tree.setColumnWidth(COL_NAME, 220)
        self.tree.setMinimumHeight(260)
        self.tree.itemChanged.connect(self._on_item_changed)
        result_frame.body_layout.addWidget(self.tree)

    # ------------------------------------------------------------------
    # Quellordner
    # ------------------------------------------------------------------
    def choose_folder(self):
        chosen = QFileDialog.getExistingDirectory(self, "Ordner zum Prüfen auswählen")
        if not chosen:
            return
        self._load_paths([Path(chosen)])

    def _load_default_folder_if_set(self):
        folder = engine.load_settings().get("default_folder")
        if folder and Path(folder).is_dir():
            self._load_paths([Path(folder)])

    def _set_default_folder(self):
        if len(self.sources) != 1 or not self.sources[0].is_dir():
            QMessageBox.warning(
                self,
                "Kein eindeutiger Ordner",
                "Bitte zuerst genau einen Ordner laden (nicht mehrere/gemischte Quellen), "
                "um ihn als Standard festzulegen.",
            )
            return
        folder = self.sources[0]
        settings = engine.load_settings()
        settings["default_folder"] = str(folder)
        engine.save_settings(settings)
        self._refresh_default_folder_label()
        QMessageBox.information(self, "Gespeichert", f"'{folder}' wird künftig beim Start automatisch geladen.")

    def _clear_default_folder(self):
        settings = engine.load_settings()
        if "default_folder" in settings:
            del settings["default_folder"]
            engine.save_settings(settings)
        self._refresh_default_folder_label()

    def _refresh_default_folder_label(self):
        folder = engine.load_settings().get("default_folder")
        self.default_folder_label.setText(f"📌 {folder}" if folder else "Kein Standardordner festgelegt")

    def _reset_source_selection(self) -> None:
        if self.sources:
            self._load_paths([])
        else:
            self._load_default_folder_if_set()

    def _load_paths(self, paths: list[Path]) -> None:
        sources = [p for p in paths if p.exists()]
        self.sources = sources
        self.groups = []
        self._rebuild_tree()

        if len(sources) == 1:
            summary = str(sources[0])
        elif sources:
            summary = f"{len(sources)} Quellen ausgewählt"
        else:
            summary = None
        self.drop_zone.set_summary(summary)
        self.status_label.setText("")

    def _on_recursive_toggled(self, checked: bool) -> None:
        settings = engine.load_settings()
        settings["recursive"] = checked
        engine.save_settings(settings)

    # ------------------------------------------------------------------
    # Scan
    # ------------------------------------------------------------------
    def start_scan(self):
        if not self.sources:
            QMessageBox.information(self, "Kein Quellordner", "Bitte zuerst einen Ordner (oder Dateien) auswählen.")
            return
        if self._worker is not None:
            return

        self.scan_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # unbestimmt, solange die Dateiliste noch nicht feststeht
        self.status_label.setText("Durchsuche Quelle(n) …")

        self._worker = ScanWorker(list(self.sources), self.recursive_check.isChecked(), self)
        self._worker.progress.connect(self._on_scan_progress)
        self._worker.finished_ok.connect(self._on_scan_finished)
        self._worker.failed.connect(self._on_scan_failed)
        self._worker.start()

    def _on_scan_progress(self, done: int, total: int, phase: str) -> None:
        label = "Teil-Prüfsummen" if phase == "partial" else "Volle Prüfsummen"
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(done)
            self.status_label.setText(f"{label}: {done}/{total} …")
        else:
            self.status_label.setText(f"{label} …")

    def _on_scan_finished(self, groups: list) -> None:
        self.groups = groups
        self._worker = None
        self.scan_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        self._rebuild_tree()

        if not groups:
            self.status_label.setText("Fertig - keine Duplikate gefunden.")
        else:
            total_files = sum(len(g.files) for g in groups)
            wasted = sum(g.wasted_bytes for g in groups)
            self.status_label.setText(
                f"Fertig - {len(groups)} Gruppe(n), {total_files} Datei(en), "
                f"{engine.format_size(wasted)} einsparbar."
            )

    def _on_scan_failed(self, message: str) -> None:
        self._worker = None
        self.scan_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Fehler beim Scannen.")
        QMessageBox.warning(
            self, "Kein Zugriff",
            "Beim Durchsuchen ist ein Fehler aufgetreten (evtl. fehlende Berechtigung "
            "unter Systemeinstellungen → Datenschutz & Sicherheit → "
            f"Festplattenvollzugriff):\n\n{message}",
        )

    # ------------------------------------------------------------------
    # Ergebnis-Tabelle
    # ------------------------------------------------------------------
    def _rebuild_tree(self) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()

        for i, group in enumerate(self.groups, start=1):
            group_item = QTreeWidgetItem([
                f"Gruppe {i} — {len(group.files)} Dateien — {engine.format_size(group.wasted_bytes)} einsparbar",
                "", "", "", "",
            ])
            bold = QFont()
            bold.setBold(True)
            group_item.setFont(0, bold)
            group_item.setFlags(group_item.flags() & ~Qt.ItemIsUserCheckable)
            self.tree.addTopLevelItem(group_item)
            group_item.setFirstColumnSpanned(True)

            for idx, entry in enumerate(group.files):
                is_original = idx == 0  # älteste Datei = Original-Vorschlag
                child = QTreeWidgetItem([
                    "",
                    entry.path.name + ("  🟢 Original" if is_original else ""),
                    str(entry.path.parent),
                    engine.format_size(entry.size),
                    _format_mtime(entry.mtime),
                ])
                child.setData(COL_CHECK, Qt.UserRole, str(entry.path))
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                child.setCheckState(COL_CHECK, Qt.Unchecked if is_original else Qt.Checked)
                if is_original:
                    child.setToolTip(COL_NAME, "Wird als Original vorgeschlagen (älteste Datei der Gruppe) - abwählbar/anders wählbar.")
                group_item.addChild(child)

            group_item.setExpanded(True)

        self.tree.blockSignals(False)
        self._update_move_button()

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column == COL_CHECK:
            self._update_move_button()

    def _iter_child_items(self):
        for i in range(self.tree.topLevelItemCount()):
            group_item = self.tree.topLevelItem(i)
            for j in range(group_item.childCount()):
                yield group_item.child(j)

    def _set_all_checked(self, checked: bool) -> None:
        self.tree.blockSignals(True)
        for child in self._iter_child_items():
            child.setCheckState(COL_CHECK, Qt.Checked if checked else Qt.Unchecked)
        self.tree.blockSignals(False)
        self._update_move_button()

    def _reset_check_selection(self) -> None:
        self._rebuild_tree()

    def _checked_paths(self) -> list[Path]:
        return [
            Path(child.data(COL_CHECK, Qt.UserRole))
            for child in self._iter_child_items()
            if child.checkState(COL_CHECK) == Qt.Checked
        ]

    def _update_move_button(self) -> None:
        self.move_button.setEnabled(bool(self._checked_paths()))

    # ------------------------------------------------------------------
    # Verschieben / Rückgängig
    # ------------------------------------------------------------------
    def move_selected(self) -> None:
        paths = self._checked_paths()
        if not paths:
            return
        total_size = sum(p.stat().st_size for p in paths if p.exists())
        reply = QMessageBox.question(
            self, "Duplikate verschieben",
            f"{len(paths)} Datei(en) ({engine.format_size(total_size)}) in den jeweiligen "
            "'Duplikate'-Unterordner verschieben?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            performed = engine.move_to_duplicates_folder(paths, self.sources)
        except OSError as exc:
            QMessageBox.warning(self, "Fehler beim Verschieben", str(exc))
            performed = []

        self._update_undo_button()
        self.status_label.setText(f"{len(performed)} Datei(en) verschoben.")
        # Betroffene Quellen neu einlesen, damit die Tabelle wieder dem
        # tatsächlichen Zustand auf der Festplatte entspricht.
        self._load_paths(self.sources)

    def undo_last(self) -> None:
        ok, errors = engine.undo_last_move()
        self._update_undo_button()
        if errors:
            QMessageBox.warning(
                self, "Teilweise rückgängig gemacht",
                f"{ok} Datei(en) wiederhergestellt, bei {len(errors)} gab es ein Problem:\n\n"
                + "\n".join(errors),
            )
        elif ok:
            QMessageBox.information(self, "Rückgängig gemacht", f"{ok} Datei(en) wiederhergestellt.")
        if self.sources:
            self._load_paths(self.sources)

    def _update_undo_button(self) -> None:
        self.undo_button.setEnabled(engine.has_undo())


def _format_mtime(timestamp: float) -> str:
    from datetime import datetime
    return datetime.fromtimestamp(timestamp).strftime("%d.%m.%Y %H:%M")


def main():
    app = QApplication([])
    window = DuplicateFinderApp()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
