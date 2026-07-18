# Contributing to Tank

Thank you for your interest in contributing to Tank! We welcome bug reports, feature requests, documentation improvements, and pull requests.

## 🛠️ Local Development Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yasirusman85/Tank.git
   cd Tank
   ```

2. **Set up a virtual environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .\.venv\Scripts\activate
   ```

3. **Install dependencies in editable mode**:
   ```bash
   pip install -e ".[dev]"
   ```

4. **Run the test suite**:
   ```bash
   pytest tests/
   ```

---

## 🧪 Testing Guidelines

- Write unit tests for new features inside the `tests/` directory.
- Ensure all tests pass before submitting a pull request.
- Keep test cases independent and clean using `pytest-asyncio`.

---

## 🔀 Pull Request Process

1. Create a feature branch off `main` (`git checkout -b feature/my-feature`).
2. Make your changes and commit with clear, descriptive messages.
3. Push to your fork and open a Pull Request against `main`.
4. Ensure CI tests pass.
