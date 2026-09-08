"""
document_viewer.py
-------------------
Eingebauter Datei-Viewer für die Ergebnis-Tabelle: zeigt die zur aktuell
ausgewählten Zeile gehörende Datei an, damit man ihren Inhalt vor dem
Verschieben prüfen kann - ursprünglich 1:1 vom Datei-Umbenenner übernommen,
seitdem um Touchpad-Gesten ergänzt (siehe unten) - der engine-Import zeigt
hier auf duplicate_engine statt rename_engine.

Unterstützt:
- PDF (natives QtPdf-Widget)
- Bilder (JPEG, PNG, TIFF, HEIC, ...) über Qts eingebaute Bildformate
- Text/Markdown/CSV/JSON/YAML (reiner Text, Markdown mit einfacher Formatierung)
- Word (.docx) als reiner Text (über python-docx, sofern installiert)
- PowerPoint (.pptx) als reiner Text je Folie (über python-pptx, sofern
  installiert) - nur Titel/Aufzählungspunkte, KEINE Bilder/Layout/
  Formatierung (siehe _show_pptx()). Nur das moderne .pptx-Format, das
  alte binäre .ppt wird nicht unterstützt.
- Videos (MP4/MOV/M4V/AVI/MKV/WEBM, siehe VIDEO_EXTENSIONS) über
  QtMultimedia (QMediaPlayer/QVideoWidget) - Wiedergabe läuft über das
  systemeigene Backend (macOS: AVFoundation), tatsächlich abspielbare
  Formate/Codecs hängen davon ab (MP4/MOV mit H.264 praktisch immer,
  z.B. manche AVI/MKV-Varianten nicht garantiert - dann erscheint statt
  des Players eine Fehlermeldung, siehe _on_video_error())

Bedienung bei Bildern/PDF: Zwei-Finger-Wischen auf dem Trackpad scrollt
(hoch/runter/links/rechts, über Qts eingebaute Scroll-Behandlung von
QScrollArea/QPdfView), Zusammen-/Auseinanderziehen (Pinch) zoomt (siehe
eventFilter() unten, macOS-Trackpad-Geste). Zoom UND Scroll-Position
bleiben dabei beim Wechsel zur nächsten Datei erhalten (als relativer
Bruchteil 0..1 je Achse, nicht als Pixelwert - siehe _scroll_fraction) -
war z.B. die rechte untere Ecke der vorherigen Datei zu sehen, zeigt die
nächste Datei ebenfalls ihre rechte untere Ecke, unabhängig von deren
tatsächlicher Größe. Der allererste Start (noch nie manuell gezoomt/
gescrollt) ist echte 100% oben links; "↺ Einpassen" setzt jederzeit
bewusst darauf zurück.

Alles läuft lokal, ohne Internetzugriff - passend zum Rest der App. Einzige
Ausnahme: bei echten Kamerafotos mit GPS-Daten zeigt eine kleine Metadaten-
Zeile Datum/Kamera/Koordinaten an, mit einem Button "🌐 Ort ermitteln", der
bewusst erst auf Klick eine Online-Abfrage bei OpenStreetMap auslöst (siehe
duplicate_engine.reverse_geocode()) - nie automatisch.
"""

from pathlib import Path

from PySide6.QtCore import QEvent, QTimer, QUrl, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import duplicate_engine as engine
from qt_app_kit.i18n import t

try:
    import docx  # python-docx - Verfügbarkeit über engine.HAS_DOCX geprüft
    # (dieselbe Bibliothek, dort bereits erkannt), hier nur zusätzlich für
    # den direkten docx.Document(...)-Aufruf unten importiert.
except ImportError:
    pass
try:
    import pptx  # python-pptx - Verfügbarkeit über engine.HAS_PPTX geprüft,
    # hier nur zusätzlich für den direkten pptx.Presentation(...)-Aufruf
    # unten importiert (siehe _show_pptx()).
except ImportError:
    pass
MARKDOWN_EXTENSIONS = {".md"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}

ZOOM_STEP = 1.25
ZOOM_MIN = 0.1
ZOOM_MAX = 5.0


class DocumentViewer(QWidget):
    """Zeigt eine einzelne Datei passend zu ihrem Typ an. Aufruf über
    `show_file(path)`, `clear()` setzt die Anzeige zurück."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_pixmap: QPixmap | None = None
        # None = automatisch auf Fensterbreite einpassen; sonst manuell
        # gewählter Zoomfaktor (1.0 = Originalgröße), nur für Bilder - für
        # PDF hält QPdfView seinen Zoom-Zustand selbst (zoomMode/zoomFactor).
        # Bleibt (wie der Zoom-Zustand von self.pdf_view) bewusst über einen
        # Dateiwechsel hinweg erhalten (siehe show_file()). Ausgangswert
        # echte 1.0 (100%) statt None/Einpassen, damit die allererste
        # angezeigte Datei ebenfalls bei echten 100% startet.
        self._image_zoom: float | None = 1.0
        # Relative Scroll-Position (0.0..1.0 je Achse) der zuletzt aktiven
        # Bild-/PDF-Ansicht - bewusst als Bruchteil statt Pixelwert, damit
        # z.B. "rechts unten" auch bei unterschiedlich großen Dateien
        # vergleichbar bleibt. Wird bei jedem manuellen Scrollen aktualisiert
        # (siehe _on_scroll_changed()) und beim Öffnen der nächsten Datei
        # wiederhergestellt (siehe _defer_scroll_restore()), damit sich
        # beim Vergleichen mehrerer Duplikate dieselbe Stelle im Blick
        # behalten lässt.
        self._scroll_fraction: tuple[float, float] = (0.0, 0.0)
        # GPS-Koordinaten des aktuell angezeigten Fotos (falls vorhanden) -
        # Grundlage für den Button "🌐 Ort ermitteln" (siehe _on_geocode_clicked).
        self._current_photo_gps: tuple[float, float] | None = None
        # Nur für die Fehlermeldung bei _on_video_error() - QMediaPlayer
        # kennt selbst keinen Dateinamen, nur die geladene Quelle.
        self._current_video_name: str = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_label = QLabel(t("viewer_title_default"))
        self.title_label.setStyleSheet("font-weight: bold;")
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        # Zoom-Leiste - nur bei Bildern/PDF sinnvoll, wird je nach
        # angezeigtem Inhalt aktiviert/deaktiviert (siehe _set_active_page).
        self.zoom_bar = QWidget()
        zoom_layout = QHBoxLayout(self.zoom_bar)
        zoom_layout.setContentsMargins(0, 0, 0, 4)
        zoom_out_btn = QPushButton("➖")
        zoom_out_btn.setFixedWidth(32)
        zoom_out_btn.setToolTip(t("viewer_zoom_out_tooltip"))
        zoom_out_btn.clicked.connect(self._zoom_out)
        zoom_layout.addWidget(zoom_out_btn)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setAlignment(Qt.AlignCenter)
        self.zoom_label.setFixedWidth(48)
        zoom_layout.addWidget(self.zoom_label)
        zoom_in_btn = QPushButton("➕")
        zoom_in_btn.setFixedWidth(32)
        zoom_in_btn.setToolTip(t("viewer_zoom_in_tooltip"))
        zoom_in_btn.clicked.connect(self._zoom_in)
        zoom_layout.addWidget(zoom_in_btn)
        zoom_fit_btn = QPushButton(t("viewer_zoom_fit_button"))
        zoom_fit_btn.setToolTip(t("viewer_zoom_fit_tooltip"))
        zoom_fit_btn.clicked.connect(self._zoom_fit)
        zoom_layout.addWidget(zoom_fit_btn)
        zoom_layout.addStretch(1)
        layout.addWidget(self.zoom_bar)

        # Metadaten-Zeile - nur bei echten Kamerafotos (EXIF-Datum/GPS)
        # sichtbar, siehe _update_photo_meta_bar().
        self.photo_meta_bar = QWidget()
        photo_meta_layout = QHBoxLayout(self.photo_meta_bar)
        photo_meta_layout.setContentsMargins(0, 0, 0, 4)
        self.photo_meta_label = QLabel()
        self.photo_meta_label.setWordWrap(True)
        self.photo_meta_label.setStyleSheet("color: palette(mid);")
        photo_meta_layout.addWidget(self.photo_meta_label, 1)
        self.geocode_btn = QPushButton(t("viewer_geocode_button"))
        self.geocode_btn.setToolTip(t("viewer_geocode_tooltip"))
        self.geocode_btn.clicked.connect(self._on_geocode_clicked)
        photo_meta_layout.addWidget(self.geocode_btn)
        self.photo_meta_bar.setVisible(False)
        layout.addWidget(self.photo_meta_bar)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        # Leer-Seite: solange (noch) nichts ausgewählt ist.
        self.empty_page = QLabel(t("viewer_empty_hint"))
        self.empty_page.setAlignment(Qt.AlignCenter)
        self.empty_page.setWordWrap(True)
        self.empty_page.setStyleSheet("color: palette(mid);")
        self.stack.addWidget(self.empty_page)

        # Hinweis-Seite: Datei ohne Vorschau bzw. Lesefehler.
        self.unsupported_page = QLabel()
        self.unsupported_page.setAlignment(Qt.AlignCenter)
        self.unsupported_page.setWordWrap(True)
        self.unsupported_page.setStyleSheet("color: palette(mid);")
        self.stack.addWidget(self.unsupported_page)

        # Text/Markdown/Word-Ansicht.
        self.text_view = QTextEdit()
        self.text_view.setReadOnly(True)
        self.stack.addWidget(self.text_view)

        # Bild-Ansicht.
        self.image_scroll = QScrollArea()
        self.image_scroll.setWidgetResizable(True)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_scroll.setWidget(self.image_label)
        self.stack.addWidget(self.image_scroll)

        # PDF-Ansicht. Ausgangswert Custom/100% statt FitToWidth (siehe
        # show_file()) - FitToWidth berechnet je nach Seiten-/Fenstergröße
        # auch mal einen Wert über 100%, was beim allerersten Öffnen einer
        # PDF-Datei überraschend/zufällig wirken würde.
        self.pdf_document = QPdfDocument(self)
        self.pdf_view = QPdfView()
        self.pdf_view.setDocument(self.pdf_document)
        self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
        self.pdf_view.setZoomFactor(1.0)
        self.stack.addWidget(self.pdf_view)

        # Video-Ansicht: QVideoWidget (Bildausgabe) + kleine Bedienleiste
        # (Play/Pause, Fortschritt, Zeit) darunter - beides zusammen als
        # eine einzige Stack-Seite (self.video_page), da eine Stack-Seite
        # immer genau ein Widget ist.
        self.video_page = QWidget()
        video_page_layout = QVBoxLayout(self.video_page)
        video_page_layout.setContentsMargins(0, 0, 0, 0)
        self.video_widget = QVideoWidget()
        video_page_layout.addWidget(self.video_widget, 1)

        video_controls = QWidget()
        video_controls_layout = QHBoxLayout(video_controls)
        video_controls_layout.setContentsMargins(0, 4, 0, 0)
        self.video_play_btn = QPushButton("▶")
        self.video_play_btn.setFixedWidth(32)
        self.video_play_btn.setToolTip(t("viewer_video_play_tooltip"))
        self.video_play_btn.clicked.connect(self._toggle_video_playback)
        video_controls_layout.addWidget(self.video_play_btn)
        self.video_position_slider = QSlider(Qt.Horizontal)
        self.video_position_slider.setRange(0, 0)
        # sliderMoved (nur bei Nutzer-Zieh-Bewegung) statt valueChanged
        # (würde auch die automatischen Positions-Updates während der
        # Wiedergabe wieder zurück in den Player schreiben und ihn so
        # dauerhaft an Position 0 festnageln).
        self.video_position_slider.sliderMoved.connect(self._seek_video)
        video_controls_layout.addWidget(self.video_position_slider, 1)
        self.video_time_label = QLabel("0:00 / 0:00")
        self.video_time_label.setFixedWidth(90)
        self.video_time_label.setAlignment(Qt.AlignCenter)
        video_controls_layout.addWidget(self.video_time_label)
        video_page_layout.addWidget(video_controls)
        self.stack.addWidget(self.video_page)

        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)
        self.media_player.playbackStateChanged.connect(self._on_video_playback_state_changed)
        self.media_player.positionChanged.connect(self._on_video_position_changed)
        self.media_player.durationChanged.connect(self._on_video_duration_changed)
        self.media_player.errorOccurred.connect(self._on_video_error)

        # Pinch-Zoom per Trackpad (macOS: "Zusammen-/Auseinanderziehen") -
        # Qt liefert das als natives Gesten-Event an das Widget unter dem
        # Mauszeiger, hier also die Viewports von Bild-/PDF-Ansicht (siehe
        # eventFilter() unten). Zwei-Finger-Scrollen (Pan) braucht dagegen
        # keinen eigenen Code - QScrollArea/QPdfView verarbeiten normale
        # Trackpad-Scroll-Gesten bereits eingebaut als Wheel-Events; über die
        # Scrollbar-Signale wird dieselbe Bewegung zusätzlich als relative
        # Position gemerkt (siehe _on_scroll_changed()).
        self.image_scroll.viewport().installEventFilter(self)
        self.pdf_view.viewport().installEventFilter(self)
        self.image_scroll.horizontalScrollBar().valueChanged.connect(self._on_scroll_changed)
        self.image_scroll.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)
        self.pdf_view.horizontalScrollBar().valueChanged.connect(self._on_scroll_changed)
        self.pdf_view.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)

        self._set_active_page(self.empty_page)

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.NativeGesture and event.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
            # event.value() ist der kleine Skalierungs-Zuwachs seit dem
            # letzten Gesten-Frame (z.B. 0.02) - direkt als Faktor auf den
            # aktuellen Zoom anwendbar.
            self._adjust_zoom(1 + event.value())
            return True
        return super().eventFilter(obj, event)

    def clear(self) -> None:
        self.title_label.setText(t("viewer_title_default"))
        self._current_pixmap = None
        self._update_photo_meta_bar(None)
        self.media_player.stop()
        self._set_active_page(self.empty_page)

    def show_file(self, path: Path) -> None:
        self.title_label.setText(path.name)
        self._current_pixmap = None
        # Zoom (self._image_zoom bzw. der Zoom-Zustand von self.pdf_view)
        # UND Scroll-Position (self._scroll_fraction) werden bewusst NICHT
        # zurückgesetzt - bleiben über den Dateiwechsel hinweg erhalten
        # (Ausgangswert beider ist echte 100% oben links, siehe __init__),
        # bis der Nutzer selbst "↺ Einpassen" klickt. So bleibt z.B. eine in
        # die rechte untere Ecke gezoomte Stelle beim Vergleichen mehrerer
        # Duplikate an derselben Stelle sichtbar.
        self._update_photo_meta_bar(None)
        # Läuft gerade ein Video, MUSS die Wiedergabe hier gestoppt werden -
        # sonst liefe der Ton unhörbar sichtbar im Hintergrund weiter, auch
        # wenn längst eine andere (nicht-Video-)Datei angezeigt wird. Auch
        # unkritisch, wenn gerade gar kein Video lief (stop() auf einem
        # bereits gestoppten Player ist ein No-Op).
        self.media_player.stop()

        if not path.exists():
            self._show_message(t("viewer_file_not_found").format(name=path.name))
            return

        ext = path.suffix.lower()
        if ext == ".pdf":
            self._show_pdf(path)
        elif ext == ".docx":
            self._show_docx(path)
        elif ext == ".pptx":
            self._show_pptx(path)
        elif ext in VIDEO_EXTENSIONS:
            self._show_video(path)
        elif ext in engine.TEXT_EXTENSIONS:
            self._show_text(path, markdown=ext in MARKDOWN_EXTENSIONS)
        else:
            # Alles andere (auch unbekannte Endungen) als Bild versuchen -
            # Qt kennt deutlich mehr Bildformate, als die App fürs {content}
            # aktiv unterstützt (z.B. auch HEIC).
            self._show_image_or_unsupported(path)

    # ------------------------------------------------------------------
    def _set_active_page(self, widget) -> None:
        """Wechselt die angezeigte Seite und schaltet die Zoom-Leiste passend
        dazu ein (Bild/PDF) oder aus (Text/Hinweis/leer)."""
        self.stack.setCurrentWidget(widget)
        self.zoom_bar.setEnabled(widget in (self.image_scroll, self.pdf_view))
        self._update_zoom_label()

    def _show_message(self, text: str) -> None:
        self.unsupported_page.setText(text)
        self._set_active_page(self.unsupported_page)

    def _show_pdf(self, path: Path) -> None:
        # load() liefert einen QPdfDocument.Error-Wert (nicht Status - ein
        # Vergleich mit Status.Ready wäre deshalb immer ungleich und somit
        # wirkungslos), erfolgreich ist genau Error.None_.
        error = self.pdf_document.load(str(path))
        if error != QPdfDocument.Error.None_:
            self._show_message(t("viewer_pdf_open_failed").format(name=path.name))
            return
        # Zoom-Zustand NICHT zurückgesetzt (siehe show_file()) - Ausgangswert
        # Custom/100% kommt bereits aus __init__.
        self._set_active_page(self.pdf_view)
        # Verzögert (siehe _defer_scroll_restore()) statt direkt hier - die
        # Scrollbar-Reichweite (horizontalScrollBar().maximum()/vertical...)
        # wird von QPdfView erst asynchron aktualisiert, NACHDEM die neue
        # Seite tatsächlich geladen/dargestellt ist. Eine sofortige
        # Wiederherstellung würde noch die Reichweite der VORHERIGEN Datei
        # lesen - genau das ließ "rechte untere Ecke" beim Dateiwechsel
        # unzuverlässig wirken.
        self._defer_scroll_restore(self.pdf_view)

    def _show_image_or_unsupported(self, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._show_message(t("viewer_no_preview").format(name=path.name))
            return
        self._current_pixmap = pixmap
        self._apply_scaled_pixmap()
        self._update_photo_meta_bar(engine.extract_photo_metadata(path))
        self._set_active_page(self.image_scroll)
        # Verzögert (siehe _defer_scroll_restore()) statt direkt hier -
        # dieselbe Begründung wie in _show_pdf().
        self._defer_scroll_restore(self.image_scroll)

    def _show_video(self, path: Path) -> None:
        self._current_video_name = path.name
        self.video_position_slider.setRange(0, 0)
        self.video_time_label.setText("0:00 / 0:00")
        self.media_player.setSource(QUrl.fromLocalFile(str(path)))
        self._set_active_page(self.video_page)
        # Startet automatisch, statt einen zusätzlichen ersten Klick auf
        # "▶" zu verlangen - passend zum Rest des Viewers, der ebenfalls
        # sofort die volle Vorschau zeigt. Ein evtl. Abspiel-Fehler (z.B.
        # nicht unterstützter Codec) kommt asynchron über errorOccurred
        # (siehe _on_video_error()), nicht als Rückgabewert hier - anders
        # als z.B. bei _show_pdf().
        self.media_player.play()

    @staticmethod
    def _format_place(lat: float, lon: float, cached: dict | None) -> str:
        """Baut die Anzeige '📍 Ort, Land (Koordinaten)' - Ort/Land nur, wenn
        bereits per reverse_geocode() ermittelt (siehe LOCATION_CACHE), sonst
        nur die reinen Koordinaten."""
        label = ""
        if cached:
            label = cached.get("ort", "")
            if cached.get("land"):
                label += (", " if label else "") + cached["land"]
        return f"📍 {label} ({lat:.5f}, {lon:.5f})" if label else f"📍 {lat:.5f}, {lon:.5f}"

    def _update_photo_meta_bar(self, meta: dict | None) -> None:
        """Zeigt bei echten Kamerafotos (EXIF-Datum und/oder GPS vorhanden)
        eine kleine Metadaten-Zeile mit Button '🌐 Ort ermitteln' an - sonst
        (Screenshots/Grafiken ohne EXIF, oder andere Dateitypen) bleibt sie
        ausgeblendet."""
        self._current_photo_gps = None
        if not meta or not (meta.get("date") or meta.get("latitude") is not None):
            self.photo_meta_bar.setVisible(False)
            return

        parts = []
        if meta.get("date"):
            parts.append(f"📅 {meta['date']}")
        if meta.get("camera"):
            parts.append(f"📷 {meta['camera']}")
        lat, lon = meta.get("latitude"), meta.get("longitude")
        if lat is not None and lon is not None:
            self._current_photo_gps = (lat, lon)
            cached = engine.LOCATION_CACHE.get(engine.location_cache_key(lat, lon))
            parts.append(self._format_place(lat, lon, cached))
        self.photo_meta_label.setText("   ".join(parts))
        self.geocode_btn.setVisible(self._current_photo_gps is not None)
        self.geocode_btn.setEnabled(True)
        self.geocode_btn.setText(t("viewer_geocode_button"))
        self.photo_meta_bar.setVisible(True)

    def _on_geocode_clicked(self) -> None:
        if self._current_photo_gps is None:
            return
        lat, lon = self._current_photo_gps
        self.geocode_btn.setEnabled(False)
        self.geocode_btn.setText(t("viewer_geocode_searching"))
        # Sorgt dafür, dass der deaktivierte Button/Text vor dem (kurz
        # blockierenden) Netzwerkaufruf gleich sichtbar wird.
        QApplication.processEvents()
        result = engine.reverse_geocode(lat, lon)
        # None = Abfrage selbst fehlgeschlagen (z.B. kein Internet); ein
        # Ergebnis-dict mit leeren Werten ist dagegen eine erfolgreiche
        # Abfrage, die für diese Koordinate nur nichts gefunden hat - beides
        # braucht eine unterschiedliche Rückmeldung.
        if result is None:
            self.geocode_btn.setText(t("viewer_geocode_no_internet"))
        elif result.get("ort") or result.get("land"):
            self.photo_meta_label.setText(
                self.photo_meta_label.text().rsplit("📍", 1)[0] + self._format_place(lat, lon, result)
            )
            self.geocode_btn.setText(t("viewer_geocode_button"))
        else:
            self.geocode_btn.setText(t("viewer_geocode_not_found"))
        self.geocode_btn.setEnabled(True)

    def _current_image_zoom(self) -> float:
        """Aktueller Zoomfaktor fürs Bild (1.0 = Originalgröße) - im
        Einpassen-Modus (self._image_zoom is None) aus der verfügbaren
        Breite berechnet, sonst der manuell gewählte Wert."""
        if self._current_pixmap is None or self._current_pixmap.width() <= 0:
            return 1.0
        if self._image_zoom is not None:
            return self._image_zoom
        viewport_width = max(10, self.image_scroll.viewport().width() - 4)
        return min(1.0, viewport_width / self._current_pixmap.width())

    def _apply_scaled_pixmap(self) -> None:
        if self._current_pixmap is None:
            return
        zoom = self._current_image_zoom()
        width = max(10, round(self._current_pixmap.width() * zoom))
        self.image_label.setPixmap(self._current_pixmap.scaledToWidth(width, Qt.SmoothTransformation))
        self._update_zoom_label()

    def _show_text(self, path: Path, markdown: bool) -> None:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            self._show_message(t("viewer_read_failed").format(error=e))
            return
        if markdown:
            self.text_view.setMarkdown(text)
        else:
            self.text_view.setPlainText(text)
        self._set_active_page(self.text_view)

    def _show_docx(self, path: Path) -> None:
        if not engine.HAS_DOCX:
            self._show_message(t("viewer_docx_missing_package"))
            return
        try:
            document = docx.Document(str(path))
            text = "\n\n".join(p.text for p in document.paragraphs if p.text.strip())
        except Exception as e:
            self._show_message(t("viewer_docx_read_failed").format(error=e))
            return
        self.text_view.setPlainText(text or t("viewer_docx_empty"))
        self._set_active_page(self.text_view)

    def _show_pptx(self, path: Path) -> None:
        """Zeigt nur den Text je Folie an (Titel/Aufzählungspunkte,
        Trennzeile '— Folie N —') - keine Bilder, kein Layout, keine
        Formatierung. Bewusst so einfach gehalten wie _show_docx() oben,
        eine echte visuelle Folien-Vorschau bräuchte einen externen
        Konverter (z.B. LibreOffice), den diese App nicht voraussetzt."""
        if not engine.HAS_PPTX:
            self._show_message(t("viewer_pptx_missing_package"))
            return
        try:
            presentation = pptx.Presentation(str(path))
            slide_texts = []
            for i, slide in enumerate(presentation.slides, start=1):
                lines = [t("viewer_pptx_slide_label").format(number=i)]
                for shape in slide.shapes:
                    if shape.has_text_frame and shape.text_frame.text.strip():
                        lines.append(shape.text_frame.text.strip())
                slide_texts.append("\n".join(lines))
            text = "\n\n".join(slide_texts)
        except Exception as e:
            self._show_message(t("viewer_pptx_read_failed").format(error=e))
            return
        self.text_view.setPlainText(text or t("viewer_pptx_empty"))
        self._set_active_page(self.text_view)

    # ------------------------------------------------------------------
    # Video
    # ------------------------------------------------------------------
    def _toggle_video_playback(self) -> None:
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def _on_video_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.video_play_btn.setText("⏸" if playing else "▶")

    def _on_video_duration_changed(self, duration_ms: int) -> None:
        self.video_position_slider.setRange(0, duration_ms)
        self._update_video_time_label()

    def _on_video_position_changed(self, position_ms: int) -> None:
        # Während der Nutzer selbst am Schieberegler zieht (isSliderDown())
        # nicht überschreiben - sonst "kämpft" die laufende Wiedergabe
        # gegen die Zieh-Bewegung.
        if not self.video_position_slider.isSliderDown():
            self.video_position_slider.setValue(position_ms)
        self._update_video_time_label()

    def _seek_video(self, position_ms: int) -> None:
        self.media_player.setPosition(position_ms)

    def _update_video_time_label(self) -> None:
        current = self._format_video_time(self.media_player.position())
        total = self._format_video_time(self.media_player.duration())
        self.video_time_label.setText(f"{current} / {total}")

    @staticmethod
    def _format_video_time(milliseconds: int) -> str:
        total_seconds = max(0, milliseconds) // 1000
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes}:{seconds:02d}"

    def _on_video_error(self, error: QMediaPlayer.Error, error_string: str) -> None:
        """QMediaPlayer meldet einen Abspiel-Fehler (z.B. nicht
        unterstützter Codec/Container) asynchron über dieses Signal, statt
        wie z.B. QPdfDocument.load() einen Fehler-Rückgabewert direkt bei
        _show_video() zu liefern - bis dahin zeigt der Stack also schon die
        (leere/kaputte) Video-Seite an, wird hier auf die Hinweis-Seite mit
        Fehlertext umgeschaltet."""
        if error == QMediaPlayer.Error.NoError:
            return
        self._show_message(t("viewer_video_error").format(name=self._current_video_name, error=error_string))

    # ------------------------------------------------------------------
    # Zoom (Bilder + PDF)
    # ------------------------------------------------------------------
    def _zoom_in(self) -> None:
        self._adjust_zoom(ZOOM_STEP)

    def _zoom_out(self) -> None:
        self._adjust_zoom(1 / ZOOM_STEP)

    def _adjust_zoom(self, factor: float) -> None:
        current = self.stack.currentWidget()
        if current is self.image_scroll and self._current_pixmap is not None:
            self._image_zoom = max(ZOOM_MIN, min(ZOOM_MAX, self._current_image_zoom() * factor))
            self._apply_scaled_pixmap()
        elif current is self.pdf_view:
            new_factor = max(ZOOM_MIN, min(ZOOM_MAX, self.pdf_view.zoomFactor() * factor))
            self.pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
            self.pdf_view.setZoomFactor(new_factor)
            self._update_zoom_label()

    def _zoom_fit(self) -> None:
        current = self.stack.currentWidget()
        self._scroll_fraction = (0.0, 0.0)
        if current is self.image_scroll:
            self._image_zoom = None
            self._apply_scaled_pixmap()
        elif current is self.pdf_view:
            self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
            self._update_zoom_label()

    def _on_scroll_changed(self, _value: int = 0) -> None:
        """Merkt sich die aktuelle Scroll-Position der gerade aktiven Bild-/
        PDF-Ansicht als Bruchteil (0.0..1.0) je Achse statt als Pixelwert -
        so bleibt z.B. "rechts unten" auch bei unterschiedlich großen
        Dateien vergleichbar (siehe _defer_scroll_restore()).

        Ermittelt die Ansicht über self.sender() (welche Scrollbar hat das
        Signal ausgelöst) statt über self.stack.currentWidget() - beim
        Seitenwechsel wird sonst kurzzeitig noch die VORHERIGE Seite als
        "aktuell" gelesen, obwohl schon die neue Scrollbar feuert (siehe
        _defer_scroll_restore()), was den gemerkten Bruchteil mit falschen
        Werten überschreiben könnte."""
        sender = self.sender()
        if sender in (self.image_scroll.horizontalScrollBar(), self.image_scroll.verticalScrollBar()):
            view = self.image_scroll
        elif sender in (self.pdf_view.horizontalScrollBar(), self.pdf_view.verticalScrollBar()):
            view = self.pdf_view
        else:
            return
        hbar, vbar = view.horizontalScrollBar(), view.verticalScrollBar()
        self._scroll_fraction = (
            hbar.value() / hbar.maximum() if hbar.maximum() else 0.0,
            vbar.value() / vbar.maximum() if vbar.maximum() else 0.0,
        )

    def _defer_scroll_restore(self, view) -> None:
        """Stellt die zuletzt gemerkte relative Scroll-Position
        (self._scroll_fraction) in der übergebenen Bild-/PDF-Ansicht wieder
        her - verzögert per QTimer.singleShot(0, ...) statt sofort, weil
        QScrollArea/QPdfView ihre Scrollbar-Reichweite (maximum()) erst
        asynchron neu berechnen, NACHDEM Qt das durch das neue Bild/PDF
        ausgelöste QEvent::LayoutRequest verarbeitet hat (das passiert erst
        beim nächsten Durchlauf der Event-Loop, nicht sofort beim
        Setzen des Pixmaps/Ladens der PDF-Seite). Eine sofortige
        Wiederherstellung würde also noch mit der Reichweite der
        VORHERIGEN Datei rechnen - das war die eigentliche Ursache dafür,
        dass "an derselben Stelle bleiben" beim Dateiwechsel unzuverlässig
        wirkte.

        Prüft beim tatsächlichen Ausführen (nicht beim Planen) erneut, ob
        `view` noch die aktive Seite ist - wechselt der Nutzer schneller
        weiter, als die 0ms-Timer abgearbeitet werden (z.B. schnelles
        Durchblättern), würde ein noch ausstehender, veralteter Restore
        sonst setValue() auf der inzwischen unsichtbaren Ansicht aufrufen.
        Das würde nicht nur sichtbar nichts bewirken, sondern über
        valueChanged auch _on_scroll_changed() erneut auslösen und so
        self._scroll_fraction mit dem (falschen) Bruchteil der alten
        Ansicht überschreiben - ein no-op statt eines Verzichts auf die
        Prüfung schließt das strukturell aus, statt sich auf die
        Ausführungsreihenfolge mehrerer verschachtelter Timer zu
        verlassen."""
        x_frac, y_frac = self._scroll_fraction

        def restore() -> None:
            if self.stack.currentWidget() is not view:
                return
            hbar, vbar = view.horizontalScrollBar(), view.verticalScrollBar()
            hbar.setValue(round(x_frac * hbar.maximum()))
            vbar.setValue(round(y_frac * vbar.maximum()))

        QTimer.singleShot(0, restore)

    def _update_zoom_label(self) -> None:
        # Hinweis: QPdfView.zoomFactor() liefert im Modus "FitToWidth" nicht
        # den tatsächlich angezeigten Skalierungsfaktor (bleibt am zuletzt
        # manuell gesetzten Wert stehen) - deshalb dort "Auto" statt einer
        # (falschen) Prozentzahl anzeigen.
        current = self.stack.currentWidget()
        if current is self.image_scroll and self._current_pixmap is not None:
            if self._image_zoom is None:
                self.zoom_label.setText(t("viewer_zoom_auto"))
            else:
                self.zoom_label.setText(f"{round(self._image_zoom * 100)}%")
        elif current is self.pdf_view:
            if self.pdf_view.zoomMode() == QPdfView.ZoomMode.FitToWidth:
                self.zoom_label.setText(t("viewer_zoom_auto"))
            else:
                self.zoom_label.setText(f"{round(self.pdf_view.zoomFactor() * 100)}%")
        else:
            self.zoom_label.setText("–")

    # ------------------------------------------------------------------
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._current_pixmap is not None and self.stack.currentWidget() is self.image_scroll:
            self._apply_scaled_pixmap()
