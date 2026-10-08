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
        outer = QHBoxLayout(root)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(16)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(215)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 22, 16, 16)
        side.setSpacing(9)
        side.addWidget(heading("NEXUS", "Brand"))
        side.addWidget(QLabel("PERSONAL COMMAND CENTER"))
        side.addSpacing(18)
        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        self.pages = QStackedWidget()
        self.page_names = ["Overview", "Quests", "Habits", "Focus", "Finance", "Journal"]
        for index, name in enumerate(self.page_names):
            button = QPushButton(("◈   " if index == 0 else "·   ") + name)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, i=index: self._navigate(i))
            self.nav.addButton(button, index)
            side.addWidget(button)
            if index == 0:
                self.nav.button(0).setChecked(True)
        side.addStretch(1)
        hint = QLabel("CTRL + 1–6  NAVIGATE\nCTRL + N  NEW QUEST\nCTRL + SHIFT + B  BACKUP")
        hint.setObjectName("Muted")
        side.addWidget(hint)
        side.addWidget(QLabel("LOCAL-FIRST  •  v0.1.0"))
        outer.addWidget(sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(3, 2, 2, 2)
        content_layout.setSpacing(14)
        top = QHBoxLayout()
        self.page_title = heading("Overview", "Hero")
        top.addWidget(self.page_title)
        top.addStretch(1)
        self.date_label = QLabel()
        self.date_label.setObjectName("Muted")
        top.addWidget(self.date_label)
        backup_button = QPushButton("Backup")
        backup_button.clicked.connect(self._backup_database)
        export_button = QPushButton("Export JSON")
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
        intro = panel()
        intro_layout = QVBoxLayout(intro)
        intro_layout.setContentsMargins(22, 20, 22, 20)
        intro_layout.addWidget(QLabel("YOUR PERSONAL SYSTEM"))
        intro_layout.addWidget(heading("Make today count.", "Hero"))
        intro_layout.addWidget(QLabel("Small actions. Compounding progress. Your life, on your terms."))
        layout.addWidget(intro)

        grid = QGridLayout()
        grid.setSpacing(12)
        self.metric_labels: dict[str, QLabel] = {}
        metrics = [
            ("tasks_done", "QUESTS COMPLETED", "0"),
            ("xp", "TOTAL XP", "0 XP"),
            ("habits_done", "HABITS TODAY", "0"),
            ("balance", "NET BALANCE", "0.00"),
        ]
        for i, (key, label, default) in enumerate(metrics):
            card = panel()
            box = QVBoxLayout(card)
            box.setContentsMargins(17, 15, 17, 15)
            box.addWidget(QLabel(label))
            value = heading(default, "Metric")
            box.addWidget(value)
            self.metric_labels[key] = value
            grid.addWidget(card, i // 2, i % 2)
        layout.addLayout(grid)

        bottom = QHBoxLayout()
        quest_card = panel()
        ql = QVBoxLayout(quest_card)
        ql.addWidget(heading("Next up"))
        self.overview_tasks = QListWidget()
        self.overview_tasks.setMaximumHeight(185)
        ql.addWidget(self.overview_tasks)
        bottom.addWidget(quest_card, 3)
        progress_card = panel()
        pl = QVBoxLayout(progress_card)
        pl.addWidget(heading("Quest progress"))
        self.daily_progress = QProgressBar()
        self.daily_progress.setRange(0, 100)
        pl.addWidget(self.daily_progress)
        self.progress_copy = QLabel("Your next small win is waiting.")
        self.progress_copy.setWordWrap(True)
        pl.addWidget(self.progress_copy)
        pl.addStretch(1)
        quick = QPushButton("+  Add a quest")
        quick.setObjectName("Primary")
        quick.clicked.connect(self._add_task)
        pl.addWidget(quick)
        bottom.addWidget(progress_card, 2)
        layout.addLayout(bottom)
        layout.addStretch(1)
        return page

    def _quests_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        row = QHBoxLayout()
        self.task_input = QLineEdit()
        self.task_input.setPlaceholderText("Name your next quest...")
        self.task_category = QComboBox()
        self.task_category.addItems(["Personal", "Work", "Learning", "Health", "Creative"])
        self.task_xp = QSpinBox()
        self.task_xp.setRange(5, 500)
        self.task_xp.setValue(25)
        self.task_xp.setSuffix(" XP")
        add = QPushButton("Add quest")
        add.setObjectName("Primary")
        add.clicked.connect(self._add_task_from_form)
        self.task_input.returnPressed.connect(self._add_task_from_form)
        row.addWidget(self.task_input, 3)
        row.addWidget(self.task_category, 1)
        row.addWidget(self.task_xp)
        row.addWidget(add)
        layout.addLayout(row)
        self.task_list = QListWidget()
        layout.addWidget(self.task_list, 1)
        actions = QHBoxLayout()
        complete = QPushButton("Complete selected  +XP")
        complete.clicked.connect(self._complete_task)
        delete = QPushButton("Delete selected")
        delete.clicked.connect(self._delete_task)
        actions.addWidget(complete)
        actions.addWidget(delete)
        actions.addStretch(1)
        layout.addLayout(actions)
        return page

    def _habits_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Build the kind of consistency that survives bad days. Check in once per day."))
        row = QHBoxLayout()
        self.habit_input = QLineEdit()
        self.habit_input.setPlaceholderText("New habit, e.g. Read 10 pages")
        self.habit_input.returnPressed.connect(self._add_habit)
        add = QPushButton("Add habit")
        add.setObjectName("Primary")
        add.clicked.connect(self._add_habit)
        row.addWidget(self.habit_input, 1)
        row.addWidget(add)
        layout.addLayout(row)
        self.habit_list = QListWidget()
        layout.addWidget(self.habit_list, 1)
        actions = QHBoxLayout()
        check = QPushButton("Toggle today's check-in")
        check.clicked.connect(self._toggle_habit)
        remove = QPushButton("Delete habit")
        remove.clicked.connect(self._delete_habit)
        actions.addWidget(check)
        actions.addWidget(remove)
        actions.addStretch(1)
        layout.addLayout(actions)
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
        layout.addWidget(QLabel("A simple ledger. Track what comes in and what goes out."))
        row = QHBoxLayout()
        self.money_title = QLineEdit()
        self.money_title.setPlaceholderText("What was it?")
        self.money_amount = QDoubleSpinBox()
        self.money_amount.setRange(0.01, 100000000)
        self.money_amount.setDecimals(2)
        self.money_amount.setPrefix("руб. ")
        self.money_kind = QComboBox()
        self.money_kind.addItem("Expense", "expense")
        self.money_kind.addItem("Income", "income")
        add = QPushButton("Add entry")
        add.setObjectName("Primary")
        add.clicked.connect(self._add_transaction)
        row.addWidget(self.money_title, 2)
        row.addWidget(self.money_amount, 1)
        row.addWidget(self.money_kind)
        row.addWidget(add)
        layout.addLayout(row)
        self.money_list = QListWidget()
        layout.addWidget(self.money_list, 1)
        return page

    def _journal_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("A private space to think clearly. Saved on this device."))
        self.journal_title = QLineEdit()
        self.journal_title.setPlaceholderText("Entry title")
        self.journal_body = QTextEdit()
        self.journal_body.setPlaceholderText("What is on your mind?")
        save = QPushButton("Save entry")
        save.setObjectName("Primary")
        save.clicked.connect(self._save_journal)
        layout.addWidget(self.journal_title)
        layout.addWidget(self.journal_body, 2)
        layout.addWidget(save)
        layout.addWidget(heading("Recent entries"))
        self.journal_list = QListWidget()
        self.journal_list.itemDoubleClicked.connect(self._open_journal_entry)
        layout.addWidget(self.journal_list, 2)
        return page

    def refresh_all(self) -> None:
        from datetime import datetime
        self.date_label.setText(datetime.now().strftime("%A, %d %B"))
        stats = self.db.stats()
        self.metric_labels["tasks_done"].setText(str(stats["tasks_done"]))
        self.metric_labels["xp"].setText(f'{stats["xp"]} XP')
        self.metric_labels["habits_done"].setText(f'{stats["habits_done"]}/{stats["habits_total"]}')
        self.metric_labels["balance"].setText(f'{stats["balance"]:.2f}')
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
            self.task_list.clear()
            for task in self.db.get_tasks():
                mark = "✓" if task["done"] else "○"
                self.task_list.addItem(f'{mark}  {task["title"]}   ·   {task["category"]}   ·   {task["xp"]} XP   ·   #{task["id"]}')
        if hasattr(self, "habit_list"):
            self.habit_list.clear()
            for habit in self.db.get_habits():
                mark = "✓" if habit["done"] else "○"
                self.habit_list.addItem(f'{mark}  {habit["title"]}   ·   #{habit["id"]}')
        if hasattr(self, "money_list"):
            self.money_list.clear()
            for item in self.db.get_transactions():
                sign = "+" if item["kind"] == "income" else "−"
                self.money_list.addItem(f'{sign} {item["amount"]:.2f}   ·   {item["title"]}   ·   {item["created_at"][:10]}')
        if hasattr(self, "journal_list"):
            self.journal_list.clear()
            for entry in self.db.get_journal_entries():
                self.journal_list.addItem(f'{entry["title"]}   ·   {entry["created_at"][:16].replace("T", " ")}   ·   #{entry["id"]}')

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
            QMessageBox.information(self, "NEXUS Focus", "25 minutes complete. Take a short break.")
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
