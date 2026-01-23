# BLE API Reference

API documentation for mobile app developers integrating with the Face Access Control System.

## Overview

The system exposes a BLE GATT service for employee registration and management. All communication happens via BLE characteristics with JSON-formatted commands.

## BLE Service

### Service UUID
```
12345678-1234-5678-1234-56789abcdef0
```

### Characteristics

| UUID | Type | Description |
|------|------|-------------|
| `12345678-1234-5678-1234-56789abcdef1` | Write | Command input |
| `12345678-1234-5678-1234-56789abcdef2` | Notify | Response output |

## Authentication

### HMAC-SHA256

All admin commands must include HMAC authentication:

```javascript
// JavaScript example
const crypto = require('crypto');

function signCommand(command, sharedSecret) {
    // Add nonce
    const nonce = `${Math.floor(Date.now() / 1000)}_${randomHex(16)}`;
    command.nonce = nonce;

    // Compute HMAC
    const message = JSON.stringify(command, Object.keys(command).sort());
    const hmac = crypto.createHmac('sha256', sharedSecret)
                      .update(message)
                      .digest('hex');

    command.hmac = hmac;
    return command;
}
```

```python
# Python example
import json
import hmac
import hashlib
import time
import os

def sign_command(command, shared_secret):
    # Add nonce
    nonce = f"{int(time.time())}_{os.urandom(8).hex()}"
    command['nonce'] = nonce

    # Compute HMAC
    message = json.dumps(command, sort_keys=True).encode('utf-8')
    signature = hmac.new(
        shared_secret.encode('utf-8'),
        message,
        hashlib.sha256
    ).hexdigest()

    command['hmac'] = signature
    return command
```

```swift
// Swift example
import Foundation
import CryptoKit

func signCommand(_ command: inout [String: Any], sharedSecret: String) {
    // Add nonce
    let nonce = "\(Int(Date().timeIntervalSince1970))_\(UUID().uuidString.prefix(16))"
    command["nonce"] = nonce

    // Sort keys and create message
    let sortedKeys = command.keys.sorted()
    let jsonData = try! JSONSerialization.data(withJSONObject: command)

    // Compute HMAC
    let key = SymmetricKey(data: sharedSecret.data(using: .utf8)!)
    let signature = HMAC<SHA256>.authenticationCode(for: jsonData, using: key)
    command["hmac"] = signature.map { String(format: "%02x", $0) }.joined()
}
```

## Commands

### 1. BEGIN_UPSERT

Start employee registration session.

**Request:**
```json
{
    "command": "BEGIN_UPSERT",
    "employee_id": "EMP001",
    "display_name": "John Doe",
    "access_start": "2025-01-01T00:00:00Z",
    "access_end": "2025-12-31T23:59:59Z",
    "num_photos": 3,
    "nonce": "1737590400_a1b2c3d4e5f6",
    "hmac": "abc123...def789"
}
```

**Fields:**
- `employee_id` (required): Unique employee identifier
- `display_name` (optional): Human-readable name
- `access_start` (required): ISO 8601 datetime
- `access_end` (required): ISO 8601 datetime
- `num_photos` (required): Number of photos (1-5)
- `nonce` (required): Fresh nonce
- `hmac` (required): HMAC signature

**Response:**
```json
{
    "type": "OK",
    "message": "Session started for EMP001",
    "session_id": "EMP001"
}
```

**Error Response:**
```json
{
    "type": "ERROR",
    "message": "Admin mode not enabled"
}
```

### 2. PHOTO_CHUNK

Send photo data in chunks.

**Request:**
```json
{
    "command": "PHOTO_CHUNK",
    "chunk_index": 0,
    "total_chunks": 50,
    "data": "base64_encoded_chunk_data_here...",
    "is_last": false
}
```

**Last Chunk (include SHA256):**
```json
{
    "command": "PHOTO_CHUNK",
    "chunk_index": 49,
    "total_chunks": 50,
    "data": "base64_encoded_chunk_data_here...",
    "is_last": true,
    "sha256": "abc123...def789"
}
```

**Fields:**
- `chunk_index` (required): Zero-based chunk index
- `total_chunks` (required): Total number of chunks
- `data` (required): Base64-encoded chunk data
- `is_last` (required): True if last chunk
- `sha256` (required for last chunk): SHA256 hash of complete photo

**Progress Response:**
```json
{
    "type": "PROGRESS",
    "progress": 50,
    "chunk_index": 24,
    "total_chunks": 50
}
```

**Success Response (last chunk):**
```json
{
    "type": "OK",
    "message": "Photo 1 received",
    "photos_received": 1,
    "photos_total": 3
}
```

**Chunking Example (JavaScript):**
```javascript
async function sendPhoto(photoData, chunkSize = 512) {
    const totalChunks = Math.ceil(photoData.length / chunkSize);
    const photoHash = await sha256(photoData);

    for (let i = 0; i < totalChunks; i++) {
        const start = i * chunkSize;
        const end = Math.min(start + chunkSize, photoData.length);
        const chunk = photoData.slice(start, end);

        const command = {
            command: "PHOTO_CHUNK",
            chunk_index: i,
            total_chunks: totalChunks,
            data: btoa(chunk),
            is_last: i === totalChunks - 1
        };

        if (command.is_last) {
            command.sha256 = photoHash;
        }

        await sendCommand(command);
        await waitForResponse();
    }
}
```

### 3. END_UPSERT

Complete registration and process photos.

**Request:**
```json
{
    "command": "END_UPSERT"
}
```

**Response:**
```json
{
    "type": "OK",
    "message": "Registered EMP001 with 3 embeddings"
}
```

**Error Response:**
```json
{
    "type": "ERROR",
    "message": "No valid embeddings extracted from photos"
}
```

### 4. UPDATE_PERIOD

Update employee access period.

**Request:**
```json
{
    "command": "UPDATE_PERIOD",
    "employee_id": "EMP001",
    "access_start": "2026-01-01T00:00:00Z",
    "access_end": "2026-12-31T23:59:59Z",
    "nonce": "1737590400_xyz789",
    "hmac": "def456...abc123"
}
```

**Response:**
```json
{
    "type": "OK",
    "message": "Period updated for EMP001"
}
```

### 5. DEACTIVATE

Deactivate an employee.

**Request:**
```json
{
    "command": "DEACTIVATE",
    "employee_id": "EMP001",
    "nonce": "1737590400_qwe456",
    "hmac": "ghi789...jkl012"
}
```

**Response:**
```json
{
    "type": "OK",
    "message": "Employee EMP001 deactivated"
}
```

### 6. DELETE (Optional)

Permanently delete an employee.

**Request:**
```json
{
    "command": "DELETE",
    "employee_id": "EMP001",
    "nonce": "1737590400_mno345",
    "hmac": "pqr678...stu901"
}
```

**Response:**
```json
{
    "type": "OK",
    "message": "Employee EMP001 deleted"
}
```

### 7. GET_STATUS

Query system status.

**Request:**
```json
{
    "command": "GET_STATUS"
}
```

**Response:**
```json
{
    "type": "STATUS",
    "data": {
        "active_employees": 25,
        "total_employees": 30,
        "total_embeddings": 75,
        "recent_attempts_1h": 12
    }
}
```

## Complete Registration Flow

### Sequence Diagram

```
Mobile App                  Raspberry Pi
    |                            |
    |---- BEGIN_UPSERT --------->|
    |                            |--- Create session
    |<------- OK ----------------|
    |                            |
    |                            |
    |---- PHOTO_CHUNK (0) ------>|
    |<------- PROGRESS ----------|
    |                            |
    |---- PHOTO_CHUNK (1) ------>|
    |<------- PROGRESS ----------|
    |                            |
    |         ...                |
    |                            |
    |---- PHOTO_CHUNK (last) --->|
    |                            |--- Verify hash
    |<------- OK ----------------|
    |                            |
    |                            |
    |   (Repeat for other photos)|
    |                            |
    |                            |
    |---- END_UPSERT ----------->|
    |                            |--- Process photos
    |                            |--- Detect faces
    |                            |--- Compute embeddings
    |                            |--- Save to database
    |<------- OK ----------------|
```

### Example Implementation (Swift)

```swift
import CoreBluetooth

class FaceAccessBLEManager: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    private var centralManager: CBCentralManager!
    private var peripheral: CBPeripheral?
    private var commandCharacteristic: CBCharacteristic?
    private var responseCharacteristic: CBCharacteristic?

    private let serviceUUID = CBUUID(string: "12345678-1234-5678-1234-56789abcdef0")
    private let commandUUID = CBUUID(string: "12345678-1234-5678-1234-56789abcdef1")
    private let responseUUID = CBUUID(string: "12345678-1234-5678-1234-56789abcdef2")

    func registerEmployee(
        id: String,
        name: String,
        accessStart: Date,
        accessEnd: Date,
        photos: [Data]
    ) async throws {
        // 1. BEGIN_UPSERT
        var beginCommand: [String: Any] = [
            "command": "BEGIN_UPSERT",
            "employee_id": id,
            "display_name": name,
            "access_start": ISO8601DateFormatter().string(from: accessStart),
            "access_end": ISO8601DateFormatter().string(from: accessEnd),
            "num_photos": photos.count
        ]

        signCommand(&beginCommand, sharedSecret: "your_secret")
        try await sendCommand(beginCommand)
        let response = try await waitForResponse()
        guard response["type"] as? String == "OK" else {
            throw BLEError.commandFailed
        }

        // 2. Send photos
        for photo in photos {
            try await sendPhotoChunked(photo)
        }

        // 3. END_UPSERT
        try await sendCommand(["command": "END_UPSERT"])
        _ = try await waitForResponse()
    }

    private func sendPhotoChunked(_ photoData: Data, chunkSize: Int = 512) async throws {
        let totalChunks = (photoData.count + chunkSize - 1) / chunkSize
        let photoHash = photoData.sha256()

        for i in 0..<totalChunks {
            let start = i * chunkSize
            let end = min(start + chunkSize, photoData.count)
            let chunk = photoData[start..<end]

            let command: [String: Any] = [
                "command": "PHOTO_CHUNK",
                "chunk_index": i,
                "total_chunks": totalChunks,
                "data": chunk.base64EncodedString(),
                "is_last": i == totalChunks - 1,
                "sha256": i == totalChunks - 1 ? photoHash : nil
            ].compactMapValues { $0 }

            try await sendCommand(command)
            _ = try await waitForResponse()
        }
    }

    private func sendCommand(_ command: [String: Any]) async throws {
        let jsonData = try JSONSerialization.data(withJSONObject: command)
        peripheral?.writeValue(jsonData, for: commandCharacteristic!, type: .withResponse)
    }

    // ... BLE delegate methods
}
```

## Error Handling

### Error Types

| Error Message | Cause | Solution |
|---------------|-------|----------|
| "Admin mode not enabled" | Admin mode is disabled | Enable admin mode or use GPIO button |
| "HMAC verification failed" | Invalid signature or old nonce | Check shared secret and nonce freshness |
| "No active session" | PHOTO_CHUNK without BEGIN_UPSERT | Send BEGIN_UPSERT first |
| "Photo hash mismatch" | Data corruption or wrong hash | Resend photo |
| "Photo size exceeds limit" | Photo too large | Compress photo (max 5MB) |
| "No valid embeddings" | Poor photo quality | Use better quality photos |
| "Employee not found" | Invalid employee_id | Check employee exists |

### Best Practices

1. **Photo Quality**:
   - Resolution: 640x480 or higher
   - Format: JPEG
   - Face size: At least 80x80 pixels
   - Good lighting
   - Single face per photo
   - Different angles (3-5 photos)

2. **Network**:
   - Handle BLE disconnections
   - Implement retry logic
   - Show progress to user
   - Validate response types

3. **Security**:
   - Never log shared secret
   - Generate fresh nonce per command
   - Verify response authenticity
   - Use secure storage for secret

4. **UX**:
   - Show photo capture guidelines
   - Display registration progress
   - Handle errors gracefully
   - Provide feedback on success/failure

## Testing

### Test with Simulator

```bash
python tools/ble_client_simulator.py \
  --action register \
  --employee-id TEST001 \
  --display-name "Test User" \
  --access-start "2025-01-01T00:00:00Z" \
  --access-end "2026-12-31T23:59:59Z" \
  --photos photo1.jpg photo2.jpg photo3.jpg \
  --shared-secret "your_secret_here"
```

### Mock Responses

For UI testing without hardware:

```javascript
// Mock BLE responses
const mockResponses = {
    BEGIN_UPSERT: { type: "OK", message: "Session started" },
    PHOTO_CHUNK: { type: "PROGRESS", progress: 50 },
    END_UPSERT: { type: "OK", message: "Registered with 3 embeddings" }
};
```

## Rate Limits

- Max photo size: 5 MB
- Max photos per registration: 5
- Max registration duration: 5 minutes (session timeout)
- Command rate: Unlimited (controlled by admin mode)

## Versioning

Current API version: 1.0

The API follows semantic versioning. Breaking changes will increment the major version.

## Support

For API issues or questions:
- Check response error messages
- Review this documentation
- Test with BLE simulator
- Check Raspberry Pi logs: `face_access.log`

---

**Document Version**: 1.0
**Last Updated**: 2025-01-22
