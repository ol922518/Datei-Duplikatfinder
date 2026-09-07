"""
main.py
-------
Grafische Oberfläche des Datei-Duplikatfinders, auf Basis von PySide6 (Qt) -
strukturell an den Datei-Umbenenner angelehnt (gleiche Bausteine aus dem
geteilten qt_app_kit-Paket, gleiches Muster für Quellordner-Auswahl/
Standardordner).

Die eigentliche Vergleichs-/Verschiebe-Logik ist unabhängig von der
Oberfläche in duplicate_engine.py.

Starten mit:  python3 main.py
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
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
import translations
from document_viewer import DocumentViewer
from qt_app_kit.i18n import get_language, set_language, t
from qt_app_kit.qt_widgets import InfoIcon, ResizableSplitFrame, TitledFrame, TwoColumnFrame, flow_row
from qt_app_kit.result_dialogs import show_partial_result


# Als Funktionen statt Modul-Konstanten, da sie übersetzten Text enthalten
# (t()) - zum Zeitpunkt des Modul-Imports ist die Sprache
# (translations.init(), siehe __main__ unten) noch nicht gesetzt.
def _recursive_help() -> str:
    return t("main_recursive_help")


def _compare_help() -> str:
    return t("main_compare_help")


def _target_folder_help() -> str:
    return t("main_target_folder_help")


def _similar_help() -> str:
    return t("main_similar_help")


COL_CHECK, COL_NAME, COL_FOLDER, COL_SIZE, COL_MODIFIED = range(5)


class DropZone(QFrame):
    """Fläche zum Hineinziehen von Dateien/Ordnern (Drag & Drop) - Klick
    öffnet alternativ den klassischen Ordner-Auswahldialog. Zeigt normalerweise
    einen Hinweistext an, nach Auswahl stattdessen eine Zusammenfassung der
    geladenen Quelle(n) (siehe set_summary)."""

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
        self.label = QLabel(t("main_dropzone_default_text"))
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)

    def set_summary(self, text: str | None) -> None:
        self.label.setText(text if text else t("main_dropzone_default_text"))

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


# Dieselbe Datei, in die "Datei-Duplikatfinder.app"/"App öffnen.command"
# bereits Fehler beim Start umleiten (siehe Launcher-Skript im
# App-Bundle) - unabhängig davon, wie main.py gerade gestartet wurde
# (Bundle, .command-Skript oder direkt "python3 main.py"), landet ein
# unerwarteter Scan-Fehler damit immer an derselben, bekannten Stelle.
CRASH_LOG_FILE = Path(__file__).resolve().parent / ".app_launch.log"


def _log_unexpected_error(exc: Exception) -> None:
    """Hängt einen vollständigen Traceback an CRASH_LOG_FILE an - siehe
    ScanWorker.run(). Schlägt auch das fehl (z.B. Ordner nicht
    schreibbar), bleibt nur die (deutlich knappere) Dialogmeldung übrig,
    kein weiterer Absturz."""
    import traceback
    from datetime import datetime

    try:
        with CRASH_LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(f"\n--- {datetime.now().isoformat(timespec='seconds')} ---\n")
            f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    except OSError:
        pass


class ScanWorker(QThread):
    """Führt die Duplikat-Suche in einem Hintergrund-Thread aus, damit die
    Oberfläche bei großen Ordnern nicht einfriert. Erst exakte Duplikate
    (siehe duplicate_engine.find_exact_duplicates), optional anschließend
    ähnliche Bilder unter den übrig gebliebenen Dateien (siehe
    duplicate_engine.scan_for_similar_images) - so entstehen keine
    doppelten Gruppen für bereits exakt erkannte Dateien. progress meldet
    den Fortschritt, finished_ok liefert die fertigen Gruppen (exakte zuerst)."""

    progress = Signal(int, int, str)
    finished_ok = Signal(list)
    # (Meldung, unerwartet) - unerwartet=True bei jedem Fehler außer OSError
    # (siehe run()), main.py zeigt dafür eine andere Dialog-Variante.
    failed = Signal(str, bool)

    def __init__(self, sources: list[Path], recursive: bool, find_similar: bool,
                 target_folder: Path | None, parent=None):
        super().__init__(parent)
        self._sources = sources
        self._recursive = recursive
        self._find_similar = find_similar
        self._target_folder = target_folder

    def run(self):
        try:
            # Ein gesetzter zentraler Zielordner wird vom Scan ausgeschlossen -
            # sonst könnten dort bereits verschobene Duplikate bei einem
            # erneuten Scan wieder als (weitere) Quelle mitgezählt werden,
            # falls er innerhalb einer der Quellen liegt.
            exclude = {self._target_folder} if self._target_folder is not None else None
            files = engine.collect_files(self._sources, recursive=self._recursive, exclude_dirs=exclude)
            exact_groups = engine.find_exact_duplicates(
                files,
                progress_callback=lambda done, total, phase: self.progress.emit(done, total, phase),
            )
            groups = list(exact_groups)
            if self._find_similar and engine.PILLOW_AVAILABLE:
                # Nur die "zu verschiebenden" Dateien einer exakten Gruppe
                # ausschließen (Index 0 = Original bleibt teilnahmeberechtigt) -
                # sonst würde z.B. eine verkleinerte/neu komprimierte Kopie
                # keinen Vergleichspartner mehr finden, nur weil ihr exaktes
                # Gegenstück bereits (unter anderem Namen) exakt gruppiert wurde.
                already_grouped = {entry.path for g in exact_groups for entry in g.files[1:]}
                remaining = [f for f in files if f not in already_grouped]
                similar_groups = engine.scan_for_similar_images(
                    remaining,
                    progress_callback=lambda done, total, phase: self.progress.emit(done, total, phase),
                )
                groups += similar_groups
        except OSError as exc:
            self.failed.emit(str(exc), False)
            return
        except Exception as exc:
            # Jeder andere Fehlertyp (z.B. ein Programmierfehler) wurde bisher
            # gar nicht abgefangen - der Hintergrund-Thread starb lautlos,
            # die Oberfläche bemerkte das nie (Button blieb dauerhaft
            # deaktiviert, Fortschrittsbalken blieb stehen, keinerlei
            # Fehlermeldung - siehe Bug-Report 07.09.2026, dort war die
            # eigentliche Ursache zwar keine Exception, sondern eine sehr
            # langsame Schleife, aber die Frage "würde ich einen echten
            # Fehler überhaupt bemerken" war berechtigt - jetzt ja).
            # Vollständiger Traceback zusätzlich protokolliert.
            _log_unexpected_error(exc)
            self.failed.emit(f"{type(exc).__name__}: {exc}", True)
            return
        self.finished_ok.emit(groups)


class DuplicateFinderApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(t("main_window_title"))
        self.resize(900, 760)
        self.setMinimumSize(360, 300)

        # self.sources kann mehrere Ordner/Dateien enthalten (z.B. per Drag &
        # Drop mehrfach hereingezogen).
        self.sources: list[Path] = []
        self.groups: list[engine.DuplicateGroup] = []
        self._worker: ScanWorker | None = None
        # Pfad der aktuell im Viewer gezeigten Datei - damit _rebuild_tree()
        # die Vorschau nur dann leert, wenn genau diese Datei betroffen war
        # (verschoben/gelöscht), statt sie bei jedem Neuaufbau grundsätzlich
        # zu verwerfen (siehe _remove_paths_from_results()).
        self._current_preview_path: Path | None = None

        self._build_ui()
        self._update_undo_button()
        self._load_default_folder_if_set()

    # ------------------------------------------------------------------
    # UI-Aufbau
    # ------------------------------------------------------------------
    def _build_ui(self):
        outer = QVBoxLayout(self)

        # --- Sprachumschalter (oben rechts, außerhalb des scrollbaren
        # Bereichs) - wirkt erst nach einem Neustart, siehe
        # _on_language_switch_clicked() und ROADMAP.md "Sprachumschaltung
        # Deutsch/Englisch". Bewusst eine eigene QHBoxLayout-Zeile statt
        # flow_row() - FlowLayout (siehe qt_widgets.py) kennt kein
        # addStretch(), das für die Rechtsbündigkeit hier gebraucht wird.
        language_row = QWidget()
        language_row_layout = QHBoxLayout(language_row)
        language_row_layout.setContentsMargins(0, 0, 0, 0)
        language_row_layout.addStretch(1)
        language_btn = QPushButton(t("language_switch_button"))
        language_btn.setToolTip(t("language_switch_tooltip"))
        language_btn.clicked.connect(self._on_language_switch_clicked)
        language_row_layout.addWidget(language_btn)
        outer.addWidget(language_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body_widget = QWidget()
        body = QVBoxLayout(body_widget)
        scroll.setWidget(body_widget)
        outer.addWidget(scroll, 1)

        # Reihe 1 (Einstellungen): zwei Spalten - Quellordner (Drop-Zone)
        # links, Optionen (Häkchen + Scan-Button) rechts - wie beim
        # Datei-Umbenenner. TwoColumnFrame bricht bei schmalem Fenster
        # automatisch in eine gestapelte Einzelspalte um.
        top_split = TwoColumnFrame(min_width_left=260, min_width_right=380, left_stretch=1, right_stretch=2)
        body.addWidget(top_split)
        self._build_source_section(top_split.left)
        self._build_options_section(top_split.right)

        # Reihe 2 (Ergebnis): volle Breite, wächst mit der Fensterhöhe.
        self._build_result_section(body)

        hint = QLabel(t("main_hint_text"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid);")
        body.addWidget(hint)

        bottom = flow_row(outer)
        self.move_button = QPushButton(t("main_move_button"))
        self.move_button.setEnabled(False)
        self.move_button.setToolTip(t("main_move_tooltip"))
        self.move_button.clicked.connect(self.move_selected)
        bottom.layout().addWidget(self.move_button)
        self.undo_button = QPushButton(t("main_undo_button"))
        self.undo_button.setToolTip(t("main_undo_tooltip"))
        self.undo_button.clicked.connect(self.undo_last)
        bottom.layout().addWidget(self.undo_button)
        # Löscht dieselbe Häkchen-Auswahl wie "Verschieben" oben, nur in den
        # Papierkorb statt in den 'Duplikate'-Ordner - unabhängig von der
        # per Maus markierten Auswahl unten ("🗑 Markierte Zeilen löschen",
        # siehe _delete_selected()). Zwei bewusst getrennte Auswahlen für
        # zwei unterschiedliche Zwecke (siehe dortiger Kommentar).
        self.delete_checked_btn = QPushButton(t("main_delete_checked_button"))
        self.delete_checked_btn.setEnabled(False)
        self.delete_checked_btn.setToolTip(t("main_delete_checked_tooltip"))
        self.delete_checked_btn.clicked.connect(self._delete_checked)
        if not engine.HAS_SEND2TRASH:
            self.delete_checked_btn.setEnabled(False)
            self.delete_checked_btn.setToolTip(t("main_delete_unavailable_tooltip"))
        bottom.layout().addWidget(self.delete_checked_btn)

    def _build_source_section(self, container: QWidget) -> None:
        """Linke Spalte von Reihe 1: Quellordner (Drop-Zone mit Buttons,
        darunter kompakt der feste Standardordner). Wächst vertikal mit
        (QSizePolicy.Expanding), damit sie sich an der Höhe der - meist
        etwas höheren - Optionen-Box daneben ausrichtet."""
        self.source_frame = TitledFrame(t("main_source_frame_title"))
        self.source_frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        container.layout().addWidget(self.source_frame)

        drop_row = QWidget()
        drop_row_layout = QHBoxLayout(drop_row)
        drop_row_layout.setContentsMargins(0, 0, 0, 0)
        self.drop_zone = DropZone(on_drop=self._load_paths, on_click=self.choose_folder)
        self.drop_zone.setToolTip(t("main_dropzone_tooltip"))
        drop_row_layout.addWidget(self.drop_zone, 1)

        button_stack = QVBoxLayout()
        button_stack.setSpacing(4)
        reset_selection_btn = QPushButton("↺")
        reset_selection_btn.setFixedWidth(36)
        reset_selection_btn.setToolTip(t("main_reset_source_tooltip"))
        reset_selection_btn.clicked.connect(self._reset_source_selection)
        button_stack.addWidget(reset_selection_btn)
        set_default_btn = QPushButton("📌")
        set_default_btn.setFixedWidth(36)
        set_default_btn.setToolTip(t("main_set_default_tooltip"))
        set_default_btn.clicked.connect(self._set_default_folder)
        button_stack.addWidget(set_default_btn)
        clear_default_btn = QPushButton("✕")
        clear_default_btn.setFixedWidth(36)
        clear_default_btn.setToolTip(t("main_clear_default_tooltip"))
        clear_default_btn.clicked.connect(self._clear_default_folder)
        button_stack.addWidget(clear_default_btn)
        button_stack.addStretch(1)
        drop_row_layout.addLayout(button_stack)
        self.source_frame.body_layout.addWidget(drop_row)

        self.default_folder_label = QLabel(t("main_no_default_folder"))
        self.default_folder_label.setWordWrap(True)
        self.source_frame.body_layout.addWidget(self.default_folder_label)
        self._refresh_default_folder_label()

    def _build_options_section(self, container: QWidget) -> None:
        """Rechte Spalte von Reihe 1: Optionen (Unterordner/Ähnliche Bilder
        mit je einem Info-Symbol) und darunter der Scan-Button mit
        Fortschrittsanzeige - alle in derselben Box. Wächst vertikal mit
        (QSizePolicy.Expanding), damit sich Quellordner und Optionen immer
        an der Höhe der jeweils größeren Box ausrichten."""
        options_frame = TitledFrame(t("main_options_frame_title"))
        options_frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        container.layout().addWidget(options_frame)

        options_row = flow_row(None)
        self.recursive_check = QCheckBox(t("main_recursive_check"))
        self.recursive_check.setChecked(engine.load_settings().get("recursive", True))
        self.recursive_check.toggled.connect(self._on_recursive_toggled)
        options_row.layout().addWidget(self.recursive_check)
        options_row.layout().addWidget(InfoIcon(_recursive_help()))
        options_row.layout().addWidget(InfoIcon(_compare_help(), title=t("main_compare_help_title")))
        options_frame.body_layout.addWidget(options_row)

        similar_row = flow_row(None)
        self.similar_check = QCheckBox(t("main_similar_check"))
        self.similar_check.setChecked(engine.load_settings().get("find_similar", False))
        self.similar_check.toggled.connect(self._on_similar_toggled)
        similar_row.layout().addWidget(self.similar_check)
        similar_row.layout().addWidget(InfoIcon(_similar_help(), title=t("main_similar_help_title")))
        if not engine.PILLOW_AVAILABLE:
            missing_label = QLabel(t("main_pillow_missing"))
            missing_label.setStyleSheet("color: palette(mid);")
            similar_row.layout().addWidget(missing_label)
        options_frame.body_layout.addWidget(similar_row)

        target_row = flow_row(None)
        self.target_folder_label = QLabel()
        self.target_folder_label.setWordWrap(True)
        target_row.layout().addWidget(self.target_folder_label)
        choose_target_btn = QPushButton(t("main_choose_target_button"))
        choose_target_btn.setToolTip(t("main_choose_target_tooltip"))
        choose_target_btn.clicked.connect(self._choose_target_folder)
        target_row.layout().addWidget(choose_target_btn)
        reset_target_btn = QPushButton(t("main_reset_target_button"))
        reset_target_btn.setToolTip(t("main_reset_target_tooltip"))
        reset_target_btn.clicked.connect(self._reset_target_folder)
        target_row.layout().addWidget(reset_target_btn)
        target_row.layout().addWidget(InfoIcon(_target_folder_help(), title=t("main_target_folder_help_title")))
        options_frame.body_layout.addWidget(target_row)
        self._refresh_target_folder_label()

    def _build_result_section(self, body: QVBoxLayout) -> None:
        result_frame = TitledFrame(t("main_result_frame_title"))
        result_frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        body.addWidget(result_frame, 1)

        # Scan-Button + Fortschritt oben in der Ergebnis-Box statt in den
        # Optionen - an der Stelle, wo vorher dauerhaft "Noch nicht
        # gescannt." stand (der Text war nie aktualisiert worden).
        scan_row = flow_row(None)
        self.scan_button = QPushButton(t("main_scan_button"))
        self.scan_button.clicked.connect(self.start_scan)
        scan_row.layout().addWidget(self.scan_button)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedWidth(220)
        scan_row.layout().addWidget(self.progress_bar)
        self.status_label = QLabel("")
        scan_row.layout().addWidget(self.status_label)
        result_frame.body_layout.addWidget(scan_row)

        check_row = flow_row(None)
        select_all_btn = QPushButton(t("main_select_all_button"))
        select_all_btn.setToolTip(t("main_select_all_tooltip"))
        select_all_btn.clicked.connect(lambda: self._set_all_checked(True))
        check_row.layout().addWidget(select_all_btn)
        select_none_btn = QPushButton(t("main_select_none_button"))
        select_none_btn.clicked.connect(lambda: self._set_all_checked(False))
        check_row.layout().addWidget(select_none_btn)
        reset_selection_btn = QPushButton(t("main_reset_check_button"))
        reset_selection_btn.setToolTip(t("main_reset_check_tooltip"))
        reset_selection_btn.clicked.connect(self._reset_check_selection)
        check_row.layout().addWidget(reset_selection_btn)
        result_frame.body_layout.addWidget(check_row)

        # Baumansicht links, Datei-Viewer rechts - per Maus verschiebbarer
        # Trenner (ResizableSplitFrame, wie beim Datei-Umbenenner), der bei
        # schmalem Fenster automatisch auf untereinander umschaltet.
        result_split = ResizableSplitFrame(min_width_left=260, min_width_right=380, left_stretch=1, right_stretch=2)
        result_frame.body_layout.addWidget(result_split, 1)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels([
            "", t("main_col_name"), t("main_col_folder"), t("main_col_size"), t("main_col_modified"),
        ])
        header = self.tree.header()
        header.setSectionResizeMode(COL_CHECK, QHeaderView.Fixed)
        header.setSectionResizeMode(COL_NAME, QHeaderView.Interactive)
        # "Ordner" ebenfalls per Maus verschiebbar (Interactive statt
        # Stretch) - Stretch-Spalten lassen sich in Qt nicht von Hand
        # verschieben. "Geändert am" (letzte Spalte) übernimmt stattdessen
        # per setStretchLastSection() das Auffüllen des restlichen Platzes.
        header.setSectionResizeMode(COL_FOLDER, QHeaderView.Interactive)
        header.setSectionResizeMode(COL_SIZE, QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        self.tree.setColumnWidth(COL_CHECK, 34)  # echtes QCheckBox-Widget braucht mehr Rand als eine reine Indikatorspalte
        self.tree.setColumnWidth(COL_NAME, 220)
        self.tree.setColumnWidth(COL_FOLDER, 260)
        self.tree.setMinimumHeight(260)
        # Dateizeilen sind eigene Top-Level-Elemente statt echter Kinder
        # ihrer Gruppenzeile (siehe _rebuild_tree()) - keine Einrück-Pfeile
        # nötig, die fette Gruppenzeile trennt optisch trotzdem klar genug.
        self.tree.setRootIsDecorated(False)
        # Mehrfachauswahl per Maus (Shift-Klick zusammenhängend, Cmd-Klick
        # einzeln) - unabhängig vom Häkchen zum Verschieben, siehe
        # "🗑 Markierte Zeilen löschen" unten.
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.currentItemChanged.connect(self._on_current_item_changed)
        result_split.left.layout().addWidget(self.tree)

        # Eigene Zeile unterhalb des Baums, bewusst getrennt von "Alle
        # auswählen"/"Alle abwählen" oben (die beziehen sich auf das Häkchen
        # zum Verschieben) - hier geht es um die per Maus MARKIERTEN Zeilen,
        # eine eigene, unabhängige Auswahl. Identisch zum Datei-Umbenenner.
        delete_row = flow_row(result_split.left.layout())
        self.delete_selected_btn = QPushButton(t("main_delete_selected_button"))
        self.delete_selected_btn.setToolTip(t("main_delete_selected_tooltip"))
        self.delete_selected_btn.clicked.connect(self._delete_selected)
        if not engine.HAS_SEND2TRASH:
            self.delete_selected_btn.setEnabled(False)
            self.delete_selected_btn.setToolTip(t("main_delete_unavailable_tooltip"))
        delete_row.layout().addWidget(self.delete_selected_btn)
        self.reveal_btn = QPushButton(t("main_reveal_button"))
        self.reveal_btn.setToolTip(t("main_reveal_tooltip"))
        self.reveal_btn.clicked.connect(self._reveal_current_in_finder)
        delete_row.layout().addWidget(self.reveal_btn)

        self.viewer = DocumentViewer()
        self.viewer.setMinimumWidth(220)
        result_split.right.layout().addWidget(self.viewer)

    # ------------------------------------------------------------------
    # Quellordner
    # ------------------------------------------------------------------
    def choose_folder(self):
        chosen = QFileDialog.getExistingDirectory(self, t("main_choose_folder_dialog_title"))
        if not chosen:
            return
        self._load_paths([Path(chosen)])

    def _on_language_switch_clicked(self):
        """Wechselt zwischen Deutsch und Englisch und speichert die Wahl
        dauerhaft (settings["language"], siehe engine.load_settings()/
        save_settings()) - wirkt gemäß Grundgerüst-Entscheidung (siehe
        file_renamer/ROADMAP.md "Sprachumschaltung Deutsch/Englisch") erst
        nach einem Neustart der App, statt alle Texte live neu zu setzen."""
        new_language = "en" if get_language() == "de" else "de"
        set_language(new_language)
        settings = engine.load_settings()
        settings["language"] = new_language
        engine.save_settings(settings)
        QMessageBox.information(
            self, t("language_switch_restart_title"), t("language_switch_restart_text")
        )

    def _load_default_folder_if_set(self):
        folder = engine.load_settings().get("default_folder")
        if folder and Path(folder).is_dir():
            self._load_paths([Path(folder)])

    def _set_default_folder(self):
        if len(self.sources) != 1 or not self.sources[0].is_dir():
            QMessageBox.warning(
                self,
                t("main_no_unique_folder_title"),
                t("main_no_unique_folder_text"),
            )
            return
        folder = self.sources[0]
        settings = engine.load_settings()
        settings["default_folder"] = str(folder)
        engine.save_settings(settings)
        self._refresh_default_folder_label()
        QMessageBox.information(
            self, t("main_default_folder_saved_title"),
            t("main_default_folder_saved_text").format(folder=folder),
        )

    def _clear_default_folder(self):
        settings = engine.load_settings()
        if "default_folder" in settings:
            del settings["default_folder"]
            engine.save_settings(settings)
        self._refresh_default_folder_label()

    def _refresh_default_folder_label(self):
        folder = engine.load_settings().get("default_folder")
        self.default_folder_label.setText(f"📌 {folder}" if folder else t("main_no_default_folder"))

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
            summary = t("main_summary_multiple_sources").format(count=len(sources))
        else:
            summary = None
        self.drop_zone.set_summary(summary)
        self.status_label.setText("")

    def _on_recursive_toggled(self, checked: bool) -> None:
        settings = engine.load_settings()
        settings["recursive"] = checked
        engine.save_settings(settings)

    def _on_similar_toggled(self, checked: bool) -> None:
        settings = engine.load_settings()
        settings["find_similar"] = checked
        engine.save_settings(settings)

    def _target_folder(self) -> Path | None:
        """Der aktuell konfigurierte zentrale Zielordner - None, wenn keiner
        gesetzt ist (Standard: 'Duplikate'-Unterordner je Quelle)."""
        folder = engine.load_settings().get("target_folder")
        return Path(folder) if folder else None

    def _choose_target_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, t("main_choose_target_dialog_title"))
        if not chosen:
            return
        settings = engine.load_settings()
        settings["target_folder"] = chosen
        engine.save_settings(settings)
        self._refresh_target_folder_label()

    def _reset_target_folder(self) -> None:
        settings = engine.load_settings()
        if "target_folder" in settings:
            del settings["target_folder"]
            engine.save_settings(settings)
        self._refresh_target_folder_label()

    def _refresh_target_folder_label(self) -> None:
        folder = self._target_folder()
        if folder:
            self.target_folder_label.setText(t("main_target_folder_set").format(folder=folder))
        else:
            self.target_folder_label.setText(t("main_target_folder_default"))

    # ------------------------------------------------------------------
    # Scan
    # ------------------------------------------------------------------
    def start_scan(self):
        if not self.sources:
            QMessageBox.information(self, t("main_no_source_title"), t("main_no_source_text"))
            return
        if self._worker is not None:
            return

        find_similar = self.similar_check.isChecked()
        if find_similar and not engine.PILLOW_AVAILABLE:
            QMessageBox.warning(
                self, t("main_missing_package_title"), t("main_missing_package_text"),
            )
            find_similar = False

        self.scan_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # unbestimmt, solange die Dateiliste noch nicht feststeht
        self.status_label.setText(t("main_scanning_status"))

        self._worker = ScanWorker(
            list(self.sources), self.recursive_check.isChecked(), find_similar, self._target_folder(), self,
        )
        self._worker.progress.connect(self._on_scan_progress)
        self._worker.finished_ok.connect(self._on_scan_finished)
        self._worker.failed.connect(self._on_scan_failed)
        self._worker.start()

    def _on_scan_progress(self, done: int, total: int, phase: str) -> None:
        labels = {
            "partial": t("main_progress_partial"),
            "full": t("main_progress_full"),
            "phash": t("main_progress_phash"),
        }
        label = labels.get(phase, phase)
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(done)
            self.status_label.setText(t("main_progress_with_total").format(label=label, done=done, total=total))
        else:
            self.status_label.setText(t("main_progress_no_total").format(label=label))

    def _on_scan_finished(self, groups: list) -> None:
        self.groups = groups
        self._worker = None
        self.scan_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        self._rebuild_tree()

        if not groups:
            self.status_label.setText(t("main_scan_done_none"))
        else:
            total_files = sum(len(g.files) for g in groups)
            wasted = sum(g.wasted_bytes for g in groups)
            n_similar = sum(1 for g in groups if g.kind == "similar")
            n_exact = len(groups) - n_similar
            breakdown = t("main_count_exact").format(count=n_exact) + (
                t("main_count_similar_suffix").format(count=n_similar) if n_similar else ""
            )
            self.status_label.setText(
                t("main_scan_done_summary").format(
                    groups=len(groups), breakdown=breakdown, files=total_files,
                    wasted=engine.format_size(wasted),
                )
            )

    def _on_scan_failed(self, message: str, unexpected: bool) -> None:
        self._worker = None
        self.scan_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText(t("main_scan_failed_status"))
        if unexpected:
            # Jeder Fehler außer OSError (siehe ScanWorker.run()) - bisher
            # gab es dafür GAR KEINE Rückmeldung, der Scan-Button blieb
            # einfach dauerhaft deaktiviert, ohne dass die Oberfläche
            # erkennen ließ, ob noch gerechnet wird oder etwas schiefging.
            QMessageBox.critical(
                self, t("main_unexpected_error_title"),
                t("main_unexpected_error_text").format(message=message),
            )
        else:
            QMessageBox.warning(
                self, t("main_no_access_title"), t("main_no_access_text").format(message=message),
            )

    # ------------------------------------------------------------------
    # Ergebnis-Tabelle
    # ------------------------------------------------------------------
    def _rebuild_tree(self, preserve_checks: bool = False) -> None:
        """Baut den Ergebnisbaum aus self.groups neu auf. `preserve_checks`
        (True nur bei _remove_paths_from_results()) übernimmt die zuvor
        gesetzten Häkchen unveränderter Dateien statt sie auf den Standard
        zurückzusetzen - sonst würde z.B. das Löschen einer markierten Datei
        in Gruppe A auch ein bewusst abgewähltes Häkchen in der ganz
        unbeteiligten Gruppe B stillschweigend wieder anhaken (die
        Baum-Elemente werden bei jedem Neuaufbau komplett neu erzeugt, die
        alten Checkbox-Widgets samt ihrem Zustand gehen sonst verloren).
        Das zuvor gesetzte Häkchen wird dabei NUR übernommen, wenn die Datei
        auch ihre Original/Duplikat-Rolle behält - schrumpft eine Gruppe so,
        dass eine andere Datei zum neuen Original wird, bekommt sie den für
        Originale üblichen (abgewählten) Standard statt ihres alten,
        Duplikat-typischen Häkchens (das sie sonst fälschlich weiter zum
        Verschieben/Löschen vorgemerkt ließe, obwohl die Oberfläche sie
        gerade erst als Original vorschlägt)."""
        previous_checks: dict[str, tuple[bool, bool]] = {}
        if preserve_checks:
            for child in self._iter_child_items():
                path_str = child.data(COL_CHECK, Qt.UserRole)
                checkbox = self.tree.itemWidget(child, COL_CHECK)
                if path_str and checkbox is not None:
                    was_original = bool(child.data(COL_CHECK, Qt.UserRole + 1))
                    previous_checks[path_str] = (checkbox.isChecked(), was_original)

        self.tree.blockSignals(True)
        # Verhindert, dass Qt bei jedem einzelnen addTopLevelItem() unten
        # sofort neu zeichnet/layoutet (siehe Kommentar bei
        # self.tree.addTopLevelItems() weiter unten - der eigentliche Fix
        # ist das gebündelte Einfügen, dies hier nur zusätzliche
        # Absicherung).
        self.tree.setUpdatesEnabled(False)
        self.tree.clear()
        # Ist der zuvor gemerkte Vorschau-Pfad nicht mehr gültig (Datei
        # verschoben/gelöscht), auch das Tracking selbst zurücksetzen -
        # sonst hält die App eine "Auswahl" fest, die im Viewer längst
        # nicht mehr sichtbar ist (z.B. "📂 Ablageort öffnen" meldete dann
        # fälschlich "existiert nicht mehr" statt "keine Auswahl").
        if self._current_preview_path is not None and not self._current_preview_path.exists():
            self._current_preview_path = None
        if self._current_preview_path is None:
            self.viewer.clear()

        # Alle Zeilen werden zunächst nur als Python-Objekte gesammelt
        # (all_items) und ERST GANZ AM ENDE in einem einzigen Aufruf
        # eingefügt (siehe addTopLevelItems() unten) - nicht sofort per
        # addTopLevelItem() in dieser Schleife. Grund (Bug-Report
        # 07.09.2026, per Live-Stack-Sample bestätigt): jeder einzelne
        # addTopLevelItem()-Aufruf löst in Qt eine komplette Neuberechnung
        # des gesamten Baum-Layouts aus (inkl. Text-Shaping aller
        # sichtbaren Zeilen, sichtbar im Profil als
        # QTreeView::updateGeometries() -> QTextEngine::shapeText()) - bei
        # wenigen hundert Zeilen unmerklich, bei mehreren tausend (z.B.
        # 1695 gescannte Dateien) ein mehrminütiges Einfrieren der
        # Oberfläche OHNE Fehlermeldung, da rein rechnerisch, nicht
        # abgestürzt. Checkbox-Widgets (brauchen eine bereits im Baum
        # hängende Zeile) werden deshalb ebenfalls erst in einem zweiten
        # Durchlauf NACH dem Batch-Insert gesetzt.
        all_items: list[QTreeWidgetItem] = []
        group_items: list[QTreeWidgetItem] = []
        pending_checkboxes: list[tuple[QTreeWidgetItem, bool, str]] = []

        exact_i = 0
        similar_i = 0
        for group in self.groups:
            if group.kind == "similar":
                similar_i += 1
                label = (
                    t("main_similar_group_label").format(index=similar_i, count=len(group.files))
                    + (t("main_similarity_suffix").format(percent=round(group.similarity * 100)) if group.similarity is not None else "")
                    + t("main_wasted_suffix").format(wasted=engine.format_size(group.wasted_bytes))
                )
                original_tooltip = t("main_original_tooltip_similar")
                original_badge = t("main_original_badge_similar")
            else:
                exact_i += 1
                label = (
                    t("main_exact_group_label").format(index=exact_i, count=len(group.files))
                    + t("main_wasted_suffix").format(wasted=engine.format_size(group.wasted_bytes))
                )
                original_tooltip = t("main_original_tooltip_exact")
                original_badge = t("main_original_badge_exact")

            group_item = QTreeWidgetItem([label, "", "", "", ""])
            bold = QFont()
            bold.setBold(True)
            group_item.setFont(0, bold)
            all_items.append(group_item)
            group_items.append(group_item)

            for idx, entry in enumerate(group.files):
                is_original = idx == 0  # Index 0 = Original-Vorschlag (siehe DuplicateGroup-Sortierkonvention)
                # Badge (Original/Beste Qualität) vorangestellt statt
                # angehängt - so bleibt er unabhängig von der Länge des
                # Dateinamens immer an derselben Stelle erkennbar.
                child = QTreeWidgetItem([
                    "",
                    (original_badge if is_original else "") + entry.path.name,
                    str(entry.path.parent),
                    engine.format_size(entry.size),
                    _format_mtime(entry.mtime),
                ])
                child.setData(COL_CHECK, Qt.UserRole, str(entry.path))
                child.setData(COL_CHECK, Qt.UserRole + 1, is_original)
                if is_original:
                    child.setToolTip(COL_NAME, original_tooltip)
                # Als eigenes Top-Level-Element statt group_item.addChild():
                # QTreeWidget positioniert bei echten Kind-Elementen per
                # setItemWidget() gesetzte Checkbox-Widgets nachweislich
                # falsch (immer bei (0,0) statt in der jeweiligen Zeile -
                # reproduzierbar per Pixelvergleich, unabhängig von Stil/
                # Palette). Als Geschwister-Element klappt es einwandfrei.
                # setRootIsDecorated(False) blendet dafür die (bei echten
                # Kindern üblichen) Einrückung/den Pfeil aus, die fette
                # Gruppenzeile bleibt trotzdem als optische Trennung sichtbar.
                # Einfügen ins Baum-Widget selbst passiert gebündelt weiter
                # unten (siehe addTopLevelItems()), hier nur sammeln.
                all_items.append(child)
                pending_checkboxes.append((child, is_original, str(entry.path)))

        # Einziger Einfüge-Aufruf für den gesamten Baum (Gruppenzeilen +
        # Dateizeilen zusammen) statt eines addTopLevelItem()-Aufrufs pro
        # Zeile - siehe Kommentar oben, das ist der eigentliche Performance-
        # Fix.
        self.tree.addTopLevelItems(all_items)
        for group_item in group_items:
            group_item.setFirstColumnSpanned(True)

        # Echtes QCheckBox-Widget statt der eingebauten Baum-Häkchen
        # (Qt.ItemIsUserCheckable/setCheckState) - die werden von
        # QTreeWidget unter dem hier nötigen Fusion-Stil (siehe
        # _dark_fusion_palette) nachweislich nicht sichtbar gezeichnet (bei
        # QTableWidget tritt derselbe Fehler nicht auf - per Pixelvergleich
        # verifiziert). Muss NACH dem Einfügen ins Baum-Widget gesetzt
        # werden (siehe addTopLevelItems() oben). setChecked() vor dem
        # Verbinden von toggled(), damit der Aufbau selbst kein Signal
        # auslöst.
        for child, is_original, path_str in pending_checkboxes:
            checkbox = QCheckBox()
            prev = previous_checks.get(path_str)
            if prev is not None and prev[1] == is_original:
                checkbox.setChecked(prev[0])
            else:
                # Kein vorheriger Zustand bekannt, oder die Rolle
                # (Original/Duplikat) hat sich seit dem letzten Aufbau
                # geändert - dann gilt der rollenabhängige Standard, nicht
                # das alte Häkchen (siehe Docstring oben).
                checkbox.setChecked(not is_original)
            checkbox.toggled.connect(self._update_move_button)
            self.tree.setItemWidget(child, COL_CHECK, checkbox)

        self.tree.setUpdatesEnabled(True)
        self.tree.blockSignals(False)
        self._update_move_button()

    def _on_current_item_changed(self, current: QTreeWidgetItem | None, previous: QTreeWidgetItem | None) -> None:
        """Zeigt die zur aktuell ausgewählten Zeile gehörende Datei im
        Viewer-Panel an (siehe DocumentViewer) - Gruppenzeilen selbst haben
        keinen Dateipfad und leeren den Viewer stattdessen."""
        if current is None:
            self._current_preview_path = None
            self.viewer.clear()
            return
        path_str = current.data(COL_CHECK, Qt.UserRole)
        if not path_str:
            self._current_preview_path = None
            self.viewer.clear()
            return
        self._current_preview_path = Path(path_str)
        self.viewer.show_file(self._current_preview_path)

    def _reveal_current_in_finder(self) -> None:
        """Öffnet den Finder am Ort der aktuell in der Vorschau gezeigten
        Datei und markiert sie dort (macOS: 'open -R')."""
        if self._current_preview_path is None:
            QMessageBox.information(self, t("main_no_selection_title"), t("main_reveal_no_selection_text"))
            return
        if not self._current_preview_path.exists():
            QMessageBox.warning(
                self, t("main_not_found_title"),
                t("main_not_found_text").format(name=self._current_preview_path.name),
            )
            return
        subprocess.run(["open", "-R", str(self._current_preview_path)])

    def _iter_child_items(self):
        """Liefert alle Datei-Zeilen (nicht die fetten Gruppenzeilen dazwischen)
        - beide sind gleichrangige Top-Level-Elemente (siehe _rebuild_tree()),
        Dateizeilen aber immer mit Pfad in COL_CHECK/Qt.UserRole, Gruppenzeilen nie."""
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.data(COL_CHECK, Qt.UserRole):
                yield item

    def _set_all_checked(self, checked: bool) -> None:
        for child in self._iter_child_items():
            checkbox = self.tree.itemWidget(child, COL_CHECK)
            if checkbox is not None:
                checkbox.setChecked(checked)
        self._update_move_button()

    def _reset_check_selection(self) -> None:
        self._rebuild_tree()

    def _checked_paths(self) -> list[Path]:
        paths = []
        for child in self._iter_child_items():
            checkbox = self.tree.itemWidget(child, COL_CHECK)
            if checkbox is not None and checkbox.isChecked():
                paths.append(Path(child.data(COL_CHECK, Qt.UserRole)))
        return paths

    def _update_move_button(self) -> None:
        has_checked = bool(self._checked_paths())
        self.move_button.setEnabled(has_checked)
        self.delete_checked_btn.setEnabled(has_checked and engine.HAS_SEND2TRASH)

    # ------------------------------------------------------------------
    # Verschieben / Rückgängig
    # ------------------------------------------------------------------
    def move_selected(self) -> None:
        paths = self._checked_paths()
        if not paths:
            return
        target_folder = self._target_folder()
        destination = f"'{target_folder}'" if target_folder else t("main_default_destination")
        total_size = sum(p.stat().st_size for p in paths if p.exists())
        reply = QMessageBox.question(
            self, t("main_confirm_move_title"),
            t("main_confirm_move_text").format(
                count=len(paths), size=engine.format_size(total_size), destination=destination,
            ),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # move_to_duplicates_folder() versucht jede Datei einzeln - eine
        # fehlgeschlagene Datei verwirft nicht mehr die bereits erfolgreich
        # verschobenen (die bleiben protokolliert/nachvollziehbar).
        performed, errors = engine.move_to_duplicates_folder(paths, self.sources, target_folder=target_folder)

        self._update_undo_button()
        show_partial_result(
            self, len(performed), t("main_verb_moved"), errors, total=len(paths),
            on_success=lambda: self.status_label.setText(t("main_move_success_status").format(count=len(performed))),
        )
        # Nur die tatsächlich verschobenen Dateien aus den Gruppen entfernen,
        # statt den ganzen Scan zu verwerfen - der Rest der Ergebnisse (und
        # die Vorschau, falls nicht betroffen) bleibt so erhalten.
        self._remove_paths_from_results({Path(old) for old, _new in performed})

    def undo_last(self) -> None:
        ok, errors = engine.undo_last_move()
        self._update_undo_button()
        if errors:
            QMessageBox.warning(
                self, t("main_partial_undo_title"),
                t("main_partial_undo_text").format(count=ok, errors=len(errors)) + "\n".join(errors),
            )
        elif ok:
            QMessageBox.information(self, t("main_undo_done_title"), t("main_undo_done_text").format(count=ok))
        if self.sources:
            self._load_paths(self.sources)

    def _update_undo_button(self) -> None:
        self.undo_button.setEnabled(engine.has_undo())

    def _delete_selected(self) -> None:
        """Verschiebt die per Maus im Baum markierten Dateien in den
        Papierkorb (Button "🗑 Markierte Zeilen löschen") - unabhängig vom
        Häkchen zum Verschieben, das eine andere, unabhängige Auswahl ist.
        Gruppenzeilen selbst haben keinen Dateipfad und werden ignoriert,
        falls mitmarkiert. Identisch zum Datei-Umbenenner übernommen."""
        paths = []
        for item in self.tree.selectedItems():
            path_str = item.data(COL_CHECK, Qt.UserRole)
            if path_str:
                paths.append(Path(path_str))
        if not paths:
            QMessageBox.information(self, t("main_no_selection_title"), t("main_no_selection_text"))
            return

        names = "\n".join(p.name for p in paths[:10])
        if len(paths) > 10:
            names += t("main_more_files_suffix").format(count=len(paths) - 10)
        if QMessageBox.question(
            self, t("main_confirm_trash_title"),
            t("main_confirm_trash_text").format(count=len(paths), names=names),
        ) != QMessageBox.Yes:
            return

        count, errors = engine.move_to_trash(paths)
        show_partial_result(self, count, t("main_verb_trashed"), errors)

        # Nur die tatsächlich gelöschten Dateien aus den Gruppen entfernen
        # (an ihrer Nicht-mehr-Existenz erkennbar - bei Fehlern bleibt eine
        # Datei ja an ihrem Platz), statt den ganzen Scan zu verwerfen.
        self._remove_paths_from_results({p for p in paths if not p.exists()})

    def _delete_checked(self) -> None:
        """Verschiebt die per Häkchen angehakten Dateien in den Papierkorb
        (Button "🗑 Angehakte löschen") - dieselbe Auswahl wie beim
        Verschieben-Button ("🗂 Ausgewählte in 'Duplikate'-Ordner
        verschieben"), nur als Löschen statt Verschieben. Unabhängig von
        der per Maus markierten Auswahl, siehe _delete_selected()."""
        paths = self._checked_paths()
        if not paths:
            return

        names = "\n".join(p.name for p in paths[:10])
        if len(paths) > 10:
            names += t("main_more_files_suffix").format(count=len(paths) - 10)
        if QMessageBox.question(
            self, t("main_confirm_trash_title"),
            t("main_confirm_trash_checked_text").format(count=len(paths), names=names),
        ) != QMessageBox.Yes:
            return

        count, errors = engine.move_to_trash(paths)
        show_partial_result(self, count, t("main_verb_trashed"), errors)

        # Nur die tatsächlich gelöschten Dateien aus den Gruppen entfernen
        # (an ihrer Nicht-mehr-Existenz erkennbar - bei Fehlern bleibt eine
        # Datei ja an ihrem Platz), statt den ganzen Scan zu verwerfen.
        self._remove_paths_from_results({p for p in paths if not p.exists()})

    def _remove_paths_from_results(self, removed_paths: set[Path]) -> None:
        """Entfernt die angegebenen (soeben verschobenen/gelöschten) Dateien
        aus den aktuell angezeigten Ergebnis-Gruppen, ohne den gesamten Scan
        zu verwerfen - Gruppen, die dadurch auf unter 2 Dateien schrumpfen,
        fallen ganz weg. So bleiben die restlichen Ergebnisse (und die
        Vorschau, sofern die dort gezeigte Datei nicht betroffen ist)
        erhalten, statt nach jeder Aktion einen erneuten Scan zu erzwingen."""
        if not removed_paths:
            return
        new_groups = []
        for group in self.groups:
            remaining = [f for f in group.files if f.path not in removed_paths]
            if len(remaining) >= 2:
                similarity = group.similarity
                # Bei geschrumpften "Ähnliche Bilder"-Gruppen den Wert neu
                # berechnen - der für die ursprüngliche (größere) Gruppe
                # ermittelte Durchschnitt passt sonst nicht mehr zu den
                # verbleibenden Dateien.
                if group.kind == "similar" and len(remaining) != len(group.files):
                    similarity = engine.recompute_similarity([f.path for f in remaining])
                new_groups.append(engine.DuplicateGroup(files=remaining, kind=group.kind, similarity=similarity))
        self.groups = new_groups
        # preserve_checks=True: nur die betroffene(n) Datei(en) verschwinden,
        # Häkchen in unbeteiligten Gruppen bleiben unverändert (siehe
        # _rebuild_tree()).
        self._rebuild_tree(preserve_checks=True)


def _format_mtime(timestamp: float) -> str:
    from datetime import datetime
    return datetime.fromtimestamp(timestamp).strftime("%d.%m.%Y %H:%M")


def _system_is_dark(app: QApplication) -> bool:
    """Erkennt, ob das System (z.B. macOS) gerade im Dark Mode ist - wichtig,
    weil app.setStyle("Fusion") unten sonst immer seine eigene, feste helle
    Palette mitbringt und dem System-Erscheinungsbild nicht folgt (Ergebnis:
    z.T. dunkle, kaum lesbare Schrift auf dunklem Hintergrund)."""
    try:
        if app.styleHints().colorScheme() == Qt.ColorScheme.Dark:
            return True
        if app.styleHints().colorScheme() == Qt.ColorScheme.Light:
            return False
    except AttributeError:
        pass  # ältere Qt-Version ohne styleHints().colorScheme()
    # Fallback: Standard-Fensterfarbe auswerten, bevor Fusion sie überschreibt.
    return app.palette().color(QPalette.Window).lightness() < 128


def _dark_fusion_palette() -> QPalette:
    """Verbreitetes 'Dark Fusion'-Palettenrezept (identisch zum
    Datei-Umbenenner), damit alle Fusion-Widgets (Buttons, Labels, Tabellen/
    Baum, Eingabefelder, Gruppenrahmen, ...) im Dark Mode durchgängig helle
    statt dunkler Schrift auf dunklem Hintergrund zeigen - inklusive aller
    Stellen in dieser App, die per Stylesheet auf palette(...)-Rollen
    verweisen (z.B. DropZone, Ergebnis-Baum)."""
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.WindowText, QColor(220, 220, 220))
    palette.setColor(QPalette.Base, QColor(35, 35, 35))
    palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ToolTipBase, QColor(220, 220, 220))
    palette.setColor(QPalette.ToolTipText, QColor(35, 35, 35))
    palette.setColor(QPalette.Text, QColor(220, 220, 220))
    palette.setColor(QPalette.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ButtonText, QColor(220, 220, 220))
    palette.setColor(QPalette.BrightText, QColor(255, 60, 60))
    palette.setColor(QPalette.Link, QColor(90, 160, 255))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    # Ohne diese vier Rollen bleiben sie auf dem undefinierten, viel zu
    # dunklen Standardwert der QPalette-Basisklasse stehen (sichtbar z.B. am
    # "Tipp:"-Hinweistext unter dem Ergebnisbereich, der "color: palette(mid)"
    # per Stylesheet nutzt - dort stand vorher kaum lesbarer dunkler Text auf
    # dunklem Hintergrund).
    palette.setColor(QPalette.Mid, QColor(150, 150, 150))
    palette.setColor(QPalette.Midlight, QColor(80, 80, 80))
    palette.setColor(QPalette.Dark, QColor(20, 20, 20))
    palette.setColor(QPalette.Light, QColor(90, 90, 90))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(127, 127, 127))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(127, 127, 127))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(127, 127, 127))
    return palette


def main():
    from qt_app_kit.i18n import init as init_translations

    init_translations(translations.TEXTS, language=engine.load_settings().get("language", "de"))

    app = QApplication([])
    is_dark = _system_is_dark(app)
    app.setStyle("Fusion")
    if is_dark:
        app.setPalette(_dark_fusion_palette())
    window = DuplicateFinderApp()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
