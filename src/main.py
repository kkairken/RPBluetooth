"""
Main service runner for offline face access control system.
Production-ready with watchdog, error recovery, and graceful shutdown.
"""
import asyncio
import argparse
import logging
import logging.handlers
import sys
import signal
import os
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone
import time
import traceback
import cv2
import numpy as np

from config import load_config, SystemConfig

logger = logging.getLogger(__name__)

# Systemd watchdog support
try:
    import sdnotify
    SYSTEMD_AVAILABLE = True
except ImportError:
    SYSTEMD_AVAILABLE = False

from db import Database
from camera.usb_camera import USBCamera
from camera.rtsp_camera import RTSPCamera
from camera.base import CameraBase

# Pi Camera support (only on Raspberry Pi)
try:
    from camera.picamera_camera import PiCamera
    PICAMERA_AVAILABLE = True
except (ImportError, RuntimeError):
    PICAMERA_AVAILABLE = False
from face.detector import FaceDetector
from face.align import FaceAligner
from face.matcher import FaceMatcher
from face.quality import FaceQualityChecker

# Import both embedders for config-based selection
ONNX_RUNTIME_AVAILABLE = False
OPENCV_DNN_AVAILABLE = False

try:
    from face.embedder_onnx import FaceEmbedder as FaceEmbedderONNX
    ONNX_RUNTIME_AVAILABLE = True
except ImportError:
    FaceEmbedderONNX = None

try:
    from face.embedder_opencv import FaceEmbedderOpenCV
    OPENCV_DNN_AVAILABLE = True
except ImportError:
    FaceEmbedderOpenCV = None

# Default fallback
if ONNX_RUNTIME_AVAILABLE:
    FaceEmbedder = FaceEmbedderONNX
elif OPENCV_DNN_AVAILABLE:
    FaceEmbedder = FaceEmbedderOpenCV
    logger.info("ONNX Runtime not available, using OpenCV DNN backend")
else:
    FaceEmbedder = None
    logger.error("No face embedder backend available!")

from access_control import AccessController
from lock import LockController
from ble_server import BLEProtocol, BLEServer

# Try to import real BLE server (requires dbus and gi)
try:
    from ble_server_real import RealBLEServer
    REAL_BLE_AVAILABLE = True
except ImportError:
    REAL_BLE_AVAILABLE = False
    logger.info("Real BLE server not available (missing dbus/gi dependencies)")


class FaceAccessSystem:
    """Main face access control system with production features."""

    def __init__(self, config: SystemConfig):
        """
        Initialize system.

        Args:
            config: System configuration
        """
        self.config = config
        self.running = False
        self._shutdown_event = asyncio.Event()
        self._error_count = 0
        self._max_consecutive_errors = 10
        self._last_watchdog_ping = 0

        # Systemd watchdog
        self._sd_notifier = None
        if SYSTEMD_AVAILABLE:
            try:
                self._sd_notifier = sdnotify.SystemdNotifier()
                logger.info("Systemd watchdog enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize systemd notifier: {e}")

        # Initialize components
        logger.info("Initializing Face Access Control System...")

        self.db = Database(config.database.path)
        self.camera = self._init_camera()
        self.detector = FaceDetector(
            detector_type=config.face.detector_type,
            scale_factor=config.face.detector_scale_factor,
            min_neighbors=config.face.detector_min_neighbors,
            min_face_size=config.face.detector_min_face_size
        )
        self.aligner = FaceAligner(output_size=config.face.input_size)
        self.embedder = self._init_embedder(config)
        self.matcher = FaceMatcher(similarity_threshold=config.face.similarity_threshold)
        self.quality_checker = FaceQualityChecker(
            min_face_size=config.face.quality_min_face_size,
            blur_threshold=config.face.quality_blur_threshold
        )
        self.access_controller = AccessController(
            max_attempts_per_minute=config.access.max_attempts_per_minute,
            cooldown_sec=config.access.cooldown_sec,
            granted_lockout_sec=config.access.granted_lockout_sec
        )
        self.lock = LockController(
            gpio_pin=config.lock.gpio_pin,
            gpio_chip=config.lock.gpio_chip,
            active_high=config.lock.active_high,
            mock_mode=config.lock.mock_mode,
            unlock_duration=config.access.unlock_duration_sec,
            button_pin=config.lock.button_pin,
            button_active_low=config.lock.button_active_low,
            button_debounce_ms=config.lock.button_debounce_ms
        )

        # BLE server
        self.ble_protocol = BLEProtocol(
            shared_secret=config.ble.shared_secret,
            hmac_enabled=config.ble.hmac_enabled,
            max_photo_size=config.ble.max_photo_size,
            admin_mode_enabled=config.access.admin_mode_enabled
        )

        # Choose BLE server implementation
        use_real_ble = getattr(config.ble, 'use_real_ble', False)
        if use_real_ble and REAL_BLE_AVAILABLE:
            logger.info("Using REAL BLE server (BlueZ)")
            self.ble_server = RealBLEServer(config.ble, self.ble_protocol)
            # Set callbacks
            self.ble_server.set_callbacks(
                end_upsert_cb=self.process_registration_photos,
                update_period_cb=self.update_period_callback,
                deactivate_cb=self.deactivate_callback,
                status_cb=self.get_status_callback,
                list_employees_cb=self.list_employees_callback,
                audit_logs_cb=self.audit_logs_callback,
                delete_cb=self.delete_callback
            )
        else:
            if use_real_ble and not REAL_BLE_AVAILABLE:
                logger.warning("Real BLE requested but not available, using mock")
            logger.info("Using MOCK BLE server")
            self.ble_server = BLEServer(config.ble, self.ble_protocol)

        logger.info("System initialized successfully")

    def _init_camera(self) -> CameraBase:
        """Initialize camera based on config."""
        if self.config.camera.type == 'usb':
            return USBCamera(
                device_id=self.config.camera.device_id or 0,
                width=self.config.camera.width,
                height=self.config.camera.height,
                fps=self.config.camera.fps
            )
        elif self.config.camera.type == 'rtsp':
            if not self.config.camera.rtsp_url:
                raise ValueError("RTSP URL required for RTSP camera")
            return RTSPCamera(
                rtsp_url=self.config.camera.rtsp_url,
                transport=self.config.camera.rtsp_transport,
                width=self.config.camera.width,
                height=self.config.camera.height
            )
        elif self.config.camera.type == 'picamera':
            if not PICAMERA_AVAILABLE:
                raise RuntimeError("picamera not available. Install with: sudo apt install python3-picamera")
            return PiCamera(
                width=self.config.camera.width,
                height=self.config.camera.height,
                fps=self.config.camera.fps,
                rotation=self.config.camera.rotation,
                hflip=self.config.camera.hflip,
                vflip=self.config.camera.vflip
            )
        else:
            raise ValueError(f"Unknown camera type: {self.config.camera.type}")

    def _init_embedder(self, config):
        """Initialize face embedder based on config."""
        backend = getattr(config.face, 'embedder_backend', 'onnx')

        embedder_kwargs = dict(
            model_path=config.face.onnx_model_path,
            embedding_dim=config.face.embedding_dim,
            input_size=config.face.input_size,
            norm_mean=config.face.norm_mean,
            norm_std=config.face.norm_std
        )

        if backend == 'opencv' and OPENCV_DNN_AVAILABLE:
            logger.info("Using OpenCV DNN backend for face embeddings (configured)")
            return FaceEmbedderOpenCV(**embedder_kwargs)
        elif backend == 'onnx' and ONNX_RUNTIME_AVAILABLE:
            logger.info("Using ONNX Runtime backend for face embeddings")
            return FaceEmbedderONNX(**embedder_kwargs)
        elif OPENCV_DNN_AVAILABLE:
            logger.info("Falling back to OpenCV DNN backend")
            return FaceEmbedderOpenCV(**embedder_kwargs)
        elif ONNX_RUNTIME_AVAILABLE:
            logger.info("Falling back to ONNX Runtime backend")
            return FaceEmbedderONNX(**embedder_kwargs)
        else:
            raise RuntimeError("No face embedder backend available!")

    def process_registration_photos(self, session: dict) -> dict:
        """
        Process employee registration with photos.

        Args:
            session: Registration session dict with photos

        Returns:
            Result dict
        """
        try:
            employee_id = session['employee_id']
            display_name = session.get('display_name')
            access_start = datetime.fromisoformat(session['access_start'])
            access_end = datetime.fromisoformat(session['access_end'])
            photos = session['photos']

            logger.info(f"Processing registration for {employee_id} with {len(photos)} photos")

            # Process each photo
            embeddings = []
            for i, photo_bytes in enumerate(photos):
                # Decode JPEG
                nparr = np.frombuffer(photo_bytes, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                if frame is None:
                    logger.warning(f"Failed to decode photo {i+1}")
                    continue

                # Detect face
                faces = self.detector.detect(frame)

                # Validate photo quality
                valid, reason = self.quality_checker.validate_for_registration(frame, faces)
                if not valid:
                    logger.warning(f"Photo {i+1} quality check failed: {reason}")
                    continue

                # Align face
                aligned = self.aligner.align(frame, faces[0])
                if aligned is None:
                    logger.warning(f"Failed to align face in photo {i+1}")
                    continue

                # Compute embedding
                embedding = self.embedder.compute_embedding(aligned)
                if embedding is None:
                    logger.warning(f"Failed to compute embedding for photo {i+1}")
                    continue

                embeddings.append(embedding)

            if not embeddings:
                return {
                    'type': 'ERROR',
                    'message': 'No valid embeddings extracted from photos'
                }

            # Upsert employee
            self.db.upsert_employee(
                employee_id=employee_id,
                access_start=access_start,
                access_end=access_end,
                display_name=display_name,
                is_active=True
            )

            # Delete old embeddings
            self.db.delete_embeddings(employee_id)

            # Add new embeddings
            for embedding in embeddings:
                self.db.add_embedding(employee_id, embedding)

            logger.info(f"Registration complete for {employee_id}: {len(embeddings)} embeddings")

            return {
                'type': 'OK',
                'message': f'Registered {employee_id} with {len(embeddings)} embeddings'
            }

        except Exception as e:
            logger.error(f"Registration processing error: {e}")
            return {'type': 'ERROR', 'message': str(e)}

    def update_period_callback(self, employee_id: str, access_start: str, access_end: str) -> bool:
        """Callback for updating employee access period."""
        try:
            start_dt = datetime.fromisoformat(access_start)
            end_dt = datetime.fromisoformat(access_end)
            return self.db.update_employee_period(employee_id, start_dt, end_dt)
        except Exception as e:
            logger.error(f"Update period error: {e}")
            return False

    def deactivate_callback(self, employee_id: str) -> bool:
        """Callback for deactivating employee."""
        return self.db.deactivate_employee(employee_id)

    def get_status_callback(self) -> dict:
        """Callback for getting system status."""
        return self.db.get_system_status()

    def list_employees_callback(self) -> list:
        """Callback for listing all employees with embedding counts."""
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT e.employee_id, e.display_name, e.is_active,
                   e.access_start, e.access_end,
                   (SELECT COUNT(*) FROM embeddings WHERE employee_id = e.employee_id) as emb_count
            FROM employees e
            ORDER BY e.display_name
        """)
        result = []
        for row in cursor.fetchall():
            result.append({
                'employee_id': row[0],
                'display_name': row[1] or row[0],
                'is_active': bool(row[2]),
                'access_start': row[3],
                'access_end': row[4],
                'embedding_count': row[5]
            })
        return result

    def audit_logs_callback(self, employee_id=None, limit=100) -> list:
        """Callback for getting audit logs."""
        return self.db.get_audit_logs(employee_id=employee_id, limit=limit)

    def delete_callback(self, employee_id: str) -> bool:
        """Callback for deleting an employee."""
        return self.db.delete_employee(employee_id)

    async def recognition_loop(self):
        """Main face recognition loop with error recovery."""
        logger.info("Starting recognition loop")

        # Open camera with retries
        camera_retries = 3
        for attempt in range(camera_retries):
            if self.camera.open():
                break
            logger.warning(f"Camera open attempt {attempt + 1}/{camera_retries} failed")
            await asyncio.sleep(2)
        else:
            raise RuntimeError("Failed to open camera after multiple attempts")

        try:
            consecutive_frame_errors = 0
            max_frame_errors = 30  # ~3 seconds at 10fps

            # Face tracking optimization - skip embedding if same face detected
            last_face_pos = None  # (x, y, w, h)
            last_face_time = 0
            face_stable_count = 0
            FACE_STABLE_THRESHOLD = 3  # Need 3 stable detections before embedding
            FACE_POSITION_TOLERANCE = 50  # pixels

            while self.running:
                try:
                    # Read frame
                    ret, frame = self.camera.read_frame()
                    if not ret or frame is None:
                        consecutive_frame_errors += 1
                        if consecutive_frame_errors >= max_frame_errors:
                            logger.error("Too many consecutive frame errors, reopening camera")
                            self.camera.release()
                            await asyncio.sleep(1)
                            if not self.camera.open():
                                raise RuntimeError("Failed to reopen camera")
                            consecutive_frame_errors = 0
                        await asyncio.sleep(0.05)
                        continue

                    consecutive_frame_errors = 0  # Reset on success

                    # Detect faces
                    t_detect_start = time.time()
                    faces = self.detector.detect(frame)
                    t_detect = time.time() - t_detect_start

                    if not faces:
                        # No face - reset tracking
                        last_face_pos = None
                        face_stable_count = 0
                        await asyncio.sleep(0.02)
                        continue

                    # Process largest face
                    largest_face = max(faces, key=lambda f: f[2] * f[3])
                    face_x, face_y, face_w, face_h = largest_face

                    # Check if face position is stable (same person standing still)
                    if last_face_pos is not None:
                        dx = abs(face_x - last_face_pos[0])
                        dy = abs(face_y - last_face_pos[1])
                        if dx < FACE_POSITION_TOLERANCE and dy < FACE_POSITION_TOLERANCE:
                            face_stable_count += 1
                        else:
                            face_stable_count = 1  # New face position
                    else:
                        face_stable_count = 1

                    last_face_pos = (face_x, face_y, face_w, face_h)

                    # Only do expensive embedding if face is stable for N frames
                    if face_stable_count < FACE_STABLE_THRESHOLD:
                        logger.info(f"Face detected, waiting for stable ({face_stable_count}/{FACE_STABLE_THRESHOLD})...")
                        await asyncio.sleep(0.1)
                        continue

                    logger.info(f"Face STABLE: size={face_w}x{face_h} at ({face_x},{face_y}), detect={t_detect*1000:.0f}ms - starting embedding...")

                    # Align
                    t_align_start = time.time()
                    aligned = self.aligner.align(frame, largest_face)
                    t_align = time.time() - t_align_start
                    if aligned is None:
                        logger.warning(f"Face alignment failed, align_time={t_align*1000:.1f}ms")
                        continue

                    # Compute embedding
                    t_embed_start = time.time()
                    embedding = self.embedder.compute_embedding(aligned)
                    t_embed = time.time() - t_embed_start
                    if embedding is None:
                        logger.warning(f"Embedding computation failed, embed_time={t_embed*1000:.1f}ms")
                        continue

                    # Get active employees with embeddings
                    t_db_start = time.time()
                    employees_data = self.db.get_active_employees_with_embeddings()
                    t_db = time.time() - t_db_start

                    # Match
                    t_match_start = time.time()
                    employee_id, score, display_name = self.matcher.find_best_match(
                        embedding,
                        employees_data
                    )
                    t_match = time.time() - t_match_start

                    # Log timing summary
                    total_time = t_detect + t_align + t_embed + t_db + t_match
                    logger.info(
                        f"Recognition pipeline: detect={t_detect*1000:.0f}ms, align={t_align*1000:.0f}ms, "
                        f"embed={t_embed*1000:.0f}ms, db={t_db*1000:.0f}ms, match={t_match*1000:.0f}ms, "
                        f"TOTAL={total_time*1000:.0f}ms | best_match={employee_id}, score={score:.3f}"
                    )

                    # Get employee record
                    employee = None
                    if employee_id:
                        employee = self.db.get_employee(employee_id)

                    # Process access attempt
                    granted, reason, metadata = self.access_controller.process_access_attempt(
                        employee,
                        score,
                        self.config.face.similarity_threshold
                    )

                    # Log attempt (with error handling)
                    try:
                        self.db.log_access_attempt(
                            event_type='face_recognition',
                            result='granted' if granted else 'denied',
                            employee_id=employee_id,
                            matched_employee_id=employee_id,
                            similarity_score=score,
                            reason=reason,
                            metadata=metadata
                        )
                    except Exception as db_err:
                        logger.error(f"Failed to log access attempt: {db_err}")

                    if granted:
                        logger.info(f">>> Access GRANTED: {employee_id} ({display_name}) - score: {score:.3f}")
                        # Reset face tracking after recognition
                        face_stable_count = 0
                        last_face_pos = None
                        # Check if lock is already unlocking (additional safety)
                        if self.lock.is_unlocking():
                            logger.debug(f"Lock already unlocking, skipping for {employee_id}")
                        else:
                            try:
                                self.lock.unlock()
                            except Exception as lock_err:
                                logger.error(f"Failed to unlock: {lock_err}")
                        # Cooldown only after successful grant
                        logger.info(f"Cooldown: sleeping {self.config.access.cooldown_sec}s after grant")
                        await asyncio.sleep(self.config.access.cooldown_sec)
                    else:
                        logger.info(f"<<< Access DENIED: {reason} - score: {score:.3f}")
                        # Reset tracking to try again with fresh detection
                        face_stable_count = 0
                        # Short delay for denied attempts (lockout handles repeat prevention)
                        await asyncio.sleep(0.1)

                except asyncio.CancelledError:
                    raise
                except Exception as loop_err:
                    logger.error(f"Error in recognition iteration: {loop_err}")
                    await asyncio.sleep(0.5)

        finally:
            self.camera.release()
            logger.info("Recognition loop stopped")

    def _on_exit_button_pressed(self):
        """Callback when exit button is pressed."""
        logger.info("Exit button pressed - unlocking door")
        # Log the event
        try:
            self.db.log_access_attempt(
                event_type='exit_button',
                result='granted',
                reason='Exit button pressed'
            )
        except Exception as e:
            logger.error(f"Failed to log exit button event: {e}")
        # Unlock the door
        try:
            self.lock.unlock()
        except Exception as e:
            logger.error(f"Failed to unlock door: {e}")

    def _notify_watchdog(self):
        """Notify systemd watchdog that we're alive."""
        if self._sd_notifier:
            try:
                self._sd_notifier.notify("WATCHDOG=1")
                self._last_watchdog_ping = time.time()
            except Exception as e:
                logger.warning(f"Watchdog notify failed: {e}")

    def _notify_ready(self):
        """Notify systemd that service is ready."""
        if self._sd_notifier:
            try:
                self._sd_notifier.notify("READY=1")
                logger.info("Notified systemd: service ready")
            except Exception as e:
                logger.warning(f"Ready notify failed: {e}")

    def _notify_stopping(self):
        """Notify systemd that service is stopping."""
        if self._sd_notifier:
            try:
                self._sd_notifier.notify("STOPPING=1")
            except Exception:
                pass

    async def _watchdog_loop(self):
        """Background task to ping systemd watchdog."""
        while self.running:
            self._notify_watchdog()
            await asyncio.sleep(15)  # Ping every 15 seconds (WatchdogSec=60)

    async def run(self):
        """Run the system with production error handling."""
        self.running = True

        # Start exit button monitor if configured
        if self.config.lock.button_pin is not None:
            self.lock.start_button_monitor(callback=self._on_exit_button_pressed)

        # Notify systemd we're ready
        self._notify_ready()

        # Start tasks
        tasks = [
            asyncio.create_task(self._watchdog_loop(), name="watchdog"),
            asyncio.create_task(self._recognition_loop_wrapper(), name="recognition"),
            asyncio.create_task(self._ble_server_wrapper(), name="ble_server")
        ]
        shutdown_task = asyncio.create_task(self._shutdown_event.wait(), name="shutdown")

        try:
            # Wait for shutdown or task failure
            done, pending = await asyncio.wait(
                tasks + [shutdown_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            # Check for exceptions
            for task in done:
                if task is shutdown_task:
                    continue
                if task.exception():
                    logger.error(f"Task {task.get_name()} failed: {task.exception()}")

            # Cancel pending tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        except asyncio.CancelledError:
            logger.info("System shutting down")
        except Exception as e:
            logger.error(f"Unexpected error in run loop: {e}")
            logger.error(traceback.format_exc())

    async def _recognition_loop_wrapper(self):
        """Wrapper for recognition loop with automatic restart on errors."""
        restart_delay = 5  # seconds
        max_restart_delay = 60

        while self.running:
            try:
                await self.recognition_loop()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._error_count += 1
                logger.error(f"Recognition loop error ({self._error_count}): {e}")
                logger.error(traceback.format_exc())

                if self._error_count >= self._max_consecutive_errors:
                    logger.critical("Too many consecutive errors, stopping recognition")
                    break

                # Exponential backoff
                delay = min(restart_delay * (2 ** (self._error_count - 1)), max_restart_delay)
                logger.info(f"Restarting recognition loop in {delay} seconds...")
                await asyncio.sleep(delay)
            else:
                # Reset error count on clean exit
                self._error_count = 0

    async def _ble_server_wrapper(self):
        """Wrapper for BLE server with automatic restart."""
        restart_delay = 5

        while self.running:
            try:
                await self.ble_server.start()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"BLE server error: {e}")
                logger.error(traceback.format_exc())

                if not self.running:
                    break

                logger.info(f"Restarting BLE server in {restart_delay} seconds...")
                await asyncio.sleep(restart_delay)

    async def stop(self):
        """Stop the system gracefully."""
        logger.info("Stopping system...")
        self._notify_stopping()
        self.running = False
        self._shutdown_event.set()

        # Stop components in order
        try:
            await asyncio.wait_for(self.ble_server.stop(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("BLE server stop timed out")
        except Exception as e:
            logger.error(f"Error stopping BLE server: {e}")

        try:
            self.lock.cleanup()
        except Exception as e:
            logger.error(f"Error cleaning up lock: {e}")

        try:
            self.db.close()
        except Exception as e:
            logger.error(f"Error closing database: {e}")

        logger.info("System stopped")


def export_logs(db_path: str, output_file: str):
    """
    Export audit logs to file.

    Args:
        db_path: Database path
        output_file: Output file path
    """
    import json

    db = Database(db_path)
    logs = db.get_audit_logs(limit=1000)

    with open(output_file, 'w') as f:
        json.dump(logs, f, indent=2)

    logger.info(f"Exported {len(logs)} log entries to {output_file}")


def setup_logging(log_level: str, log_dir: str = "logs"):
    """Setup production logging with rotation."""
    # Create logs directory
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level))

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)

    # File handler with rotation (10MB, keep 5 files)
    file_handler = logging.handlers.RotatingFileHandler(
        log_path / 'face_access.log',
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(file_format)
    root_logger.addHandler(file_handler)

    # Error file (only errors)
    error_handler = logging.handlers.RotatingFileHandler(
        log_path / 'errors.log',
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_format)
    root_logger.addHandler(error_handler)

    return root_logger


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Offline Face Access Control System')
    parser.add_argument(
        '--config',
        type=str,
        required=True,
        help='Path to configuration file (YAML)'
    )
    parser.add_argument(
        '--export-logs',
        type=str,
        help='Export audit logs to JSON file'
    )
    parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level'
    )
    parser.add_argument(
        '--log-dir',
        type=str,
        default='logs',
        help='Directory for log files'
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.log_level, args.log_dir)
    logger.info("=" * 60)
    logger.info("RP3 Face Access Control System starting...")
    logger.info(f"Config: {args.config}")
    logger.info(f"PID: {os.getpid()}")
    logger.info("=" * 60)

    # Load config
    try:
        config = load_config(args.config)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        sys.exit(1)

    # Handle export logs command
    if args.export_logs:
        export_logs(config.database.path, args.export_logs)
        return

    # Create system
    try:
        system = FaceAccessSystem(config)
    except Exception as e:
        logger.critical(f"Failed to initialize system: {e}")
        logger.critical(traceback.format_exc())
        sys.exit(1)

    # Signal handlers
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, initiating shutdown...")
        loop.call_soon_threadsafe(
            lambda: asyncio.create_task(system.stop())
        )

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run async main loop
    exit_code = 0
    try:
        loop.run_until_complete(system.run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.critical(f"Fatal system error: {e}")
        logger.critical(traceback.format_exc())
        exit_code = 1
    finally:
        # Cleanup
        try:
            loop.run_until_complete(system.stop())
        except Exception:
            pass
        loop.close()
        logger.info("System shutdown complete")

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
