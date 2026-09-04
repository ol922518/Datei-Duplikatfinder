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
from document_viewer import DocumentViewer
from qt_app_kit.qt_widgets import InfoIcon, ResizableSplitFrame, TitledFrame, TwoColumnFrame, flow_row

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

TARGET_FOLDER_HELP = (
    "Standardmäßig landet jede verschobene Datei im 'Duplikate'-Unterordner "
    "ihrer jeweiligen Quelle (Ordnerstruktur bleibt dabei erhalten). Über "
    "'Ändern…' lässt sich stattdessen ein einziger, zentraler Zielordner "
    "festlegen, in den dann alle verschobenen Duplikate wandern - egal aus "
    "welcher Quelle sie stammen. Die Einstellung wird gemerkt (auch über "
    "einen Neustart hinweg) und gilt für alle künftigen 'Verschieben'-"
    "Aktionen, bis sie über '↺ Standard' wieder zurückgesetzt wird."
)

SIMILAR_HELP = (
    "Findet zusätzlich Bilder, die sich zwar leicht unterscheiden (andere "
    "Auflösung, erneut komprimiert, minimal bearbeitet), aber ganz ähnlich "
    "aussehen - über einen Bildvergleich (Perceptual Hashing), nicht über "
    "exakte Prüfsummen. Kann daher auch mal Bilder als 'ähnlich' einstufen, "
    "die bei genauerem Hinsehen doch unterschiedlich sind - vor dem "
    "Verschieben bitte prüfen. Innerhalb jeder Gruppe gilt die größte Datei "
    "als Vorschlag (vermutlich beste Qualität). Braucht das Paket 'Pillow' "
    "(siehe requirements.txt) - ohne das Paket bleibt die Option wirkungslos."
)

COL_CHECK, COL_NAME, COL_FOLDER, COL_SIZE, COL_MODIFIED = range(5)


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
    """Führt die Duplikat-Suche in einem Hintergrund-Thread aus, damit die
    Oberfläche bei großen Ordnern nicht einfriert. Erst exakte Duplikate
    (siehe duplicate_engine.find_exact_duplicates), optional anschließend
    ähnliche Bilder unter den übrig gebliebenen Dateien (siehe
    duplicate_engine.scan_for_similar_images) - so entstehen keine
    doppelten Gruppen für bereits exakt erkannte Dateien. progress meldet
    den Fortschritt, finished_ok liefert die fertigen Gruppen (exakte zuerst)."""

    progress = Signal(int, int, str)
    finished_ok = Signal(list)
    failed = Signal(str)

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

        hint = QLabel(
            "Tipp: Häkchen markiert eine Datei zum Verschieben - je Gruppe ist die älteste "
            "Datei standardmäßig abgewählt (Original). Zeile auswählen zeigt die Datei in der "
            "Vorschau rechts. Verschobene Dateien landen im Unterordner 'Duplikate' der "
            "jeweiligen Quelle (oder im festgelegten Zielordner) und lassen sich per "
            "'Verschieben rückgängig machen' wiederherstellen."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid);")
        body.addWidget(hint)

        bottom = flow_row(outer)
        self.move_button = QPushButton("🗂 Ausgewählte in 'Duplikate'-Ordner verschieben")
        self.move_button.setEnabled(False)
        self.move_button.setToolTip("Verschiebt alle angehakten Dateien in einen 'Duplikate'-Unterordner ihrer jeweiligen Quelle.")
        self.move_button.clicked.connect(self.move_selected)
        bottom.layout().addWidget(self.move_button)
        self.undo_button = QPushButton("↺ Verschieben rückgängig machen")
        self.undo_button.setToolTip("Macht die zuletzt durchgeführte Verschiebe-Aktion wieder rückgängig.")
        self.undo_button.clicked.connect(self.undo_last)
        bottom.layout().addWidget(self.undo_button)

    def _build_source_section(self, container: QWidget) -> None:
        """Linke Spalte von Reihe 1: Quellordner (Drop-Zone mit Buttons,
        darunter kompakt der feste Standardordner). Wächst vertikal mit
        (QSizePolicy.Expanding), damit sie sich an der Höhe der - meist
        etwas höheren - Optionen-Box daneben ausrichtet."""
        self.source_frame = TitledFrame("Quellordner")
        self.source_frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        container.layout().addWidget(self.source_frame)

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
        self.source_frame.body_layout.addWidget(drop_row)

        self.default_folder_label = QLabel("Kein Standardordner festgelegt")
        self.default_folder_label.setWordWrap(True)
        self.source_frame.body_layout.addWidget(self.default_folder_label)
        self._refresh_default_folder_label()

    def _build_options_section(self, container: QWidget) -> None:
        """Rechte Spalte von Reihe 1: Optionen (Unterordner/Ähnliche Bilder
        mit je einem Info-Symbol) und darunter der Scan-Button mit
        Fortschrittsanzeige - alle in derselben Box. Wächst vertikal mit
        (QSizePolicy.Expanding), damit sich Quellordner und Optionen immer
        an der Höhe der jeweils größeren Box ausrichten."""
        options_frame = TitledFrame("Optionen")
        options_frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        container.layout().addWidget(options_frame)

        options_row = flow_row(None)
        self.recursive_check = QCheckBox("Unterordner einbeziehen (rekursiv)")
        self.recursive_check.setChecked(engine.load_settings().get("recursive", True))
        self.recursive_check.toggled.connect(self._on_recursive_toggled)
        options_row.layout().addWidget(self.recursive_check)
        options_row.layout().addWidget(InfoIcon(RECURSIVE_HELP))
        options_row.layout().addWidget(InfoIcon(COMPARE_HELP, title="Vergleichskriterium"))
        options_frame.body_layout.addWidget(options_row)

        similar_row = flow_row(None)
        self.similar_check = QCheckBox("🖼️ Ähnliche Bilder zusätzlich erkennen (experimentell)")
        self.similar_check.setChecked(engine.load_settings().get("find_similar", False))
        self.similar_check.toggled.connect(self._on_similar_toggled)
        similar_row.layout().addWidget(self.similar_check)
        similar_row.layout().addWidget(InfoIcon(SIMILAR_HELP, title="Ähnliche Bilder"))
        if not engine.PILLOW_AVAILABLE:
            missing_label = QLabel("(Paket 'Pillow' fehlt - siehe requirements.txt)")
            missing_label.setStyleSheet("color: palette(mid);")
            similar_row.layout().addWidget(missing_label)
        options_frame.body_layout.addWidget(similar_row)

        target_row = flow_row(None)
        self.target_folder_label = QLabel()
        self.target_folder_label.setWordWrap(True)
        target_row.layout().addWidget(self.target_folder_label)
        choose_target_btn = QPushButton("Ändern…")
        choose_target_btn.setToolTip("Legt einen zentralen Ordner fest, in den alle verschobenen Duplikate landen - egal aus welcher Quelle.")
        choose_target_btn.clicked.connect(self._choose_target_folder)
        target_row.layout().addWidget(choose_target_btn)
        reset_target_btn = QPushButton("↺ Standard")
        reset_target_btn.setToolTip("Zurück zum Standard: jede Datei landet im 'Duplikate'-Unterordner ihrer jeweiligen Quelle.")
        reset_target_btn.clicked.connect(self._reset_target_folder)
        target_row.layout().addWidget(reset_target_btn)
        target_row.layout().addWidget(InfoIcon(TARGET_FOLDER_HELP, title="Zielordner"))
        options_frame.body_layout.addWidget(target_row)
        self._refresh_target_folder_label()

    def _build_result_section(self, body: QVBoxLayout) -> None:
        result_frame = TitledFrame("Ergebnis")
        result_frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        body.addWidget(result_frame, 1)

        # Scan-Button + Fortschritt oben in der Ergebnis-Box statt in den
        # Optionen - an der Stelle, wo vorher dauerhaft "Noch nicht
        # gescannt." stand (der Text war nie aktualisiert worden).
        scan_row = flow_row(None)
        self.scan_button = QPushButton("🔍 Auf Duplikate prüfen")
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

        # Baumansicht links, Datei-Viewer rechts - per Maus verschiebbarer
        # Trenner (ResizableSplitFrame, wie beim Datei-Umbenenner), der bei
        # schmalem Fenster automatisch auf untereinander umschaltet.
        result_split = ResizableSplitFrame(min_width_left=260, min_width_right=380, left_stretch=1, right_stretch=2)
        result_frame.body_layout.addWidget(result_split, 1)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels(["", "Datei", "Ordner", "Größe", "Geändert am"])
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
        self.delete_selected_btn = QPushButton("🗑 Markierte Zeilen löschen")
        self.delete_selected_btn.setToolTip(
            "Verschiebt die im Baum markierten (angeklickten) Dateien in den "
            "Papierkorb - unabhängig vom Häkchen zum Verschieben. Mehrfachauswahl per "
            "Shift-Klick (zusammenhängend) oder Cmd-Klick (einzeln) möglich."
        )
        self.delete_selected_btn.clicked.connect(self._delete_selected)
        if not engine.HAS_SEND2TRASH:
            self.delete_selected_btn.setEnabled(False)
            self.delete_selected_btn.setToolTip(
                "Nicht verfügbar - dafür fehlt das Paket 'send2trash' "
                "(siehe requirements.txt: pip install -r requirements.txt)."
            )
        delete_row.layout().addWidget(self.delete_selected_btn)
        self.reveal_btn = QPushButton("📂 Ablageort öffnen")
        self.reveal_btn.setToolTip("Öffnet den Finder am Ort der aktuell in der Vorschau gezeigten Datei (markiert sie dort).")
        self.reveal_btn.clicked.connect(self._reveal_current_in_finder)
        delete_row.layout().addWidget(self.reveal_btn)

        self.viewer = DocumentViewer()
        self.viewer.setMinimumWidth(220)
        result_split.right.layout().addWidget(self.viewer)

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
        chosen = QFileDialog.getExistingDirectory(self, "Zentralen Zielordner für Duplikate wählen")
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
            self.target_folder_label.setText(f"🗂 Zielordner: {folder}")
        else:
            self.target_folder_label.setText("🗂 Zielordner: 'Duplikate'-Unterordner je Quelle (Standard)")

    # ------------------------------------------------------------------
    # Scan
    # ------------------------------------------------------------------
    def start_scan(self):
        if not self.sources:
            QMessageBox.information(self, "Kein Quellordner", "Bitte zuerst einen Ordner (oder Dateien) auswählen.")
            return
        if self._worker is not None:
            return

        find_similar = self.similar_check.isChecked()
        if find_similar and not engine.PILLOW_AVAILABLE:
            QMessageBox.warning(
                self, "Paket fehlt",
                "Für 'Ähnliche Bilder erkennen' fehlt das Python-Paket 'Pillow' "
                "(siehe requirements.txt). Der Scan läuft ohne diese Option weiter.",
            )
            find_similar = False

        self.scan_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # unbestimmt, solange die Dateiliste noch nicht feststeht
        self.status_label.setText("Durchsuche Quelle(n) …")

        self._worker = ScanWorker(
            list(self.sources), self.recursive_check.isChecked(), find_similar, self._target_folder(), self,
        )
        self._worker.progress.connect(self._on_scan_progress)
        self._worker.finished_ok.connect(self._on_scan_finished)
        self._worker.failed.connect(self._on_scan_failed)
        self._worker.start()

    def _on_scan_progress(self, done: int, total: int, phase: str) -> None:
        labels = {"partial": "Teil-Prüfsummen", "full": "Volle Prüfsummen", "phash": "Bildvergleich"}
        label = labels.get(phase, phase)
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
            n_similar = sum(1 for g in groups if g.kind == "similar")
            n_exact = len(groups) - n_similar
            breakdown = f"{n_exact} exakt" + (f", {n_similar} ähnlich" if n_similar else "")
            self.status_label.setText(
                f"Fertig - {len(groups)} Gruppe(n) ({breakdown}), {total_files} Datei(en), "
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
    def _rebuild_tree(self, preserve_checks: bool = False) -> None:
        """Baut den Ergebnisbaum aus self.groups neu auf. `preserve_checks`
        (True nur bei _remove_paths_from_results()) übernimmt die zuvor
        gesetzten Häkchen unveränderter Dateien statt sie auf den Standard
        zurückzusetzen - sonst würde z.B. das Löschen einer markierten Datei
        in Gruppe A auch ein bewusst abgewähltes Häkchen in der ganz
        unbeteiligten Gruppe B stillschweigend wieder anhaken (die
        Baum-Elemente werden bei jedem Neuaufbau komplett neu erzeugt, die
        alten Checkbox-Widgets samt ihrem Zustand gehen sonst verloren)."""
        previous_checks: dict[str, bool] = {}
        if preserve_checks:
            for child in self._iter_child_items():
                path_str = child.data(COL_CHECK, Qt.UserRole)
                checkbox = self.tree.itemWidget(child, COL_CHECK)
                if path_str and checkbox is not None:
                    previous_checks[path_str] = checkbox.isChecked()

        self.tree.blockSignals(True)
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

        exact_i = 0
        similar_i = 0
        for group in self.groups:
            if group.kind == "similar":
                similar_i += 1
                label = (
                    f"🖼️ Ähnliche Bilder {similar_i} — {len(group.files)} Dateien"
                    + (f" — ~{group.similarity * 100:.0f}% ähnlich" if group.similarity is not None else "")
                    + f" — {engine.format_size(group.wasted_bytes)} einsparbar"
                )
                original_tooltip = "Wird als beste Qualität vorgeschlagen (größte Datei der Gruppe) - abwählbar/anders wählbar."
                original_badge = "🖼️ Beste Qualität  "
            else:
                exact_i += 1
                label = f"Gruppe {exact_i} — {len(group.files)} Dateien — {engine.format_size(group.wasted_bytes)} einsparbar"
                original_tooltip = "Wird als Original vorgeschlagen (älteste Datei der Gruppe) - abwählbar/anders wählbar."
                original_badge = "🟢 Original  "

            group_item = QTreeWidgetItem([label, "", "", "", ""])
            bold = QFont()
            bold.setBold(True)
            group_item.setFont(0, bold)
            self.tree.addTopLevelItem(group_item)
            group_item.setFirstColumnSpanned(True)

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
                if is_original:
                    child.setToolTip(COL_NAME, original_tooltip)
                # Als eigenes Top-Level-Element statt group_item.addChild():
                # QTreeWidget positioniert bei echten Kind-Elementen per
                # setItemWidget() gesetzte Checkbox-Widgets nachweislich
                # falsch (immer bei (0,0) statt in der jeweiligen Zeile -
                # reproduzierbar per Pixelvergleich, unabhängig von Stil/
                # Palette). Als Geschwister-Element klappt es einwandfrei.
                # setRootIsDecorated(False) blendet dafür die (bei echten
                # Kindern übliche) Einrückung/den Pfeil aus, die fette
                # Gruppenzeile bleibt trotzdem als optische Trennung sichtbar.
                self.tree.addTopLevelItem(child)

                # Echtes QCheckBox-Widget statt der eingebauten Baum-Häkchen
                # (Qt.ItemIsUserCheckable/setCheckState) - die werden von
                # QTreeWidget unter dem hier nötigen Fusion-Stil (siehe
                # _dark_fusion_palette) nachweislich nicht sichtbar
                # gezeichnet (bei QTableWidget tritt derselbe Fehler nicht
                # auf - per Pixelvergleich verifiziert). Muss NACH dem
                # Einfügen ins Baum-Widget gesetzt werden. setChecked() vor
                # dem Verbinden von toggled(), damit der Aufbau selbst kein
                # Signal auslöst.
                checkbox = QCheckBox()
                path_str = str(entry.path)
                if path_str in previous_checks:
                    checkbox.setChecked(previous_checks[path_str])
                else:
                    checkbox.setChecked(not is_original)
                checkbox.toggled.connect(self._update_move_button)
                self.tree.setItemWidget(child, COL_CHECK, checkbox)

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
            QMessageBox.information(self, "Keine Auswahl", "Bitte zuerst eine Datei im Baum auswählen.")
            return
        if not self._current_preview_path.exists():
            QMessageBox.warning(self, "Nicht gefunden", f"'{self._current_preview_path.name}' existiert nicht mehr.")
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
        self.move_button.setEnabled(bool(self._checked_paths()))

    # ------------------------------------------------------------------
    # Verschieben / Rückgängig
    # ------------------------------------------------------------------
    def move_selected(self) -> None:
        paths = self._checked_paths()
        if not paths:
            return
        target_folder = self._target_folder()
        destination = f"'{target_folder}'" if target_folder else "den jeweiligen 'Duplikate'-Unterordner"
        total_size = sum(p.stat().st_size for p in paths if p.exists())
        reply = QMessageBox.question(
            self, "Duplikate verschieben",
            f"{len(paths)} Datei(en) ({engine.format_size(total_size)}) nach {destination} verschieben?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # move_to_duplicates_folder() versucht jede Datei einzeln - eine
        # fehlgeschlagene Datei verwirft nicht mehr die bereits erfolgreich
        # verschobenen (die bleiben protokolliert/nachvollziehbar).
        performed, errors = engine.move_to_duplicates_folder(paths, self.sources, target_folder=target_folder)

        self._update_undo_button()
        if errors:
            QMessageBox.warning(
                self, "Teilweise erfolgreich",
                f"{len(performed)} von {len(paths)} Datei(en) verschoben, {len(errors)} Fehler:\n" + "\n".join(errors),
            )
        else:
            self.status_label.setText(f"{len(performed)} Datei(en) verschoben.")
        # Nur die tatsächlich verschobenen Dateien aus den Gruppen entfernen,
        # statt den ganzen Scan zu verwerfen - der Rest der Ergebnisse (und
        # die Vorschau, falls nicht betroffen) bleibt so erhalten.
        self._remove_paths_from_results({Path(old) for old, _new in performed})

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
            QMessageBox.information(
                self, "Keine Auswahl",
                "Bitte zuerst eine oder mehrere Zeilen im Baum markieren "
                "(anklicken, mit Shift/Cmd für mehrere).",
            )
            return

        names = "\n".join(p.name for p in paths[:10])
        if len(paths) > 10:
            names += f"\n… und {len(paths) - 10} weitere"
        if QMessageBox.question(
            self, "In den Papierkorb verschieben",
            f"{len(paths)} Datei(en) werden in den Papierkorb verschoben:\n\n{names}\n\nFortfahren?",
        ) != QMessageBox.Yes:
            return

        count, errors = engine.move_to_trash(paths)
        if errors:
            QMessageBox.warning(self, "Teilweise erfolgreich",
                                 f"{count} in den Papierkorb verschoben, {len(errors)} Fehler:\n" + "\n".join(errors))
        else:
            QMessageBox.information(self, "Fertig", f"{count} Datei(en) in den Papierkorb verschoben.")

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
