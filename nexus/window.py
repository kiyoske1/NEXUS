"""Main NEXUS desktop interface."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from PySide6.QtCore import Qt, QTimer, QSettings, QDate, QThread, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QStackedWidget, QFrame, QListWidget, QListWidgetItem, QLineEdit,
    QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QInputDialog, QFileDialog,
    QMessageBox, QProgressBar, QButtonGroup, QRadioButton, QScrollArea,
    QGridLayout, QCalendarWidget, QDialog,
)

from nexus.database import Database
from nexus.backup import create_backup, create_full_backup, export_json
from nexus.charts import WeeklyActivityChart
from nexus.sync import SyncClient, SyncError
from nexus.secure_storage import load_secret, save_secret, clear_secret


STYLES = """
* { font-family: 'Segoe UI'; font-size: 13px; }
QMainWindow, QWidget { background: #0d0e12; color: #f0f0f5; }
QWidget#AppRoot { background: #0d0e12; }
QFrame#Sidebar { background: #101117; border: 1px solid #252630; border-radius: 24px; }
QFrame#Panel { background: #15161e; border: 1px solid #292a36; border-radius: 20px; }
QFrame#HeroPanel { background: #171722; border: 1px solid #322e46; border-radius: 24px; }
QFrame#AccentPanel { background: #c7f36b; border: none; border-radius: 18px; color: #171a12; }
QLabel { color: #eeeeF4; background: transparent; }
QLabel#Brand { font-size: 25px; font-weight: 850; letter-spacing: 4px; color: #c7f36b; }
QLabel#BrandSub { color: #777988; font-size: 9px; font-weight: 700; letter-spacing: 1.7px; }
QLabel#Muted { color: #858797; }
QLabel#Eyebrow { color: #aaa1d7; font-size: 10px; font-weight: 800; letter-spacing: 2px; }
QLabel#Hero { font-size: 34px; font-weight: 750; letter-spacing: -0.7px; color: #f7f6ff; }
QLabel#Metric { font-size: 30px; font-weight: 750; color: #f5f4fb; }
QLabel#MetricAccent { font-size: 28px; font-weight: 800; color: #c7f36b; }
QLabel#Section { font-size: 15px; font-weight: 750; color: #f4f2fc; }
QLabel#Tiny { color: #8d8e9d; font-size: 10px; font-weight: 700; letter-spacing: 1px; }
QLabel#Pill { background: #22242e; color: #b8b1e5; border: 1px solid #343346; border-radius: 9px; padding: 6px 9px; font-size: 10px; font-weight: 700; }
QLabel#StatusGood { color: #c7f36b; font-size: 11px; font-weight: 800; }
QLabel#StatusWarn { color: #e7b8ff; font-size: 11px; font-weight: 800; }
QLabel#AccentText { color: #191d12; }
QPushButton { background: #20212b; color: #e9e8f1; border: 1px solid #30313e; border-radius: 10px; padding: 10px 13px; text-align: left; }
QPushButton:hover { background: #2b2c39; border-color: #7d78a9; }
QPushButton:checked { background: #242332; color: #d6f68b; border: 1px solid #45415e; font-weight: 700; }
QPushButton#Primary { background: #c7f36b; color: #171a12; border: 1px solid #c7f36b; font-weight: 800; }
QPushButton#Primary:hover { background: #d5ff86; }
QPushButton#Nav { font-size: 12px; background: transparent; color: #8d8e9d; border: 1px solid transparent; padding: 12px 13px; border-radius: 11px; }
QPushButton#Nav:hover { background: #1a1b25; color: #f0eff8; }
QPushButton#Nav:checked { background: #22222f; color: #d8f79b; border: 1px solid #353449; font-weight: 700; }
QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: #101117; color: #f0eff8; border: 1px solid #323340; border-radius: 10px; padding: 10px; selection-background-color: #5f5a86; }
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border: 1px solid #a59bdc; }
QComboBox::drop-down { border: none; width: 24px; }
QListWidget { background: transparent; border: none; outline: none; padding: 2px; }
QListWidget::item { background: #1c1d27; border: 1px solid #292a37; border-radius: 10px; padding: 12px; margin: 4px 0; color: #e5e4ed; }
QListWidget::item:hover { background: #232431; border-color: #444157; }
QListWidget::item:selected { border: 1px solid #8c84ba; background: #29283a; color: #f6f4ff; }
QProgressBar { border: none; background: #292a35; border-radius: 5px; height: 9px; text-align: center; color: transparent; }
QProgressBar::chunk { background: #c7f36b; border-radius: 5px; }
QScrollArea { border: none; background: transparent; }
QRadioButton { spacing: 8px; }
QToolTip { background: #22232d; color: #f0eff8; border: 1px solid #48445e; padding: 6px; }
"""


def panel() -> QFrame:
    frame = QFrame()
    frame.setObjectName("Panel")
    frame.setFrameShape(QFrame.Shape.StyledPanel)
    return frame


def heading(text: str, object_name: str = "Section") -> QLabel:
    label = QLabel(text)
    label.setObjectName(object_name)
    return label


class CloudSyncWorker(QThread):
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, sync_client: SyncClient) -> None:
        super().__init__()
        self.sync_client = sync_client

    def run(self) -> None:
        try:
            result = self.sync_client.sync()
            self.finished.emit(result)
        except Exception as error:
            self.failed.emit(str(error))


class MainWindow(QMainWindow):
    def __init__(self, db: Database | None = None) -> None:
        super().__init__()
        self.db = db or Database()
        self.setWindowTitle("NEXUS | Personal Command Center")
        self.resize(1280, 820)
        self.setMinimumSize(980, 680)
        self.setStyleSheet(STYLES)
        self.setWindowOpacity(1.0)
        self.settings = QSettings("NEXUS", "PersonalCommandCenter")
        self.currency = self.settings.value("currency", "RUB")
        self.language = self.settings.value("language", "English")
        self.theme = self.settings.value("theme", "NEXUS Lime")
        self.sync_client = SyncClient(self.db, api_url=self.settings.value("cloud_api_url", "http://127.0.0.1:8000"), token=load_secret(self.settings, "cloud_access_token"), refresh_token=load_secret(self.settings, "cloud_refresh_token"), token_saver=self._save_cloud_tokens)
        self.cloud_user: dict[str, str] = {}
        self._focus_total_seconds = 25 * 60
        self._focus_seconds = self._focus_total_seconds
        self._focus_running = False
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._cloud_sync_running = False
        self._cloud_worker: CloudSyncWorker | None = None
        self._cloud_timer = QTimer(self)
        self._cloud_timer.setInterval(5 * 60 * 1000)
        self._cloud_timer.timeout.connect(self._background_cloud_sync)
        self._cloud_timer.start()
        self._build_shell()
        self._apply_theme()
        self._show_auth_gate_if_needed()
        self._apply_language()
        self._apply_currency()
        self.refresh_all()

    def _build_shell(self) -> None:
        root = QWidget()
        root.setObjectName("AppRoot")
        outer = QHBoxLayout(root)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(16)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(218)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(15, 22, 15, 16)
        side.setSpacing(7)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(9)
        brand_row.addWidget(heading("N", "Brand"))
        brand_copy = QVBoxLayout()
        brand_copy.setSpacing(0)
        brand_copy.addWidget(heading("NEXUS", "Brand"))
        brand_copy.addWidget(heading("PERSONAL OS", "BrandSub"))
        brand_row.addLayout(brand_copy)
        brand_row.addStretch(1)
        side.addLayout(brand_row)
        side.addSpacing(23)
        side.addWidget(heading("WORKSPACE", "Tiny"))

        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        self.pages = QStackedWidget()
        self.page_names = ["Overview", "Quests", "Habits", "Focus", "Finance", "Journal", "Calendar", "Insights", "Settings"]
        symbols = ["⌂", "◇", "✳", "◷", "↗", "▤", "▦", "◒", "⚙"]
        for index, name in enumerate(self.page_names):
            button = QPushButton(f"{symbols[index]}     {name}")
            button.setObjectName("Nav")
            button.setCheckable(True)
            button.setMinimumHeight(42)
            button.clicked.connect(lambda checked=False, i=index: self._navigate(i))
            self.nav.addButton(button, index)
            side.addWidget(button)
            if index == 0:
                button.setChecked(True)

        side.addSpacing(18)
        side.addWidget(heading("YOUR SYSTEM", "Tiny"))
        local_card = QFrame()
        local_card.setObjectName("Panel")
        local_layout = QVBoxLayout(local_card)
        local_layout.setContentsMargins(12, 12, 12, 12)
        local_layout.setSpacing(5)
        local_layout.addWidget(heading("●  LOCAL-FIRST", "Eyebrow"))
        account = self.db.get_profile()
        account_label = QLabel(f"@{account['username']}" if account and account.get("username") else "No account")
        account_label.setStyleSheet("font-size: 12px; font-weight: 750; color: #f0eff8;")
        local_layout.addWidget(account_label)
        local_layout.addWidget(QLabel("Private workspace on this device."))
        local_layout.addWidget(heading("ISOLATED ACCOUNT  ·  SQLITE", "Tiny"))
        side.addWidget(local_card)
        side.addStretch(1)

        shortcut_hint = QLabel("CTRL + 1–9    NAVIGATE\nCTRL + N       NEW QUEST\nCTRL + SHIFT + B   BACKUP")
        shortcut_hint.setObjectName("Muted")
        shortcut_hint.setStyleSheet("font-size: 10px; line-height: 1.5;")
        side.addWidget(shortcut_hint)
        side.addSpacing(8)
        footer = QHBoxLayout()
        footer.addWidget(heading("NEXUS", "BrandSub"))
        footer.addStretch(1)
        footer.addWidget(heading("V 0.1.0", "Tiny"))
        side.addLayout(footer)
        outer.addWidget(sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(2, 2, 2, 2)
        content_layout.setSpacing(15)

        top = QHBoxLayout()
        top.setSpacing(10)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        self.page_title = heading("Overview", "Hero")
        title_col.addWidget(self.page_title)
        title_col.addWidget(heading("A little progress, every day.", "Muted"))
        top.addLayout(title_col)
        top.addStretch(1)

        self.date_label = QLabel()
        self.date_label.setObjectName("Pill")
        top.addWidget(self.date_label)
        backup_button = QPushButton("↧  Backup")
        backup_button.setToolTip("Create a local copy of your database")
        backup_button.clicked.connect(self._backup_database)
        self.notification_button = QPushButton("◉  0")
        self.notification_button.setToolTip("Open notification center")
        self.notification_button.clicked.connect(self._show_notifications)
        backup_button = QPushButton("↧  Backup")
        backup_button.setToolTip("Create a local copy of your database")
        backup_button.clicked.connect(self._backup_database)
        export_button = QPushButton("⇧  Export")
        export_button.setToolTip("Export all NEXUS data to JSON")
        export_button.clicked.connect(self._export_json)
        top.addWidget(self.notification_button)
        top.addWidget(backup_button)
        top.addWidget(export_button)
        content_layout.addLayout(top)

        self.pages.addWidget(self._overview_page())
        self.pages.addWidget(self._quests_page())
        self.pages.addWidget(self._habits_page())
        self.pages.addWidget(self._focus_page())
        self.pages.addWidget(self._finance_page())
        self.pages.addWidget(self._journal_page())
        self.pages.addWidget(self._calendar_page())
        self.pages.addWidget(self._insights_page())
        self.pages.addWidget(self._settings_page())
        content_layout.addWidget(self.pages, 1)
        outer.addWidget(content, 1)
        self._app_root = root
        self.setCentralWidget(root)

        self._shortcuts = []
        for index in range(min(len(self.page_names), 9)):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{index + 1}"), self)
            shortcut.activated.connect(lambda i=index: self._navigate(i))
            self._shortcuts.append(shortcut)
        new_quest_shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        new_quest_shortcut.activated.connect(self._add_task)
        self._shortcuts.append(new_quest_shortcut)
        backup_shortcut = QShortcut(QKeySequence("Ctrl+Shift+B"), self)
        backup_shortcut.activated.connect(self._backup_database)
        self._shortcuts.append(backup_shortcut)


    def _show_auth_gate_if_needed(self) -> None:
        self._show_auth_choice()

    def _auth_shell(self, title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        root = QWidget(); root.setObjectName("AppRoot")
        outer = QVBoxLayout(root); outer.setContentsMargins(40, 40, 40, 40); outer.addStretch(1)
        card = panel(); card.setMaximumWidth(520)
        box = QVBoxLayout(card); box.setContentsMargins(34, 34, 34, 34); box.setSpacing(14)
        box.addWidget(heading("NEXUS", "Brand")); box.addWidget(heading(title, "Hero")); box.addWidget(QLabel(subtitle))
        outer.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter); outer.addStretch(1)
        return root, box

    def _show_auth_choice(self) -> None:
        root, box = self._auth_shell("Welcome to NEXUS", "Choose how you want to enter your personal command center.")
        login = QPushButton("→  Sign in"); login.setObjectName("Primary"); login.setMinimumHeight(48); login.clicked.connect(self._show_login_screen)
        register = QPushButton("+  Create account"); register.setMinimumHeight(48); register.clicked.connect(self._show_register_screen)
        box.addWidget(login); box.addWidget(register)
        accounts = self.db.list_accounts()
        if accounts:
            names = ", ".join(f"@{account['username']}" for account in accounts[:3])
            if len(accounts) > 3:
                names += f" +{len(accounts) - 3}"
            note = QLabel(f"Local accounts on this PC · {names}"); note.setObjectName("Muted"); box.addWidget(note)
        note = QLabel("Each account has its own quests, habits, focus history, finances, journal, and profile."); note.setObjectName("Muted"); note.setWordWrap(True); box.addWidget(note)
        if accounts:
            box.addWidget(heading("LOCAL WORKSPACES", "Tiny"))
            for account in accounts:
                account_button = QPushButton(f"  @{account['username']}   ·   {account['name']}")
                account_button.setMinimumHeight(42)
                account_button.setObjectName("Secondary")
                account_button.clicked.connect(lambda checked=False, u=account["username"]: self._prefill_account(u))
                box.addWidget(account_button)
        self.setCentralWidget(root)

    def _prefill_account(self, username: str) -> None:
        self._show_login_screen()
        if hasattr(self, "auth_username"):
            self.auth_username.setText(username)
            self.auth_password.setFocus()

    def _show_register_screen(self) -> None:
        root, box = self._auth_shell("Create your NEXUS", "Set up your local account and personal workspace.")
        self.auth_name = QLineEdit(); self.auth_name.setPlaceholderText("Display name")
        self.auth_email = QLineEdit(); self.auth_email.setPlaceholderText("Email")
        self.auth_username = QLineEdit(); self.auth_username.setPlaceholderText("Username")
        self.auth_password = QLineEdit(); self.auth_password.setPlaceholderText("Password (6+ characters)"); self.auth_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.auth_status = QLabel(""); self.auth_status.setObjectName("Muted"); self.auth_status.setWordWrap(True)
        create = QPushButton("Create account"); create.setObjectName("Primary"); create.setMinimumHeight(46); create.clicked.connect(self._register_account); self.auth_password.returnPressed.connect(self._register_account)
        back = QPushButton("←  Back"); back.clicked.connect(self._show_auth_choice)
        for widget in (self.auth_name, self.auth_email, self.auth_username, self.auth_password, create, back): box.addWidget(widget)
        box.addWidget(self.auth_status)
        note = QLabel("Your account is stored locally on this PC. Cloud sync can be connected later."); note.setObjectName("Muted"); note.setWordWrap(True); box.addWidget(note)
        self.setCentralWidget(root)

    def _show_login_screen(self) -> None:
        root, box = self._auth_shell("Welcome back", "Sign in to unlock your NEXUS workspace.")
        profile = self.db.get_profile() or {}
        self.auth_username = QLineEdit(); self.auth_username.setText(profile.get("username", "")); self.auth_username.setPlaceholderText("Username or email")
        self.auth_password = QLineEdit(); self.auth_password.setPlaceholderText("Password"); self.auth_password.setEchoMode(QLineEdit.EchoMode.Password)
        login = QPushButton("Sign in"); login.setObjectName("Primary"); login.setMinimumHeight(46); login.clicked.connect(self._login_account); self.auth_password.returnPressed.connect(self._login_account); self.auth_username.returnPressed.connect(lambda: self.auth_password.setFocus())
        back = QPushButton("←  Back"); back.clicked.connect(self._show_auth_choice)
        self.auth_status = QLabel(""); self.auth_status.setObjectName("Muted")
        for widget in (self.auth_username, self.auth_password, login, back, self.auth_status): box.addWidget(widget)
        self.setCentralWidget(root)

    def _register_account(self) -> None:
        name = self.auth_name.text().strip()
        email = self.auth_email.text().strip()
        username = self.auth_username.text().strip()
        password = self.auth_password.text()

        self.auth_status.setText("")
        if not name:
            self.auth_status.setText("Enter your display name.")
            self.auth_name.setFocus()
            return
        if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            self.auth_status.setText("Enter a valid email address.")
            self.auth_email.setFocus()
            return
        if not username:
            self.auth_status.setText("Choose a username.")
            self.auth_username.setFocus()
            return
        if len(password) < 6:
            self.auth_status.setText("Password must be at least 6 characters.")
            self.auth_password.setFocus()
            return

        try:
            self.db.create_account(name, email, username, password)
        except Exception as error:
            self.auth_status.setText(f"Could not create account: {error}")
            return

        self._unlock_workspace()

    def _login_account(self) -> None:
        password = self.auth_password.text()
        if not password:
            self.auth_status.setText("Enter your password.")
            self.auth_password.setFocus()
            return
        if self.db.authenticate_account(self.auth_username.text(), password):
            self._unlock_workspace()
        else:
            self.auth_status.setText("Incorrect password.")
            self.auth_password.selectAll()
            self.auth_password.setFocus()

    def _unlock_workspace(self) -> None:
        # The auth screen replaces QMainWindow's central widget. Qt owns and
        # deletes the previous widget, so the cached _app_root is no longer
        # safe to reuse after login. Rebuild the workspace shell instead.
        for shortcut in getattr(self, "_shortcuts", []):
            shortcut.deleteLater()
        self._shortcuts = []
        self._build_shell()
        self._apply_theme()
        self._apply_language()
        self._apply_currency()
        self.refresh_all()

    def _calendar_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(13)
        card = panel()
        box = QVBoxLayout(card)
        box.setContentsMargins(18, 16, 18, 16)
        box.addWidget(heading("Your calendar", "Hero"))
        box.addWidget(QLabel("Pick a day and review your logged activity."))
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(False)
        self.calendar.setSelectedDate(QDate.currentDate())
        self.calendar.selectionChanged.connect(self._calendar_selected)
        box.addWidget(self.calendar)
        layout.addWidget(card, 1)
        activity = panel()
        abox = QVBoxLayout(activity)
        abox.setContentsMargins(18, 16, 18, 16)
        self.calendar_day_label = heading("Today", "Section")
        self.calendar_day_list = QListWidget()
        abox.addWidget(self.calendar_day_label)
        abox.addWidget(self.calendar_day_list)
        layout.addWidget(activity, 1)
        self._calendar_selected()
        return page

    def _calendar_selected(self) -> None:
        if not hasattr(self, "calendar_day_label"):
            return
        qd = self.calendar.selectedDate()
        iso = qd.toString("yyyy-MM-dd")
        self.calendar_day_label.setText(qd.toString("dddd, d MMMM yyyy"))
        self.calendar_day_list.clear()
        for task in self.db.get_tasks(include_done=True):
            if task.get("completed_at", "").startswith(iso):
                self.calendar_day_list.addItem(f"✓  {task['title']}   ·   {task['xp']} XP")
        if not self.calendar_day_list.count():
            self.calendar_day_list.addItem("No logged activity for this day.")

    def _insights_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(13)
        hero = panel()
        hb = QVBoxLayout(hero)
        hb.setContentsMargins(20, 18, 20, 18)
        hb.addWidget(heading("Your numbers, at a glance.", "Hero"))
        hb.addWidget(QLabel("A compact view of consistency, quests, focus, and money."))
        layout.addWidget(hero)
        grid = QGridLayout()
        grid.setSpacing(13)
        self.insight_labels = {}
        items = [
            ("tasks", "Completed quests"),
            ("xp", "Experience earned"),
            ("focus", "Focus minutes"),
            ("balance", "Current balance"),
            ("habits", "Habits completed"),
            ("entries", "Journal entries"),
        ]
        for idx, (key, title) in enumerate(items):
            card = panel()
            cb = QVBoxLayout(card)
            cb.setContentsMargins(18, 16, 18, 16)
            cb.addWidget(heading(title, "Tiny"))
            value = heading("0", "Metric")
            cb.addWidget(value)
            self.insight_labels[key] = value
            grid.addWidget(card, idx // 3, idx % 3)
        layout.addLayout(grid)
        activity_card = panel()
        activity_box = QVBoxLayout(activity_card)
        activity_box.setContentsMargins(18, 16, 18, 16)
        activity_header = QHBoxLayout()
        activity_header.addWidget(heading("Activity history", "Section"))
        activity_header.addStretch(1)
        clear_hint = heading("LATEST 12 EVENTS", "Tiny")
        activity_header.addWidget(clear_hint)
        activity_box.addLayout(activity_header)
        self.activity_list = QListWidget()
        self.activity_list.setMinimumHeight(190)
        activity_box.addWidget(self.activity_list)
        for event in self.db.get_activity(12):
            stamp = event["created_at"].replace("T", " · ")[:19]
            self.activity_list.addItem(f'{event["action"]}   ·   {event["detail"]}   ·   {stamp}')
        layout.addWidget(activity_card, 1)
        return page

    def _show_notifications(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("NEXUS · Notifications")
        dialog.setMinimumSize(520, 520)
        box = QVBoxLayout(dialog)
        box.setContentsMargins(22, 20, 22, 20)
        header = QHBoxLayout()
        header.addWidget(heading("Notification center", "Hero"))
        header.addStretch(1)
        read_all = QPushButton("Mark all read")
        read_all.clicked.connect(lambda: (self.db.mark_all_notifications_read(), dialog.accept(), self.refresh_all()))
        header.addWidget(read_all)
        box.addLayout(header)
        notifications = self.db.get_notifications(limit=60)
        if not notifications:
            box.addWidget(QLabel("Everything is quiet. Your next signal will appear here."))
        else:
            for item in notifications:
                row = QFrame()
                row.setObjectName("Panel")
                rb = QVBoxLayout(row)
                rb.setContentsMargins(12, 10, 12, 10)
                title = QLabel(("● " if not item["read"] else "○ ") + item["title"])
                title.setStyleSheet("font-weight: 800;")
                rb.addWidget(title)
                if item["body"]:
                    rb.addWidget(QLabel(item["body"]))
                rb.addWidget(QLabel(item["created_at"].replace("T", "  ·  ")))
                box.addWidget(row)
                if not item["read"]:
                    self.db.mark_notification_read(item["id"])
        dialog.exec()
        self.refresh_all()

    def _currency_prefix(self) -> str:
        return {"RUB": "₽ ", "PMR": "р. ", "USD": "$ ", "EUR": "€ ", "USDT": "₮ "}.get(self.currency, "₽ ")

    def _money(self, value: float) -> str:
        return f"{self._currency_prefix()}{value:,.2f}"

    def _apply_currency(self) -> None:
        if hasattr(self, "money_amount"):
            self.money_amount.setPrefix(self._currency_prefix())
        if hasattr(self, "metric_labels") and "balance" in self.metric_labels:
            self.metric_labels["balance"].setText(self._money(self.db.stats()["balance"]))
        if hasattr(self, "money_list"):
            self.money_list.clear()
            for item in self.db.get_transactions():
                sign = "+" if item["kind"] == "income" else "−"
                self.money_list.addItem(f"{sign} {self._money(item['amount'])}   ·   {item['title']}   ·   {item['created_at'][:10]}")

    def _apply_theme(self) -> None:
        themes = {
            "NEXUS Lime": ("#0d0e12", "#15161e", "#171722", "#c7f36b", "#aaa1d7", "#101117"),
            "Violet Night": ("#0d0b14", "#171321", "#1d1729", "#c6a7ff", "#9d8bd7", "#120f19"),
            "Sunset Ember": ("#160d0b", "#241513", "#321a16", "#ff9f68", "#e6b4a0", "#1b0f0c"),
            "Ocean Neon": ("#071316", "#0e2024", "#122d32", "#55f5dc", "#82b9c5", "#09191c"),
            "Mono": ("#0d0d0d", "#171717", "#1c1c1c", "#f0f0f0", "#a0a0a0", "#111111"),
        }
        bg, card, hero, accent, lavender, sidebar = themes.get(self.theme, themes["NEXUS Lime"])
        self.setStyleSheet(STYLES.replace("#0d0e12", bg).replace("#15161e", card).replace("#171722", hero).replace("#c7f36b", accent).replace("#aaa1d7", lavender).replace("#101117", sidebar))


    def _translated_names(self) -> list[str]:
        return {
            "English": ["Overview", "Quests", "Habits", "Focus", "Finance", "Journal", "Calendar", "Insights", "Settings"],
            "Русский": ["Обзор", "Задачи", "Привычки", "Фокус", "Финансы", "Дневник", "Календарь", "Статистика", "Настройки"],
            "Română": ["Panou", "Sarcini", "Obiceiuri", "Focus", "Finanțe", "Jurnal", "Calendar", "Statistici", "Setări"],
        }.get(self.language, ["Overview", "Quests", "Habits", "Focus", "Finance", "Journal", "Settings"])

    def _tr(self, text: str) -> str:
        ru = {
            "Your data stays on this device.":"Твои данные остаются на этом устройстве.","DATABASE  ·  SQLITE":"БАЗА ДАННЫХ  ·  SQLITE","CTRL + 1–7    NAVIGATE\\nCTRL + N       NEW QUEST\\nCTRL + SHIFT + B   BACKUP":"CTRL + 1–7    НАВИГАЦИЯ\\nCTRL + N       НОВАЯ ЗАДАЧА\\nCTRL + SHIFT + B   БЭКАП",
            "Create a local copy of your database":"Создать локальную копию базы данных","Export all NEXUS data to JSON":"Экспортировать все данные NEXUS в JSON","Change the atmosphere, language, and money format. Your choices are saved locally.":"Измени оформление, язык и формат денег. Настройки сохраняются локально.","No account required. Preferences are stored with your desktop app settings.":"Аккаунт не требуется. Настройки сохраняются на этом компьютере.",
            "YOUR PERSONAL COMMAND CENTER":"ТВОЙ ПЕРСОНАЛЬНЫЙ ЦЕНТР","Make room for\\nwhat matters.":"Освободи место для\\nтого, что важно.","Less noise. More intention. One good move at a time.":"Меньше шума. Больше смысла. По одному хорошему шагу.","+  Create a quest":"+  Создать задачу","SMALL ACTIONS. REAL MOMENTUM.":"МАЛЕНЬКИЕ ДЕЙСТВИЯ. РЕАЛЬНЫЙ ПРОГРЕСС.","TOTAL EXPERIENCE EARNED":"ВСЕГО ОПЫТА","QUESTS DONE":"ЗАДАЧ ВЫПОЛНЕНО","TOTAL EXPERIENCE":"ВСЕГО ОПЫТА","HABITS TODAY":"ПРИВЫЧКИ СЕГОДНЯ","NET BALANCE":"ОБЩИЙ БАЛАНС","Next up":"ДАЛЬШЕ","OPEN QUESTS":"ОТКРЫТЫЕ ЗАДАЧИ","Daily rhythm":"РИТМ ДНЯ","CHECK IN":"ОТМЕТКА","Start with one small habit.":"Начни с одной маленькой привычки.","TODAY'S COMPLETION":"ВЫПОЛНЕНИЕ СЕГОДНЯ","Momentum":"ДВИЖЕНИЕ","ALL-TIME QUEST PROGRESS":"ПРОГРЕСС ЗАДАЧ","Your next small win is waiting.":"Следующая маленькая победа ждёт.","LAST 7 DAYS":"ПОСЛЕДНИЕ 7 ДНЕЙ","FOCUS MINUTES":"МИНУТЫ ФОКУСА",
            "Give your next action a name, a category, and a reward.":"Назови следующее действие, категорию и награду.","What would move you forward?":"Что двинет тебя вперёд?","Consistency, without the pressure.":"Стабильность без давления.","Build small rituals that still count on difficult days. Check in once a day.":"Создавай маленькие ритуалы, которые работают даже в сложные дни. Отмечай раз в день.","A small habit, e.g. read 10 pages":"Маленькая привычка, например читать 10 страниц","＋  Add habit":"＋  Добавить привычку","One task. One window. Everything else can wait.":"Одна задача. Одно окно. Остальное подождёт.","A private ledger that stays on this computer.":"Личный учёт, который остаётся на этом компьютере.","Transaction description":"Описание операции","A private space to think. Your entries stay on this device.":"Личное пространство для мыслей. Записи остаются на этом устройстве.","Give this entry a title":"Дай записи название","What is on your mind today? Start anywhere.":"О чём ты думаешь сегодня? Начни с чего угодно.","Double-click an entry to read it.":"Дважды кликни по записи, чтобы открыть её.","Delete quest":"Удалить задачу","Delete this quest permanently?":"Удалить эту задачу навсегда?","Delete this habit and its streak history?":"Удалить эту привычку и историю серии?","Delete transaction":"Удалить операцию","Delete this transaction permanently?":"Удалить эту операцию навсегда?","Select a quest first.":"Сначала выбери задачу.","That quest is already completed.":"Эта задача уже выполнена.","Select a habit first.":"Сначала выбери привычку.","Select a journal entry first.":"Сначала выбери запись дневника.","No matching entries yet.":"Подходящих записей пока нет.","Delete journal entry":"Удалить запись дневника","Delete this entry permanently? This cannot be undone.":"Удалить эту запись навсегда? Это действие нельзя отменить.","Create NEXUS backup":"Создать резервную копию NEXUS","Backup created successfully.":"Резервная копия создана.","Export NEXUS data":"Экспортировать данные NEXUS","JSON export created successfully.":"JSON-экспорт создан.",
            "WORKSPACE":"РАБОЧЕЕ ПРОСТРАНСТВО","YOUR SYSTEM":"ВАША СИСТЕМА","A little progress, every day.":"Небольшой прогресс каждый день.",
            "Backup":"Резервная копия","Export":"Экспорт","Create a new quest":"Создать новую задачу","Your quest board":"Ваши задачи",
            "All quests":"Все задачи","Open only":"Только открытые","Completed":"Выполненные","＋  Add quest":"＋  Добавить задачу",
            "✓  Complete selected  +XP":"✓  Выполнить выбранную  +XP","Delete selected":"Удалить выбранную","Edit selected":"Редактировать выбранное",
            "Today's check-in":"Сегодня","✓  Toggle today's check-in":"✓  Отметить сегодня","Delete habit":"Удалить привычку",
            "Protect your attention.":"Береги внимание.","Session length":"Длительность","Start / Pause":"Старт / Пауза","Reset":"Сбросить",
            "Know where your money goes.":"Знай, куда уходят деньги.","Recent activity":"Последние операции","＋  Add entry":"＋  Добавить операцию",
            "Expense":"Расход","Income":"Доход","Clear your head.":"Освободи голову.","Recent entries":"Последние записи",
            "Search titles and thoughts…":"Поиск по заметкам…","Save entry  ↗":"Сохранить запись  ↗","Delete selected entry":"Удалить выбранную запись",
            "Personalize NEXUS":"Настройка NEXUS","Your profile":"Ваш профиль","Save profile":"Сохранить профиль","Display name":"Имя","Email":"Email","Username":"Имя пользователя","Profile saved.":"Профиль сохранён.","Appearance":"Оформление","Interface language":"Язык интерфейса","Currency":"Валюта",
            
            "quest":"задача","quests":"задач","left to move forward.":"осталось до следующего шага.","habits complete":"привычек выполнено","quests completed overall":"задач выполнено всего","focus minutes logged":"минут фокуса",
            "No open quests. Enjoy the breathing room.":"Открытых задач нет. Можно выдохнуть.","No completed quests yet.":"Выполненных задач пока нет.","Your quest board is clear. Add the first one.":"Список задач пуст. Добавь первую.",
            "Edit quest":"Редактировать задачу","Edit habit":"Редактировать привычку","Edit transaction":"Редактировать операцию","Edit note":"Редактировать заметку",
            "You're building consistency.":"Ты формируешь стабильность.","Add one small habit to begin.":"Добавь одну маленькую привычку.",
            "Your next win is waiting.":"Следующая победа уже ждёт.","quest":"задача","quests":"задач","No open quests. Add a small win.":"Открытых задач нет. Добавь маленькую победу.",
            "Timer reset.":"Таймер сброшен.","Session complete. Nice work.":"Сессия завершена. Хорошая работа.","Focus mode active. Keep going.":"Фокус включён. Продолжай.",
            "Paused. Resume when ready.":"Пауза. Продолжи, когда будешь готов.","Ready when you are.":"Готов, когда готов ты."
        };
        ro = {
            "Your data stays on this device.":"Datele tale rămân pe acest dispozitiv.","DATABASE  ·  SQLITE":"BAZA DE DATE  ·  SQLITE","CTRL + 1–7    NAVIGATE\\nCTRL + N       NEW QUEST\\nCTRL + SHIFT + B   BACKUP":"CTRL + 1–7    NAVIGARE\\nCTRL + N       SARCINĂ NOUĂ\\nCTRL + SHIFT + B   BACKUP","Create a local copy of your database":"Creează o copie locală a bazei de date","Export all NEXUS data to JSON":"Exportă toate datele NEXUS în JSON","Change the atmosphere, language, and money format. Your choices are saved locally.":"Schimbă aspectul, limba și formatul banilor. Setările sunt salvate local.","No account required. Preferences are stored with your desktop app settings.":"Nu este necesar un cont. Setările sunt salvate pe acest computer.","YOUR PERSONAL COMMAND CENTER":"CENTRUL TĂU PERSONAL","Make room for\\nwhat matters.":"Fă loc pentru\\nceea ce contează.","Less noise. More intention. One good move at a time.":"Mai puțin zgomot. Mai multă intenție. Câte un pas bun.","+  Create a quest":"+  Creează o sarcină","SMALL ACTIONS. REAL MOMENTUM.":"ACȚIUNI MICI. PROGRES REAL.","TOTAL EXPERIENCE EARNED":"EXPERIENȚĂ TOTALĂ","QUESTS DONE":"SARCINI FINALIZATE","TOTAL EXPERIENCE":"EXPERIENȚĂ TOTALĂ","HABITS TODAY":"OBICEIURI AZI","NET BALANCE":"SOLD NET","Next up":"URMEAZĂ","OPEN QUESTS":"SARCINI DESCHISE","Daily rhythm":"RITM ZILNIC","CHECK IN":"VERIFICARE","Start with one small habit.":"Începe cu un obicei mic.","TODAY'S COMPLETION":"FINALIZARE AZI","Momentum":"PROGRES","ALL-TIME QUEST PROGRESS":"PROGRES TOTAL AL SARCINILOR","Your next small win is waiting.":"Următoarea victorie mică te așteaptă.","LAST 7 DAYS":"ULTIMELE 7 ZILE","FOCUS MINUTES":"MINUTE DE FOCUS","Give your next action a name, a category, and a reward.":"Dă următoarei acțiuni un nume, o categorie și o recompensă.","What would move you forward?":"Ce te-ar ajuta să avansezi?","Consistency, without the pressure.":"Consecvență fără presiune.","Build small rituals that still count on difficult days. Check in once a day.":"Construiește ritualuri mici care contează și în zilele grele. Bifează o dată pe zi.","A small habit, e.g. read 10 pages":"Un obicei mic, de ex. citește 10 pagini","＋  Add habit":"＋  Adaugă obicei","One task. One window. Everything else can wait.":"O sarcină. O fereastră. Restul poate aștepta.","A private ledger that stays on this computer.":"Un registru privat care rămâne pe acest computer.","Transaction description":"Descrierea operației","A private space to think. Your entries stay on this device.":"Un spațiu privat pentru gânduri. Înregistrările rămân pe acest dispozitiv.","Give this entry a title":"Dă un titlu înregistrării","What is on your mind today? Start anywhere.":"La ce te gândești azi? Începe de oriunde.","Double-click an entry to read it.":"Dublu clic pentru a citi înregistrarea.","Delete quest":"Șterge sarcina","Delete this quest permanently?":"Ștergi definitiv această sarcină?","Delete this habit and its streak history?":"Ștergi acest obicei și istoricul seriei?","Delete transaction":"Șterge operația","Delete this transaction permanently?":"Ștergi definitiv această operație?","Select a quest first.":"Selectează mai întâi o sarcină.","That quest is already completed.":"Această sarcină este deja finalizată.","Select a habit first.":"Selectează mai întâi un obicei.","Select a journal entry first.":"Selectează mai întâi o înregistrare.","No matching entries yet.":"Nu există încă înregistrări potrivite.","Delete journal entry":"Șterge înregistrarea","Delete this entry permanently? This cannot be undone.":"Ștergi definitiv această înregistrare? Acțiunea nu poate fi anulată.","Create NEXUS backup":"Creează backup NEXUS","Backup created successfully.":"Backup creat cu succes.","Export NEXUS data":"Exportă datele NEXUS","JSON export created successfully.":"Export JSON creat cu succes.",
            "WORKSPACE":"SPAȚIU DE LUCRU","YOUR SYSTEM":"SISTEMUL TĂU","A little progress, every day.":"Puțin progres, în fiecare zi.",
            "Backup":"Backup","Export":"Export","Create a new quest":"Creează o sarcină","Your quest board":"Panoul tău",
            "All quests":"Toate sarcinile","Open only":"Doar deschise","Completed":"Finalizate","＋  Add quest":"＋  Adaugă sarcină",
            "✓  Complete selected  +XP":"✓  Finalizează +XP","Delete selected":"Șterge","Edit selected":"Editează",
            "Today's check-in":"Astăzi","✓  Toggle today's check-in":"✓  Bifează azi","Delete habit":"Șterge obiceiul",
            "Protect your attention.":"Protejează-ți atenția.","Session length":"Durata sesiunii","Start / Pause":"Start / Pauză","Reset":"Resetare",
            "Know where your money goes.":"Știi unde merg banii.","Recent activity":"Activitate recentă","＋  Add entry":"＋  Adaugă operație",
            "Expense":"Cheltuială","Income":"Venit","Clear your head.":"Eliberează-ți mintea.","Recent entries":"Înregistrări recente",
            "Search titles and thoughts…":"Caută în notițe…","Save entry  ↗":"Salvează ↗","Delete selected entry":"Șterge înregistrarea",
            "Personalize NEXUS":"Personalizează NEXUS","Your profile":"Profilul tău","Save profile":"Salvează profilul","Display name":"Nume","Email":"Email","Username":"Utilizator","Profile saved.":"Profil salvat.","Appearance":"Aspect","Interface language":"Limba interfeței","Currency":"Valută",
            
            "quest":"sarcină","quests":"sarcini","left to move forward.":"până la următorul pas.","habits complete":"obiceiuri finalizate","quests completed overall":"sarcini finalizate în total","focus minutes logged":"minute de focus",
            "No open quests. Enjoy the breathing room.":"Nu ai sarcini deschise. Poți respira.","No completed quests yet.":"Nu există sarcini finalizate.","Your quest board is clear. Addă prima.":"Panoul de sarcini este gol. Adaugă prima.",
            "Edit quest":"Editează sarcina","Edit habit":"Editează obiceiul","Edit transaction":"Editează operația","Edit note":"Editează nota",
            "You're building consistency.":"Îți construiești consecvența.","Add one small habit to begin.":"Adaugă un obicei mic.",
            "Your next win is waiting.":"Următoarea victorie te așteaptă.","No open quests. Add a small win.":"Nu ai sarcini deschise. Adaugă o mică victorie.",
            "Timer reset.":"Cronometrul a fost resetat.","Session complete. Nice work.":"Sesiunea s-a încheiat. Bravo.","Focus mode active. Keep going.":"Modul focus este activ. Continuă.",
            "Paused. Resume when ready.":"Pauză. Reia când ești gata.","Ready when you are.":"Gata când ești."
        };
        if self.language == "Русский":
            return ru.get(text, text)
        if self.language == "Română":
            return ro.get(text, text)
        return text

    def _translate_tree(self) -> None:
        from PySide6.QtWidgets import QApplication
        for widget in QApplication.allWidgets():
            if widget.objectName() in {"Nav", "Hero"} or widget is getattr(self, "page_title", None):
                continue
            if isinstance(widget, (QLabel, QPushButton)):
                original = widget.property("nexus_original_text")
                if original is None:
                    original = widget.text()
                    widget.setProperty("nexus_original_text", original)
                widget.setText(self._tr(original))
            elif isinstance(widget, (QLineEdit, QTextEdit)):
                original = widget.property("nexus_original_placeholder")
                if original is None:
                    original = widget.placeholderText()
                    widget.setProperty("nexus_original_placeholder", original)
                if original:
                    widget.setPlaceholderText(self._tr(original))

    def _apply_language(self) -> None:
        translations = {
            "English": ["Overview", "Quests", "Habits", "Focus", "Finance", "Journal", "Calendar", "Insights", "Settings"],
            "Русский": ["Обзор", "Задачи", "Привычки", "Фокус", "Финансы", "Дневник", "Календарь", "Статистика", "Настройки"],
            "Română": ["Panou", "Sarcini", "Obiceiuri", "Focus", "Finanțe", "Jurnal", "Calendar", "Statistici", "Setări"],
        }
        names = translations.get(self.language, translations["English"])
        symbols = ["⌂", "◇", "✳", "◷", "↗", "▤", "▦", "◒", "⚙"]
        for i in range(len(self.page_names)):
            button = self.nav.button(i)
            if button:
                button.setText(f"{symbols[i]}     {names[i]}")
        self.page_title.setText(names[self.pages.currentIndex()])
        if hasattr(self, "language_note"):
            self.language_note.setText(self._tr("Interface language"))
        self._translate_tree()

    def _settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(13)
        card = panel()
        box = QVBoxLayout(card)
        box.setContentsMargins(22, 20, 22, 20)
        box.setSpacing(16)
        box.addWidget(heading("Personalize NEXUS", "Hero"))
        box.addWidget(QLabel("Change the atmosphere, language, and money format. Your choices are saved locally."))

        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Appearance"))
        theme_row.addStretch(1)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["NEXUS Lime", "Violet Night", "Sunset Ember", "Ocean Neon", "Mono"])
        self.theme_combo.setCurrentText(self.theme)
        self.theme_combo.currentTextChanged.connect(self._change_theme)
        theme_row.addWidget(self.theme_combo)
        box.addLayout(theme_row)

        lang_row = QHBoxLayout()
        self.language_note = QLabel("Interface language")
        lang_row.addWidget(self.language_note)
        lang_row.addStretch(1)
        self.language_combo = QComboBox()
        self.language_combo.addItems(["English", "Русский", "Română"])
        self.language_combo.setCurrentText(self.language)
        self.language_combo.currentTextChanged.connect(self._change_language)
        lang_row.addWidget(self.language_combo)
        box.addLayout(lang_row)

        money_row = QHBoxLayout()
        money_row.addWidget(QLabel("Currency"))
        money_row.addStretch(1)
        self.currency_combo = QComboBox()
        self.currency_combo.addItems(["RUB", "PMR", "USD", "EUR", "USDT"])
        self.currency_combo.setCurrentText(self.currency)
        self.currency_combo.currentTextChanged.connect(self._change_currency)
        money_row.addWidget(self.currency_combo)
        box.addLayout(money_row)


        profile_card = panel()
        profile_box = QVBoxLayout(profile_card)
        profile_box.setContentsMargins(18, 16, 18, 16)
        profile_box.setSpacing(10)
        profile_box.addWidget(heading("Your profile", "Section"))
        profile_box.addWidget(QLabel("Local profile and cloud identity are separate by design. Your local workspace stays available offline."))
        profile_row = QHBoxLayout()
        self.profile_name = QLineEdit()
        self.profile_name.setPlaceholderText("Display name")
        self.profile_email = QLineEdit()
        self.profile_email.setPlaceholderText("Email")
        self.profile_username = QLineEdit()
        self.profile_username.setPlaceholderText("Username")
        save_profile = QPushButton("Save profile")
        save_profile.setObjectName("Primary")
        save_profile.clicked.connect(self._save_profile)
        profile_row.addWidget(self.profile_name, 2)
        profile_row.addWidget(self.profile_email, 2)
        profile_row.addWidget(self.profile_username, 2)
        profile_row.addWidget(save_profile)
        profile_box.addLayout(profile_row)
        summary = self.db.account_summary()
        self.profile_stats = QLabel(f'{summary["tasks_done"]}/{summary["tasks"]} quests  ·  {summary["xp"]} XP  ·  {summary["focus_sessions"]} focus sessions')
        self.profile_stats.setObjectName("Muted")
        profile_box.addWidget(self.profile_stats)
        password_button = QPushButton("Change password")
        password_button.clicked.connect(self._change_password)
        profile_box.addWidget(password_button)
        profile = self.db.get_profile()
        if profile:
            self.profile_name.setText(profile["name"])
            self.profile_email.setText(profile["email"])
            self.profile_username.setText(profile["username"])
            if hasattr(self, "profile_stats"):
                summary = self.db.account_summary()
                self.profile_stats.setText(f'{summary["tasks_done"]}/{summary["tasks"]} quests  ·  {summary["xp"]} XP  ·  {summary["focus_sessions"]} focus sessions')
        box.addWidget(profile_card)

        sync_card = panel()
        sync_box = QVBoxLayout(sync_card)
        sync_box.setContentsMargins(18, 16, 18, 16)
        sync_box.setSpacing(10)
        sync_box.addWidget(heading("Cloud sync", "Section"))
        sync_box.addWidget(QLabel("Optional encrypted-in-transit sync between this desktop and your NEXUS API account."))
        api_row = QHBoxLayout()
        api_row.addWidget(QLabel("API endpoint"))
        self.sync_api_url = QLineEdit(self.sync_client.api_url)
        self.sync_api_url.setPlaceholderText("https://api.example.com")
        api_row.addWidget(self.sync_api_url, 1)
        sync_box.addLayout(api_row)
        self.sync_status = QLabel()
        self.sync_status.setObjectName("Muted")
        sync_box.addWidget(self.sync_status)
        self.sync_progress = QProgressBar()
        self.sync_progress.setRange(0, 0)
        self.sync_progress.setMaximumHeight(5)
        self.sync_progress.setVisible(False)
        sync_box.addWidget(self.sync_progress)
        self.sync_stats_label = QLabel("↑ 0 pushed  ·  ↓ 0 pulled")
        self.sync_stats_label.setObjectName("Tiny")
        sync_box.addWidget(self.sync_stats_label)
        self.cloud_profile_label = QLabel("Cloud profile: not connected")
        self.cloud_profile_label.setObjectName("Muted")
        sync_box.addWidget(self.cloud_profile_label)
        self.last_sync_label = QLabel("Last sync: never")
        self.last_sync_label.setObjectName("Tiny")
        sync_box.addWidget(self.last_sync_label)
        self.background_sync_label = QLabel("↻  Background sync: every 5 minutes")
        self.background_sync_label.setObjectName("Tiny")
        sync_box.addWidget(self.background_sync_label)
        sync_row = QHBoxLayout()
        cloud_connect = QPushButton("☁  Connect cloud account")
        cloud_connect.clicked.connect(self._connect_cloud)
        cloud_register = QPushButton("+  Create cloud account")
        cloud_register.clicked.connect(self._register_cloud)
        cloud_sync = QPushButton("↻  Sync now")
        cloud_sync.setObjectName("Primary")
        cloud_sync.clicked.connect(self._cloud_sync)
        self.cloud_sync_button = cloud_sync
        cloud_disconnect = QPushButton("Disconnect")
        cloud_disconnect.clicked.connect(self._disconnect_cloud)
        sync_row.addWidget(cloud_connect)
        sync_row.addWidget(cloud_register)
        sync_row.addWidget(cloud_sync)
        sync_row.addWidget(cloud_disconnect)
        sync_box.addLayout(sync_row)

        conflicts_label = QLabel("CONFLICTS")
        conflicts_label.setObjectName("Tiny")
        sync_box.addWidget(conflicts_label)
        self.sync_conflicts_label = QLabel("No unresolved conflicts")
        self.sync_conflicts_label.setObjectName("Muted")
        sync_box.addWidget(self.sync_conflicts_label)
        resolve_conflicts = QPushButton("⚡  Review conflicts")
        resolve_conflicts.clicked.connect(self._show_sync_conflicts)
        sync_box.addWidget(resolve_conflicts)

        history_label = QLabel("SYNC HISTORY")
        history_label.setObjectName("Tiny")
        sync_box.addWidget(history_label)
        self.sync_history = QListWidget()
        self.sync_history.setMaximumHeight(180)
        self.sync_history.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        sync_box.addWidget(self.sync_history)
        history_refresh = QPushButton("↻  Refresh history")
        history_refresh.clicked.connect(self._refresh_sync_history)
        sync_box.addWidget(history_refresh)

        devices_label = QLabel("DEVICES")
        devices_label.setObjectName("Tiny")
        sync_box.addWidget(devices_label)
        self.cloud_devices = QListWidget()
        self.cloud_devices.setMaximumHeight(220)
        self.cloud_devices.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.cloud_devices.itemDoubleClicked.connect(self._manage_selected_device)
        self.cloud_devices.setVisible(False)
        sync_box.addWidget(self.cloud_devices)
        devices_row = QHBoxLayout()
        refresh_devices = QPushButton("↻  Refresh devices")
        refresh_devices.clicked.connect(self._refresh_cloud_devices)
        devices_row.addWidget(refresh_devices)
        logout_all = QPushButton("⎋  Sign out all devices")
        logout_all.clicked.connect(self._logout_all_cloud_devices)
        devices_row.addWidget(logout_all)
        devices_row.addStretch(1)
        sync_box.addLayout(devices_row)

        box.addWidget(sync_card)
        self._refresh_sync_status()

        box.addSpacing(8)
        account_card = panel()
        account_box = QVBoxLayout(account_card)
        account_box.setContentsMargins(18, 16, 18, 16)
        account_box.addWidget(heading("Account", "Section"))
        account_box.addWidget(QLabel("Switch without mixing workspaces. Every account keeps its own data on this PC."))
        switch_account = QPushButton("⇄  Switch account")
        switch_account.setMinimumHeight(42)
        switch_account.clicked.connect(self._switch_account)
        account_box.addWidget(switch_account)
        box.addWidget(account_card)

        box.addWidget(heading("NEXUS // LOCAL CONFIG", "Tiny"))
        box.addWidget(QLabel("No account required. Preferences are stored with your desktop app settings."))
        box.addStretch(1)
        layout.addWidget(card)
        layout.addStretch(1)
        return page


    def _logout_all_cloud_devices(self) -> None:
        if not self.sync_client.token:
            return
        answer = QMessageBox.question(
            self,
            "Sign out all devices",
            "This will invalidate every active NEXUS cloud session. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.sync_client._request("POST", "/auth/logout-all")
        except SyncError as error:
            QMessageBox.warning(self, "Sign out", str(error))
            return
        self.sync_client.token = ""
        self.sync_client.refresh_token = ""
        self.cloud_user = {}
        self._save_cloud_tokens("", "")
        self.cloud_devices.clear()
        self.cloud_devices.setVisible(False)
        self._refresh_sync_status()
        self._message("Signed out from all cloud devices.")

    def _refresh_cloud_devices(self) -> None:
        if not self.sync_client.token:
            self.cloud_devices.clear()
            self.cloud_devices.setVisible(False)
            return
        try:
            devices = self.sync_client._request("GET", "/devices")
        except SyncError as error:
            QMessageBox.warning(self, "Devices", str(error))
            return
        self.cloud_devices.clear()
        for device in devices:
            current = "  ·  THIS DEVICE" if device.get("id") == self.sync_client.device_id else ""
            item = QListWidgetItem(
                f"{device.get('name', 'NEXUS device')}{current}\n"
                f"{self._device_status(device.get('last_seen_at', ''))}  ·  Last seen: {device.get('last_seen_at', 'unknown')}"
            )
            item.setData(Qt.ItemDataRole.UserRole, device)
            self.cloud_devices.addItem(item)
        self.cloud_devices.setVisible(bool(devices))

    @staticmethod
    def _device_status(last_seen: str) -> str:
        if not last_seen:
            return "○ Unknown"
        try:
            seen = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - seen).total_seconds()
            if age < 120:
                return "● Online"
            if age < 900:
                return "◐ Recently active"
            return "○ Offline"
        except (ValueError, TypeError):
            return "○ Unknown"

    def _manage_selected_device(self, item: QListWidgetItem) -> None:
        device = item.data(Qt.ItemDataRole.UserRole) or {}
        device_id = device.get("id")
        if not device_id:
            return
        if device_id == self.sync_client.device_id:
            QMessageBox.information(self, "Device", "This is the current device. Use Sign out all devices for a full reset.")
            return
        answer = QMessageBox.question(
            self,
            "Revoke device",
            f"Revoke access for “{device.get('name', 'NEXUS device')}”?\n\n"
            "Its active sessions and refresh tokens will be invalidated.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.sync_client._request("DELETE", f"/devices/{device_id}")
        except SyncError as error:
            QMessageBox.warning(self, "Devices", str(error))
            return
        self._refresh_cloud_devices()
        self._message(f"Device access revoked: {device.get('name', 'NEXUS device')}.")

    def _save_cloud_tokens(self, access_token: str, refresh_token: str) -> None:
        if access_token:
            save_secret(self.settings, "cloud_access_token", access_token)
        else:
            clear_secret(self.settings, "cloud_access_token")
        if refresh_token:
            save_secret(self.settings, "cloud_refresh_token", refresh_token)
        else:
            clear_secret(self.settings, "cloud_refresh_token")

    def _sync_endpoint(self) -> None:
        endpoint = self.sync_api_url.text().strip().rstrip("/") if hasattr(self, "sync_api_url") else self.sync_client.api_url
        if endpoint:
            self.sync_client.api_url = endpoint
            self.settings.setValue("cloud_api_url", endpoint)

    def _refresh_sync_status(self) -> None:
        if not hasattr(self, "sync_status"):
            return
        if self.sync_client.token:
            self.sync_status.setText(f"● CLOUD CONNECTED  ·  {self.sync_client.api_url}")
            self.sync_status.setObjectName("StatusGood")
            if not self.cloud_user:
                try:
                    self.cloud_user = self.sync_client._request("GET", "/me")
                except SyncError:
                    self.cloud_user = {}
            if self.cloud_user:
                self.cloud_profile_label.setText(
                    f"☁  {self.cloud_user.get('name', self.cloud_user.get('username', 'NEXUS user'))}  ·  @{self.cloud_user.get('username', '')}"
                )
            else:
                self.cloud_profile_label.setText("☁  Cloud profile connected")
            self.last_sync_label.setText(
                f"Last sync: {self.sync_client.last_sync_at or 'never'}"
            )
        else:
            self.sync_status.setText(f"○ CLOUD OFFLINE  ·  API {self.sync_client.api_url}")
            self.sync_status.setObjectName("StatusWarn")
            self.cloud_profile_label.setText("Cloud profile: not connected")
            self.last_sync_label.setText("Last sync: never")
        self.sync_status.style().unpolish(self.sync_status)
        self.sync_status.style().polish(self.sync_status)

    def _connect_cloud(self) -> None:
        self._sync_endpoint()
        identifier, ok = QInputDialog.getText(self, "Connect cloud account", "Username or email:")
        if not ok or not identifier.strip():
            return
        password, ok = QInputDialog.getText(self, "Connect cloud account", "Cloud password:", QLineEdit.EchoMode.Password)
        if not ok:
            return
        try:
            user = self.sync_client.login(identifier.strip(), password)
            self.cloud_user = user
            self._save_cloud_tokens(self.sync_client.token, self.sync_client.refresh_token)
            self._refresh_sync_status()
            self._message(f"Cloud connected as @{user['username']}.")
        except SyncError as error:
            self._message(str(error))

    def _register_cloud(self) -> None:
        self._sync_endpoint()
        name, ok = QInputDialog.getText(self, "Create cloud account", "Name:")
        if not ok or not name.strip():
            return
        email, ok = QInputDialog.getText(self, "Create cloud account", "Email:")
        if not ok or not email.strip():
            return
        username, ok = QInputDialog.getText(self, "Create cloud account", "Username:")
        if not ok or not username.strip():
            return
        password, ok = QInputDialog.getText(self, "Create cloud account", "Password (6+ characters):", QLineEdit.EchoMode.Password)
        if not ok:
            return
        try:
            user = self.sync_client.register(name.strip(), email.strip(), username.strip(), password)
            self.cloud_user = user
            self._save_cloud_tokens(self.sync_client.token, self.sync_client.refresh_token)
            self._refresh_sync_status()
            self._message(f"Cloud account created for @{user['username']}.")
        except SyncError as error:
            self._message(str(error))

    def _refresh_sync_history(self) -> None:
        if not hasattr(self, "sync_history"):
            return
        self.sync_history.clear()
        if not self.sync_client.token:
            self.sync_history.addItem("Connect a cloud account to see sync history.")
            return
        try:
            history = self.sync_client.list_history(20)
        except Exception:
            self.sync_history.addItem("Sync history unavailable.")
            return
        if not history:
            self.sync_history.addItem("No sync runs yet.")
            return
        for run in history:
            status = run.get("status", "unknown").upper()
            stamp = run.get("finished_at") or run.get("started_at", "")
            pushed = int(run.get("pushed", 0))
            pulled = int(run.get("pulled", 0))
            conflicts = int(run.get("conflicts", 0))
            detail = f"↑ {pushed}  ·  ↓ {pulled}"
            if conflicts:
                detail += f"  ·  ⚠ {conflicts} conflicts"
            if run.get("error"):
                detail += f"  ·  {run['error']}"
            item = QListWidgetItem(f"{status}  ·  {stamp}\n{detail}")
            self.sync_history.addItem(item)

    def _refresh_sync_conflicts(self) -> None:
        if not hasattr(self, "sync_conflicts_label"):
            return
        try:
            count = len(self.sync_client.list_conflicts())
            self.sync_conflicts_label.setText(
                f"⚠  {count} conflict{'s' if count != 1 else ''} need review"
                if count else "No unresolved conflicts"
            )
        except Exception:
            self.sync_conflicts_label.setText("Conflict status unavailable")

    def _show_sync_conflicts(self) -> None:
        conflicts = self.sync_client.list_conflicts()
        if not conflicts:
            QMessageBox.information(self, "Sync Center", "No unresolved conflicts. Your cloud data is in sync.")
            return
        conflict = conflicts[0]
        dialog = QDialog(self)
        dialog.setWindowTitle("NEXUS · Resolve conflict")
        dialog.resize(760, 520)
        layout = QVBoxLayout(dialog)
        layout.addWidget(heading(f"Conflict · {conflict['entity']}", "Section"))
        layout.addWidget(QLabel("The same record was changed locally and in the cloud. Choose which version survives."))

        def preview(title: str, payload: dict) -> QTextEdit:
            box = QTextEdit()
            box.setReadOnly(True)
            box.setPlainText(repr(payload))
            box.setPlaceholderText(title)
            return box

        columns = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel("LOCAL VERSION"))
        left.addWidget(preview("Local", conflict["local_payload"]))
        right = QVBoxLayout()
        right.addWidget(QLabel("CLOUD VERSION"))
        right.addWidget(preview("Cloud", conflict["remote_payload"]))
        columns.addLayout(left, 1)
        columns.addLayout(right, 1)
        layout.addLayout(columns)

        buttons = QHBoxLayout()
        local = QPushButton("Keep local")
        remote = QPushButton("Use cloud")
        local.setObjectName("Primary")
        remote.setObjectName("Primary")
        buttons.addWidget(local)
        buttons.addWidget(remote)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        def resolve(choice: str) -> None:
            try:
                self.sync_client.resolve_conflict(conflict["id"], choice)
                dialog.accept()
                self._refresh_sync_conflicts()
                self.refresh_all()
                self._message(f"Conflict resolved: {'local' if choice == 'local' else 'cloud'} version kept.")
            except SyncError as error:
                QMessageBox.warning(dialog, "Conflict", str(error))

        local.clicked.connect(lambda: resolve("local"))
        remote.clicked.connect(lambda: resolve("remote"))
        dialog.exec()

    def _set_sync_center_state(self, state: str, result: dict | None = None) -> None:
        if not hasattr(self, "sync_progress"):
            return
        connected = bool(self.sync_client.token)
        if state == "syncing":
            self.sync_progress.setVisible(True)
            self.sync_status.setText("●  Syncing cloud data…")
            self.cloud_sync_button.setEnabled(False)
            self.cloud_sync_button.setText("↻  Syncing…")
            return
        self.sync_progress.setVisible(False)
        self.cloud_sync_button.setEnabled(True)
        self.cloud_sync_button.setText("↻  Sync now")
        if state == "offline":
            self.sync_status.setText("○  Offline · will retry automatically")
            return
        if not connected:
            self.sync_status.setText("○  Cloud not connected")
            return
        self.sync_status.setText("●  Connected")
        if result:
            self.sync_stats_label.setText(
                f"↑ {result.get('pushed', 0)} pushed  ·  ↓ {result.get('pulled', 0)} pulled"
            )
        self.last_sync_label.setText(
            f"Last sync: {self.sync_client.last_sync_at or 'never'}"
        )
        self._refresh_sync_conflicts()

    def _background_cloud_sync(self) -> None:
        if (
            not self.sync_client.token
            or self._cloud_sync_running
            or (self._cloud_worker and self._cloud_worker.isRunning())
        ):
            return
        self._cloud_sync_running = True
        self._set_sync_center_state("syncing")
        self._cloud_worker = CloudSyncWorker(self.sync_client)
        self._cloud_worker.finished.connect(self._on_background_sync_finished)
        self._cloud_worker.failed.connect(self._on_background_sync_failed)
        self._cloud_worker.finished.connect(self._cleanup_cloud_worker)
        self._cloud_worker.failed.connect(self._cleanup_cloud_worker)
        self._cloud_worker.start()

    def _on_background_sync_finished(self, result: dict) -> None:
        self._cloud_sync_running = False
        self._set_sync_center_state("connected", result)
        self._refresh_sync_status()
        self.refresh_all()

    def _on_background_sync_failed(self, message: str) -> None:
        self._cloud_sync_running = False
        if self.sync_client.token:
            self._set_sync_center_state("offline")
            self._refresh_sync_status()

    def _cleanup_cloud_worker(self, *_args) -> None:
        worker = self._cloud_worker
        self._cloud_worker = None
        if worker:
            worker.deleteLater()


    def _cloud_sync(self) -> None:
        self._sync_endpoint()
        if not self.sync_client.token:
            self._connect_cloud()
            if not self.sync_client.token:
                return
        if self._cloud_sync_running or (self._cloud_worker and self._cloud_worker.isRunning()):
            return
        self._cloud_sync_running = True
        self._set_sync_center_state("syncing")
        self._cloud_worker = CloudSyncWorker(self.sync_client)
        self._cloud_worker.finished.connect(self._on_manual_sync_finished)
        self._cloud_worker.failed.connect(self._on_manual_sync_failed)
        self._cloud_worker.finished.connect(self._cleanup_cloud_worker)
        self._cloud_worker.failed.connect(self._cleanup_cloud_worker)
        self._cloud_worker.start()

    def _on_manual_sync_finished(self, result: dict) -> None:
        self._cloud_sync_running = False
        self._set_sync_center_state("connected", result)
        self._refresh_sync_status()
        self.refresh_all()
        self._message(
            f"Sync complete. Pulled {result.get('pulled', 0)} records, "
            f"pushed {result.get('pushed', 0)}."
        )

    def _on_manual_sync_failed(self, message: str) -> None:
        self._cloud_sync_running = False
        self._set_sync_center_state("offline")
        self._refresh_sync_status()
        self._message(message)

    def _disconnect_cloud(self) -> None:
        try:
            self.sync_client.logout()
        except SyncError:
            pass
        self.cloud_user = {}
        clear_secret(self.settings, "cloud_access_token")
        clear_secret(self.settings, "cloud_refresh_token")
        self._refresh_sync_status()
        self._message("Cloud account disconnected. Local data remains untouched.")

    def _switch_account(self) -> None:
        answer = QMessageBox.question(self, "Switch account", "Return to the account chooser?\n\nYour local NEXUS data will remain on this PC.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes)
        if answer == QMessageBox.StandardButton.Yes:
            # Auth screens replace the central widget. Remove workspace shortcuts
            # first so repeated account switches cannot stack duplicate hotkeys.
            for shortcut in getattr(self, "_shortcuts", []):
                shortcut.deleteLater()
            self._shortcuts = []
            self._show_auth_choice()

    def _change_password(self) -> None:
        profile = self.db.get_profile()
        if not profile:
            self._message("No local profile is available.")
            return
        current, ok = QInputDialog.getText(self, "Change password", "Current password:", QLineEdit.EchoMode.Password)
        if not ok:
            return
        if not self.db.verify_profile_password(current):
            self._message("Current password is incorrect.")
            return
        new_password, ok = QInputDialog.getText(self, "Change password", "New password (6+ characters):", QLineEdit.EchoMode.Password)
        if not ok:
            return
        if len(new_password) < 6:
            self._message("New password must be at least 6 characters.")
            return
        confirm, ok = QInputDialog.getText(self, "Change password", "Repeat new password:", QLineEdit.EchoMode.Password)
        if not ok:
            return
        if new_password != confirm:
            self._message("The new passwords do not match.")
            return
        try:
            self.db.save_profile(profile["name"], profile["email"], profile["username"], new_password)
            self._message("Password changed successfully.")
        except ValueError as error:
            self._message(str(error))

    def _save_profile(self) -> None:
        try:
            self.db.save_profile(self.profile_name.text(), self.profile_email.text(), self.profile_username.text())
            self._message(self._tr("Profile saved.") if self.language != "English" else "Profile saved.")
        except ValueError as error:
            self._message(str(error))

    def _change_theme(self, theme: str) -> None:
        self.theme = theme
        self.settings.setValue("theme", theme)
        self._apply_theme()

    def _change_language(self, language: str) -> None:
        self.language = language
        self.settings.setValue("language", language)
        self._apply_language()

    def _change_currency(self, currency: str) -> None:
        self.currency = currency
        self.settings.setValue("currency", currency)
        self._apply_currency()
        self.refresh_all()

    def _navigate(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.page_title.setText(self._translated_names()[index])
        button = self.nav.button(index)
        if button and not button.isChecked():
            button.setChecked(True)
        self.refresh_all()

    def _overview_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(13)

        hero_row = QHBoxLayout()
        hero_row.setSpacing(13)
        hero = QFrame()
        hero.setObjectName("HeroPanel")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(23, 20, 23, 20)
        hero_layout.setSpacing(8)
        hero_layout.addWidget(heading("YOUR PERSONAL COMMAND CENTER", "Eyebrow"))
        hero_layout.addWidget(heading("Make room for\nwhat matters.", "Hero"))
        sub = QLabel("Less noise. More intention. One good move at a time.")
        sub.setObjectName("Muted")
        hero_layout.addWidget(sub)
        hero_actions = QHBoxLayout()
        create = QPushButton("+  Create a quest")
        create.setObjectName("Primary")
        create.clicked.connect(self._add_task)
        hero_actions.addWidget(create, 0)
        hero_actions.addWidget(heading("SMALL ACTIONS. REAL MOMENTUM.", "Tiny"), 1)
        hero_layout.addLayout(hero_actions)
        hero_row.addWidget(hero, 3)

        signal = QFrame()
        signal.setObjectName("AccentPanel")
        signal_layout = QVBoxLayout(signal)
        signal_layout.setContentsMargins(19, 18, 19, 18)
        signal_layout.setSpacing(8)
        eyebrow = heading("YOUR MOMENTUM", "Tiny")
        eyebrow.setStyleSheet("color: #515b3a;")
        signal_layout.addWidget(eyebrow)
        signal_layout.addStretch(1)
        self.hero_xp_label = QLabel("0 XP")
        self.hero_xp_label.setObjectName("AccentText")
        self.hero_xp_label.setStyleSheet("font-size: 36px; font-weight: 850; letter-spacing: -1px;")
        signal_layout.addWidget(self.hero_xp_label)
        signal_layout.addWidget(heading("TOTAL EXPERIENCE EARNED", "Tiny"))
        self.hero_quest_copy = QLabel("Your next win is waiting.")
        self.hero_quest_copy.setObjectName("AccentText")
        self.hero_quest_copy.setWordWrap(True)
        signal_layout.addWidget(self.hero_quest_copy)
        signal_layout.addStretch(1)
        hero_row.addWidget(signal, 1)
        layout.addLayout(hero_row)

        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(11)
        self.metric_labels: dict[str, QLabel] = {}
        metrics = [
            ("tasks_done", "QUESTS DONE", "0", "↗"),
            ("xp", "TOTAL EXPERIENCE", "0 XP", "✳"),
            ("habits_done", "HABITS TODAY", "0/0", "◷"),
            ("balance", "NET BALANCE", "0.00", "⌁"),
        ]
        for key, label, default, symbol in metrics:
            card = panel()
            box = QVBoxLayout(card)
            box.setContentsMargins(15, 14, 15, 14)
            box.setSpacing(8)
            line = QHBoxLayout()
            caption = heading(label, "Tiny")
            line.addWidget(caption)
            line.addStretch(1)
            glyph = QLabel(symbol)
            glyph.setStyleSheet("color: #a69bd8; font-size: 16px; font-weight: 800;")
            line.addWidget(glyph)
            box.addLayout(line)
            value = heading(default, "MetricAccent" if key == "xp" else "Metric")
            box.addWidget(value)
            self.metric_labels[key] = value
            metrics_row.addWidget(card, 1)
        layout.addLayout(metrics_row)

        bottom = QHBoxLayout()
        bottom.setSpacing(13)
        quest_card = panel()
        ql = QVBoxLayout(quest_card)
        ql.setContentsMargins(16, 15, 16, 14)
        ql.setSpacing(8)
        qhead = QHBoxLayout()
        qhead.addWidget(heading("Next up", "Section"))
        qhead.addStretch(1)
        qhead.addWidget(heading("OPEN QUESTS", "Tiny"))
        ql.addLayout(qhead)
        quick = QHBoxLayout()
        for title, handler in [("＋ Quest", self._add_task), ("＋ Expense", self._add_transaction), ("✎ Journal", lambda: self._navigate(5)), ("▶ Focus", lambda: self._navigate(3))]:
            button = QPushButton(title)
            button.clicked.connect(handler)
            quick.addWidget(button)
        ql.addLayout(quick)
        self.overview_tasks = QListWidget()
        self.overview_tasks.setMinimumHeight(145)
        self.overview_tasks.setMaximumHeight(180)
        ql.addWidget(self.overview_tasks, 1)
        bottom.addWidget(quest_card, 5)

        habit_card = panel()
        hl = QVBoxLayout(habit_card)
        hl.setContentsMargins(16, 15, 16, 14)
        hl.setSpacing(10)
        hl.addWidget(heading("Daily rhythm", "Section"))
        hl.addWidget(heading("CHECK IN", "Tiny"))
        self.overview_habits = QLabel("Start with one small habit.")
        self.overview_habits.setWordWrap(True)
        self.overview_habits.setStyleSheet("font-size: 13px; color: #d7d5e2;")
        hl.addWidget(self.overview_habits)
        hl.addStretch(1)
        hl.addWidget(heading("TODAY'S COMPLETION", "Tiny"))
        self.habits_progress = QProgressBar()
        self.habits_progress.setRange(0, 100)
        self.habits_progress.setValue(0)
        hl.addWidget(self.habits_progress)
        self.habits_copy = QLabel("0 of 0 habits complete")
        self.habits_copy.setObjectName("Muted")
        hl.addWidget(self.habits_copy)
        bottom.addWidget(habit_card, 3)

        progress_card = panel()
        pl = QVBoxLayout(progress_card)
        pl.setContentsMargins(16, 15, 16, 14)
        pl.setSpacing(10)
        pl.addWidget(heading("Momentum", "Section"))
        pl.addWidget(heading("ALL-TIME QUEST PROGRESS", "Tiny"))
        self.level_progress = QProgressBar()
        self.level_progress.setRange(0, 100)
        pl.addWidget(self.level_progress)
        self.level_copy = QLabel("Level 1 · 0/500 XP · 0 day streak")
        self.level_copy.setObjectName("Muted")
        pl.addWidget(self.level_copy)
        self.daily_progress = QProgressBar()
        self.daily_progress.setRange(0, 100)
        pl.addWidget(self.daily_progress)
        self.progress_copy = QLabel("Your next small win is waiting.")
        self.progress_copy.setWordWrap(True)
        self.progress_copy.setObjectName("Muted")
        pl.addWidget(self.progress_copy)
        pl.addSpacing(2)
        pl.addWidget(heading("LAST 7 DAYS", "Tiny"))
        self.activity_chart = WeeklyActivityChart()
        pl.addWidget(self.activity_chart)
        self.streak_badge = heading("0 DAY STREAK", "Pill")
        pl.addWidget(self.streak_badge)
        pl.addStretch(1)
        focus_line = QHBoxLayout()
        focus_line.addWidget(heading("FOCUS MINUTES", "Tiny"))
        focus_line.addStretch(1)
        self.focus_minutes_copy = heading("0 min", "MetricAccent")
        focus_line.addWidget(self.focus_minutes_copy)
        pl.addLayout(focus_line)
        bottom.addWidget(progress_card, 3)
        layout.addLayout(bottom, 1)
        return page

    def _refresh_dashboard_summary(self) -> None:
        if not hasattr(self, "hero_xp_label"):
            return
        data = self.db.dashboard_summary()
        self.hero_xp_label.setText(f'{data["xp"]} XP')
        self.hero_quest_copy.setText(f'{data["open_tasks"]} open quests  ·  {data["done_today"]} completed today')
        if hasattr(self, "daily_progress"):
            target = max(data["week_done"], 7)
            self.daily_progress.setValue(min(100, int(data["week_done"] / target * 100)))
        if hasattr(self, "progress_copy"):
            self.progress_copy.setText(f'{data["week_done"]} quests completed across the last 7 days · {data["focus_today"]} focus min today')
        if hasattr(self, "focus_minutes_copy"):
            self.focus_minutes_copy.setText(f'{data["focus_today"]} min')

    def _quests_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(13)

        form_card = panel()
        form = QVBoxLayout(form_card)
        form.setContentsMargins(17, 16, 17, 16)
        form.setSpacing(10)
        form.addWidget(heading("Create a new quest", "Section"))
        form.addWidget(QLabel("Give your next action a name, a category, and a reward."))
        row = QHBoxLayout()
        self.task_input = QLineEdit()
        self.task_input.setPlaceholderText("What would move you forward?")
        self.task_category = QComboBox()
        self.task_category.addItems(["Personal", "Work", "Learning", "Health", "Creative"])
        self.task_xp = QSpinBox()
        self.task_xp.setRange(5, 500)
        self.task_xp.setValue(25)
        self.task_xp.setSuffix(" XP")
        add = QPushButton("＋  Add quest")
        add.setObjectName("Primary")
        add.clicked.connect(self._add_task_from_form)
        self.task_input.returnPressed.connect(self._add_task_from_form)
        row.addWidget(self.task_input, 3)
        row.addWidget(self.task_category, 1)
        row.addWidget(self.task_xp)
        row.addWidget(add)
        form.addLayout(row)
        layout.addWidget(form_card)

        list_card = panel()
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(17, 15, 17, 15)
        quest_header = QHBoxLayout()
        quest_header.addWidget(heading("Your quest board", "Section"))
        quest_header.addStretch(1)
        self.task_filter = QComboBox()
        self.task_filter.addItem("All quests", "all")
        self.task_filter.addItem("Open only", "open")
        self.task_filter.addItem("Completed", "done")
        self.task_filter.currentIndexChanged.connect(self._refresh_task_list)
        quest_header.addWidget(self.task_filter)
        list_layout.addLayout(quest_header)
        self.task_list = QListWidget()
        self.task_list.itemDoubleClicked.connect(lambda _item: self._edit_task())
        list_layout.addWidget(self.task_list, 1)
        actions = QHBoxLayout()
        complete = QPushButton("✓  Complete selected  +XP")
        complete.setObjectName("Primary")
        complete.clicked.connect(self._complete_task)
        delete = QPushButton("Delete selected")
        delete.clicked.connect(self._delete_task)

        edit = QPushButton("Edit selected")
        edit.clicked.connect(self._edit_task)
        actions.insertWidget(1, edit)
        actions.addWidget(complete)
        actions.addWidget(delete)
        actions.addStretch(1)
        list_layout.addLayout(actions)
        layout.addWidget(list_card, 1)
        return page
    def _habits_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(13)

        intro = panel()
        intro_layout = QVBoxLayout(intro)
        intro_layout.setContentsMargins(18, 16, 18, 16)
        intro_layout.setSpacing(6)
        intro_layout.addWidget(heading("Consistency, without the pressure.", "Section"))
        intro_layout.addWidget(QLabel("Build small rituals that still count on difficult days. Check in once a day."))
        row = QHBoxLayout()
        self.habit_input = QLineEdit()
        self.habit_input.setPlaceholderText("A small habit, e.g. read 10 pages")
        self.habit_input.returnPressed.connect(self._add_habit)
        add = QPushButton("＋  Add habit")
        add.setObjectName("Primary")
        add.clicked.connect(self._add_habit)
        row.addWidget(self.habit_input, 1)
        row.addWidget(add)
        intro_layout.addLayout(row)
        layout.addWidget(intro)

        list_card = panel()
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(17, 15, 17, 15)
        list_layout.addWidget(heading("Today's check-in", "Section"))
        self.habit_list = QListWidget()
        self.habit_list.itemDoubleClicked.connect(lambda _item: self._edit_habit())
        list_layout.addWidget(self.habit_list, 1)
        actions = QHBoxLayout()
        check = QPushButton("✓  Toggle today's check-in")
        check.setObjectName("Primary")
        check.clicked.connect(self._toggle_habit)
        remove = QPushButton("Delete habit")
        remove.clicked.connect(self._delete_habit)

        edit = QPushButton("Edit selected")
        edit.clicked.connect(self._edit_habit)
        actions.insertWidget(1, edit)
        actions.addWidget(check)
        actions.addWidget(remove)
        actions.addStretch(1)
        list_layout.addLayout(actions)
        layout.addWidget(list_card, 1)
        return page
    def _focus_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addStretch(1)
        card = panel()
        card.setMaximumWidth(540)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 28, 28, 28)
        card_layout.setSpacing(16)
        card_layout.addWidget(heading("Protect your attention.", "Hero"))
        card_layout.addWidget(QLabel("One task. One window. Everything else can wait."))
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Session length"))
        self.focus_preset = QComboBox()
        self.focus_preset.addItem("15 minutes", 15)
        self.focus_preset.addItem("25 minutes", 25)
        self.focus_preset.addItem("45 minutes", 45)
        self.focus_preset.addItem("60 minutes", 60)
        self.focus_preset.setCurrentIndex(1)
        self.focus_preset.currentIndexChanged.connect(self._set_focus_preset)
        preset_row.addWidget(self.focus_preset)
        card_layout.addLayout(preset_row)
        self.focus_time = heading("25:00", "Metric")
        self.focus_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.focus_time)
        self.focus_progress = QProgressBar()
        self.focus_progress.setRange(0, self._focus_total_seconds)
        self.focus_progress.setValue(self._focus_total_seconds)
        card_layout.addWidget(self.focus_progress)
        buttons = QHBoxLayout()
        start = QPushButton("Start / Pause")
        start.setObjectName("Primary")
        start.clicked.connect(self._toggle_focus)
        reset = QPushButton("Reset")
        reset.clicked.connect(self._reset_focus)
        buttons.addWidget(start)
        buttons.addWidget(reset)
        card_layout.addLayout(buttons)
        self.focus_status = QLabel("Ready when you are.")
        self.focus_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.focus_status)
        layout.addWidget(card, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        return page

    def _finance_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(13)

        intro = panel()
        intro_layout = QVBoxLayout(intro)
        intro_layout.setContentsMargins(18, 16, 18, 16)
        intro_layout.setSpacing(8)
        intro_layout.addWidget(heading("Know where your money goes.", "Section"))
        intro_layout.addWidget(QLabel("A private ledger that stays on this computer."))
        row = QHBoxLayout()
        self.money_title = QLineEdit()
        self.money_title.setPlaceholderText("Transaction description")
        self.money_amount = QDoubleSpinBox()
        self.money_amount.setRange(0.01, 100000000)
        self.money_amount.setDecimals(2)
        self.money_amount.setPrefix(self._currency_prefix())
        self.money_kind = QComboBox()
        self.money_kind.addItem("Expense", "expense")
        self.money_kind.addItem("Income", "income")
        add = QPushButton("＋  Add entry")
        add.setObjectName("Primary")
        add.clicked.connect(self._add_transaction)
        row.addWidget(self.money_title, 2)
        row.addWidget(self.money_amount, 1)
        row.addWidget(self.money_kind)
        row.addWidget(add)
        intro_layout.addLayout(row)
        layout.addWidget(intro)

        ledger = panel()
        ledger_layout = QVBoxLayout(ledger)
        ledger_layout.setContentsMargins(17, 15, 17, 15)
        ledger_layout.addWidget(heading("Recent activity", "Section"))
        self.money_list = QListWidget()
        self.money_list.itemDoubleClicked.connect(lambda _item: self._edit_transaction())
        ledger_layout.addWidget(self.money_list, 1)
        finance_actions = QHBoxLayout()
        edit_finance = QPushButton("Edit selected")
        edit_finance.clicked.connect(self._edit_transaction)
        delete_finance = QPushButton("Delete selected")
        delete_finance.clicked.connect(self._delete_transaction)
        finance_actions.addWidget(edit_finance)
        finance_actions.addWidget(delete_finance)
        finance_actions.addStretch(1)
        ledger_layout.addLayout(finance_actions)
        layout.addWidget(ledger, 1)
        return page
    def _journal_page(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(13)

        editor = panel()
        editor_layout = QVBoxLayout(editor)
        editor_layout.setContentsMargins(17, 16, 17, 16)
        editor_layout.setSpacing(10)
        editor_layout.addWidget(heading("Clear your head.", "Section"))
        editor_layout.addWidget(QLabel("A private space to think. Your entries stay on this device."))
        self.journal_title = QLineEdit()
        self.journal_title.setPlaceholderText("Give this entry a title")
        self.journal_body = QTextEdit()
        self.journal_body.setPlaceholderText("What is on your mind today? Start anywhere.")
        save = QPushButton("Save entry  ↗")
        save.setObjectName("Primary")
        save.clicked.connect(self._save_journal)
        editor_layout.addWidget(self.journal_title)
        editor_layout.addWidget(self.journal_body, 1)
        editor_layout.addWidget(save)
        layout.addWidget(editor, 3)

        entries = panel()
        entries_layout = QVBoxLayout(entries)
        entries_layout.setContentsMargins(15, 15, 15, 15)
        entries_layout.addWidget(heading("Recent entries", "Section"))
        self.journal_search = QLineEdit()
        self.journal_search.setPlaceholderText("Search titles and thoughts…")
        self.journal_search.textChanged.connect(self._filter_journal_entries)
        entries_layout.addWidget(self.journal_search)
        self.journal_list = QListWidget()
        self.journal_list.itemDoubleClicked.connect(self._open_journal_entry)
        entries_layout.addWidget(self.journal_list, 1)
        hint = QLabel("Double-click an entry to read it.")
        hint.setObjectName("Muted")
        entries_layout.addWidget(hint)
        delete_entry = QPushButton("Delete selected entry")
        delete_entry.clicked.connect(self._delete_journal_entry)
        entries_layout.addWidget(delete_entry)
        edit_entry = QPushButton("Edit selected")
        edit_entry.clicked.connect(self._edit_journal_entry)
        entries_layout.addWidget(edit_entry)
        layout.addWidget(entries, 2)
        return page
    def refresh_all(self) -> None:
        from datetime import datetime
        self.date_label.setText(datetime.now().strftime("%a  ·  %d %b %Y").upper())
        stats = self.db.stats()
        if hasattr(self, "insight_labels"):
            self.insight_labels["tasks"].setText(str(stats["tasks_done"]))
            self.insight_labels["xp"].setText(f'{stats["xp"]} XP')
            self.insight_labels["focus"].setText(f'{stats["focus_minutes"]} min')
            self.insight_labels["balance"].setText(self._money(stats["balance"]))
            self.insight_labels["habits"].setText(f'{stats["habits_done"]}/{stats["habits_total"]}')
            self.insight_labels["entries"].setText(str(len(self.db.get_journal_entries())))
        self.metric_labels["tasks_done"].setText(str(stats["tasks_done"]))
        self.metric_labels["xp"].setText(f'{stats["xp"]} XP')
        self.metric_labels["habits_done"].setText(f'{stats["habits_done"]}/{stats["habits_total"]}')
        self.metric_labels["balance"].setText(self._money(stats["balance"]))
        level = self.db.level_info()
        streak = self.db.streak_days()
        self.hero_xp_label.setText(f'LVL {level["level"]}  ·  {stats["xp"]} XP')
        if hasattr(self, "level_copy"):
            self.level_copy.setText(f'Level {level["level"]}  ·  {level["current"]}/{level["next"]} XP to next level  ·  {self.db.streak_days()} day streak')
        if hasattr(self, "level_progress"):
            self.level_progress.setValue(level["percent"])
            self.level_copy.setText(f'Level {level["level"]} · {level["current"]}/{level["next"]} XP · {streak} day streak')
        open_quests = stats["tasks_total"] - stats["tasks_done"]
        self.hero_quest_copy.setText(f'{open_quests} {self._tr("quests" if open_quests != 1 else "quest")} {self._tr("left to move forward.")}')
        habit_pct = round(stats["habits_done"] / stats["habits_total"] * 100) if stats["habits_total"] else 0
        self.habits_progress.setValue(habit_pct)
        self.habits_copy.setText(f'{stats["habits_done"]} / {stats["habits_total"]} {self._tr("habits complete")}')
        self.overview_habits.setText(self._tr("You're building consistency.") if stats["habits_total"] else self._tr("Add one small habit to begin."))
        self.focus_minutes_copy.setText(f'{stats["focus_minutes"]} min')
        self._refresh_dashboard_summary()
        if hasattr(self, "streak_badge"):
            streak = self.db.streak_days()
            self.streak_badge.setText(f'{streak} DAY STREAK')
            self.streak_badge.setObjectName("StatusGood" if streak else "StatusWarn")
            self.streak_badge.style().unpolish(self.streak_badge)
            self.streak_badge.style().polish(self.streak_badge)
        if hasattr(self, "notification_button"):
            unread = self.db.unread_notification_count()
            self.notification_button.setText(f"◉  {unread}")
        self.activity_chart.set_data(self.db.weekly_activity())
        pending = self.db.get_tasks(include_done=False)
        self.overview_tasks.clear()
        for task in pending[:5]:
            self.overview_tasks.addItem(f'○  {task["title"]}   ·   {task["xp"]} XP')
        if not pending:
            self.overview_tasks.addItem(self._tr("No open quests. Add a small win."))
        total = stats["tasks_total"]
        pct = round(stats["tasks_done"] / total * 100) if total else 0
        self.daily_progress.setValue(pct)
        self.progress_copy.setText(f'{stats["tasks_done"]} / {total} {self._tr("quests completed overall")} · {stats["focus_minutes"]} {self._tr("focus minutes logged")}')
        if hasattr(self, "task_list"):
            self._refresh_task_list()
        if hasattr(self, "habit_list"):
            self.habit_list.clear()
            for habit in self.db.get_habits():
                mark = "✓" if habit["done"] else "○"
                streak = self.db.habit_streak(habit["id"])
                streak_copy = f"🔥 {streak}d" if streak else "Start a streak"
                self.habit_list.addItem(f'{mark}  {habit["title"]}   ·   {streak_copy}   ·   #{habit["id"]}')
        if hasattr(self, "money_list"):
            self.money_list.clear()
            for item in self.db.get_transactions():
                sign = "+" if item["kind"] == "income" else "−"
                self.money_list.addItem(f'{sign} {self._money(item["amount"])}   ·   {item["title"]}   ·   {item["created_at"][:10]}')
        if hasattr(self, "journal_list"):
            self._filter_journal_entries()

    def _refresh_task_list(self) -> None:
        if not hasattr(self, "task_list"):
            return
        mode = self.task_filter.currentData() if hasattr(self, "task_filter") else "all"
        tasks = self.db.get_tasks()
        if mode == "open":
            tasks = [task for task in tasks if not task["done"]]
        elif mode == "done":
            tasks = [task for task in tasks if task["done"]]
        self.task_list.clear()
        for task in tasks:
            mark = "✓" if task["done"] else "○"
            self.task_list.addItem(f'{mark}  {task["title"]}   ·   {task["category"]}   ·   {task["xp"]} XP   ·   #{task["id"]}')
        if not tasks:
            empty = self._tr("No open quests. Enjoy the breathing room.") if mode == "open" else self._tr("No completed quests yet.") if mode == "done" else self._tr("Your quest board is clear. Add the first one.")
            self.task_list.addItem(empty)

    def _selected_id(self, widget: QListWidget) -> int | None:
        item = widget.currentItem()
        if not item:
            return None
        marker = item.text().rsplit("#", 1)
        if len(marker) != 2:
            return None
        try:
            return int(marker[1].strip())
        except ValueError:
            return None


    def _edit_task(self) -> None:
        task_id = self._selected_id(self.task_list)
        if task_id is None: return
        task = next((x for x in self.db.get_tasks() if x["id"] == task_id), None)
        if not task: return
        title, ok = QInputDialog.getText(self, "Edit quest", "Title:", text=task["title"])
        if not ok: return
        xp, ok = QInputDialog.getInt(self, "Edit quest", "XP:", task["xp"], 1, 500)
        if not ok: return
        category, ok = QInputDialog.getText(self, "Edit quest", "Category:", text=task["category"])
        if ok:
            try: self.db.update_task(task_id, title, category, xp); self.refresh_all()
            except ValueError as e: self._message(str(e))

    def _edit_habit(self) -> None:
        habit_id = self._selected_id(self.habit_list)
        if habit_id is None: return
        habit = next((x for x in self.db.get_habits() if x["id"] == habit_id), None)
        if not habit: return
        title, ok = QInputDialog.getText(self, "Edit habit", "Name:", text=habit["title"])
        if ok:
            try: self.db.update_habit(habit_id, title); self.refresh_all()
            except ValueError as e: self._message(str(e))

    def _edit_transaction(self) -> None:
        tx_id = self._selected_id(self.money_list)
        if tx_id is None: return
        tx = next((x for x in self.db.get_transactions() if x["id"] == tx_id), None)
        if not tx: return
        title, ok = QInputDialog.getText(self, "Edit transaction", "Description:", text=tx["title"])
        if not ok: return
        amount, ok = QInputDialog.getDouble(self, "Edit transaction", "Amount:", tx["amount"], 0.01, 100000000, 2)
        if not ok: return
        kind, ok = QInputDialog.getItem(self, "Edit transaction", "Type:", ["Expense", "Income"], 0 if tx["kind"]=="expense" else 1, False)
        if ok:
            try: self.db.update_transaction(tx_id, title, amount, "expense" if kind=="Expense" else "income"); self.refresh_all()
            except ValueError as e: self._message(str(e))

    def _delete_transaction(self) -> None:
        tx_id = self._selected_id(self.money_list)
        if tx_id is None:
            return
        answer = QMessageBox.question(self, self._tr("Delete transaction"), self._tr("Delete this transaction permanently?"), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.db.delete_transaction(tx_id)
            self.refresh_all()

    def _edit_journal_entry(self) -> None:
        entry_id = self._selected_id(self.journal_list)
        if entry_id is None: return
        entry = next((x for x in self.db.get_journal_entries() if x["id"] == entry_id), None)
        if not entry: return
        title, ok = QInputDialog.getText(self, "Edit note", "Title:", text=entry["title"])
        if not ok: return
        body, ok = QInputDialog.getMultiLineText(self, "Edit note", "Text:", entry["body"])
        if ok:
            try: self.db.update_journal_entry(entry_id, title, body); self.refresh_all()
            except ValueError as e: self._message(str(e))

    def _add_task(self) -> None:
        title, ok = QInputDialog.getText(self, "New quest", "What do you want to finish?")
        if ok and title.strip():
            self.db.add_task(title)
            self.refresh_all()

    def _add_task_from_form(self) -> None:
        try:
            self.db.add_task(self.task_input.text(), self.task_category.currentText(), self.task_xp.value())
        except ValueError as error:
            self._message(str(error))
            return
        self.task_input.clear()
        self.refresh_all()

    def _complete_task(self) -> None:
        task_id = self._selected_id(self.task_list)
        if task_id is None:
            self._message("Select a quest first.")
        elif self.db.complete_task(task_id):
            self.refresh_all()
        else:
            self._message("That quest is already completed.")

    def _delete_task(self) -> None:
        task_id = self._selected_id(self.task_list)
        if task_id is None:
            return
        answer = QMessageBox.question(self, self._tr("Delete quest"), self._tr("Delete this quest permanently?"), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.db.delete_task(task_id)
            self.refresh_all()

    def _add_habit(self) -> None:
        try:
            self.db.add_habit(self.habit_input.text())
        except ValueError as error:
            self._message(str(error))
            return
        except Exception:
            self._message("That habit already exists.")
            return
        self.habit_input.clear()
        self.refresh_all()

    def _toggle_habit(self) -> None:
        habit_id = self._selected_id(self.habit_list)
        if habit_id is None:
            self._message("Select a habit first.")
            return
        self.db.toggle_habit(habit_id)
        self.refresh_all()

    def _delete_habit(self) -> None:
        habit_id = self._selected_id(self.habit_list)
        if habit_id is None:
            return
        answer = QMessageBox.question(self, self._tr("Delete habit"), self._tr("Delete this habit and its streak history?"), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.db.delete_habit(habit_id)
            self.refresh_all()

    def _toggle_focus(self) -> None:
        if self._focus_running:
            self._timer.stop()
            self._focus_running = False
            self.focus_status.setText(self._tr("Paused. Resume when ready."))
        else:
            self._timer.start()
            self._focus_running = True
            self.focus_status.setText(self._tr("Focus mode active. Keep going."))
    def _tick(self) -> None:
        self._focus_seconds -= 1
        self.focus_time.setText(f"{self._focus_seconds // 60:02d}:{self._focus_seconds % 60:02d}")
        self.focus_progress.setValue(self._focus_seconds)
        if self._focus_seconds <= 0:
            self._timer.stop()
            self._focus_running = False
            self.db.add_focus_session(max(1, self._focus_total_seconds // 60))
            self.focus_status.setText(self._tr("Session complete. Nice work."))
            QMessageBox.information(self, "NEXUS Focus", f"{self._focus_total_seconds // 60} minutes complete. Take a short break.")
            self.refresh_all()

    def _set_focus_preset(self) -> None:
        if self._focus_running:
            self._timer.stop()
            self._focus_running = False
        minutes = int(self.focus_preset.currentData())
        self._focus_total_seconds = minutes * 60
        self._focus_seconds = self._focus_total_seconds
        self.focus_time.setText(f"{minutes:02d}:00")
        self.focus_progress.setRange(0, self._focus_total_seconds)
        self.focus_progress.setValue(self._focus_total_seconds)
        self.focus_status.setText(f"{minutes}-minute session ready.")

    def _reset_focus(self) -> None:
        self._timer.stop()
        self._focus_running = False
        self._focus_seconds = self._focus_total_seconds
        self.focus_time.setText(f"{self._focus_seconds // 60:02d}:{self._focus_seconds % 60:02d}")
        self.focus_progress.setValue(self._focus_total_seconds)
        self.focus_status.setText(self._tr("Timer reset."))

    def _add_transaction(self) -> None:
        try:
            self.db.add_transaction(self.money_title.text(), self.money_amount.value(), self.money_kind.currentData())
        except ValueError as error:
            self._message(str(error))
            return
        self.money_title.clear()
        self.refresh_all()

    def _save_journal(self) -> None:
        try:
            self.db.add_journal_entry(self.journal_title.text(), self.journal_body.toPlainText())
        except ValueError as error:
            self._message(str(error))
            return
        self.journal_title.clear()
        self.journal_body.clear()
        self.refresh_all()

    def _open_journal_entry(self, item) -> None:
        entry_id = self._selected_id(self.journal_list)
        if entry_id is None:
            return
        entry = next((row for row in self.db.get_journal_entries() if row["id"] == entry_id), None)
        if entry:
            QMessageBox.information(self, entry["title"], entry["body"] or "(Empty entry)")

    def _filter_journal_entries(self, query: str | None = None) -> None:
        if not hasattr(self, "journal_list"):
            return
        search = (self.journal_search.text() if query is None else query).strip().casefold()
        self.journal_list.clear()
        entries = self.db.get_journal_entries()
        matches = [
            entry for entry in entries
            if not search or search in entry["title"].casefold() or search in entry["body"].casefold()
        ]
        for entry in matches:
            stamp = entry["created_at"][:16].replace("T", " ")
            self.journal_list.addItem(f'{entry["title"]}   ·   {stamp}   ·   #{entry["id"]}')
        if not matches:
            self.journal_list.addItem("No matching entries yet.")

    def _delete_journal_entry(self) -> None:
        entry_id = self._selected_id(self.journal_list)
        if entry_id is None:
            self._message("Select a journal entry first.")
            return
        answer = QMessageBox.question(
            self,
            "Delete journal entry",
            "Delete this entry permanently? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.db.delete_journal_entry(entry_id)
            self.refresh_all()

    def _backup_database(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Create NEXUS backup",
            "nexus-backup.nexus.zip",
            "NEXUS backup (*.nexus.zip);;SQLite database (*.db)",
        )
        if not path:
            return
        try:
            if path.lower().endswith(".nexus.zip"):
                create_full_backup(self.db, path)
                self._message("Full backup created. Account registry and local workspaces are included.")
            else:
                create_backup(self.db, path)
                self._message("Workspace backup created successfully.")
        except Exception as error:
            self._message(f"Backup failed: {error}")

    def _export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export NEXUS data", "nexus-export.json", "JSON file (*.json)"
        )
        if not path:
            return
        try:
            export_json(self.db, path)
            self._message("JSON export created successfully.")
        except Exception as error:
            self._message(f"Export failed: {error}")

    def _message(self, text: str) -> None:
        QMessageBox.information(self, "NEXUS", text)