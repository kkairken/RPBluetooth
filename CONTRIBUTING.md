# Contributing Guide

Thank you for considering contributing to the Offline Face Access Control System!

## Development Setup

1. **Clone repository:**
   ```bash
   git clone https://github.com/yourusername/rp3-face-access.git
   cd rp3-face-access
   ```

2. **Install development dependencies:**
   ```bash
   make install
   make dev
   ```

3. **Run tests:**
   ```bash
   make test
   ```

## Code Style

- **Python**: Follow PEP 8
- **Type Hints**: Use type hints for all functions
- **Docstrings**: Google-style docstrings
- **Line Length**: Max 100 characters

Format code with Black:
```bash
black src/ tests/
```

Lint with flake8:
```bash
flake8 src/ tests/ --max-line-length=100
```

## Testing

- Write unit tests for all new features
- Maintain >80% code coverage
- Test on actual Raspberry Pi 3 hardware when possible

Run tests:
```bash
pytest tests/ -v --cov=src
```

## Architecture Guidelines

### Module Responsibilities

- **config.py**: Configuration loading and validation
- **db.py**: Database operations (SQLite)
- **camera/**: Camera abstraction layer
- **face/**: Face detection, alignment, embedding, matching
- **access_control.py**: Access validation logic
- **lock.py**: GPIO lock control
- **ble_server.py**: BLE protocol and GATT server
- **main.py**: Application entry point

### Design Principles

1. **Modularity**: Each module has single responsibility
2. **Testability**: All components are testable in isolation
3. **Configurability**: Behavior controlled via config files
4. **Offline-First**: No external dependencies at runtime
5. **Performance**: Optimized for Raspberry Pi 3

## Adding New Features

### 1. Face Detector

Add new detector in `src/face/detector.py`:

```python
def _init_your_detector(self):
    """Initialize your detector."""
    # Implementation
    pass

def _detect_your_detector(self, frame):
    """Detect faces with your detector."""
    # Return list of (x, y, w, h) tuples
    pass
```

### 2. Camera Source

Add new camera in `src/camera/`:

```python
from .base import CameraBase

class YourCamera(CameraBase):
    def open(self) -> bool:
        # Implementation
        pass

    def read_frame(self):
        # Return (success, frame)
        pass
```

### 3. Authentication Method

Extend `ble_server.py` protocol:

```python
def handle_your_command(self, command, callback):
    """Handle your custom command."""
    # Implementation
    pass
```

## Pull Request Process

1. **Create feature branch:**
   ```bash
   git checkout -b feature/your-feature
   ```

2. **Make changes and commit:**
   ```bash
   git add .
   git commit -m "Add: your feature description"
   ```

3. **Write/update tests:**
   ```bash
   pytest tests/test_your_feature.py
   ```

4. **Update documentation:**
   - Update README.md if needed
   - Add docstrings to new functions
   - Update config examples if needed

5. **Push and create PR:**
   ```bash
   git push origin feature/your-feature
   ```

## Commit Message Format

```
Type: Brief description

Detailed explanation if needed.

Fixes #issue_number
```

Types:
- `Add`: New feature
- `Fix`: Bug fix
- `Update`: Update existing feature
- `Refactor`: Code refactoring
- `Docs`: Documentation changes
- `Test`: Test additions/changes

## Issues

### Reporting Bugs

Include:
- Raspberry Pi model and OS version
- Python version
- Steps to reproduce
- Expected vs actual behavior
- Relevant log excerpts

### Feature Requests

Include:
- Use case description
- Proposed implementation approach
- Potential challenges
- Hardware requirements (if any)

## Performance Optimization

When optimizing:

1. **Profile first:**
   ```python
   import cProfile
   cProfile.run('your_function()')
   ```

2. **Benchmark:**
   ```python
   import time
   start = time.time()
   # Your code
   print(f"Duration: {time.time() - start:.2f}s")
   ```

3. **Document impact:**
   - FPS improvement
   - Memory usage
   - CPU usage

## Security Considerations

- Never commit secrets or credentials
- Validate all external inputs
- Use parameterized SQL queries
- Follow OWASP guidelines
- Test HMAC implementation thoroughly

## Hardware Testing

Test on real hardware:
- Raspberry Pi 3 Model B
- Various USB cameras
- Different lighting conditions
- Different relay modules

## Documentation

Update docs for:
- New configuration options
- New CLI commands
- API changes
- Hardware requirements

## Release Process

1. Update version in `setup.py`
2. Update CHANGELOG.md
3. Tag release: `git tag v1.x.x`
4. Create release notes

## Questions?

Open an issue or discussion on GitHub.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
