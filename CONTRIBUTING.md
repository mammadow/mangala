# Contributing to Mangala

Thank you for your interest in improving Turkish Mangala! Whether you are reporting a bug, proposing an improvement to the AI evaluation heuristic, or enhancing the web interface, your contributions are welcome.

---

## 🛠️ Development Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/mammadow/mangala.git
   cd mangala
   ```

2. **Create a virtual environment and install dependencies**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e .[dev,gui]
   ```

3. **Install pre-commit hooks (optional but recommended)**:
   ```bash
   pre-commit install
   ```

---

## 🧪 Testing & Code Quality

Before opening a pull request, ensure all tests, linting, and type checks pass cleanly:

```bash
# Run unit and integration tests with coverage
pytest --cov=mangala tests/

# Run property-based hypothesis tests
pytest tests/test_properties.py

# Format and lint check
ruff check .

# Static type checking
mypy src/mangala/
```

---

## 📋 Pull Request Guidelines

1. **Keep Engine Logic Pure**: `src/mangala/engine.py` must remain free of external dependencies, side-effects, and mutations.
2. **AI Changes Require Benchmark Evidence**: If proposing changes to the AI search or evaluation weights, run `tools/selfplay.py` across at least 50 games to verify that the change produces a positive win rate or search depth improvement.
3. **Write Tests**: Any bug fix or new feature must include corresponding unit tests in `tests/`.
4. **Follow Semantic Versioning**: Major architectural changes or breaking API adjustments should be noted in `CHANGELOG.md`.
