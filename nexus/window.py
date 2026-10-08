"""Main NEXUS desktop interface."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QStackedWidget, QFrame, QListWidget, QListWidgetItem, QLineEdit,
    QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QInputDialog, QFileDialog,
    QMessageBox, QProgressBar, QButtonGroup, QRadioButton, QScrollArea,
    QGridLayout,
)

from nexus.database import Database
from nexus.backup import create_backup, export_json
from nexus.charts import WeeklyActivityChart


STYLES = """
* { font-family: 'Segoe UI'; font-size: 13px; }
QMainWindow, QWidget { background: #0d0e12; color: #f0f0f5; }
QWidget#AppRoot { background: #0d0e12; }
QFrame#Sidebar { background: #111218; border: 1px solid #242530; border-radius: 20px; }
QFrame#Panel { background: #15161e; border: 1px solid #282936; border-radius: 18px; }
QFrame#HeroPanel { background: #171722; border: 1px solid #302c43; border-radius: 22px; }
QFrame#AccentPanel { background: #c7f36b; border: none; border-radius: 18px; color: #171a12; }
QLabel { color: #eeeeF4; background: transparent; }
QLabel#Brand { font-size: 25px; font-weight: 850; letter-spacing: 4px; color: #c7f36b; }
QLabel#BrandSub { color: #777988; font-size: 9px; font-weight: 700; letter-spacing: 1.7px; }
QLabel#Muted { color: #858797; }
QLabel#Eyebrow { color: #aaa1d7; font-size: 10px; font-weight: 800; letter-spacing: 2px; }
QLabel#Hero { font-size: 31px; font-weight: 750; letter-spacing: -0.7px; color: #f7f6ff; }
QLabel#Metric { font-size: 28px; font-weight: 750; color: #f5f4fb; }
QLabel#MetricAccent { font-size: 28px; font-weight: 800; color: #c7f36b; }
QLabel#Section { font-size: 15px; font-weight: 750; color: #f4f2fc; }
QLabel#Tiny { color: #8d8e9d; font-size: 10px; font-weight: 700; letter-spacing: 1px; }
QLabel#Pill { background: #22242e; color: #b8b1e5; border: 1px solid #343346; border-radius: 9px; padding: 6px 9px; font-size: 10px; font-weight: 700; }
QLabel#AccentText { color: #191d12; }
QPushButton { background: #20212b; color: #e9e8f1; border: 1px solid #30313e; border-radius: 10px; padding: 10px 13px; text-align: left; }
QPushButton:hover { background: #2b2c39; border-color: #7d78a9; }
QPushButton:checked { background: #242332; color: #d6f68b; border: 1px solid #45415e; font-weight: 700; }
QPushButton#Primary { background: #c7f36b; color: #171a12; border: 1px solid #c7f36b; font-weight: 800; }
QPushButton#Primary:hover { background: #d5ff86; }
QPushButton#Nav { background: transparent; color: #8d8e9d; border: 1px solid transparent; padding: 12px 13px; border-radius: 11px; }
QPushButton#Nav:hover { background: #1a1b25; color: #f0eff8; }
QPushButton#Nav:checked { background: #22222f; color: #d8f79b; border: 1px solid #353449; font-weight: 700; }
QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: #101117; color: #f0eff8; border: 1px solid #323340; border-radius: 10px; padding: 10px; selection-background-color: #5f5a86; }
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border: 1px solid #a59bdc; }
QComboBox::drop-down { border: none; width: 24px; }
QListWidget { background: transparent; border: none; outline: none; padding: 2px; }
QListWidget::item { background: #1c1d27; border: 1px solid #292a37; border-radius: 10px; padding: 12px; margin: 4px 0; color: #e5e4ed; }
QListWidget::item:hover { background: #232431; border-color: #444157; }
QListWidget::item:selected { border: 1px solid #8c84ba; background: #29283a; color: #f6f4ff; }
QProgressBar { border: none; background: #2a2b36; border-radius: 5px; height: 8px; text-align: center; color: transparent; }
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


class MainWindow(QMainWindow):
    def __init__(self, db: Database | None = None) -> None:
        super().__init__()
        self.db = db or Database()
        self.setWindowTitle("NEXUS | Personal Command Center")
        self.resize(1180, 780)
        self.setMinimumSize(940, 640)
        self.setStyleSheet(STYLES)
        self._focus_total_seconds = 25 * 60
        self._focus_seconds = self._focus_total_seconds
        self._focus_running = False
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._build_shell()
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
        self.page_names = ["Overview", "Quests", "Habits", "Focus", "Finance", "Journal"]
        symbols = ["⌂", "◇", "✳", "◷", "↗", "▤"]
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
        local_layout.addWidget(QLabel("Your data stays on this device."))
        local_layout.addWidget(heading("DATABASE  ·  SQLITE", "Tiny"))
        side.addWidget(local_card)
        side.addStretch(1)

        shortcut_hint = QLabel("CTRL + 1–6    NAVIGATE\nCTRL + N       NEW QUEST\nCTRL + SHIFT + B   BACKUP")
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
        export_button = QPushButton("⇧  Export")
        export_button.setToolTip("Export all NEXUS data to JSON")
        export_button.clicked.connect(self._export_json)
        top.addWidget(backup_button)
        top.addWidget(export_button)
        content_layout.addLayout(top)

        self.pages.addWidget(self._overview_page())
        self.pages.addWidget(self._quests_page())
        self.pages.addWidget(self._habits_page())
        self.pages.addWidget(self._focus_page())
        self.pages.addWidget(self._finance_page())
        self.pages.addWidget(self._journal_page())
        content_layout.addWidget(self.pages, 1)
        outer.addWidget(content, 1)
        self.setCentralWidget(root)

        self._shortcuts = []
        for index in range(len(self.page_names)):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{index + 1}"), self)
            shortcut.activated.connect(lambda i=index: self._navigate(i))
            self._shortcuts.append(shortcut)
        new_quest_shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        new_quest_shortcut.activated.connect(self._add_task)
        self._shortcuts.append(new_quest_shortcut)
        backup_shortcut = QShortcut(QKeySequence("Ctrl+Shift+B"), self)
        backup_shortcut.activated.connect(self._backup_database)
        self._shortcuts.append(backup_shortcut)

    def _navigate(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.page_title.setText(self.page_names[index])
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
        list_layout.addWidget(self.task_list, 1)
        actions = QHBoxLayout()
        complete = QPushButton("✓  Complete selected  +XP")
        complete.setObjectName("Primary")
        complete.clicked.connect(self._complete_task)
        delete = QPushButton("Delete selected")
        delete.clicked.connect(self._delete_task)
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
        list_layout.addWidget(self.habit_list, 1)
        actions = QHBoxLayout()
        check = QPushButton("✓  Toggle today's check-in")
        check.setObjectName("Primary")
        check.clicked.connect(self._toggle_habit)
        remove = QPushButton("Delete habit")
        remove.clicked.connect(self._delete_habit)
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
        self.money_amount.setPrefix("руб. ")
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
        ledger_layout.addWidget(self.money_list, 1)
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
        layout.addWidget(entries, 2)
        return page
    def refresh_all(self) -> None:
        from datetime import datetime
        self.date_label.setText(datetime.now().strftime("%a  ·  %d %b %Y").upper())
        stats = self.db.stats()
        self.metric_labels["tasks_done"].setText(str(stats["tasks_done"]))
        self.metric_labels["xp"].setText(f'{stats["xp"]} XP')
        self.metric_labels["habits_done"].setText(f'{stats["habits_done"]}/{stats["habits_total"]}')
        self.metric_labels["balance"].setText(f'{stats["balance"]:.2f} руб.')
        self.hero_xp_label.setText(f'{stats["xp"]} XP')
        open_quests = stats["tasks_total"] - stats["tasks_done"]
        self.hero_quest_copy.setText(f'{open_quests} quest{"s" if open_quests != 1 else ""} left to move forward.')
        habit_pct = round(stats["habits_done"] / stats["habits_total"] * 100) if stats["habits_total"] else 0
        self.habits_progress.setValue(habit_pct)
        self.habits_copy.setText(f'{stats["habits_done"]} of {stats["habits_total"]} habits complete')
        self.overview_habits.setText("You're building consistency." if stats["habits_total"] else "Add one small habit to begin.")
        self.focus_minutes_copy.setText(f'{stats["focus_minutes"]} min')
        self.activity_chart.set_data(self.db.weekly_activity())
        pending = self.db.get_tasks(include_done=False)
        self.overview_tasks.clear()
        for task in pending[:5]:
            self.overview_tasks.addItem(f'○  {task["title"]}   ·   {task["xp"]} XP')
        if not pending:
            self.overview_tasks.addItem("No open quests. Add a small win.")
        total = stats["tasks_total"]
        pct = round(stats["tasks_done"] / total * 100) if total else 0
        self.daily_progress.setValue(pct)
        self.progress_copy.setText(f'{stats["tasks_done"]} of {total} quests completed overall · {stats["focus_minutes"]} focus minutes logged')
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
                self.money_list.addItem(f'{sign} {item["amount"]:.2f}   ·   {item["title"]}   ·   {item["created_at"][:10]}')
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
            empty = "No open quests. Enjoy the breathing room." if mode == "open" else "No completed quests yet." if mode == "done" else "Your quest board is clear. Add the first one."
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
        if task_id is not None:
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
        if habit_id is not None:
            self.db.delete_habit(habit_id)
            self.refresh_all()

    def _toggle_focus(self) -> None:
        if self._focus_running:
            self._timer.stop()
            self._focus_running = False
            self.focus_status.setText("Paused. Resume when ready.")
        else:
            self._timer.start()
            self._focus_running = True
            self.focus_status.setText("Focus mode active. Keep going.")
    def _tick(self) -> None:
        self._focus_seconds -= 1
        self.focus_time.setText(f"{self._focus_seconds // 60:02d}:{self._focus_seconds % 60:02d}")
        self.focus_progress.setValue(self._focus_seconds)
        if self._focus_seconds <= 0:
            self._timer.stop()
            self._focus_running = False
            self.db.add_focus_session(max(1, self._focus_total_seconds // 60))
            self.focus_status.setText("Session complete. Nice work.")
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
        self.focus_status.setText("Timer reset.")

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
            self, "Create NEXUS backup", "nexus-backup.db", "SQLite database (*.db)"
        )
        if not path:
            return
        try:
            create_backup(self.db, path)
            self._message("Backup created successfully.")
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
