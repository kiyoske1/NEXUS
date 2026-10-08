# NEXUS

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/UI-PySide6-41CD52?logo=qt&logoColor=white)
![Storage](https://img.shields.io/badge/storage-SQLite-003B57?logo=sqlite&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-d8ff78)

**Your personal command center.** A local-first Windows desktop app for goals, habits, focus sessions, money, and notes.

NEXUS is designed around one idea: make progress visible without turning your life into another noisy social network.

## Current release

The first version is an early foundation with:
- Overview dashboard with daily progress and quick stats
- Quests with XP rewards
- Habit check-ins
- Focus timer
- Simple income and expense tracking
- Private journal
- Local SQLite database

## Stack

- Python 3.11+
- PySide6 for the desktop UI
- SQLite for local persistence
- pytest for database tests
- GitHub Actions for automated checks

## Run locally

On Windows, the easiest route is to install Python 3.11 or newer, then double-click `run_nexus.bat`. The script creates a virtual environment, installs dependencies, and launches the app.

Manual route:

1. Install Python 3.11 or newer.
2. Open a terminal in the repository folder.
3. Create and activate a virtual environment:

   Windows:
   `python -m venv .venv`
   `.venv\\Scripts\\activate`

4. Install dependencies:

   `pip install -r requirements.txt`

5. Launch NEXUS:

   `python main.py`

## Build a Windows executable

Double-click `build_windows.bat` or run it from a terminal. The packaged app will be placed in `dist/NEXUS/`. A Windows build can also be triggered from the GitHub Actions workflow.

## Run tests

`python -m pytest`

## Data and privacy

The database is stored in your user home directory at `~/.nexus/nexus.db`. Your journal and finance entries are not uploaded anywhere by the app.

## Repository structure

- `main.py`: application entry point
- `nexus/window.py`: desktop UI and user interactions
- `nexus/database.py`: SQLite persistence and business rules
- `nexus/backup.py`: consistent database backups and portable JSON export
- `tests/`: automated database and backup tests
- `.github/workflows/`: CI tests and Windows build pipeline

## Roadmap

- [x] Initial desktop shell and navigation
- [x] SQLite persistence
- [x] Quests, habits, focus, finance, journal
- [ ] Habit streaks and weekly insights
- [ ] Search and calendar
- [ ] Export and database backup
- [ ] Windows executable build
- [ ] Keyboard shortcuts and accessibility pass

## Project principles

- Local-first by default
- Fast, calm, keyboard-friendly interface
- No accounts or cloud dependency
- Features should work, not just look good

## License

MIT. See LICENSE.
