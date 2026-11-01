import ctypes
import logging
import json
import os
import re
import shutil
import sys
import threading
import time
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import List, Tuple

import markdown
import yaml
from PySide6.QtCore import (Qt, QAbstractTableModel, QSize, QDateTime, QFileSystemWatcher, QModelIndex,
                            QSettings, QSortFilterProxyModel, QThread, QTimer, QUrl, Signal)
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence, QRegularExpressionValidator, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
                               QScrollArea, QSpinBox, QSplitter, QTableView, QTextBrowser, QVBoxLayout, QWidget)

import GuiElement
import SupportedFormats
import ToolsPanel
import data.repository.DlcRepository as repository
import i18n
import naming
from ConfigLoader import app_dir, bundle_dir, load_config
from i18n import tr
from version import __version__

JSON = "json"
XML = "xml"

DEFAULT_INPUT_FOLDER_NAME = "My Songs"
DEFAULT_OUTPUT_FOLDER_NAME = "_Patch"
MAX_LOG_LINES = 5000

logger = logging.getLogger(__name__)

strip_accents = naming.strip_accents
construct_name_id_from_directory_name = naming.construct_name_id_from_directory_name

Icon = GuiElement.Icon


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------

class QtLogHandler(logging.Handler):
    """Logging handler that emits records via a Qt signal (thread-safe)."""

    def __init__(self, signal):
        super().__init__()
        self.signal = signal

    def emit(self, record):
        self.signal.emit(record.levelno, self.format(record))


class ConversionWorker(QThread):
    log_message = Signal(int, str)  # (level, text)
    progress = Signal(int, int)  # (current, total)
    song_state = Signal(str, str, str)  # (folder, state, detail)
    done = Signal(object)  # summary dict from ConvertFiles.main
    error = Signal(str)

    def __init__(self, cfg, stop_event, only_dirs=None):
        super().__init__()
        self.cfg = cfg
        self.stop_event = stop_event
        self.only_dirs = only_dirs

    def run(self):
        try:
            import ConvertFiles
        except Exception as e:
            self.error.emit(str(e))
            return

        handler = QtLogHandler(self.log_message)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter('%(message)s'))
        logging.getLogger().addHandler(handler)
        try:
            summary = ConvertFiles.main(self.cfg, stop_event=self.stop_event,
                                        progress_callback=self.progress.emit,
                                        song_callback=self.song_state.emit,
                                        only_dirs=self.only_dirs)
        except Exception as e:
            logger.exception("Conversion failed")
            self.error.emit(str(e))
            return
        finally:
            logging.getLogger().removeHandler(handler)
        self.done.emit(summary)


@dataclass
class SongRow:
    directory: str
    path: str
    name_id: str
    name_ids: list
    has_video: bool = False
    cached_video: bool = False
    has_audio: bool = False
    cached_audio: bool = False
    has_image: bool = False
    cached_image: bool = False
    has_txt: bool = False
    cached_txt: bool = False
    doubtful_sync: bool = False
    sync_note: str = ''  # result of the voice check (tools/sync_scan.py), when the song was checked
    official_vxla: bool = False
    still_video: bool = False  # the converted .bk2 is the still cover, not a video
    order: int = 0
    checked: bool = False
    state: str = ''  # '', running, ok, skipped, failed, stopped
    detail: str = ''

    @property
    def fully_cached(self):
        return self.cached_video and self.cached_audio and self.cached_image and self.cached_txt


VOICE_CHECK_TEXT = {'ok': "the lyrics are on the voice", 'parcial': "a part of the lyrics is out of time",
                    'desfase': "all the lyrics are early or late", 'otra_version': "the audio is another version",
                    'dudosa': "little of the voice matches the notes: check it by ear"}


def voice_check(directory_path, sidecar_name, txt_path, txt_mtime):
    """(verdict, text for the tooltip) of tools/sync_scan.py if it checked this same txt, else None."""
    try:
        with open(os.path.join(directory_path, sidecar_name), encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if data.get('txt') != txt_path.name or abs(float(data.get('txt_mtime', 0)) - (txt_mtime or 0)) > 1:
        return None  # the txt changed since (re-synced): the old result no longer applies
    verdict = data.get('verdict', '')
    text = tr(VOICE_CHECK_TEXT.get(verdict, verdict))
    if data.get('detail') and verdict != 'ok':
        text += f" ({data['detail']})"
    return verdict, tr("Voice check: {result}.").format(result=text)


def is_doubtful_sync(txt_path) -> bool:
    """Heuristic warning: negative GAP, odd BPM or lyrics starting in the first half second."""
    import UltrastarToSingit
    try:
        us_data = UltrastarToSingit.parse_file(txt_path)
        bpm = float(us_data.get("BPM", "100").replace(',', '.'))
        gap = float(us_data.get("GAP", "0").replace(',', '.') or 0)
        if gap < 0 or bpm > 400 or bpm < 50:
            return True
        for note in us_data.get("notes", []):
            if note[0] in [':', '*', 'F', 'R', 'G']:
                return float(note[1]) * 60 / bpm / 4 * 1000 + gap < 500
        return False
    except Exception:
        return False


def scan_song_folders(input_path: str, video_suffix: str, sync_cache: dict, only=None) -> list:
    """Reads the input folder (runs in a background thread). only: set of folder names to read."""
    import ConvertFiles
    rows = []
    names = sorted(os.listdir(input_path), key=str.lower) if only is None else sorted(only, key=str.lower)
    for directory in names:
        directory_path = os.path.join(input_path, directory)
        if not os.path.isdir(directory_path) or " - " not in directory or directory.startswith(('_', '.')):
            continue
        clean = directory.rstrip('.')
        name_id = construct_name_id_from_directory_name(clean)
        name_ids = naming.all_name_ids(clean)
        try:
            all_files = os.listdir(directory_path)
        except OSError:
            continue
        source_files = [x for x in all_files if not naming.is_generated_file(x, name_ids) and '.tmp.' not in x]
        lower = [x.lower() for x in source_files]
        row = SongRow(directory=directory, path=directory_path, name_id=name_id, name_ids=name_ids, order=len(rows))
        row.has_video = any(x.endswith(SupportedFormats.VIDEO_EXTENSIONS) for x in lower)
        row.has_audio = any(x.endswith(SupportedFormats.AUDIO_EXTENSIONS) for x in lower)
        row.has_image = any(x.endswith(SupportedFormats.IMAGE_EXTENSIONS) for x in lower)
        row.has_txt = any(x.endswith(SupportedFormats.TXT_EXTENSIONS) for x in lower)
        row.cached_video = (name_id + video_suffix) in all_files
        row.cached_audio = (name_id + naming.AUDIO_SUFFIX) in all_files
        row.cached_image = (name_id + naming.COVER_SUFFIX) in all_files
        row.cached_txt = (name_id + naming.VXLA_SUFFIX) in all_files
        row.official_vxla = naming.OFFICIAL_VXLA_NAME in all_files
        if row.cached_video and video_suffix == naming.VIDEO_BK2_SUFFIX:
            try:
                with open(os.path.join(directory_path, name_id + naming.VXLA_META_SUFFIX), encoding='utf-8') as f:
                    duration = json.load(f).get('duration')
                if duration:
                    row.still_video = ConvertFiles.is_still_bk2(Path(directory_path) / (name_id + video_suffix),
                                                                duration)
            except (OSError, ValueError):
                pass

        txt_files = [Path(directory_path) / x for x in source_files if x.lower().endswith('.txt')]
        txt_path = ConvertFiles.choose_txt_file(txt_files) if txt_files else None
        if txt_path is not None:
            try:
                mtime = txt_path.stat().st_mtime
            except OSError:
                mtime = None
            cached = sync_cache.get(str(txt_path))
            if cached and cached[0] == mtime:
                row.doubtful_sync = cached[1]
            else:
                row.doubtful_sync = is_doubtful_sync(txt_path)
                sync_cache[str(txt_path)] = (mtime, row.doubtful_sync)
            checked = voice_check(directory_path, name_id + naming.SYNC_REPORT_SUFFIX, txt_path, mtime)
            if checked:  # the voice check knows better than the guess from the txt
                row.doubtful_sync = checked[0] != 'ok'
                row.sync_note = checked[1]
        rows.append(row)
    return rows


class ScanWorker(QThread):
    scanned = Signal(object, int)  # (rows, generation)

    def __init__(self, input_path, video_suffix, sync_cache, generation):
        super().__init__()
        self.input_path = input_path
        self.video_suffix = video_suffix
        self.sync_cache = sync_cache
        self.generation = generation

    def run(self):
        try:
            rows = scan_song_folders(self.input_path, self.video_suffix, self.sync_cache)
        except Exception as e:
            logger.error(f"Error scanning input folder: {e}")
            rows = []
        self.scanned.emit(rows, self.generation)


# ---------------------------------------------------------------------------
# Song table
# ---------------------------------------------------------------------------

COL_CHECK, COL_NAME, COL_STATUS, COL_VIDEO, COL_AUDIO, COL_IMAGE, COL_LYRICS, COL_SYNC, COL_PLAY = range(9)
HEADERS = ["", "Song", "Status", "Video", "Audio", "Image", "Lyrics", "Sync", "Play"]
STATE_TEXT = {
    'running': "Converting…", 'ok': "Converted", 'skipped': "Skipped", 'failed': "Error", 'stopped': "Stopped",
}


class SongTableModel(QAbstractTableModel):
    checked_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: List[SongRow] = []
        self.playing_path = None

    # --- data ---
    def set_rows(self, rows):
        previous = {r.directory: r for r in self.rows}
        for r in rows:
            old = previous.get(r.directory)
            if old is not None:
                r.checked, r.state, r.detail = old.checked, old.state, old.detail
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()
        self.checked_changed.emit()

    def row_of(self, directory):
        for i, r in enumerate(self.rows):
            if r.directory == directory:
                return i
        return -1

    def update_state(self, directory, state, detail=''):
        i = self.row_of(directory)
        if i < 0:
            return
        self.rows[i].state, self.rows[i].detail = state, detail
        self.dataChanged.emit(self.index(i, 0), self.index(i, self.columnCount() - 1))

    def refresh_row(self, directory, new_row):
        i = self.row_of(directory)
        if i < 0 or new_row is None:
            return
        old = self.rows[i]
        new_row.checked, new_row.state, new_row.detail, new_row.order = old.checked, old.state, old.detail, old.order
        self.rows[i] = new_row
        self.dataChanged.emit(self.index(i, 0), self.index(i, self.columnCount() - 1))

    def checked_rows(self):
        return [r for r in self.rows if r.checked]

    def set_checked(self, rows, checked):
        for r in rows:
            r.checked = checked
        if self.rows:
            self.dataChanged.emit(self.index(0, COL_CHECK), self.index(len(self.rows) - 1, COL_CHECK))
        self.checked_changed.emit()

    def set_playing(self, path):
        self.playing_path = path
        if self.rows:
            self.dataChanged.emit(self.index(0, COL_PLAY), self.index(len(self.rows) - 1, COL_PLAY))

    # --- Qt model API ---
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return tr(HEADERS[section]) if HEADERS[section] else ""
        if orientation == Qt.Horizontal and role == Qt.ToolTipRole:
            tips = {COL_CHECK: "Mark songs for 'Convert checked' and 'Clear cache'",
                    COL_VIDEO: "✓ source file found · database icon: converted file cached",
                    COL_SYNC: "Open the sync editor (orange: possible desync)",
                    COL_PLAY: "Play the song"}
            return tr(tips[section]) if section in tips else None
        return None

    def flags(self, index):
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == COL_CHECK:
            base |= Qt.ItemIsUserCheckable
        return base

    @staticmethod
    def _file_icon(has_source, cached):
        icon = Icon.CHECK.get_icon() if (has_source or cached) else Icon.X.get_icon()
        return GuiElement.combine_icons(icon, Icon.FILE_CHECK.get_icon()) if cached else icon

    def _status(self, r: SongRow):
        if r.state in STATE_TEXT:
            icon = {'running': Icon.STATUS_RUNNING, 'ok': Icon.STATUS_OK, 'skipped': Icon.STATUS_SKIPPED,
                    'failed': Icon.STATUS_ERROR, 'stopped': Icon.STATUS_SKIPPED}[r.state]
            return tr(STATE_TEXT[r.state]), icon
        if r.fully_cached:
            return tr("Cached"), Icon.STATUS_CACHED
        return tr("Pending"), Icon.STATUS_PENDING

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        r = self.rows[index.row()]
        col = index.column()
        if role == Qt.CheckStateRole and col == COL_CHECK:
            return Qt.Checked if r.checked else Qt.Unchecked
        if col == COL_NAME:
            if role in (Qt.DisplayRole, Qt.ToolTipRole):
                return r.directory if role == Qt.DisplayRole else f"{r.directory}\nID: {r.name_id}"
        if col == COL_STATUS:
            text, icon = self._status(r)
            if role == Qt.DisplayRole:
                return text
            if role == Qt.DecorationRole:
                return icon.get_icon()
            if role == Qt.ToolTipRole:
                return r.detail or text
        icons = {COL_VIDEO: (r.has_video, r.cached_video), COL_AUDIO: (r.has_audio, r.cached_audio),
                 COL_IMAGE: (r.has_image, r.cached_image), COL_LYRICS: (r.has_txt, r.cached_txt)}
        if col == COL_VIDEO and r.still_video:
            if role == Qt.DecorationRole:
                return GuiElement.combine_icons(Icon.ALERT_TRIANGLE.get_icon(), Icon.FILE_CHECK.get_icon())
            if role == Qt.ToolTipRole:
                return tr("The converted video is the still cover. Put the song's video in its folder (named like "
                          "the folder, e.g. \"{name}.mp4\") and convert it: the still .bk2 is replaced (the old one "
                          "is kept in _replaced_videos).").format(name=r.directory)
        if col in icons and role == Qt.DecorationRole:
            return self._file_icon(*icons[col])
        if col == COL_LYRICS and role == Qt.ToolTipRole and r.official_vxla:
            return tr("Official Let's Sing lyrics and notes (exact timing and pitch)")
        if col == COL_SYNC:
            if role == Qt.DecorationRole:
                return (Icon.SYNC_WARNING if r.doubtful_sync else Icon.SYNC).get_icon()
            if role == Qt.ToolTipRole:
                if r.sync_note:
                    return r.sync_note + " " + tr("Click to open the sync editor.")
                return tr("Possible desync detected (negative GAP, odd BPM or lyrics at the very start). "
                          "Click to open the sync editor.") if r.doubtful_sync else tr("Open the sync editor")
        if col == COL_PLAY:
            if role == Qt.DecorationRole:
                return (Icon.PAUSE if self.playing_path == r.path else Icon.PLAY).get_icon()
            if role == Qt.ToolTipRole:
                return tr("Play / pause the song")
        if role == Qt.UserRole:  # sort key
            if col == COL_NAME:
                return r.directory.lower()
            if col == COL_STATUS:
                return self._status(r)[0]
            if col in icons:
                return int(icons[col][0]) + 2 * int(icons[col][1]) - (3 if col == COL_VIDEO and r.still_video else 0)
            if col == COL_SYNC:
                return int(r.doubtful_sync)
            return r.order
        if role == Qt.TextAlignmentRole and col not in (COL_NAME, COL_STATUS):
            return Qt.AlignCenter
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if role == Qt.CheckStateRole and index.column() == COL_CHECK:
            self.rows[index.row()].checked = Qt.CheckState(value) == Qt.Checked
            self.dataChanged.emit(index, index)
            self.checked_changed.emit()
            return True
        return False


class SongFilterModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSortRole(Qt.UserRole)
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.setFilterKeyColumn(COL_NAME)
        self.only_problems = False

    def filterAcceptsRow(self, source_row, source_parent):
        if self.only_problems:
            r = self.sourceModel().rows[source_row]
            if r.state not in ('skipped', 'failed') and not r.doubtful_sync and not r.still_video:
                return False
        return super().filterAcceptsRow(source_row, source_parent)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def set_element_enabled(element, is_enabled: bool) -> None:
    if not is_enabled and isinstance(element, QLineEdit):
        mark_field_valid(element, True)
    element.setEnabled(is_enabled)


def mark_field_valid(line_edit: QLineEdit, valid: bool) -> None:
    line_edit.setProperty("has_border", "true" if not valid else "false")
    line_edit.style().unpolish(line_edit)
    line_edit.style().polish(line_edit)
    line_edit.update()


def set_dark_title_bar(hwnd: int, dark: bool) -> None:
    dwmwa_use_immersive_dark_mode = 20
    value = ctypes.c_int(1 if dark else 0)
    ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, dwmwa_use_immersive_dark_mode,
                                               ctypes.byref(value), ctypes.sizeof(value))


BASE_STYLE = """
    QLineEdit { min-height: 20px; }
    QLineEdit[has_border="true"] { border: 1px solid #b0534c; }
    QGroupBox { font-weight: bold; margin-top: 8px; }
    QGroupBox::title { subcontrol-origin: margin; left: 6px; padding: 0 3px; }
    QPushButton#primary { font-weight: bold; padding: 4px 14px; }
"""


def apply_theme_change(theme, app, window=None) -> None:
    is_dark = theme.name == 'Dark'
    if is_dark:
        tooltip_style = "QToolTip { color: #ffffff; background-color: #2d2d2d; border: 1px solid #555555; padding: 4px; }"
    else:
        tooltip_style = "QToolTip { color: #000000; background-color: #f5f5f0; border: 1px solid #aaaaaa; padding: 4px; }"
    app.setStyleSheet(BASE_STYLE + tooltip_style)  # replaced, not appended on every theme change
    if window is not None and sys.platform == 'win32':
        set_dark_title_bar(int(window.winId()), is_dark)


def is_blank(s) -> bool:
    return not (s and not str(s).isspace())


def open_in_file_manager(path):
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.cfg = load_config()
        lang = getattr(self.cfg, 'language', None) or 'en'
        i18n.load_language(lang)

        self.game_format = JSON
        self._loading_defaults = True
        self._texts = []  # (setter, english text) for every translatable text, see t()
        self._sync_cache = {}
        self._scan_generation = 0
        self._scan_worker = None
        self._rescan_pending = False
        self._stop_event = None
        self._worker = None
        self.conversion_running = False
        self.conversion_start_time = 0.0
        self.estimated_finish_time = 0.0
        self.progress_current = 0
        self.progress_total = 0
        self.settings = QSettings("LetsSingUltraStarConverter", "Converter")

        self.int_validator = QRegularExpressionValidator('(^[0-9]+$|^$)')
        self.setWindowTitle(f"Let's Sing UltraStar Converter v{__version__}")
        self.setWindowIcon(QIcon(os.path.join(bundle_dir(), "assets", "logo.ico")))

        self.init_elements()
        self.build_menus()
        self.build_layout()
        self.build_shortcuts()

        self.tick_timer = QTimer(self)
        self.tick_timer.setInterval(1000)
        self.tick_timer.timeout.connect(self.tick_progress)

        self.folder_watcher = QFileSystemWatcher(self)
        self.folder_watcher.directoryChanged.connect(self.schedule_watcher_refresh)
        self.watcher_debounce = QTimer(self)
        self.watcher_debounce.setSingleShot(True)
        self.watcher_debounce.setInterval(800)
        self.watcher_debounce.timeout.connect(self.do_watcher_refresh)

        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.mediaStatusChanged.connect(self.on_media_status_changed)

        self.field_validators = {
            self.core_id_input: self.core_id_input_fv,
            self.dlc_id_input: self.dlc_id_input_fv,
            self.dlc_json_name_input: self.dlc_json_name_input_fv,
            self.ffmpeg_path: self.ffmpeg_path_fv,
            self.rad_path: self.rad_path_fv,
            self.input_path: self.input_path_fv,
            self.max_video_size: self.max_video_size_fv,
            self.output_path: self.output_path_fv,
            self.dlc_name_txt_path: self.dlc_name_txt_path_fv,
            self.dlc_tsv_path: self.dlc_tsv_path_fv,
            self.dlc_json_path: self.dlc_json_path_fv,
        }

        self.set_defaults()
        self._loading_defaults = False
        self.restore_window_state()
        self.update_language_actions()
        self.scan_input_folder()

    # ------------------------------------------------------------------ i18n
    def t(self, setter, text):
        """Sets a translated text and remembers it, so changing the language updates every text."""
        self._texts.append((setter, text))
        setter(tr(text))

    def update_ui_language(self):
        for setter, text in self._texts:
            setter(tr(text))
        self.song_model.headerDataChanged.emit(Qt.Horizontal, 0, len(HEADERS) - 1)
        self.song_model.layoutChanged.emit()
        self.update_counts()

    def on_language_changed(self, lang):
        i18n.load_language(lang)
        self.cfg.language = lang
        self.update_ui_language()
        self.update_language_actions()
        if not self.conversion_running:
            self.save_config()

    def update_language_actions(self):
        lang = getattr(self.cfg, 'language', None) or 'en'
        self.action_en.setChecked(lang == 'en')
        self.action_es.setChecked(lang == 'es')

    # ------------------------------------------------------------------ widgets
    def init_elements(self):
        def label(text):
            w = QLabel()
            self.t(w.setText, text)
            return w

        def button(text, icon=None, tooltip=None):
            w = QPushButton()
            self.t(w.setText, text)
            if icon is not None:
                w.setIcon(icon.get_icon())
            if tooltip:
                self.t(w.setToolTip, tooltip)
            return w

        def checkbox(text, tooltip=None):
            w = QCheckBox()
            self.t(w.setText, text)
            if tooltip:
                self.t(w.setToolTip, tooltip)
            return w

        def line_edit(max_length, tooltip=None):
            w = QLineEdit()
            w.setMaxLength(max_length)
            if tooltip:
                self.t(w.setToolTip, tooltip)
            return w

        self.lets_sing_label = label("Let's Sing:")
        self.core_id_label = label('Core TitleID:')
        self.dlc_name_label = label('DLC Name:')
        self.dlc_id_label = label('DLC TitleID:')
        self.dlc_json_name_label = label('DLC JSON Name:')
        self.ffmpeg_label = label('FFmpeg:')
        self.rad_label = label('RAD Video Tools:')
        self.input_label = label('Input folder:')
        self.output_label = label('Output folder:')
        self.name_txt_label = label('name.txt:')
        self.songs_dlc_label = label('SongsDLC.tsv:')
        self.songs_json_label = label('Base songs_xx.json:')
        self.max_video_label = label('Max video size (MB):')
        self.threads_label = label('Threads:')
        self.t(self.songs_json_label.setToolTip,
               "Add your songs_xx.json (or a previous combined one) here to keep the DLC songs or songs you converted before.")

        self.core_edition_combo = QComboBox()
        self.dlc_name_combo = QComboBox()

        self.core_id_input = line_edit(16, "The unique TitleID of the base game (e.g., 0100CC30149B8000 for Let's Sing 2022).")
        self.dlc_id_input = line_edit(16, "The unique TitleID of the DLC which will be patched (e.g., 0100CC30149B9011 for Let's Sing 2022).")
        self.dlc_json_name_input = line_edit(32, "The name of the DLC metadata file in JSON format, used for Let's Sing 2024 and onward "
                                                 "(e.g., songs_fr for the French Hits DLC for Let's Sing 2025).\n\n"
                                                 "This name can be found in the name.txt file located in [DLC TITLEID]/romfs/name.txt")
        self.rad_path = line_edit(512, "Path to RAD Video Tools. Required for Let's Sing 2024 and onward for converting videos to bk2 format.")
        self.ffmpeg_path = line_edit(512, "Path to the FFmpeg release. Used for converting videos/audio/images to the format required by Let's Sing.")
        self.input_path = line_edit(512, "Path to the folder containing the UltraStar song folders.\n"
                                         "Song folders should be named as 'Artist - Song Title' and contain the txt and media files.\n\n"
                                         "Note: The program will cache the converted files in these song folders.")
        self.output_path = line_edit(512, "Path to the output folder.\n\nSAFETY FEATURE: if the selected folder contains anything other "
                                          "than TitleID folders, '_Patch' is appended so your personal files are never deleted "
                                          "(the output folder is wiped before a full conversion).")
        self.warning_action = self.output_path.addAction(Icon.ALERT_TRIANGLE.get_icon(), QLineEdit.TrailingPosition)
        self.t(self.warning_action.setToolTip, "Warning: the output folder is deleted before a full conversion. "
                                               "Converted .bk2 videos in your song folders are never deleted.")
        self.dlc_name_txt_path = line_edit(512, "Path to the name.txt file from the DLC. It contains either the list of song IDs "
                                                "(prior to Let's Sing 2024) or the name of the DLC metadata JSON file (2024 and onward).\n\n"
                                                "The file is located in [DLC TITLEID]/romfs/name.txt")
        self.dlc_tsv_path = line_edit(512, "Path to the SongsDLC.tsv file of the game (prior to Let's Sing 2024).\n\n"
                                           "The file is located in [CORE TITLEID]/romfs/Data/StreamingAssets/SongsDLC.tsv")
        self.dlc_json_path = line_edit(512, "Path to the songs_xx.json file from the DLC (Let's Sing 2024 and onward).\n\n"
                                            "The file is located in [DLC TITLEID]/romfs/songs_xx.json")
        self.max_video_size = line_edit(8, "Maximum size of each converted video. Lower values make a smaller patch with lower video quality.")

        browse = "Browse"
        self.rad_browse = button(browse)
        self.ffmpeg_browse = button(browse)
        self.input_input_browse = button(browse)
        self.output_browse = button(browse)
        self.name_txt_browse = button(browse)
        self.songs_dlc_browse = button(browse)
        self.songs_json_browse = button(browse)
        self.open_input_button = button("Open", Icon.FOLDER, "Open the input folder")
        self.open_output_button = button("Open", Icon.FOLDER, "Open the output folder")

        self.help_button = button("Help", Icon.INFO_SQUARE_ROUNDED, "Show what this program does and how to use it.")
        self.clear_logs_button = button("Clear logs", Icon.TRASH)
        self.open_error_log_button = button("Open error.log", Icon.FOLDER)
        self.refresh_button = button("Refresh", Icon.REFRESH, "Refresh the song list (F5).")
        self.clear_cache_button = button("Clear cache", Icon.FILE_X,
                                         "Delete the converted files of the checked songs. Converted .bk2 videos are protected.")
        self.stop_button = button("Stop", Icon.STOP, "Stop the conversion (Esc). Finished files stay in the cache.")
        self.convert_checked_button = button("Convert checked", Icon.CONVERT_SELECTED,
                                             "Convert only the checked songs and update the existing patch "
                                             "(the output folder is not cleared).")
        self.start_button = button("Start conversion", Icon.START,
                                   "Convert every song (Ctrl+Enter). Cached videos, audio and images are reused.")
        self.start_button.setObjectName("primary")

        self.include_dlc_checkbox = checkbox(
            "Copy DLC Media Files (audio/video) from base JSON directory to Output",
            "Merges the songs of your songs_xx.json into the new file and, if a 'Songs' folder exists next to that json, "
            "copies its audio/video files to the output. Nothing is downloaded: they are copied from your PC.")
        self.still_video_checkbox = checkbox(
            "Use cover image instead of video (very fast)",
            "Skip encoding the music videos: a static video is made from the cover image. Much faster and a smaller "
            "patch. Already converted videos are still used.")
        self.pitch_correction_checkbox = checkbox(
            "Analyze song vocals for pitch correction (Includes Vocal Isolation)",
            "UltraStar files often have lower pitch values than Let's Sing expects.\n\nChecked: analyze each song with the "
            "CREPE neural pitch tracker after isolating the vocals (slow, needs the optional modules).\n"
            "Unchecked: fast correction by whole octaves.")
        self.ignore_medley_checkbox = checkbox(
            "Ignore the UltraStar medley tags for finding chorus sections",
            "Medley tags are sometimes wrong and mark non-chorus parts as choruses. Check to rely on the other chorus "
            "detection methods instead.")
        self.force_reconvert_checkbox = checkbox(
            "Force re-generate lyrics/notes (.vxla) — videos are never re-encoded",
            "Regenerates the lyrics/notes files even if nothing changed. Converted videos, audio and covers are kept.")
        self.multithread_checkbox = checkbox("Enable Multithreading (faster conversion)")
        self.clear_output_checkbox = checkbox(
            "Clear output folder before converting",
            "Deletes the output folder before a full conversion. Your song folders and their cached conversions are not "
            "touched; a .bk2 that only exists in the output is copied back first.")
        self.keep_accents_checkbox = checkbox("Keep accents in lyrics (é, ñ, ç...)",
                                              "Keeps every character the game's lyrics files support (é, à, ñ, ç, ü, ¿, ¡...).")
        self.genius_checkbox = checkbox(
            "Look up choruses on the internet (Genius)",
            "Downloads each song's lyrics page from genius.com to find the chorus (a few hundred KB per song, cached "
            "afterwards). Turn it off on mobile data: medley tags or automatic detection are used instead.")
        self.multithread_workers = QSpinBox()
        self.multithread_workers.setRange(1, 16)
        self.multithread_workers.setValue(3)

        self.song_model = SongTableModel(self)
        self.song_proxy = SongFilterModel(self)
        self.song_proxy.setSourceModel(self.song_model)
        self.song_view = QTableView()
        self.song_view.setModel(self.song_proxy)
        self.song_view.setSortingEnabled(True)
        self.song_view.sortByColumn(COL_NAME, Qt.AscendingOrder)
        self.song_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.song_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.song_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.song_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.song_view.setAlternatingRowColors(True)
        self.song_view.setIconSize(QSize(GuiElement.ICON_SIZE * 2, GuiElement.ICON_SIZE))
        self.song_view.verticalHeader().setVisible(False)
        self.song_view.verticalHeader().setDefaultSectionSize(24)
        header = self.song_view.horizontalHeader()
        header.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        for col, width in ((COL_CHECK, 28), (COL_STATUS, 130), (COL_VIDEO, 58), (COL_AUDIO, 58), (COL_IMAGE, 58),
                           (COL_LYRICS, 58), (COL_SYNC, 44), (COL_PLAY, 44)):
            header.setSectionResizeMode(col, QHeaderView.Interactive if col == COL_STATUS else QHeaderView.Fixed)
            self.song_view.setColumnWidth(col, width)

        self.logs_text = QPlainTextEdit()
        self.logs_text.setReadOnly(True)
        self.logs_text.setMaximumBlockCount(MAX_LOG_LINES)
        self.log_filter = QComboBox()
        for text, level in (("All messages", logging.DEBUG), ("Warnings and errors", logging.WARNING),
                            ("Errors only", logging.ERROR)):
            self.log_filter.addItem(tr(text), level)
        self._texts.append((lambda _t, c=self.log_filter: [c.setItemText(i, tr(x)) for i, x in enumerate(
            ("All messages", "Warnings and errors", "Errors only"))], ''))

    def build_menus(self):
        menu_bar = self.menuBar()
        self.language_menu = menu_bar.addMenu("")
        self.t(self.language_menu.setTitle, "Language")
        self.action_en = self.language_menu.addAction("English")
        self.action_es = self.language_menu.addAction("Español")
        for action, lang in ((self.action_en, 'en'), (self.action_es, 'es')):
            action.setCheckable(True)
            action.triggered.connect(lambda _c=False, l=lang: self.on_language_changed(l))

        tools_menu = menu_bar.addMenu("")
        self.t(tools_menu.setTitle, "Tools")
        recover_action = tools_menu.addAction("")
        self.t(recover_action.setText, "Recover cache from output")
        recover_action.triggered.connect(self.tool_recover_cache)
        unpack_action = tools_menu.addAction("")
        self.t(unpack_action.setText, "Unpack DLC songs to the input folder")
        unpack_action.triggered.connect(self.tool_unpack_output)

        help_menu = menu_bar.addMenu("")
        self.t(help_menu.setTitle, "Help")
        guide_action = help_menu.addAction("")
        self.t(guide_action.setText, "User guide")
        guide_action.triggered.connect(self.show_help)

    def build_layout(self):
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.create_left_panel())
        scroll.setMinimumWidth(380)
        splitter.addWidget(scroll)
        splitter.addWidget(self.create_right_panel())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        self.main_splitter = splitter
        self.setCentralWidget(splitter)
        self.counts_label = QLabel()
        self.statusBar().addPermanentWidget(self.counts_label)

    def build_shortcuts(self):
        QShortcut(QKeySequence.Find, self, activated=lambda: (self.search_input.setFocus(), self.search_input.selectAll()))
        QShortcut(QKeySequence(Qt.Key_F5), self, activated=self.refresh_preview)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.start_conversion)
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.stop_conversion)

    def create_left_panel(self) -> QWidget:
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        # Game info
        self.game_info_group = QGroupBox()
        self.t(self.game_info_group.setTitle, "1. Game and DLC")
        form = QFormLayout()
        self.core_id_input.editingFinished.connect(self.core_id_input_fv)
        self.dlc_id_input.editingFinished.connect(self.dlc_id_input_fv)
        self.dlc_json_name_input.editingFinished.connect(self.dlc_json_name_input_fv)
        self.core_edition_combo.currentTextChanged.connect(self.core_edition_combo_fv)
        self.dlc_name_combo.currentTextChanged.connect(self.dlc_name_combo_fv)
        for core in repository.get_core_editions():
            self.core_edition_combo.addItem(core.core_edition, userData={"core_id": core.core_id})
        self.core_edition_combo.addItem("other", userData={"core_id": None})
        form.addRow(self.lets_sing_label, self.core_edition_combo)
        form.addRow(self.core_id_label, self.core_id_input)
        form.addRow(self.dlc_name_label, self.dlc_name_combo)
        form.addRow(self.dlc_id_label, self.dlc_id_input)
        form.addRow(self.dlc_json_name_label, self.dlc_json_name_input)
        self.game_info_group.setLayout(form)
        left_layout.addWidget(self.game_info_group)

        # Tools
        self.tools_group = QGroupBox()
        self.t(self.tools_group.setTitle, "2. Conversion tools")
        grid = QGridLayout()
        grid.addWidget(self.ffmpeg_label, 0, 0)
        self.ffmpeg_path.editingFinished.connect(self.ffmpeg_path_fv)
        grid.addWidget(self.ffmpeg_path, 0, 1)
        self.ffmpeg_browse.clicked.connect(lambda: self.browse_file(self.ffmpeg_path, "ffmpeg (ffmpeg ffmpeg.exe);;All Files (*)"))
        grid.addWidget(self.ffmpeg_browse, 0, 2)
        grid.addWidget(self.rad_label, 1, 0)
        self.rad_path.editingFinished.connect(self.rad_path_fv)
        grid.addWidget(self.rad_path, 1, 1)
        self.rad_browse.clicked.connect(lambda: self.browse_file(self.rad_path, "radvideo64 (*.exe);;All Files (*)"))
        grid.addWidget(self.rad_browse, 1, 2)
        grid.setColumnStretch(1, 1)
        self.tools_group.setLayout(grid)
        left_layout.addWidget(self.tools_group)

        # Folders
        self.folders_group = QGroupBox()
        self.t(self.folders_group.setTitle, "3. Input and output folders")
        grid = QGridLayout()
        grid.addWidget(self.input_label, 0, 0)
        self.input_path.editingFinished.connect(self.input_path_fv)
        grid.addWidget(self.input_path, 0, 1)
        self.input_input_browse.clicked.connect(lambda: self.browse_folder(self.input_path))
        grid.addWidget(self.input_input_browse, 0, 2)
        self.open_input_button.clicked.connect(lambda: open_in_file_manager(self.input_path.text().strip()))
        grid.addWidget(self.open_input_button, 0, 3)
        grid.addWidget(self.output_label, 1, 0)
        self.output_path.editingFinished.connect(self.output_path_fv)
        grid.addWidget(self.output_path, 1, 1)
        self.output_browse.clicked.connect(lambda: self.browse_folder(self.output_path))
        grid.addWidget(self.output_browse, 1, 2)
        self.open_output_button.clicked.connect(self.open_output_folder)
        grid.addWidget(self.open_output_button, 1, 3)
        grid.addWidget(self.songs_json_label, 2, 0)
        self.dlc_json_path.editingFinished.connect(self.dlc_json_path_fv)
        grid.addWidget(self.dlc_json_path, 2, 1)
        self.songs_json_browse.clicked.connect(lambda: self.browse_file(self.dlc_json_path, "JSON (*.json)"))
        grid.addWidget(self.songs_json_browse, 2, 2)
        self.include_dlc_checkbox.clicked.connect(self.include_dlc_checkbox_refresh)
        grid.addWidget(self.include_dlc_checkbox, 3, 0, 1, 4)
        grid.setColumnStretch(1, 1)
        self.folders_group.setLayout(grid)
        left_layout.addWidget(self.folders_group)

        # Advanced settings
        self.tweaks_group = QGroupBox()
        self.t(self.tweaks_group.setTitle, "4. Advanced settings")
        tweaks_layout = QVBoxLayout()
        grid = QGridLayout()
        grid.addWidget(self.name_txt_label, 0, 0)
        self.dlc_name_txt_path.editingFinished.connect(self.dlc_name_txt_path_fv)
        grid.addWidget(self.dlc_name_txt_path, 0, 1)
        self.name_txt_browse.clicked.connect(lambda: self.browse_file(self.dlc_name_txt_path, "name (*.txt)"))
        grid.addWidget(self.name_txt_browse, 0, 2)
        grid.addWidget(self.songs_dlc_label, 1, 0)
        self.dlc_tsv_path.editingFinished.connect(self.dlc_tsv_path_fv)
        grid.addWidget(self.dlc_tsv_path, 1, 1)
        self.songs_dlc_browse.clicked.connect(lambda: self.browse_file(self.dlc_tsv_path, "SongsDLC (*.tsv)"))
        grid.addWidget(self.songs_dlc_browse, 1, 2)
        tweaks_layout.addLayout(grid)

        for w in (self.pitch_correction_checkbox, self.still_video_checkbox, self.ignore_medley_checkbox,
                  self.keep_accents_checkbox, self.genius_checkbox, self.force_reconvert_checkbox,
                  self.clear_output_checkbox):
            tweaks_layout.addWidget(w)
        mt_layout = QHBoxLayout()
        self.multithread_checkbox.toggled.connect(self.multithread_workers.setEnabled)
        mt_layout.addWidget(self.multithread_checkbox)
        mt_layout.addWidget(self.threads_label)
        mt_layout.addWidget(self.multithread_workers)
        self.recommended_button = QPushButton()
        self.recommended_button.setFlat(True)
        self.recommended_button.clicked.connect(
            lambda: self.multithread_workers.setValue(self.recommended_button.property('workers') or 1))
        mt_layout.addWidget(self.recommended_button)
        self._texts.append((lambda _t: self.update_recommended_workers(), ''))
        self.update_recommended_workers()
        mt_layout.addStretch()
        tweaks_layout.addLayout(mt_layout)
        max_video_layout = QHBoxLayout()
        max_video_layout.addWidget(self.max_video_label)
        self.max_video_size.setValidator(self.int_validator)
        self.max_video_size.setMaximumWidth(70)
        self.max_video_size.editingFinished.connect(self.max_video_size_fv)
        max_video_layout.addWidget(self.max_video_size)
        max_video_layout.addStretch()
        tweaks_layout.addLayout(max_video_layout)

        tweaks_content = QWidget()
        tweaks_content.setLayout(tweaks_layout)
        outer = QVBoxLayout()
        outer.addWidget(tweaks_content)
        self.tweaks_group.setLayout(outer)
        self.tweaks_group.toggled.connect(tweaks_content.setVisible)
        self.tweaks_group.setCheckable(True)
        self.tweaks_group.setChecked(False)
        self.t(self.tweaks_group.setToolTip, "Unchecked: the default settings are used.")
        left_layout.addWidget(self.tweaks_group)
        self.tools_panel = ToolsPanel.ToolsPanel(self)
        left_layout.addWidget(self.tools_panel)
        left_layout.addStretch()

        help_layout = QHBoxLayout()
        self.help_button.clicked.connect(self.show_help)
        help_layout.addWidget(self.help_button)
        help_layout.addStretch()
        left_layout.addLayout(help_layout)
        return left_widget

    def create_right_panel(self) -> QWidget:
        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)

        # Songs
        songs_group = QGroupBox()
        self.t(songs_group.setTitle, "Songs in the input folder")
        layout = QVBoxLayout()
        top = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setClearButtonEnabled(True)
        self.t(self.search_input.setPlaceholderText, "Search songs (Ctrl+F)...")
        self.search_input.textChanged.connect(self.on_search_changed)
        top.addWidget(self.search_input, stretch=1)
        self.only_problems_checkbox = QCheckBox()
        self.t(self.only_problems_checkbox.setText, "Only problems")
        self.t(self.only_problems_checkbox.setToolTip, "Show only songs with errors, skipped songs, possible desync or a still image as video.")
        self.only_problems_checkbox.toggled.connect(self.on_only_problems)
        top.addWidget(self.only_problems_checkbox)
        self.check_all_checkbox = QCheckBox()
        self.t(self.check_all_checkbox.setText, "Check all visible")
        self.check_all_checkbox.clicked.connect(self.on_check_all)
        top.addWidget(self.check_all_checkbox)
        layout.addLayout(top)

        self.song_view.clicked.connect(self.on_table_clicked)
        self.song_view.doubleClicked.connect(self.on_table_double_clicked)
        self.song_view.customContextMenuRequested.connect(self.on_table_context_menu)
        self.song_model.checked_changed.connect(self.update_clear_cache_enabled)
        layout.addWidget(self.song_view)
        layout.addWidget(self.build_preview_legend())

        progress = QHBoxLayout()
        self.elapsed_label = QLabel("")
        self.elapsed_label.setStyleSheet("color: #888888;")
        progress.addWidget(self.elapsed_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v/%m  (%p%)")
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setVisible(False)
        progress.addWidget(self.progress_bar, stretch=1)
        self.remaining_label = QLabel("")
        self.remaining_label.setStyleSheet("color: #888888;")
        progress.addWidget(self.remaining_label)
        layout.addLayout(progress)

        buttons = QHBoxLayout()
        self.refresh_button.clicked.connect(self.refresh_preview)
        buttons.addWidget(self.refresh_button)
        self.clear_cache_button.clicked.connect(self.clear_cache)
        buttons.addWidget(self.clear_cache_button)
        buttons.addStretch()
        self.stop_button.clicked.connect(self.stop_conversion)
        buttons.addWidget(self.stop_button)
        self.convert_checked_button.clicked.connect(self.start_checked_conversion)
        buttons.addWidget(self.convert_checked_button)
        self.start_button.clicked.connect(self.start_conversion)
        buttons.addWidget(self.start_button)
        layout.addLayout(buttons)
        songs_group.setLayout(layout)
        splitter.addWidget(songs_group)

        # Logs
        logs_group = QGroupBox()
        self.t(logs_group.setTitle, "Log")
        logs_layout = QVBoxLayout()
        logs_layout.addWidget(self.logs_text)
        logs_buttons = QHBoxLayout()
        logs_buttons.addWidget(self.log_filter)
        logs_buttons.addStretch()
        self.open_error_log_button.clicked.connect(self.open_error_log)
        logs_buttons.addWidget(self.open_error_log_button)
        self.clear_logs_button.clicked.connect(self.clear_logs)
        logs_buttons.addWidget(self.clear_logs_button)
        logs_layout.addLayout(logs_buttons)
        logs_group.setLayout(logs_layout)
        splitter.addWidget(logs_group)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        self.right_splitter = splitter
        return splitter

    def build_preview_legend(self) -> QWidget:
        legend = QWidget()
        lay = QHBoxLayout(legend)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addStretch()
        for icon, text in ((Icon.CHECK, "Source file found"), (Icon.X, "Source file missing"),
                           (Icon.FILE_CHECK, "Converted file cached"), (Icon.SYNC_WARNING, "Possible desync")):
            icon_lbl = QLabel()
            icon_lbl.setPixmap(icon.get_icon().pixmap(14, 14))
            text_lbl = QLabel()
            text_lbl.setStyleSheet("color: #888888; margin-right: 10px;")
            self.t(text_lbl.setText, text)
            lay.addWidget(icon_lbl)
            lay.addWidget(text_lbl)
        lay.addStretch()
        return legend

    # ------------------------------------------------------------------ window state
    def restore_window_state(self):
        geometry = self.settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            screen = QApplication.primaryScreen().availableGeometry()
            self.resize(int(screen.width() * 0.85), int(screen.height() * 0.85))
        for key, splitter in (("main_splitter", self.main_splitter), ("right_splitter", self.right_splitter)):
            state = self.settings.value(key)
            if state is not None:
                splitter.restoreState(state)

    def save_window_state(self):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("main_splitter", self.main_splitter.saveState())
        self.settings.setValue("right_splitter", self.right_splitter.saveState())

    # ------------------------------------------------------------------ field validators
    def core_id_input_fv(self) -> bool:
        text = self.core_id_input.text().strip()
        valid = bool(text) and re.fullmatch(r'[0-9A-Fa-f]{16}', text) is not None
        mark_field_valid(self.core_id_input, valid)
        return valid

    def dlc_id_input_fv(self) -> bool:
        text = self.dlc_id_input.text().strip()
        valid = bool(text) and re.fullmatch(r'[0-9A-Fa-f]{16}', text) is not None
        mark_field_valid(self.dlc_id_input, valid)
        return valid

    def dlc_json_name_input_fv(self) -> bool:
        mark_field_valid(self.dlc_json_name_input, True)
        previous = self.game_format
        self.game_format = JSON if self.dlc_json_name_input.text() != '' else XML
        self.include_dlc_checkbox_refresh()
        for w in (self.rad_label, self.rad_path, self.rad_browse):
            set_element_enabled(w, self.game_format == JSON)
        if not self._loading_defaults and previous != self.game_format:
            self.scan_input_folder()  # the cached video name changes (.bk2 / .mp4)
        return True

    def core_edition_combo_fv(self, edition: str) -> None:
        core_data = self.core_edition_combo.currentData()
        self.core_id_input.setText(core_data["core_id"] if core_data and core_data["core_id"] else "")
        self.dlc_name_combo.clear()
        set_element_enabled(self.core_id_label, edition == "other")
        set_element_enabled(self.core_id_input, edition == "other")
        if edition != "other":
            for dlc in repository.get_by_core_edition(edition):
                self.dlc_name_combo.addItem(dlc.dlc_name, userData={"dlc_id": dlc.dlc_id, "dlc_json_name": dlc.dlc_json_name})
        self.dlc_name_combo.addItem("other", userData={"dlc_id": None, "dlc_json_name": None})

    def dlc_name_combo_fv(self, dlc_name: str) -> None:
        editable = dlc_name == "other"
        for w in (self.dlc_id_label, self.dlc_id_input, self.dlc_json_name_label, self.dlc_json_name_input):
            set_element_enabled(w, editable)
        dlc_data = self.dlc_name_combo.currentData()
        self.dlc_id_input.setText(dlc_data["dlc_id"] if dlc_data and dlc_data["dlc_id"] else "")
        self.dlc_json_name_input.setText(dlc_data["dlc_json_name"] if dlc_data and dlc_data["dlc_json_name"] else "")
        self.dlc_json_name_input_fv()

    def ffmpeg_path_fv(self) -> bool:
        path = self.ffmpeg_path.text().strip()
        valid = bool(path) and (os.path.isfile(path) or path.lower() == 'ffmpeg')
        mark_field_valid(self.ffmpeg_path, valid)
        return valid

    def rad_path_fv(self) -> bool:
        path = self.rad_path.text().strip()
        valid = bool(path) and os.path.isfile(path)
        mark_field_valid(self.rad_path, valid)
        return valid

    def output_path_fv(self) -> bool:
        path = self.output_path.text().strip()
        if not path:
            mark_field_valid(self.output_path, False)
            return False
        # the output folder is wiped before converting: if it contains anything other than TitleID folders a
        # _Patch subfolder is used (same rule as the converter)
        import ConvertFiles
        safe_path = ConvertFiles.safe_output_dir(path)
        if safe_path != path:
            self.output_path.setText(safe_path)
        mark_field_valid(self.output_path, True)
        return True

    def input_path_fv(self) -> bool:
        path = self.input_path.text().strip()
        if path and os.path.isdir(path):
            try:
                names = os.listdir(path)
            except OSError:
                names = []
            for folder in names:
                if os.path.isdir(os.path.join(path, folder)) and re.search(r'^((?:.*\S)?)\s-\s(\S(?:.*\S)?)$', folder):
                    mark_field_valid(self.input_path, True)
                    if not self._loading_defaults:
                        self.scan_input_folder()
                    return True
        mark_field_valid(self.input_path, False)
        self.song_model.set_rows([])
        return False

    def dlc_name_txt_path_fv(self) -> bool:
        path = self.dlc_name_txt_path.text().strip()
        valid = bool(path) and os.path.isfile(path) and path.endswith('name.txt')
        mark_field_valid(self.dlc_name_txt_path, valid)
        return valid

    def dlc_tsv_path_fv(self) -> bool:
        path = self.dlc_tsv_path.text().strip()
        valid = bool(path) and os.path.isfile(path) and path.endswith('SongsDLC.tsv')
        mark_field_valid(self.dlc_tsv_path, valid)
        return valid

    def dlc_json_path_fv(self) -> bool:
        path = self.dlc_json_path.text().strip()
        valid = bool(path) and os.path.isfile(path)
        mark_field_valid(self.dlc_json_path, valid)
        return valid

    def still_video_checkbox_fv(self) -> None:
        set_element_enabled(self.max_video_label, not self.still_video_checkbox.isChecked())
        set_element_enabled(self.max_video_size, not self.still_video_checkbox.isChecked())

    def max_video_size_fv(self) -> bool:
        self.max_video_size.setText(str(max(10, min(int(self.max_video_size.text() or 80), 200))))
        return True

    def include_dlc_checkbox_refresh(self) -> None:
        xml = self.game_format == XML
        for w in (self.name_txt_label, self.dlc_name_txt_path, self.name_txt_browse,
                  self.songs_dlc_label, self.dlc_tsv_path, self.songs_dlc_browse):
            set_element_enabled(w, xml)
        for w in (self.songs_json_label, self.dlc_json_path, self.songs_json_browse):
            set_element_enabled(w, not xml)

    # ------------------------------------------------------------------ defaults / config
    def set_defaults(self) -> None:
        dlc_entity = repository.get_by_dlc_id(str(self.cfg.dlc.id))
        if dlc_entity is not None:
            self.core_edition_combo.setCurrentText(dlc_entity.core_edition)
            self.core_id_input.setText(dlc_entity.core_id)
            self.dlc_name_combo.setCurrentText(dlc_entity.dlc_name)
            self.dlc_id_input.setText(dlc_entity.dlc_id)
            self.dlc_json_name_input.setText(dlc_entity.dlc_json_name or "")
        else:
            self.core_edition_combo.setCurrentText(repository.get_edition_by_core_id(str(self.cfg.core.id)))
            self.core_id_input.setText(str(self.cfg.core.id or ""))
            self.dlc_name_combo.setCurrentText('other')
            self.dlc_id_input.setText(str(self.cfg.dlc.id or ""))
            if not is_blank(self.cfg.dlc.json_name):
                self.dlc_json_name_input.setText(str(self.cfg.dlc.json_name))

        self.core_id_input_fv()
        self.dlc_id_input_fv()
        self.dlc_json_name_input_fv()
        self.prefill_ffmpeg_path()
        self.prefill_rad_path()
        self.prefill_input_output_paths()

        tweaks = self.cfg.conversion_tweaks
        self.tweaks_group.setChecked(bool(tweaks.enable))
        self.include_dlc_checkbox.setChecked(bool(tweaks.dlc_songs.include))
        for value, field_, validator in ((tweaks.dlc_songs.name_txt_path, self.dlc_name_txt_path, self.dlc_name_txt_path_fv),
                                         (tweaks.dlc_songs.songs_json_path, self.dlc_json_path, self.dlc_json_path_fv),
                                         (tweaks.dlc_songs.songs_dlc_tsv_path, self.dlc_tsv_path, self.dlc_tsv_path_fv)):
            if not is_blank(value):
                field_.setText(str(value))
                validator()

        self.pitch_correction_checkbox.setChecked(str(tweaks.pitch_correction).lower() == 'slow')
        self.max_video_size.setText(str(tweaks.max_video_size))
        self.max_video_size_fv()
        self.ignore_medley_checkbox.setChecked(bool(tweaks.no_medley))
        self.force_reconvert_checkbox.setChecked(bool(getattr(tweaks, "force_reconvert", False)))
        self.clear_output_checkbox.setChecked(bool(getattr(tweaks, "clear_output", True)))
        self.multithread_checkbox.setChecked(bool(getattr(tweaks, "multithreading", False)))
        self.multithread_workers.setValue(int(getattr(tweaks, "multithreading_workers", None) or 3))
        self.multithread_workers.setEnabled(self.multithread_checkbox.isChecked())
        self.keep_accents_checkbox.setChecked(bool(getattr(tweaks, "keep_accents", True)))
        self.genius_checkbox.setChecked(bool(getattr(tweaks, "genius_lookup", True)))
        self.still_video_checkbox.clicked.connect(self.still_video_checkbox_fv)
        self.still_video_checkbox.setChecked(bool(tweaks.still_video))
        self.still_video_checkbox_fv()

        self.include_dlc_checkbox_refresh()
        self.stop_button.setEnabled(False)
        self.update_clear_cache_enabled()

    def prefill_ffmpeg_path(self) -> None:
        if not is_blank(self.cfg.tools.ffmpeg_path):
            self.ffmpeg_path.setText(str(self.cfg.tools.ffmpeg_path))
            return
        import shutil
        found = shutil.which('ffmpeg')
        candidates = [found] if found else []
        candidates += [os.path.join(os.path.abspath(app_dir()), "ffmpeg", "bin", "ffmpeg.exe"), r"C:\ffmpeg\bin\ffmpeg.exe"]
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                self.ffmpeg_path.setText(candidate)
                return

    def prefill_rad_path(self) -> None:
        if not is_blank(self.cfg.tools.rad_path):
            self.rad_path.setText(str(self.cfg.tools.rad_path))
            return
        if sys.platform != "win32":
            candidate = os.path.expanduser("~/.wine/drive_c/Program Files (x86)/RADVideo/radvideo64.exe")
        else:
            candidate = r"C:\Program Files (x86)\RADVideo\radvideo64.exe"
        if os.path.exists(candidate):
            self.rad_path.setText(candidate)

    def prefill_input_output_paths(self) -> None:
        root_path = os.path.abspath(app_dir())
        input_path = os.path.abspath(str(self.cfg.folders.input)) if not is_blank(self.cfg.folders.input) \
            else os.path.join(root_path, DEFAULT_INPUT_FOLDER_NAME)
        output_path = os.path.abspath(str(self.cfg.folders.output)) if not is_blank(self.cfg.folders.output) \
            else os.path.join(root_path, DEFAULT_OUTPUT_FOLDER_NAME)
        self.input_path.setText(input_path)
        self.output_path.setText(output_path)
        self.output_path_fv()
        self.input_path_fv()

    def save_config(self) -> None:
        dlc_id = self.dlc_id_input.text().strip()
        dlc_entity = repository.get_by_dlc_id(dlc_id)
        dlc_section = {"id": dlc_id}
        config_dict = {"dlc": dlc_section}
        if not dlc_entity:
            if not is_blank(self.dlc_json_name_input.text()):
                dlc_section["json_name"] = self.dlc_json_name_input.text().strip()
            config_dict["core"] = {"id": self.core_id_input.text().strip()}

        tools_section = {"ffmpeg_path": self.ffmpeg_path.text().strip()}
        if not is_blank(self.rad_path.text()):
            tools_section["rad_path"] = self.rad_path.text().strip()
        wine_path = getattr(self.cfg.tools, 'wine_path', None)
        if not is_blank(wine_path):
            tools_section["wine_path"] = str(wine_path)
        config_dict["tools"] = tools_section
        config_dict["folders"] = {"input": self.input_path.text().strip(), "output": self.output_path.text().strip()}

        dlc_songs_section = {"include": self.include_dlc_checkbox.isChecked()}
        for key, field_ in (("name_txt_path", self.dlc_name_txt_path), ("songs_json_path", self.dlc_json_path),
                            ("songs_dlc_tsv_path", self.dlc_tsv_path)):
            if not is_blank(field_.text()):
                dlc_songs_section[key] = field_.text().strip()

        slow = self.pitch_correction_checkbox.isChecked()
        config_dict["conversion_tweaks"] = {
            "enable": self.tweaks_group.isChecked(),
            "dlc_songs": dlc_songs_section,
            "pitch_correction": "slow" if slow else "fast",
            "vocal_isolation": slow,
            "max_video_size": int(self.max_video_size.text()) if self.max_video_size.text().strip().isdigit() else None,
            "no_medley": self.ignore_medley_checkbox.isChecked(),
            "force_reconvert": self.force_reconvert_checkbox.isChecked(),
            "still_video": self.still_video_checkbox.isChecked(),
            "multithreading": self.multithread_checkbox.isChecked(),
            "clear_output": self.clear_output_checkbox.isChecked(),
            "multithreading_workers": self.multithread_workers.value(),
            "keep_accents": self.keep_accents_checkbox.isChecked(),
            "genius_lookup": self.genius_checkbox.isChecked(),
        }
        config_dict["language"] = getattr(self.cfg, 'language', 'en')

        user_path = app_dir() / 'config.yml'
        with open(user_path, 'w', encoding='utf-8') as f:
            yaml.dump(config_dict, f, default_flow_style=False, allow_unicode=True)
        self.cfg = load_config()

    # ------------------------------------------------------------------ song table
    def video_suffix(self):
        return naming.VIDEO_BK2_SUFFIX if self.game_format == JSON else naming.VIDEO_MP4_SUFFIX

    def scan_input_folder(self) -> None:
        """Rescans the input folder in a background thread."""
        input_path = os.path.normpath(self.input_path.text().strip() or '.')
        if input_path == "." or not os.path.isdir(input_path):
            self.clear_watches()
            self.song_model.set_rows([])
            self.update_counts()
            return
        if self._scan_worker is not None and self._scan_worker.isRunning():
            self._rescan_pending = True
            return
        self.sync_watched_folders(input_path)
        self._scan_generation += 1
        self.statusBar().showMessage(tr("Scanning songs..."))
        self._scan_worker = ScanWorker(input_path, self.video_suffix(), self._sync_cache, self._scan_generation)
        self._scan_worker.scanned.connect(self.on_scan_finished)
        self._scan_worker.start()

    def on_scan_finished(self, rows, generation):
        if generation != self._scan_generation:
            return
        self.song_model.set_rows(rows)
        self.statusBar().clearMessage()
        self.update_counts()
        if self._rescan_pending:
            self._rescan_pending = False
            self.scan_input_folder()

    def refresh_single_song(self, directory):
        """Updates the icons of one row after it was converted (no full rescan during a conversion)."""
        input_path = os.path.normpath(self.input_path.text().strip())
        path = os.path.join(input_path, directory)
        if not os.path.isdir(path):
            return
        try:
            rows = scan_song_folders_single(input_path, directory, self.video_suffix(), self._sync_cache)
        except Exception:
            return
        self.song_model.refresh_row(directory, rows)

    def update_counts(self):
        rows = self.song_model.rows
        cached = sum(1 for r in rows if r.cached_video)
        checked = sum(1 for r in rows if r.checked)
        problems = sum(1 for r in rows if r.state in ('skipped', 'failed'))
        text = tr("{n} songs · {v} converted videos · {c} checked").format(n=len(rows), v=cached, c=checked)
        if problems:
            text += " · " + tr("{p} with problems").format(p=problems)
        self.counts_label.setText(text)

    def update_clear_cache_enabled(self, *_args) -> None:
        any_checked = any(r.checked for r in self.song_model.rows)
        if not self.conversion_running:
            self.clear_cache_button.setEnabled(any_checked)
            self.convert_checked_button.setEnabled(any_checked)
        self.update_counts()

    def on_search_changed(self, text: str) -> None:
        self.song_proxy.setFilterFixedString(text)

    def on_only_problems(self, checked):
        self.song_proxy.only_problems = checked
        self.song_proxy.invalidateFilter()

    def visible_rows(self):
        return [self.song_model.rows[self.song_proxy.mapToSource(self.song_proxy.index(i, 0)).row()]
                for i in range(self.song_proxy.rowCount())]

    def on_check_all(self, checked):
        self.song_model.set_checked(self.visible_rows(), checked)

    def row_at(self, proxy_index):
        if not proxy_index.isValid():
            return None
        return self.song_model.rows[self.song_proxy.mapToSource(proxy_index).row()]

    def on_table_clicked(self, index):
        row = self.row_at(index)
        if row is None:
            return
        if index.column() == COL_PLAY:
            self.play_song_audio(row.path)
        elif index.column() == COL_SYNC:
            self.open_sync_editor(row.path)

    def on_table_double_clicked(self, index):
        row = self.row_at(index)
        if row is not None and index.column() in (COL_NAME, COL_STATUS):
            open_in_file_manager(row.path)

    def on_table_context_menu(self, pos):
        index = self.song_view.indexAt(pos)
        row = self.row_at(index)
        if row is None:
            return
        menu = QMenu(self)
        actions = [
            (Icon.PLAY, "Play / pause", lambda: self.play_song_audio(row.path)),
            (Icon.SYNC, "Fix sync...", lambda: self.open_sync_editor(row.path)),
            (Icon.FOLDER, "Open folder", lambda: open_in_file_manager(row.path)),
            (Icon.CONVERT_SELECTED, "Convert only this song", lambda: self.start_conversion(only=[row.directory])),
            (Icon.REFRESH, "Encode the video again from its source...", lambda: self.reencode_video(row)),
            (Icon.FOLDER, "Add a video (file or link)...", lambda: self.add_video(row)),
        ]
        busy = self.conversion_running or self.tools_panel.running()
        for icon, text, slot in actions:
            action = QAction(icon.get_icon(), tr(text), menu)
            action.triggered.connect(slot)
            action.setEnabled(not busy or text in ("Play / pause", "Open folder"))
            menu.addAction(action)
        if row.detail:
            menu.addSeparator()
            info = QAction(tr("Last result: {detail}").format(detail=row.detail), menu)
            info.setEnabled(False)
            menu.addAction(info)
        menu.exec(self.song_view.viewport().mapToGlobal(pos))

    def add_video(self, row) -> None:
        """Cuts a music video (a file or a YouTube link) to the song's audio and saves it in the song folder."""
        from PySide6.QtWidgets import QInputDialog
        title = tr("Add a video (file or link)...").rstrip('.')
        text, ok = QInputDialog.getText(
            self, title, tr("YouTube link of the video, or leave it empty to choose a file.\n\nIts sound is compared "
                            "with the song to cut it at the right second; if the video is another version of the song "
                            "nothing is saved. The current video is kept in _replaced_videos."))
        if not ok:
            return
        source = text.strip()
        if not source:
            source, _ = QFileDialog.getOpenFileName(self, title, row.path,
                                                    "Video (*.mp4 *.mkv *.webm *.avi *.mov *.flv *.mpeg);;All Files (*)")
            if not source:
                return
        # the tool saves nothing when the video does not follow the song or is a still image
        self.tools_panel.run_tool('align_video', [row.path, source, '--apply'], title)

    def reencode_video(self, row) -> None:
        """For a song converted before its real video was added (its .bk2 is the still cover): the current .bk2 is
        moved to _replaced_videos next to the songs folder (never deleted) and the song is converted again."""
        import ConvertFiles
        song_dir = Path(row.path)
        txt = ConvertFiles.choose_txt_file([p for p in song_dir.iterdir() if p.suffix.lower() == '.txt'])
        source = None
        if txt is not None:
            import UltrastarToSingit
            source = ConvertFiles.resolve_song_sources(song_dir, UltrastarToSingit.parse_file(txt), row.name_ids)[1]
        bk2 = song_dir / (row.name_id + naming.VIDEO_BK2_SUFFIX)
        title = tr("Encode the video again from its source...").rstrip('.')
        if source is None or source.suffix.lower() == naming.VIDEO_BK2_SUFFIX:
            QMessageBox.information(self, title, tr("This song has no video file to encode (only a .bk2 or none)."))
            return
        if not bk2.exists():
            self.start_conversion(only=[row.directory])
            return
        keep_dir = song_dir.parent.parent / '_replaced_videos' / song_dir.name
        answer = QMessageBox.question(
            self, title,
            tr("The converted video ({size:.1f} MB) is moved, not deleted, to:\n{folder}\n\nand {source} "
               "({source_size:.0f} MB) is encoded again. This can take a long time. Continue?").format(
                size=bk2.stat().st_size / 2 ** 20, folder=keep_dir, source=source.name,
                source_size=source.stat().st_size / 2 ** 20),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        keep_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime('%Y%m%d-%H%M%S')
        for old in (bk2, song_dir / (row.name_id + naming.VIDEO_INTERMEDIATE_SUFFIX)):
            if old.exists():
                shutil.move(old, keep_dir / f"{old.stem}.{stamp}{old.suffix}")
                self.log(tr("Moved {file} to {folder}").format(file=old.name, folder=keep_dir))
        self.start_conversion(only=[row.directory])

    # ------------------------------------------------------------------ audio preview / sync editor
    def song_txt_file(self, directory_path: str):
        import ConvertFiles
        txt_files = [Path(directory_path) / x for x in os.listdir(directory_path)
                     if x.lower().endswith(SupportedFormats.TXT_EXTENSIONS)]
        return ConvertFiles.choose_txt_file(txt_files)

    def song_audio_files(self, directory_path: str) -> list:
        """The converted audio (what the game plays) if it exists, else the song's original audio."""
        import ConvertFiles
        import UltrastarToSingit
        name = os.path.basename(directory_path).rstrip('.')
        converted = os.path.join(directory_path, construct_name_id_from_directory_name(name) + naming.AUDIO_SUFFIX)
        if os.path.isfile(converted):
            return [converted]
        txt_path = self.song_txt_file(directory_path)
        if txt_path is None:
            return []
        try:
            audio, _, _ = ConvertFiles.resolve_song_sources(Path(directory_path), UltrastarToSingit.parse_file(txt_path),
                                                            naming.all_name_ids(name))
        except Exception:
            return []
        return [str(audio)] if audio else []

    def play_song_audio(self, directory_path):
        if self.song_model.playing_path == directory_path and \
                self.media_player.playbackState() == QMediaPlayer.PlayingState:
            self.media_player.pause()
            self.song_model.set_playing(None)
            return
        audio_files = self.song_audio_files(directory_path)
        if not audio_files:
            self.log(tr("No audio file found in {path}").format(path=directory_path), logging.WARNING)
            return
        self.media_player.setSource(QUrl.fromLocalFile(audio_files[0]))
        self.media_player.play()
        self.song_model.set_playing(directory_path)

    def on_media_status_changed(self, status):
        if status == QMediaPlayer.EndOfMedia:
            self.song_model.set_playing(None)

    def open_sync_editor(self, directory_path):
        if self.conversion_running:
            return
        try:
            from SyncEditor import SyncEditorDialog
            txt_path = self.song_txt_file(directory_path)
            if txt_path is None:
                self.log(tr("No UltraStar .txt file found to edit sync!"), logging.WARNING)
                return
            self.media_player.stop()
            self.song_model.set_playing(None)
            dialog = SyncEditorDialog(str(txt_path), self)
            dialog.exec()
            if dialog.saved:
                self.log(tr("Sync saved for {song} (its lyrics will be regenerated on the next conversion)")
                         .format(song=os.path.basename(directory_path)))
                self._sync_cache.pop(str(txt_path), None)
                self.refresh_single_song(os.path.basename(directory_path))
        except Exception as e:
            logger.exception("Sync editor failed")
            self.log(tr("Failed to open the sync editor: {error}").format(error=e), logging.ERROR)

    # ------------------------------------------------------------------ files and folders
    def browse_file(self, line_edit, file_filter="All Files (*)") -> None:
        start = os.path.dirname(line_edit.text().strip()) if line_edit.text().strip() else ""
        file_path, _ = QFileDialog.getOpenFileName(self, tr("Select file"), start, file_filter)
        if file_path:
            line_edit.setText(os.path.normpath(file_path))
            validator = self.field_validators.get(line_edit)
            if validator:
                validator()

    def browse_folder(self, line_edit) -> None:
        folder_path = QFileDialog.getExistingDirectory(self, tr("Select folder"), line_edit.text().strip())
        if folder_path:
            line_edit.setText(os.path.normpath(folder_path))
            validator = self.field_validators.get(line_edit)
            if validator:
                validator()

    def open_output_folder(self):
        import ConvertFiles
        path = ConvertFiles.safe_output_dir(self.output_path.text().strip())
        if os.path.isdir(path):
            open_in_file_manager(path)
        else:
            self.log(tr("The output folder does not exist yet: {path}").format(path=path), logging.WARNING)

    def open_error_log(self):
        path = os.path.join(app_dir(), 'error.log')
        if os.path.isfile(path):
            open_in_file_manager(path)
        else:
            self.log(tr("There is no error.log yet."))

    def clear_watches(self) -> None:
        for p in self.folder_watcher.directories():
            self.folder_watcher.removePath(p)

    def sync_watched_folders(self, root: str) -> None:
        """Watches only the input folder itself (songs added, removed or renamed)."""
        root = os.path.normpath(root.strip())
        current = set(self.folder_watcher.directories())
        if current != {root}:
            self.clear_watches()
            if os.path.isdir(root):
                self.folder_watcher.addPath(root)

    def schedule_watcher_refresh(self, *_args) -> None:
        self.watcher_debounce.start()

    def do_watcher_refresh(self) -> None:
        # during a conversion each finished song refreshes its own row; a full rescan happens at the end
        if self.isVisible() and not self.conversion_running:
            self.scan_input_folder()

    def refresh_preview(self) -> None:
        if not self.conversion_running:
            self.scan_input_folder()

    # ------------------------------------------------------------------ log
    def log(self, message, level=logging.INFO) -> None:
        if level < self.log_filter.currentData():
            return
        ts = QDateTime.currentDateTime().toString("HH:mm:ss")
        color = {logging.ERROR: "#dc2626", logging.CRITICAL: "#dc2626", logging.WARNING: "#d97706"}.get(level)
        for line in str(message).splitlines() or [""]:
            text = escape(line)
            if color:
                text = f"<span style='color:{color};'>{text}</span>"
            self.logs_text.appendHtml(f"<span style='color:#888888;'>[{ts}]</span> {text}")

    def on_worker_log(self, level, message):
        self.log(message, level)

    def clear_logs(self) -> None:
        self.logs_text.clear()

    # ------------------------------------------------------------------ cache
    def clear_cache(self) -> None:
        """Deletes converted files of the checked songs. Converted .bk2 videos are protected:
        they are only deleted if the user explicitly asks for it and confirms twice."""
        rows = self.song_model.checked_rows()
        if not rows:
            self.log(tr("Clear cache: no songs checked."))
            return
        targets = []
        protected = []
        for row in rows:
            if not os.path.isdir(row.path):
                continue
            names = os.listdir(row.path)
            files = [f for f in sorted(names)
                     if naming.is_generated_file(f, row.name_ids) or ('.tmp.' in f and any(f.startswith(n) for n in row.name_ids))]
            files += [f for f in names if f.endswith('_genius_cache.json')]
            protected += [os.path.join(row.path, f) for f in files if f.endswith(naming.PROTECTED_SUFFIXES)]
            targets.append((row.path, files))

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(tr("Clear cache"))
        box.setText(tr("Delete the converted files of {n} song(s)?").format(n=len(targets)))
        box.setInformativeText(tr("The original song files are not touched. Audio, covers and lyrics are quick to "
                                  "convert again.") + "\n\n" +
                               tr("{n} converted .bk2 video(s) are PROTECTED and will be kept: encoding them again can "
                                  "take hours or days.").format(n=len(protected)))
        delete_videos = QCheckBox(tr("Also delete the converted .bk2 videos (NOT recommended)"))
        box.setCheckBox(delete_videos)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Cancel)
        if box.exec() != QMessageBox.Yes:
            self.log(tr("Clear cache cancelled."))
            return

        include_videos = bool(delete_videos.isChecked() and protected)
        if include_videos:
            answer = QMessageBox.critical(
                self, tr("Delete converted videos?"),
                tr("You are about to DELETE {n} converted .bk2 video(s).\n\nConverting them again can take hours or "
                   "even days. This cannot be undone.\n\nAre you completely sure?").format(n=len(protected)),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            include_videos = answer == QMessageBox.Yes
            if not include_videos:
                self.log(tr("The converted .bk2 videos will be kept."))

        deleted_files = affected_songs = 0
        for directory_path, files in targets:
            any_deleted = False
            for name in files:
                if name.endswith(naming.PROTECTED_SUFFIXES) and not include_videos:
                    continue
                file_path = os.path.join(directory_path, name)
                try:
                    os.remove(file_path)
                    deleted_files += 1
                    any_deleted = True
                except OSError as e:
                    self.log(tr("Failed to delete: {path} ({error})").format(path=file_path, error=e), logging.ERROR)
            affected_songs += any_deleted
        self.log(tr("Clear cache done. Deleted files: {files}, songs affected: {songs}").format(
            files=deleted_files, songs=affected_songs) + ("" if include_videos else " " + tr("(.bk2 videos kept)")))
        self.scan_input_folder()

    # ------------------------------------------------------------------ conversion
    def required_fields_missing(self) -> Tuple[List[str], List[str]]:
        missing: List[str] = []
        invalid: List[str] = []

        def req(line_edit: QLineEdit, label: str, optional: bool = False):
            if not line_edit.isEnabled():
                mark_field_valid(line_edit, True)
                return
            if optional and not line_edit.text().strip():
                mark_field_valid(line_edit, True)
                return
            if not line_edit.text().strip():
                missing.append(label)
                mark_field_valid(line_edit, False)
            else:
                validator = self.field_validators.get(line_edit)
                if validator and not validator():
                    invalid.append(label)

        req(self.core_id_input, "Core ID")
        req(self.dlc_id_input, "DLC ID")
        req(self.ffmpeg_path, "FFmpeg")
        req(self.rad_path, "RAD Video Tools")
        req(self.output_path, tr("Output folder"))
        req(self.input_path, tr("Input folder"))
        req(self.dlc_name_txt_path, "name.txt", optional=True)
        req(self.dlc_tsv_path, "SongsDLC.tsv", optional=True)
        req(self.dlc_json_path, "songs_xx.json", optional=True)
        req(self.max_video_size, tr("Max video size"))
        return missing, invalid

    def set_controls_enabled(self, enabled: bool) -> None:
        widgets = (self.game_info_group, self.tools_group, self.folders_group, self.tweaks_group,
                   self.refresh_button, self.clear_cache_button, self.start_button, self.convert_checked_button,
                   self.check_all_checkbox)
        for w in widgets:
            w.setEnabled(enabled)
        self.stop_button.setEnabled(not enabled)
        self.menuBar().setEnabled(enabled)
        if enabled:
            if self.core_edition_combo.currentText() != "other":
                set_element_enabled(self.core_id_label, False)
                set_element_enabled(self.core_id_input, False)
            if self.dlc_name_combo.currentText() != "other":
                for w in (self.dlc_id_label, self.dlc_id_input, self.dlc_json_name_label, self.dlc_json_name_input):
                    set_element_enabled(w, False)
            self.still_video_checkbox_fv()
            self.include_dlc_checkbox_refresh()
            self.dlc_json_name_input_fv()
            self.update_clear_cache_enabled()
        self.on_tool_state_changed()

    def update_recommended_workers(self) -> None:
        """'Recommended: N' next to the threads: the number of songs at once that encodes the most video per minute on
        this PC (measured after a few conversions, else from the CPU threads and the free memory)."""
        import ConvertFiles
        workers, info = ConvertFiles.recommended_workers()
        if len(info['measured']) >= 2:
            why = tr("measured on this PC, minutes of video per minute: {values}").format(
                values=', '.join(tr("{n} at once {t:.2f}").format(n=n, t=t) for n, t in sorted(info['measured'].items())))
            if info['exploring']:
                why += "; " + tr("still rising, worth trying {n}").format(n=workers)
        else:
            why = tr("{cpus} processor threads, ~8 per video; measured after a few conversions").format(cpus=info['cpus'])
        self.recommended_button.setProperty('workers', workers)
        self.recommended_button.setText(tr("Recommended: {n}").format(n=workers))
        self.recommended_button.setToolTip(
            tr("Click to use it. Videos are encoded fastest with this many songs at once ({why}). More songs at once "
               "do not finish sooner when the processor is already full.").format(why=why))

    def on_tool_state_changed(self) -> None:
        """A library tool started or ended: no conversion while it runs (they share the song folders)."""
        busy = self.tools_panel.running()
        if not self.conversion_running:
            for w in (self.start_button, self.convert_checked_button):
                w.setEnabled(not busy)
        self.tools_panel.update_buttons()

    def start_checked_conversion(self):
        rows = self.song_model.checked_rows()
        if rows:
            self.start_conversion(only=[r.directory for r in rows])

    def start_conversion(self, only=None) -> None:
        if self.conversion_running or self.tools_panel.running():
            return
        if only is not None and not isinstance(only, list):
            only = None  # called from a signal with a 'checked' argument
        missing, invalid = self.required_fields_missing()
        if missing or invalid:
            if missing:
                self.log(tr("Cannot start conversion. Fill required fields:") + "\n- " + "\n- ".join(missing), logging.ERROR)
            if invalid:
                self.log(tr("Cannot start conversion. Invalid values for fields:") + "\n- " + "\n- ".join(invalid), logging.ERROR)
            return
        if only is None and not self.confirm_output_clearing():
            return

        self.media_player.stop()
        self.song_model.set_playing(None)
        self.conversion_running = True
        self.set_controls_enabled(False)
        self.save_config()
        for r in self.song_model.rows:
            if only is None or r.directory in only:
                r.state, r.detail = '', ''
        self.song_model.layoutChanged.emit()

        self.conversion_start_time = time.monotonic()
        self.progress_current = self.progress_total = 0
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(1)
        self.progress_bar.setVisible(True)
        self.elapsed_label.setText("0:00")
        self.remaining_label.setText("")
        self.tick_timer.start()
        self.log(tr("Starting conversion of {n} song(s)...").format(n=len(only)) if only else tr("Starting conversion..."))

        self._stop_event = threading.Event()
        self._worker = ConversionWorker(self.cfg, self._stop_event, only_dirs=only)
        self._worker.log_message.connect(self.on_worker_log)
        self._worker.progress.connect(self.on_progress)
        self._worker.song_state.connect(self.on_song_state)
        self._worker.done.connect(self.on_conversion_finished)
        self._worker.error.connect(self.on_conversion_error)
        self._worker.start()

    def confirm_output_clearing(self) -> bool:
        """The output folder is wiped before a full conversion: ask first if it has content."""
        will_clear = self.clear_output_checkbox.isChecked() or not self.tweaks_group.isChecked()
        if not will_clear:
            return True
        import ConvertFiles
        output = ConvertFiles.safe_output_dir(self.output_path.text().strip())
        if not os.path.isdir(output) or not os.listdir(output):
            return True
        answer = QMessageBox.warning(
            self, tr("Clear output folder?"),
            tr("The output folder will be deleted before converting:\n{path}\n\n"
               "Your song folders and their cached conversions (including the .bk2 videos) are NOT touched. "
               "Any .bk2 that only exists in the output folder is copied back to its song folder first.\n\n"
               "Converting a large library can take a long time. Continue?").format(path=output),
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
        return answer == QMessageBox.Yes

    def on_song_state(self, directory, state, detail):
        self.song_model.update_state(directory, state, detail)
        if state != 'running':
            self.refresh_single_song(directory)
        self.update_counts()

    def on_progress(self, current: int, total: int) -> None:
        self.progress_current, self.progress_total = current, total
        self.progress_bar.setMaximum(max(total, 1))
        self.progress_bar.setValue(current)
        if current > 0:
            elapsed = time.monotonic() - self.conversion_start_time
            self.estimated_finish_time = self.conversion_start_time + elapsed / current * total
        self.tick_progress()

    def tick_progress(self) -> None:
        now = time.monotonic()
        self.elapsed_label.setText(self.format_duration(now - self.conversion_start_time))
        if 0 < self.progress_current < self.progress_total:
            self.remaining_label.setText(f"-{self.format_duration(max(0, self.estimated_finish_time - now))}")
        else:
            self.remaining_label.setText("")

    @staticmethod
    def format_duration(seconds: float) -> str:
        seconds = max(0, int(seconds))
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{h:d}:{m:02d}:{s:02d}" if h > 0 else f"{m:d}:{s:02d}"

    def on_conversion_finished(self, summary=None) -> None:
        self.tick_timer.stop()
        self.conversion_running = False
        self.update_recommended_workers()
        self.set_controls_enabled(True)
        self.scan_input_folder()

        elapsed = time.monotonic() - self.conversion_start_time
        self.elapsed_label.setText(self.format_duration(elapsed))
        self.remaining_label.setText("")

        summary = summary or {'ok': [], 'skipped': [], 'failed': [], 'stopped': False}
        ok, skipped, failed = len(summary['ok']), len(summary['skipped']), len(summary['failed'])
        if summary.get('stopped'):
            title = tr("Conversion stopped")
            headline = tr("Conversion stopped by the user after {t}.").format(t=self.format_duration(elapsed))
        elif skipped or failed:
            title = tr("Conversion finished with problems")
            headline = tr("Conversion finished in {t}.").format(t=self.format_duration(elapsed))
        else:
            title = tr("Conversion finished")
            headline = tr("Conversion finished successfully in {t}.").format(t=self.format_duration(elapsed))
        counts = tr("Converted: {ok}   Skipped: {skipped}   Errors: {failed}").format(ok=ok, skipped=skipped, failed=failed)
        self.log(f"{headline} {counts}", logging.WARNING if (skipped or failed) else logging.INFO)

        details = [f"{tr('Skipped')}: {d} — {r}" for d, r in summary['skipped']] + \
                  [f"{tr('Error')}: {d} — {e}" for d, e in summary['failed']]
        box = QMessageBox(QMessageBox.Warning if (skipped or failed) else QMessageBox.Information, title,
                          f"{headline}\n\n{counts}", QMessageBox.Ok, self)
        if details:
            box.setInformativeText(tr("Tip: tick 'Only problems' above the song list to see them."))
            box.setDetailedText("\n".join(details))
        box.exec()

    def on_conversion_error(self, error_msg: str) -> None:
        self.tick_timer.stop()
        self.conversion_running = False
        self.set_controls_enabled(True)
        self.remaining_label.setText("")
        self.log(tr("Conversion stopped due to error: {error}").format(error=error_msg), logging.ERROR)
        logger.error(f"Conversion failed: {error_msg}")

    def stop_conversion(self) -> None:
        if not self.conversion_running or self._stop_event is None or self._stop_event.is_set():
            return
        self.log(tr("Stopping conversion... (finished files are kept; an interrupted video is never saved half-done)"),
                 logging.WARNING)
        self.stop_button.setEnabled(False)
        self._stop_event.set()
        import ConvertFiles
        ConvertFiles.stop_running_processes()
        if sys.platform != "win32":
            # under Wine, terminating wine does not always stop the Windows process it started
            import subprocess
            subprocess.run(["pkill", "-f", "radvideo64.exe binkc"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def closeEvent(self, event) -> None:
        if self.conversion_running:
            answer = QMessageBox.question(
                self, tr("Conversion running"),
                tr("A conversion is running. Stop it and close the program?\n\n"
                   "Files already converted are kept in the cache."),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self.stop_conversion()
            self._worker.wait(15000)
        if self.tools_panel.running():
            answer = QMessageBox.question(
                self, tr("Tool running"),
                tr("A library tool is running. Stop it and close the program?\n\n"
                   "Running it again later continues where it stopped."),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self.tools_panel.stop()
        self.media_player.stop()
        self.save_window_state()
        event.accept()

    # ------------------------------------------------------------------ help and tools
    def show_help(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("How to use Let's Sing UltraStar Converter"))
        dlg.setWindowIcon(Icon.INFO_SQUARE_ROUNDED.get_icon())
        dlg.resize(1000, 800)
        layout = QVBoxLayout(dlg)
        browser = QTextBrowser(dlg)
        browser.setOpenExternalLinks(True)
        browser.setHtml(self.help_html())
        layout.addWidget(browser)
        buttons = QDialogButtonBox(QDialogButtonBox.Close, dlg)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        dlg.exec()

    def help_html(self) -> str:
        md_text = (bundle_dir() / "Guide.md").read_text(encoding="utf-8", errors="replace")
        body = markdown.markdown(md_text, extensions=["extra", "sane_lists", "nl2br"], output_format="html")
        return f"<html><head></head><body>{body}</body></html>"

    def tool_recover_cache(self) -> None:
        try:
            from tools.cache_recovery import recover_cache
            count, msg = recover_cache(os.path.normpath(self.input_path.text().strip()),
                                       os.path.normpath(self.output_path.text().strip()))
            (QMessageBox.information if count > 0 else QMessageBox.warning)(self, tr("Recover cache from output"), msg)
            self.scan_input_folder()
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), str(e))

    def tool_unpack_output(self) -> None:
        try:
            QMessageBox.information(self, tr("Unpack DLC songs to the input folder"),
                                    tr("Select a DLC 'Songs' folder to unpack (e.g. romfs/Songs). The songs are saved "
                                       "to your current input folder; existing song folders are never overwritten."))
            songs_dir = QFileDialog.getExistingDirectory(self, tr("Select a 'Songs' folder"), self.output_path.text())
            if not songs_dir:
                return
            from tools.unpacker import unpack_dlc
            count, msg = unpack_dlc(songs_dir, os.path.normpath(self.input_path.text().strip()))
            (QMessageBox.information if count > 0 else QMessageBox.warning)(self, tr("Unpack DLC songs to the input folder"), msg)
            self.scan_input_folder()
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), str(e))


def scan_song_folders_single(input_path, directory, video_suffix, sync_cache):
    """The row of a single song folder (used to refresh one song), or None."""
    rows = scan_song_folders(input_path, video_suffix, sync_cache, only={directory})
    return rows[0] if rows else None


def start_hang_watchdog(app, seconds=10):
    """If the window stops answering for `seconds`, writes where every thread is to hang_trace.log (once per
    freeze), so a frozen GUI can be diagnosed instead of guessed."""
    import faulthandler
    import threading
    import time
    from ConfigLoader import app_dir
    state = {'beat': time.monotonic(), 'dumped': False}

    def beat():
        state['beat'] = time.monotonic()
        state['dumped'] = False

    timer = QTimer(app)
    timer.timeout.connect(beat)
    timer.start(1000)

    def watch():
        while True:
            time.sleep(2)
            stalled = time.monotonic() - state['beat']
            if stalled > seconds and not state['dumped']:
                state['dumped'] = True
                try:
                    with open(os.path.join(app_dir(), 'hang_trace.log'), 'a', encoding='utf-8') as f:
                        f.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} window not answering for "
                                f"{stalled:.0f} s ===\n")
                        f.flush()
                        faulthandler.dump_traceback(file=f, all_threads=True)
                except OSError:
                    pass

    threading.Thread(target=watch, name='hang-watchdog', daemon=True).start()
    return timer


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("LetsSingUltraStarConverter")
    app._hang_watchdog = start_hang_watchdog(app)
    window = MainWindow()
    apply_theme_change(app.styleHints().colorScheme(), app, window)
    app.styleHints().colorSchemeChanged.connect(lambda scheme: apply_theme_change(scheme, app, window))
    window.show()
    sys.exit(app.exec())
