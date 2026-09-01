"""
qt_widgets.py
-------------
Wiederverwendbare UI-Bausteine für main.py, aufbauend auf PySide6/Qt:

- FlowLayout: ein Layout, das seine Widgets zeilenweise anordnet und
  automatisch umbricht, wenn das Fenster schmaler wird (Qt-Standardrezept,
  hier leicht angepasst) - entspricht dem, was in der CustomTkinter-Version
  "ReflowFrame" hieß.
- flow_row(): Hilfsfunktion, die ein Widget mit FlowLayout erzeugt (und
  optional direkt an ein übergeordnetes Layout hängt) - der übliche Weg,
  eine umbrechende Buttonzeile aufzubauen.
- TitledFrame: eine Box mit Rahmen und Titel oben links (Qt bringt das mit
  QGroupBox nativ mit).
- TwoColumnFrame: zwei nebeneinander angeordnete Spalten, die bei zu
  schmalem Fenster automatisch untereinander dargestellt werden.
- ResizableSplitFrame: wie TwoColumnFrame, aber mit einem vom Nutzer per
  Maus verschiebbaren Trenner zwischen den beiden Bereichen.
- InfoIcon: ein kleines "ℹ️"-Symbol, das einen Hilfetext erst beim Anklicken
  in einem Dialog anzeigt.
- AutoGrowTextEdit: ein editierbares, mehrzeiliges Textfeld, das seine Höhe
  automatisch an den (umgebrochenen) Inhalt anpasst - wie ein "wachsendes"
  einzeiliges Eingabefeld, aber ohne dass langer Text seitlich abgeschnitten
  wird.
"""

from PySide6.QtCore import QMargins, QPoint, QRect, QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class FlowLayout(QLayout):
    """Ordnet seine Widgets zeilenweise an und bricht automatisch um, sobald
    eine Zeile nicht mehr in die verfügbare Breite passt (ähnlich einem
    Flow-Layout aus dem Webdesign). Basiert auf Qts offiziellem
    "Flow Layout"-Beispiel.

    Benutzung:
        row = QWidget()
        row.setLayout(FlowLayout())
        row.layout().addWidget(QPushButton("Klick mich"))
    """

    def __init__(self, parent=None, margin: int = 0, hgap: int = 6, vgap: int = 6):
        super().__init__(parent)
        self._items: list = []
        self._hgap = hgap
        self._vgap = vgap
        self._computing_height = False
        self._last_height = 0
        self.setContentsMargins(QMargins(margin, margin, margin, margin))

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        # Sperre gegen Selbst-Rekursion: manche Qt-Konstellationen (z.B.
        # verschachtelt in einer QScrollArea) fragen während der eigenen
        # Berechnung erneut nach heightForWidth - dann den zuletzt
        # berechneten Wert zurückgeben, statt endlos weiterzurechnen.
        if self._computing_height:
            return self._last_height
        self._computing_height = True
        try:
            self._last_height = self._do_layout(QRect(0, 0, width, 0), test_only=True)
        finally:
            self._computing_height = False
        return self._last_height

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective.x()
        y = effective.y()
        line_height = 0

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._hgap
            if next_x - self._hgap > effective.right() and line_height > 0:
                x = effective.x()
                y += line_height + self._vgap
                next_x = x + hint.width() + self._hgap
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))

            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + margins.bottom()


def flow_row(parent_layout=None) -> QWidget:
    """Erzeugt ein Widget mit FlowLayout (umbrechende Zeile), hängt es
    optional direkt an ein übergeordnetes Layout und gibt es zurück - Kinder
    werden dann per `row.layout().addWidget(...)` hinzugefügt."""
    row = QWidget()
    row.setLayout(FlowLayout())
    if parent_layout is not None:
        parent_layout.addWidget(row)
    return row


class TitledFrame(QGroupBox):
    """Eine Box mit Rahmen und Titel oben links. Der eigentliche Inhalt
    kommt als Kind-Widget in `self.body` (mit eigenem QVBoxLayout)."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 4, 8, 8)
        self.body = QWidget(self)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.body)


class TwoColumnFrame(QWidget):
    """Zwei nebeneinander angeordnete Spalten (`.left`/`.right`), die
    automatisch untereinander dargestellt werden, sobald das Fenster zu
    schmal dafür wird. Über `left_stretch`/`right_stretch` lässt sich ein
    Größenverhältnis (z.B. 1:2) statt der gleichmäßigen 1:1-Aufteilung
    vorgeben.

    Benutzung:
        cols = TwoColumnFrame()
        cols.left.layout().addWidget(...)
        cols.right.layout().addWidget(...)
    """

    def __init__(self, gap: int = 16, min_width_left: int = 300, min_width_right: int = 300,
                 left_stretch: int = 1, right_stretch: int = 1, parent=None):
        super().__init__(parent)
        self._gap = gap
        self._min_width_left = min_width_left
        self._min_width_right = min_width_right
        self._left_stretch = left_stretch
        self._right_stretch = right_stretch
        self._stacked: bool | None = None

        self.left = QWidget(self)
        self.left.setLayout(QVBoxLayout())
        self.left.layout().setContentsMargins(0, 0, 0, 0)
        self.right = QWidget(self)
        self.right.setLayout(QVBoxLayout())
        self.right.layout().setContentsMargins(0, 0, 0, 0)

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._pending_stacked: bool | None = None
        self._apply_layout(stacked=True)  # sicherer Startzustand, bis das erste echte Resize-Event kommt

    def resizeEvent(self, event):
        super().resizeEvent(event)
        should_stack = event.size().width() < (self._min_width_left + self._min_width_right + self._gap)
        if should_stack == self._stacked:
            return
        # Das Umbauen (Re-Parenting) erst NACH diesem Resize-Event ausführen
        # (statt direkt synchron mittendrin) - sonst kann eine Kettenreaktion
        # aus Resize -> Umbau -> erneutem Resize entstehen, die sich endlos
        # weiter aufschaukelt (v.a. innerhalb einer QScrollArea).
        self._pending_stacked = should_stack
        QTimer.singleShot(0, self._apply_pending_layout)

    def _apply_pending_layout(self) -> None:
        if self._pending_stacked is None or self._pending_stacked == self._stacked:
            return
        self._apply_layout(stacked=self._pending_stacked)

    def _apply_layout(self, stacked: bool) -> None:
        self._stacked = stacked
        self._pending_stacked = None

        # Alte Anordnung auflösen, ohne die Spalten-Widgets selbst zu zerstören.
        # Spalten-Widgets zuerst sich selbst zuordnen: sonst würden sie beim
        # gleich folgenden Aufräumen des alten "_row"-Zwischen-Widgets als
        # dessen Kinder mit zerstört (Qt löscht beim Löschen eines Widgets
        # automatisch auch alle seine Kind-Widgets).
        self.left.setParent(self)
        self.right.setParent(self)

        while self._outer.count():
            self._outer.takeAt(0)
        if hasattr(self, "_row"):
            self._row.deleteLater()
            del self._row

        if stacked:
            self._outer.addWidget(self.left)
            self._outer.addWidget(self.right)
        else:
            self._row = QWidget(self)
            row_layout = QHBoxLayout(self._row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(self._gap)
            row_layout.addWidget(self.left, self._left_stretch)
            row_layout.addWidget(self.right, self._right_stretch)
            self._outer.addWidget(self._row)


class ResizableSplitFrame(QSplitter):
    """Wie TwoColumnFrame (siehe oben), aber mit einem vom Nutzer per Maus
    verschiebbaren Trenner zwischen den beiden Bereichen (`.left`/`.right`)
    - z.B. um die Breite von Vorschau-Tabelle und Datei-Viewer selbst
    anzupassen. Wechselt bei schmalem Fenster automatisch auf vertikale
    Anordnung (übereinander) - auch dort bleibt der Trenner per Maus in der
    Höhe verschiebbar (im Unterschied zu TwoColumnFrame, das beim Stapeln
    keinen verschiebbaren Trenner hat).

    Benutzung wie TwoColumnFrame:
        split = ResizableSplitFrame()
        split.left.layout().addWidget(...)
        split.right.layout().addWidget(...)
    """

    def __init__(self, min_width_left: int = 300, min_width_right: int = 300,
                 left_stretch: int = 1, right_stretch: int = 1, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self._min_width_left = min_width_left
        self._min_width_right = min_width_right
        self._stacked = False
        self._pending_stacked: bool | None = None

        self.left = QWidget()
        self.left.setLayout(QVBoxLayout())
        self.left.layout().setContentsMargins(0, 0, 0, 0)
        self.right = QWidget()
        self.right.setLayout(QVBoxLayout())
        self.right.layout().setContentsMargins(0, 0, 0, 0)
        self.addWidget(self.left)
        self.addWidget(self.right)
        self.setStretchFactor(0, left_stretch)
        self.setStretchFactor(1, right_stretch)
        self.setChildrenCollapsible(False)
        self.setHandleWidth(6)

        # Anfängliches Größenverhältnis nach left_stretch/right_stretch -
        # verzögert, da beim Konstruieren selbst noch keine echte Breite
        # zur Verfügung steht (sizes() wäre sonst 0/0).
        QTimer.singleShot(0, lambda: self._apply_initial_sizes(left_stretch, right_stretch))

    def _apply_initial_sizes(self, left_stretch: int, right_stretch: int) -> None:
        total_size = sum(self.sizes()) or self.width()
        if total_size <= 0:
            return
        total_stretch = left_stretch + right_stretch
        self.setSizes([
            int(total_size * left_stretch / total_stretch),
            int(total_size * right_stretch / total_stretch),
        ])

    def resizeEvent(self, event):
        super().resizeEvent(event)
        should_stack = event.size().width() < (self._min_width_left + self._min_width_right)
        if should_stack == self._stacked:
            return
        # Wie bei TwoColumnFrame: Umschalten erst NACH diesem Resize-Event,
        # um eine Kettenreaktion aus Resize -> Umschalten -> erneutem Resize
        # zu vermeiden.
        self._pending_stacked = should_stack
        QTimer.singleShot(0, self._apply_pending_orientation)

    def _apply_pending_orientation(self) -> None:
        if self._pending_stacked is None or self._pending_stacked == self._stacked:
            return
        self._stacked = self._pending_stacked
        self._pending_stacked = None
        self.setOrientation(Qt.Vertical if self._stacked else Qt.Horizontal)


class InfoIcon(QLabel):
    """Ein kleines 'ℹ️'-Symbol. Klick zeigt standardmäßig den Hilfetext in
    einem Dialog - über `on_click` lässt sich das durch eine eigene Aktion
    ersetzen (z.B. einen eigenen, editierbaren Dialog statt der reinen
    Text-Anzeige)."""

    def __init__(self, text: str, title: str = "Hinweis", parent=None, on_click=None):
        super().__init__("ℹ️", parent)
        self._text = text
        self._title = title
        self._on_click = on_click
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setStyleSheet("font-weight: normal;")
        # Auch bei eigener on_click-Aktion bleibt der Text beim Hovern
        # sichtbar - kurzer Überblick, ohne extra klicken zu müssen.
        self.setToolTip(text)

    def mousePressEvent(self, event):
        if self._on_click is not None:
            self._on_click()
        else:
            # QMessageBox.information() stellt den Haupttext auf manchen
            # Plattformen (z.B. macOS) standardmäßig fett dar - per eigener
            # QMessageBox-Instanz mit Stylesheet stattdessen normal.
            box = QMessageBox(QMessageBox.Information, self._title, self._text, parent=self.window())
            box.setStyleSheet("QLabel { font-weight: normal; }")
            box.exec()


class AutoGrowTextEdit(QTextEdit):
    """Editierbares Textfeld, das nutzbar wie ein einzeiliges Eingabefeld ist
    (z.B. für die "Ergebnis"-Vorlage), aber - anders als QLineEdit - lange
    Inhalte per Wortumbruch anzeigt statt sie seitlich abzuschneiden, und
    dabei seine Höhe automatisch an den (umgebrochenen) Inhalt anpasst,
    begrenzt auf `min_lines`..`max_lines` (darüber hinaus scrollbar)."""

    def __init__(self, min_lines: int = 1, max_lines: int = 5, parent=None):
        super().__init__(parent)
        self._min_lines = min_lines
        self._max_lines = max_lines
        self.setAcceptRichText(False)
        self.setLineWrapMode(QTextEdit.WidgetWidth)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setTabChangesFocus(True)
        # documentSizeChanged (statt nur textChanged) reagiert auch, wenn
        # sich der Umbruch durch eine geänderte Fensterbreite verschiebt,
        # nicht nur bei geändertem Text.
        self.document().documentLayout().documentSizeChanged.connect(self._update_height)
        self._update_height()

    def _update_height(self, *_args) -> None:
        line_height = self.fontMetrics().height()
        margins = self.contentsMargins()
        extra = margins.top() + margins.bottom() + 2 * self.frameWidth() + 8
        min_height = line_height * self._min_lines + extra
        max_height = line_height * self._max_lines + extra
        target = int(self.document().size().height()) + extra
        self.setFixedHeight(max(min_height, min(target, max_height)))
