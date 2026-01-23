#!/usr/bin/env python3
"""
BLE Client Simulator for testing employee registration.
Simulates mobile app sending registration commands via BLE.
"""
import argparse
import json
import hashlib
import hmac
import time
import base64
from pathlib import Path
from typing import Optional


class BLEClientSimulator:
    """Simulates BLE client for testing."""

    def __init__(self, shared_secret: Optional[str] = None):
        """
        Initialize BLE client simulator.

        Args:
            shared_secret: Shared secret for HMAC (if enabled)
        """
        self.shared_secret = shared_secret

    def _sign_command(self, command: dict) -> dict:
        """
        Sign command with HMAC.

        Args:
            command: Command dictionary

        Returns:
            Signed command with nonce and HMAC
        """
        if not self.shared_secret:
            return command

        # Generate nonce
        import os
        nonce = f"{int(time.time())}_{os.urandom(8).hex()}"
        command['nonce'] = nonce

        # Compute HMAC
        message = json.dumps(command, sort_keys=True).encode('utf-8')
        signature = hmac.new(
            self.shared_secret.encode('utf-8'),
            message,
            hashlib.sha256
        ).hexdigest()

        command['hmac'] = signature
        return command

    def register_employee(
        self,
        employee_id: str,
        display_name: str,
        access_start: str,
        access_end: str,
        photo_paths: list,
        chunk_size: int = 512
    ):
        """
        Simulate employee registration.

        Args:
            employee_id: Employee identifier
            display_name: Display name
            access_start: Access start datetime (ISO format)
            access_end: Access end datetime (ISO format)
            photo_paths: List of photo file paths
            chunk_size: Size of each photo chunk in bytes
        """
        print(f"Registering employee: {employee_id}")
        print(f"  Display name: {display_name}")
        print(f"  Access: {access_start} to {access_end}")
        print(f"  Photos: {len(photo_paths)}")

        # Step 1: BEGIN_UPSERT
        begin_command = {
            'command': 'BEGIN_UPSERT',
            'employee_id': employee_id,
            'display_name': display_name,
            'access_start': access_start,
            'access_end': access_end,
            'num_photos': len(photo_paths)
        }

        begin_command = self._sign_command(begin_command)
        print("\n1. BEGIN_UPSERT command:")
        print(json.dumps(begin_command, indent=2))

        # Step 2: Send each photo in chunks
        for photo_idx, photo_path in enumerate(photo_paths):
            print(f"\n2.{photo_idx + 1}. Sending photo: {photo_path}")

            photo_file = Path(photo_path)
            if not photo_file.exists():
                print(f"  ERROR: Photo not found: {photo_path}")
                continue

            # Read photo
            with open(photo_file, 'rb') as f:
                photo_data = f.read()

            # Compute hash
            photo_hash = hashlib.sha256(photo_data).hexdigest()
            print(f"  Size: {len(photo_data)} bytes")
            print(f"  SHA256: {photo_hash}")

            # Split into chunks
            chunks = []
            for i in range(0, len(photo_data), chunk_size):
                chunks.append(photo_data[i:i + chunk_size])

            print(f"  Chunks: {len(chunks)}")

            # Send chunks
            for chunk_idx, chunk in enumerate(chunks):
                is_last = (chunk_idx == len(chunks) - 1)

                chunk_command = {
                    'command': 'PHOTO_CHUNK',
                    'chunk_index': chunk_idx,
                    'total_chunks': len(chunks),
                    'data': base64.b64encode(chunk).decode('ascii'),
                    'is_last': is_last
                }

                if is_last:
                    chunk_command['sha256'] = photo_hash

                if chunk_idx == 0 or chunk_idx == len(chunks) - 1:
                    print(f"  Chunk {chunk_idx + 1}/{len(chunks)}: {len(chunk)} bytes")
                elif chunk_idx == 1:
                    print(f"  ... (sending remaining chunks)")

                # In real implementation, send via BLE
                # For simulation, just print first and last chunks
                if chunk_idx == 0:
                    print(f"  First chunk command (truncated):")
                    cmd_copy = chunk_command.copy()
                    cmd_copy['data'] = cmd_copy['data'][:50] + '...'
                    print(json.dumps(cmd_copy, indent=2))

        # Step 3: END_UPSERT
        end_command = {
            'command': 'END_UPSERT'
        }

        print("\n3. END_UPSERT command:")
        print(json.dumps(end_command, indent=2))

        print("\n✓ Registration simulation complete")

    def deactivate_employee(self, employee_id: str):
        """
        Simulate employee deactivation.

        Args:
            employee_id: Employee identifier
        """
        print(f"Deactivating employee: {employee_id}")

        command = {
            'command': 'DEACTIVATE',
            'employee_id': employee_id
        }

        command = self._sign_command(command)
        print("\nDEACTIVATE command:")
        print(json.dumps(command, indent=2))

    def update_period(self, employee_id: str, access_start: str, access_end: str):
        """
        Simulate period update.

        Args:
            employee_id: Employee identifier
            access_start: New access start datetime
            access_end: New access end datetime
        """
        print(f"Updating period for employee: {employee_id}")
        print(f"  New period: {access_start} to {access_end}")

        command = {
            'command': 'UPDATE_PERIOD',
            'employee_id': employee_id,
            'access_start': access_start,
            'access_end': access_end
        }

        command = self._sign_command(command)
        print("\nUPDATE_PERIOD command:")
        print(json.dumps(command, indent=2))

    def get_status(self):
        """Simulate status request."""
        print("Requesting system status")

        command = {
            'command': 'GET_STATUS'
        }

        print("\nGET_STATUS command:")
        print(json.dumps(command, indent=2))


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='BLE Client Simulator')
    parser.add_argument(
        '--action',
        type=str,
        required=True,
        choices=['register', 'deactivate', 'update-period', 'status'],
        help='Action to perform'
    )
    parser.add_argument(
        '--employee-id',
        type=str,
        help='Employee ID'
    )
    parser.add_argument(
        '--display-name',
        type=str,
        help='Display name'
    )
    parser.add_argument(
        '--access-start',
        type=str,
        help='Access start datetime (ISO format)'
    )
    parser.add_argument(
        '--access-end',
        type=str,
        help='Access end datetime (ISO format)'
    )
    parser.add_argument(
        '--photos',
        type=str,
        nargs='+',
        help='Photo file paths'
    )
    parser.add_argument(
        '--shared-secret',
        type=str,
        help='Shared secret for HMAC'
    )
    parser.add_argument(
        '--chunk-size',
        type=int,
        default=512,
        help='Chunk size in bytes (default: 512)'
    )

    args = parser.parse_args()

    client = BLEClientSimulator(shared_secret=args.shared_secret)

    if args.action == 'register':
        if not args.employee_id or not args.access_start or not args.access_end or not args.photos:
            print("ERROR: register requires --employee-id, --access-start, --access-end, and --photos")
            return

        client.register_employee(
            employee_id=args.employee_id,
            display_name=args.display_name or args.employee_id,
            access_start=args.access_start,
            access_end=args.access_end,
            photo_paths=args.photos,
            chunk_size=args.chunk_size
        )

    elif args.action == 'deactivate':
        if not args.employee_id:
            print("ERROR: deactivate requires --employee-id")
            return
        client.deactivate_employee(args.employee_id)

    elif args.action == 'update-period':
        if not args.employee_id or not args.access_start or not args.access_end:
            print("ERROR: update-period requires --employee-id, --access-start, and --access-end")
            return
        client.update_period(args.employee_id, args.access_start, args.access_end)

    elif args.action == 'status':
        client.get_status()


if __name__ == '__main__':
    main()
