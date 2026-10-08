# Contributing to NEXUS

Thanks for helping make NEXUS calmer, faster, and more useful.

## Development setup

1. Install Python 3.11 or newer.
2. Create a virtual environment.
3. Install dependencies with `pip install -r requirements.txt`.
4. Run the app with `python main.py`.
5. Run tests with `python -m pytest -q`.

## Guidelines

- Keep personal data local by default.
- Put database operations in the data layer, not directly in UI widgets.
- Use parameterized SQL queries.
- Add tests when changing persistence or business rules.
- Keep the interface keyboard-friendly and readable at smaller window sizes.
- Avoid adding network calls, accounts, or telemetry without a clear reason and explicit user choice.

## Pull requests

Please describe the problem, the change, and how you tested it. For UI changes, include a screenshot when possible.
