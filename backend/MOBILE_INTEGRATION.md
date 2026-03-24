# Mobile App Integration Guide

## Overview

The Sadak Sathi mobile app should record video while the rider is riding, extract frames every 5 seconds, and send them to the backend for pothole detection.

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                        MOBILE APP                                 │
├─────────────────────────────────────────────────────────────────┤
│  1. User starts ride → Request permissions                      │
│     - Location (GPS)                                            │
│     - Sensors (Accelerometer)                                    │
│     - Camera                                                    │
│                                                                  │
│  2. Start video recording                                       │
│                                                                  │
│  3. Every 5 seconds:                                           │
│     ┌──────────────────────────────────────┐                    │
│     │ • Extract current frame               │                    │
│     │ • Get GPS location                    │                    │
│     │ • Get speed from GPS                 │                    │
│     │ • Collect accelerometer readings      │                    │
│     │   (last 1-2 seconds, ~50Hz)          │                    │
│     │ • Send to /api/v1/detect/mobile     │                    │
│     └──────────────────────────────────────┘                    │
│                                                                  │
│  4. Continue until ride ends                                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       BACKEND API                                 │
├─────────────────────────────────────────────────────────────────┤
│  POST /api/v1/detect/mobile                                     │
│                                                                  │
│  1. Receive frame + sensor data                                 │
│  2. Run YOLO inference on image                                │
│  3. Run LSTM inference on sensor window                         │
│  4. Fuse results                                                │
│  5. If pothole detected:                                        │
│     - Find/create pothole record                               │
│     - Update confirmation count                                 │
│     - If confirmed: trigger alerts                             │
│  6. Return result                                               │
└─────────────────────────────────────────────────────────────────┘
```

## Permissions Required

### iOS (Info.plist)
```xml
<key>NSLocationWhenInUseUsageDescription</key>
<string>Sadak Sathi needs your location to detect potholes and report their exact position.</string>
<key>NSLocationAlwaysAndWhenInUseUsageDescription</key>
<string>Sadak Sathi needs background location to continue detecting potholes while riding.</string>
<key>NSMotionUsageDescription</key>
<string>Sadak Sathi uses motion sensors to detect road bumps and potholes.</string>
<key>NSCameraUsageDescription</key>
<string>Sadak Sathi uses your camera to record the road and detect potholes.</string>
```

### Android (AndroidManifest.xml)
```xml
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
<uses-permission android:name="android.permission.ACCESS_BACKGROUND_LOCATION" />
<uses-permission android:name="android.permission.HIGH_SAMPLING_RATE_SENSORS" />
<uses-permission android:name="android.permission.CAMERA" />
<uses-permission android:name="android.permission.RECORD_AUDIO" />
```

## API Request Format

### Endpoint: `POST /api/v1/detect/mobile`

**Headers:**
```
Authorization: Bearer <rider_token>
Content-Type: multipart/form-data
```

**Form Data:**
1. `image` (file) - Video frame as JPEG/PNG (optional but recommended)
2. `payload` (JSON string) - Detection data

### Payload JSON Structure:

```json
{
  "rider_id": "uuid-of-rider",
  "location": {
    "latitude": 19.0760,
    "longitude": 72.8777,
    "accuracy_meters": 5.0,
    "altitude_meters": 10.5,
    "heading_degrees": 45.0,
    "timestamp_ms": 1712345678901
  },
  "speed_kmh": 35.5,
  "sensor_window": {
    "readings": [
      {"x": 0.1, "y": 0.2, "z": 9.8, "timestamp_ms": 1712345678901},
      {"x": 0.15, "y": 0.25, "z": 9.85, "timestamp_ms": 1712345678921},
      {"x": 0.12, "y": 0.22, "z": 9.82, "timestamp_ms": 1712345678941}
    ],
    "avg_speed_kmh": 35.5,
    "road_condition": "bumpy"
  },
  "device_info": {
    "device_id": "unique-device-id",
    "device_model": "iPhone 14 Pro",
    "os_version": "iOS 17.0",
    "app_version": "1.0.0",
    "camera_resolution": "1920x1080"
  },
  "ride_context": {
    "ride_id": "uuid-of-ride",
    "is_night_mode": false,
    "weather_condition": "clear",
    "road_type": "main_road"
  },
  "frame_timestamp_ms": 1712345678901,
  "video_segment_id": "uuid-of-segment"
}
```

## Mobile App Implementation (Pseudo-code)

### Flutter/Dart Example:

```dart
class PotholeDetectionService {
  Timer? _captureTimer;
  final List<AccelerometerEvent> _sensorReadings = [];
  
  void startRide(String riderId) {
    // Start video recording
    startVideoRecording();
    
    // Start capturing frames every 5 seconds
    _captureTimer = Timer.periodic(Duration(seconds: 5), (_) {
      _captureAndSend(riderId);
    });
  }
  
  Future<void> _captureAndSend(String riderId) async {
    // 1. Extract frame from video
    final frameBytes = await extractFrame();
    if (frameBytes == null) return;
    
    // 2. Get location
    final position = await getCurrentPosition();
    
    // 3. Get speed
    final speed = await getSpeed(); // From GPS
    
    // 4. Collect sensor readings (last 1-2 seconds)
    final readings = _sensorReadings.toList();
    _sensorReadings.clear();
    
    // 5. Build payload
    final payload = {
      'rider_id': riderId,
      'location': {
        'latitude': position.latitude,
        'longitude': position.longitude,
        'accuracy_meters': position.accuracy,
        'heading_degrees': position.heading,
        'timestamp_ms': DateTime.now().millisecondsSinceEpoch,
      },
      'speed_kmh': speed,
      'sensor_window': {
        'readings': readings.map((r) => {
          'x': r.x,
          'y': r.y,
          'z': r.z,
          'timestamp_ms': r.timestamp.millisecondsSinceEpoch,
        }).toList(),
        'avg_speed_kmh': speed,
      },
      'frame_timestamp_ms': DateTime.now().millisecondsSinceEpoch,
    };
    
    // 6. Send to backend
    await sendToBackend(frameBytes, payload);
  }
  
  void stopRide() {
    _captureTimer?.cancel();
    stopVideoRecording();
  }
}
```

### React Native / Expo Example:

```typescript
import * as Location from 'expo-location';
import { Accelerometer } from 'expo-sensors';
import * as FileSystem from 'expo-file-system';

const DETECTION_INTERVAL = 5000; // 5 seconds

async function startRide() {
  // Request permissions
  const { status: locationStatus } = await Location.requestForegroundPermissionsAsync();
  const { status: sensorStatus } = await Accelerometer.requestPermissionsAsync();
  
  // Start sensor collection
  Accelerometer.setUpdateInterval(20); // ~50Hz
  
  // Start location tracking
  const locationSubscription = await Location.watchPositionAsync(
    { accuracy: Location.Accuracy.High },
    (location) => { /* store location */ }
  );
  
  // Start frame capture interval
  const intervalId = setInterval(async () => {
    const frame = await captureFrame(); // From camera
    const location = await getCurrentLocation();
    const speed = await getCurrentSpeed();
    const readings = getRecentSensorReadings();
    
    const payload = {
      rider_id: currentRider.id,
      location: {
        latitude: location.latitude,
        longitude: location.longitude,
        accuracy_meters: location.accuracy,
        timestamp_ms: Date.now(),
      },
      speed_kmh: speed,
      sensor_window: {
        readings: readings,
        avg_speed_kmh: speed,
      },
      frame_timestamp_ms: Date.now(),
    };
    
    await uploadFrame(frame, payload);
  }, DETECTION_INTERVAL);
}
```

## Response Format

### Success Response:
```json
{
  "pothole_id": "uuid-of-pothole",
  "status": "confirmed",  // candidate | confirmed | rejected | not_detected
  "report_count": 5,
  "severity": "S2",
  "message": "Pothole confirmed! Alerts dispatched to nearby riders.",
  "yolo_confidence": 0.87,
  "lstm_severity": "S2",
  "fused_confidence": 0.92
}
```

### Not Detected Response:
```json
{
  "pothole_id": "",
  "status": "not_detected",
  "report_count": 0,
  "severity": "S1",
  "message": "No pothole detected by ML models.",
  "yolo_confidence": 0.15,
  "lstm_severity": null,
  "fused_confidence": 0.1
}
```

## Best Practices

1. **Frame Extraction**: Extract frames at 5-second intervals from the video stream
2. **Sensor Collection**: Collect ~50-100 accelerometer readings (1-2 seconds at 50Hz)
3. **Location**: Use high-accuracy GPS mode
4. **Compression**: Compress images to ~100-200KB before upload
5. **Offline Support**: Cache frames locally if no network, upload when connected
6. **Battery**: Use efficient camera settings to conserve battery
7. **Night Mode**: Detect if driving at night and include in ride_context

## Error Handling

- **Network Error**: Cache locally and retry with exponential backoff
- **GPS Unavailable**: Use last known location, mark accuracy as poor
- **Sensor Unavailable**: Send detection with camera only (detection_method: "camera")
- **Large Frame**: Compress or resize before upload
