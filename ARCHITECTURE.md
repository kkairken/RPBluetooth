# System Architecture

Technical architecture documentation for the Offline Face Access Control System.

## Overview

The system is designed as a modular, offline-capable face recognition access control solution for Raspberry Pi 3. All processing happens locally without any external API calls or internet dependency.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Application Layer                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   main.py    │  │    CLI       │  │   Logging    │      │
│  │  (Orchestr.) │  │  Interface   │  │              │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                      Service Layer                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ BLE Protocol │  │Access Control│  │ Lock Control │      │
│  │    Server    │  │   Service    │  │   Service    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                      Core Layer                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Face Engine  │  │   Database   │  │   Config     │      │
│  │ (Detection,  │  │   Manager    │  │   Loader     │      │
│  │  Embedding,  │  │              │  │              │      │
│  │  Matching)   │  │              │  │              │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                    Hardware Layer                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Camera       │  │  BLE Radio   │  │ GPIO Relay   │      │
│  │ (USB/RTSP)   │  │              │  │              │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

## Module Details

### 1. Camera Module (`src/camera/`)

**Purpose**: Abstract camera input sources

**Components**:
- `base.py`: Abstract base class defining camera interface
- `usb_camera.py`: USB/UVC camera implementation using OpenCV
- `rtsp_camera.py`: RTSP IP camera implementation

**Key Features**:
- Unified interface for different camera types
- Automatic reconnection for RTSP
- Configurable resolution and FPS
- Thread-safe frame reading

**Data Flow**:
```
Hardware Camera → VideoCapture → read_frame() → BGR numpy array → Face Engine
```

### 2. Face Recognition Module (`src/face/`)

**Purpose**: Face detection, alignment, embedding, and matching

#### 2.1 Detector (`detector.py`)

**Algorithms Supported**:
- OpenCV Haar Cascade (default, fastest)
- MediaPipe Face Detection (optional, more accurate)
- None (use full frame as face region)

**Output**: List of bounding boxes `[(x, y, w, h), ...]`

#### 2.2 Aligner (`align.py`)

**Purpose**: Crop and resize faces for embedding model

**Process**:
1. Extract face region with margin
2. Resize to 112x112 (standard for InsightFace)
3. Handle edge cases (face near frame boundary)

**Output**: Aligned face image (112x112 BGR)

#### 2.3 Embedder (`embedder_onnx.py`)

**Purpose**: Generate face embeddings using ONNX model

**Process**:
1. Preprocess: BGR→RGB, normalize to [-1, 1], CHW format
2. ONNX inference with CPU provider
3. L2 normalization of output vector
4. Return 512-dim embedding (model-dependent)

**Performance**: ~200-500ms per face on Raspberry Pi 3

**Model Requirements**:
- Input: [1, 3, 112, 112] float32
- Output: [1, 512] float32 (or other embedding dim)
- Format: ONNX

#### 2.4 Matcher (`matcher.py`)

**Purpose**: Compare embeddings using cosine similarity

**Algorithm**:
```python
similarity = dot(embedding1, embedding2) / (norm(embedding1) * norm(embedding2))
```

**Threshold**: Configurable (default 0.6)
- Higher threshold: More secure, higher false rejection
- Lower threshold: More convenient, higher false acceptance

**Matching Process**:
1. Compare query embedding with all stored embeddings
2. Find maximum similarity score
3. Return match if score > threshold

#### 2.5 Quality Checker (`quality.py`)

**Purpose**: Validate registration photo quality

**Checks**:
1. **Single Face**: Exactly one face detected
2. **Face Size**: Minimum dimensions (default 80x80)
3. **Blur Detection**: Laplacian variance > threshold
4. **Alignment**: Face not too close to edges
5. **Aspect Ratio**: Reasonable face proportions

### 3. Database Module (`src/db.py`)

**Technology**: SQLite with sqlite3

**Schema**:

```sql
-- Employees
CREATE TABLE employees (
    employee_id TEXT PRIMARY KEY,
    display_name TEXT,
    access_start TEXT NOT NULL,
    access_end TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Face Embeddings (multiple per employee)
CREATE TABLE embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id TEXT NOT NULL,
    embedding BLOB NOT NULL,  -- numpy array as bytes
    photo_hash TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE
);

-- Audit Log
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    employee_id TEXT,
    matched_employee_id TEXT,
    similarity_score REAL,
    result TEXT NOT NULL,
    reason TEXT,
    metadata TEXT  -- JSON
);
```

**Operations**:
- CRUD for employees
- Embedding storage (numpy → bytes)
- Audit logging
- Efficient queries with indexes

### 4. Access Control Module (`src/access_control.py`)

**Purpose**: Validate access rights and enforce policies

**Checks**:
1. **Employee Active**: `is_active = 1`
2. **Time Period**: `access_start <= now <= access_end`
3. **Recognition Score**: `similarity >= threshold`
4. **Rate Limiting**: Max attempts per minute
5. **Cooldown**: Time between attempts

**Rate Limiting Algorithm**:
- Track timestamps of recent attempts
- Sliding window (1 minute)
- Per-employee and global limits

### 5. Lock Control Module (`src/lock.py`)

**Purpose**: Control door lock via GPIO relay

**Hardware Interface**:
- GPIO pin (BCM numbering)
- Active high/low configurable
- Mock mode for testing

**Operation**:
1. `unlock()`: Set GPIO HIGH (or LOW if active-low)
2. Wait for configured duration (default 3s)
3. Set GPIO LOW (lock)

**Safety**:
- Always lock on shutdown
- GPIO cleanup
- Error handling

### 6. BLE Server Module (`src/ble_server.py`)

**Purpose**: GATT server for employee registration via mobile app

#### 6.1 Protocol Handler

**Commands**:
- `BEGIN_UPSERT`: Start registration session
- `PHOTO_CHUNK`: Send photo data in chunks
- `END_UPSERT`: Complete registration
- `UPDATE_PERIOD`: Update access period
- `DEACTIVATE`: Deactivate employee
- `GET_STATUS`: Query system status

**Photo Chunking**:
1. Mobile app splits photo into 512-byte chunks
2. Each chunk sent via BLE characteristic
3. Raspberry Pi reassembles and verifies SHA256
4. Process multiple photos per employee

#### 6.2 Security (HMAC)

**Authentication Flow**:
```
1. Mobile app generates nonce: timestamp + random
2. Mobile app computes HMAC-SHA256(command + nonce, shared_secret)
3. Send {command, nonce, hmac}
4. Raspberry Pi verifies:
   - Nonce freshness (±5 min)
   - Nonce uniqueness (no replay)
   - HMAC signature
```

**Nonce Format**: `{unix_timestamp}_{random_hex}`

**HMAC Computation**:
```python
message = json.dumps(command, sort_keys=True).encode('utf-8')
signature = hmac.new(shared_secret, message, hashlib.sha256).hexdigest()
```

### 7. Configuration Module (`src/config.py`)

**Format**: YAML

**Dataclasses**:
- Type-safe configuration
- Validation on load
- Default values

**Loading**:
```python
config = load_config('config/my_config.yaml')
# Returns SystemConfig with nested dataclasses
```

## Data Flow

### Registration Flow

```
Mobile App
    │
    ├─> BEGIN_UPSERT (employee_id, access_start, access_end, num_photos)
    │       │
    │       v
    │   BLEProtocol: Create session
    │
    ├─> PHOTO_CHUNK (chunk_index, data, is_last, sha256?)
    │       │ (repeat for all chunks of all photos)
    │       v
    │   BLEProtocol: Reassemble photo
    │
    ├─> END_UPSERT
    │       │
    │       v
    │   Process photos:
    │       ├─> Decode JPEG
    │       ├─> Detect face
    │       ├─> Validate quality
    │       ├─> Align face
    │       └─> Compute embedding
    │
    │   Database:
    │       ├─> Upsert employee
    │       ├─> Delete old embeddings
    │       └─> Add new embeddings
    │
    └─> Response (OK/ERROR)
```

### Recognition Flow

```
Camera
    │
    v
Read frame (BGR image)
    │
    v
Face Detector: Detect faces → [(x,y,w,h), ...]
    │
    v
Select largest face
    │
    v
Face Aligner: Crop and resize → (112x112)
    │
    v
Embedder (ONNX): Compute embedding → [512-dim vector]
    │
    v
Database: Load active employees + embeddings
    │
    v
Matcher: Find best match → (employee_id, score)
    │
    v
Access Controller: Validate
    ├─> Check if active
    ├─> Check time period
    ├─> Check similarity threshold
    ├─> Check rate limit
    └─> Decision: GRANT/DENY
    │
    v
If GRANT:
    ├─> Lock Controller: Unlock for N seconds
    └─> Log: audit_log (granted, employee_id, score)

If DENY:
    └─> Log: audit_log (denied, reason, score)
```

## Performance Characteristics

### Raspberry Pi 3 (BCM2837, 1.2 GHz quad-core ARM Cortex-A53)

**Face Detection**:
- OpenCV Haar: 50-100ms per frame (640x480)
- MediaPipe: 100-200ms per frame

**Face Alignment**: 5-10ms

**Embedding (ONNX)**:
- InsightFace Medium: 200-500ms per face
- CPU inference only (no GPU)

**Matching**:
- 10 employees: <1ms
- 100 employees: 5-10ms
- 1000 employees: 50-100ms

**Total Pipeline**: 1-3 FPS with full processing

**Optimization Strategies**:
1. Frame skipping (process every Nth frame)
2. Lower camera resolution
3. Smaller/faster face detector
4. Lighter ONNX model
5. Reduce active employee count

## Scalability

**Employees**: 100-500 recommended
- Linear search through embeddings
- In-memory during matching
- SQLite handles thousands easily

**Embeddings per Employee**: 1-5 recommended
- More embeddings = better accuracy
- More embeddings = slower matching

**Storage**:
- Employee record: ~200 bytes
- Embedding: ~2 KB (512 float32)
- Audit log: ~500 bytes per entry
- 100 employees × 3 embeddings = ~600 KB
- 10,000 audit logs = ~5 MB

**Database**: SQLite easily handles this scale

## Security Model

### Threat Model

**In Scope**:
- Unauthorized registration via BLE
- Registration photo manipulation
- Replay attacks
- Access period bypass

**Out of Scope** (physical security assumed):
- Physical device tampering
- SD card theft
- Network attacks (system is offline)
- Camera feed manipulation

### Security Measures

1. **HMAC Authentication**: Prevents unauthorized BLE commands
2. **Nonce System**: Prevents replay attacks
3. **Photo Hash Verification**: Ensures photo integrity
4. **Admin Mode**: Restricts registration capability
5. **Audit Logging**: Forensic trail
6. **Offline Operation**: No network attack surface

### Limitations

- No face liveness detection (photos can be spoofed)
- No anti-spoofing (printed photos, screens)
- Shared secret must be distributed securely
- Physical access to device = full compromise

## Future Enhancements

### Potential Improvements

1. **Face Liveness Detection**
   - Blink detection
   - Head movement
   - Depth sensing (if camera supports)

2. **Real BLE Implementation**
   - Replace mock with bleak/bluezero
   - Full GATT server
   - Secure pairing

3. **Multi-Camera Support**
   - Multiple entry points
   - Synchronized recognition

4. **Remote Monitoring** (optional)
   - Encrypted logs upload
   - Status dashboard
   - Alert system

5. **Performance**
   - Model quantization (int8)
   - Neural compute stick support
   - Async processing

6. **UI**
   - LED indicators
   - LCD display
   - Buzzer feedback

## Testing Strategy

### Unit Tests

- Database CRUD operations
- Access control logic
- HMAC authentication
- Protocol chunking
- Rate limiting

### Integration Tests

- End-to-end registration
- Recognition pipeline
- BLE protocol flow

### Hardware Tests

- Camera capture
- GPIO control
- Different lighting
- Various face angles

### Performance Tests

- FPS benchmarking
- Memory profiling
- Stress testing (many employees)

## Deployment Considerations

### Hardware

- **Temperature**: Add heatsink or fan
- **Power**: Use quality 2.5A+ supply
- **Camera**: Position at eye level, 0.5-1m distance
- **Relay**: Use optocoupler for isolation
- **SD Card**: Use high-endurance card

### Software

- **Autostart**: Use systemd service
- **Logging**: Rotate logs (logrotate)
- **Backup**: Regular DB backups
- **Updates**: Test on dev device first

### Maintenance

- Monitor logs for errors
- Check disk space
- Verify camera functionality
- Test lock mechanism
- Review audit logs

## Compliance

### Privacy Considerations

- Store only embeddings (not photos)
- Implement data retention policy
- Provide employee deletion capability
- Log access to audit trail
- Comply with local regulations (GDPR, CCPA, etc.)

### Data Protection

- Encrypt SD card (optional)
- Secure physical access
- Regular backups
- Access control to database

---

**Document Version**: 1.0
**Last Updated**: 2025-01-22
