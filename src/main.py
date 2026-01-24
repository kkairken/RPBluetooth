"""
Main service runner for offline face access control system.
"""
import asyncio
import argparse
import logging
import sys
import signal
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone
import time
import cv2
import numpy as np

from config import load_config, SystemConfig
from db import Database
from camera.usb_camera import USBCamera
from camera.rtsp_camera import RTSPCamera
from camera.base import CameraBase
from face.detector import FaceDetector
from face.align import FaceAligner
from face.embedder_onnx import FaceEmbedder
from face.matcher import FaceMatcher
from face.quality import FaceQualityChecker
from access_control import AccessController
from lock import LockController
from ble_server import BLEProtocol, BLEServer

# Try to import real BLE server (requires dbus and gi)
try:
    from ble_server_real import RealBLEServer
    REAL_BLE_AVAILABLE = True
except ImportError:
    REAL_BLE_AVAILABLE = False
    logger.warning("Real BLE server not available (missing dbus/gi dependencies)")

logger = logging.getLogger(__name__)


class FaceAccessSystem:
    """Main face access control system."""

    def __init__(self, config: SystemConfig):
        """
        Initialize system.

        Args:
            config: System configuration
        """
        self.config = config
        self.running = False

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
        self.aligner = FaceAligner(output_size=(112, 112))
        self.embedder = FaceEmbedder(
            model_path=config.face.onnx_model_path,
            embedding_dim=config.face.embedding_dim
        )
        self.matcher = FaceMatcher(similarity_threshold=config.face.similarity_threshold)
        self.quality_checker = FaceQualityChecker(
            min_face_size=config.face.quality_min_face_size,
            blur_threshold=config.face.quality_blur_threshold
        )
        self.access_controller = AccessController(
            max_attempts_per_minute=config.access.max_attempts_per_minute,
            cooldown_sec=config.access.cooldown_sec
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
                status_cb=self.get_status_callback
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
        else:
            raise ValueError(f"Unknown camera type: {self.config.camera.type}")

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

    async def recognition_loop(self):
        """Main face recognition loop."""
        logger.info("Starting recognition loop")

        # Open camera
        if not self.camera.open():
            logger.error("Failed to open camera")
            return

        try:
            frame_skip = 2  # Process every Nth frame
            frame_count = 0

            while self.running:
                # Read frame
                ret, frame = self.camera.read_frame()
                if not ret or frame is None:
                    await asyncio.sleep(0.1)
                    continue

                frame_count += 1
                if frame_count % frame_skip != 0:
                    await asyncio.sleep(0.01)
                    continue

                # Detect faces
                faces = self.detector.detect(frame)

                if not faces:
                    await asyncio.sleep(0.1)
                    continue

                # Process largest face
                largest_face = max(faces, key=lambda f: f[2] * f[3])

                # Align
                aligned = self.aligner.align(frame, largest_face)
                if aligned is None:
                    continue

                # Compute embedding
                embedding = self.embedder.compute_embedding(aligned)
                if embedding is None:
                    continue

                # Get active employees with embeddings
                employees_data = self.db.get_active_employees_with_embeddings()

                # Match
                employee_id, score, display_name = self.matcher.find_best_match(
                    embedding,
                    employees_data
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

                # Log attempt
                self.db.log_access_attempt(
                    event_type='face_recognition',
                    result='granted' if granted else 'denied',
                    employee_id=employee_id,
                    matched_employee_id=employee_id,
                    similarity_score=score,
                    reason=reason,
                    metadata=metadata
                )

                if granted:
                    logger.info(f"Access GRANTED: {employee_id} ({display_name}) - score: {score:.3f}")
                    self.lock.unlock()
                else:
                    logger.info(f"Access DENIED: {reason} - score: {score:.3f}")

                # Cooldown
                await asyncio.sleep(self.config.access.cooldown_sec)

        finally:
            self.camera.release()
            logger.info("Recognition loop stopped")

    def _on_exit_button_pressed(self):
        """Callback when exit button is pressed."""
        logger.info("Exit button pressed - unlocking door")
        # Log the event
        self.db.log_access_attempt(
            event_type='exit_button',
            result='granted',
            reason='Exit button pressed'
        )
        # Unlock is called automatically by LockController

    async def run(self):
        """Run the system."""
        self.running = True

        # Start exit button monitor if configured
        if self.config.lock.button_pin is not None:
            self.lock.start_button_monitor(callback=self._on_exit_button_pressed)

        # Start tasks
        tasks = [
            asyncio.create_task(self.recognition_loop()),
            asyncio.create_task(self.ble_server.start())
        ]

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("System shutting down")

    async def stop(self):
        """Stop the system."""
        logger.info("Stopping system...")
        self.running = False
        await self.ble_server.stop()
        self.lock.cleanup()
        self.db.close()
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

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('face_access.log')
        ]
    )

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

    # Create and run system
    system = FaceAccessSystem(config)

    # Signal handlers
    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        asyncio.create_task(system.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run async main loop
    try:
        asyncio.run(system.run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"System error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
