.PHONY: help install test run clean dev

help:
	@echo "Available commands:"
	@echo "  make install    - Install dependencies"
	@echo "  make test       - Run unit tests"
	@echo "  make run        - Run system with USB camera"
	@echo "  make run-rtsp   - Run system with RTSP camera"
	@echo "  make clean      - Clean up generated files"
	@echo "  make dev        - Install development dependencies"
	@echo "  make register   - Register test employee"
	@echo "  make logs       - Export audit logs"

install:
	python3 -m venv venv || true
	. venv/bin/activate && pip install --upgrade pip
	. venv/bin/activate && pip install -r requirements.txt
	mkdir -p data models
	@echo "Installation complete. Don't forget to place ONNX model in models/"

test:
	. venv/bin/activate && python -m pytest tests/ -v

run:
	. venv/bin/activate && python src/main.py --config config/usb_config.yaml

run-rtsp:
	. venv/bin/activate && python src/main.py --config config/rtsp_config.yaml

clean:
	rm -rf __pycache__ src/__pycache__ tests/__pycache__
	rm -rf src/*/__pycache__
	rm -rf .pytest_cache
	rm -f *.log
	rm -f data/*.db-journal

dev:
	. venv/bin/activate && pip install pytest pytest-asyncio black flake8 mypy

register:
	. venv/bin/activate && python tools/ble_client_simulator.py \
		--action register \
		--employee-id TEST001 \
		--display-name "Test User" \
		--access-start "2025-01-01T00:00:00Z" \
		--access-end "2026-12-31T23:59:59Z" \
		--photos examples/photo1.jpg examples/photo2.jpg

logs:
	. venv/bin/activate && python src/main.py \
		--config config/usb_config.yaml \
		--export-logs audit_logs_export.json
	@echo "Logs exported to audit_logs_export.json"

status:
	sqlite3 data/access_control.db "SELECT * FROM employees;"
	@echo ""
	sqlite3 data/access_control.db "SELECT COUNT(*) as total_embeddings FROM embeddings;"
	@echo ""
	sqlite3 data/access_control.db "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 5;"
