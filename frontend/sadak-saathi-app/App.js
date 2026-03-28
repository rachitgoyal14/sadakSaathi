import { CameraView, useCameraPermissions } from "expo-camera";
import * as Location from "expo-location";
import { Accelerometer } from "expo-sensors";
import { useRef, useState, useCallback } from "react";
import { View } from "react-native";
import { WebView } from "react-native-webview";

const API_URL = "http://172.20.10.2:8000/api/v1";
const DETECTION_INTERVAL = 2000; // 2 seconds

export default function App() {
  const webRef = useRef(null);

  const [permission, requestPermission] = useCameraPermissions();
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraReady, setCameraReady] = useState(false);
  const cameraRef = useRef(null);
  const cameraReadyRef = useRef(false);

  const locationSubscription = useRef(null);
  const accelSubscription = useRef(null);
  const detectionIntervalRef = useRef(null);
  
  const currentLocation = useRef({ latitude: 0, longitude: 0, speed: 0, accuracy: 0, altitude: 0, heading: 0 });
  const accelReadings = useRef([]);
  const riderId = useRef(null);
  const authToken = useRef(null);

  const setRiderInfo = useCallback((rider, token) => {
    riderId.current = rider.id;
    authToken.current = token;
    console.log("✅ Rider info set:", riderId.current);
  }, []);

  const sendDetection = useCallback(async () => {
    const rid = riderId.current;
    const token = authToken.current;
    
    console.log("🔍 Detection check - Rider:", rid, "Token exists:", !!token, "Camera ready:", cameraReadyRef.current);
    
    if (!rid || !token) {
      console.log("❌ No rider ID or token, skipping detection");
      return;
    }

    if (!cameraRef.current || !cameraReadyRef.current) {
      console.log("❌ Camera not ready yet");
      return;
    }

    const lat = currentLocation.current.latitude;
    const lon = currentLocation.current.longitude;
    const rawSpeed = currentLocation.current.speed;
    
    // Guard: Skip if we don't have valid location data
    if (!lat || !lon || lat === 0 || lon === 0) {
      console.log("❌ Invalid location, skipping detection:", { lat, lon });
      return;
    }
    
    // Guard: Ensure speed is valid (>= 0)
    let speed = 0;
    if (rawSpeed !== null && rawSpeed !== undefined && rawSpeed >= 0) {
      speed = rawSpeed;
    }
    const speedKmh = speed * 3.6;

    console.log("📍 Valid location:", { lat, lon, speed, speedKmh });

    try {
      console.log("📸 Taking picture for detection...");
      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.5,
        base64: true,
        skipProcessing: true,
      });

      if (!photo?.base64) return;
      const accuracy = currentLocation.current.accuracy || 10;
      
      console.log("📤 Sending:", { lat, lon, speedKmh, accuracy });
      
      const formData = new FormData();
      formData.append('rider_id', rid);
      formData.append('latitude', lat.toString());
      formData.append('longitude', lon.toString());
      formData.append('speed_kmh', speedKmh.toString());
      formData.append('frame_timestamp_ms', Date.now().toString());
      formData.append('accuracy_meters', accuracy.toString());
      if (currentLocation.current.altitude) {
        formData.append('altitude_meters', currentLocation.current.altitude.toString());
      }
      if (currentLocation.current.heading) {
        formData.append('heading_degrees', currentLocation.current.heading.toString());
      }
      
      if (accelReadings.current.length > 0) {
        formData.append('sensor_readings_json', JSON.stringify(accelReadings.current.slice(-10)));
        accelReadings.current = [];
      }

      formData.append('image', {
        uri: photo.uri,
        type: 'image/jpeg',
        name: 'frame.jpg',
      });

      const token = authToken.current;
      console.log("📡 Sending detection request to:", `${API_URL}/detect/mobile`);
      
      const response = await fetch(`${API_URL}/detect/mobile`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
        body: formData,
      });

      console.log("📊 Response status:", response.status);
      const result = await response.json();
      
      console.log("🔍 Detection result:", result);
      
      if (result.status === 'not_detected') {
        webRef.current?.postMessage(JSON.stringify({
          type: "DETECTION_RESULT",
          data: { detected: false, message: result.message }
        }));
      } else if (result.pothole_id) {
        webRef.current?.postMessage(JSON.stringify({
          type: "DETECTION_RESULT",
          data: { 
            detected: true, 
            potholeId: result.pothole_id,
            status: result.status,
            severity: result.severity,
            message: result.message 
          }
        }));
      }
    } catch (error) {
      console.error("❌ Detection error:", error);
    }
  }, [cameraReady]);

  const startLocationTracking = async () => {
    const { status } = await Location.requestForegroundPermissionsAsync();

    if (status !== "granted") {
      console.log("❌ Location permission denied");
      return;
    }

    locationSubscription.current = await Location.watchPositionAsync(
      {
        accuracy: Location.Accuracy.High,
        timeInterval: 1000,
        distanceInterval: 1,
      },
      (loc) => {
        const coords = loc.coords;
        const validSpeed = (coords.speed && coords.speed > 0) ? coords.speed : 0;
        currentLocation.current = {
          latitude: coords.latitude,
          longitude: coords.longitude,
          speed: validSpeed,
          accuracy: coords.accuracy || 10,
          altitude: coords.altitude || 0,
          heading: coords.heading || 0,
        };

        const rawSpeed = coords.speed;
        let speed = 0;
        if (rawSpeed && rawSpeed > 0.5) {
          speed = rawSpeed;
        }
        const speedKmh = (speed * 3.6).toFixed(2);

        console.log("🚗 SPEED:", speedKmh, "km/h");

        webRef.current?.postMessage(
          JSON.stringify({
            type: "LOCATION",
            data: {
              latitude: coords.latitude,
              longitude: coords.longitude,
              speed,
              speedKmh,
            },
          }),
        );
      },
    );
  };

  const stopLocationTracking = () => {
    locationSubscription.current?.remove();
    locationSubscription.current = null;
  };

  const startAccelerometer = () => {
    Accelerometer.setUpdateInterval(100);

    accelSubscription.current = Accelerometer.addListener((data) => {
      accelReadings.current.push({
        x: data.x,
        y: data.y,
        z: data.z,
        timestamp_ms: Date.now(),
      });
      
      if (accelReadings.current.length > 50) {
        accelReadings.current = accelReadings.current.slice(-50);
      }

      webRef.current?.postMessage(
        JSON.stringify({
          type: "ACCEL",
          data,
        }),
      );
    });
  };

  const stopAccelerometer = () => {
    accelSubscription.current?.remove();
    accelSubscription.current = null;
  };

  const startDetection = () => {
    if (detectionIntervalRef.current) {
      clearInterval(detectionIntervalRef.current);
    }
    detectionIntervalRef.current = setInterval(sendDetection, DETECTION_INTERVAL);
  };

  const stopDetection = () => {
    if (detectionIntervalRef.current) {
      clearInterval(detectionIntervalRef.current);
      detectionIntervalRef.current = null;
    }
  };

  const handleMessage = async (event) => {
    try {
      const msg = JSON.parse(event.nativeEvent.data);
      console.log("📩 Received message:", msg.type);

      if (msg.type === "SET_RIDER_INFO") {
        setRiderInfo(msg.rider, msg.token);
      }

      if (msg.type === "GET_LOCATION") {
        startLocationTracking();
      }

      if (msg.type === "START_CAMERA") {
        console.log("🚀 Starting camera and detection...");
        
        if (!permission?.granted) {
          const res = await requestPermission();
          if (!res.granted) {
            console.log("❌ Camera permission denied");
            return;
          }
        }

        setCameraReady(false);
        setCameraActive(true);
        startLocationTracking();
        startAccelerometer();
        
        const checkAndStart = () => {
          if (cameraReadyRef.current) {
            console.log("⏰ Camera ready, starting detection interval");
            startDetection();
          } else {
            console.log("⏳ Waiting for camera... checking again in 500ms");
            setTimeout(checkAndStart, 500);
          }
        };
        
        setTimeout(checkAndStart, 1000);

        webRef.current?.postMessage(JSON.stringify({ type: "CAMERA_STARTED" }));
      }

      if (msg.type === "STOP_CAMERA") {
        setCameraActive(false);
        stopLocationTracking();
        stopAccelerometer();
        stopDetection();
        webRef.current?.postMessage(JSON.stringify({ type: "CAMERA_STOPPED" }));
      }
    } catch (e) {
      console.log("Invalid message:", e);
    }
  };

  return (
    <View style={{ flex: 1 }}>
      <WebView
        ref={webRef}
        source={{ uri: "http://172.20.10.2:3000/" }}
        onMessage={handleMessage}
      />

      {cameraActive && (
        <CameraView
          ref={cameraRef}
          style={{
            position: "absolute",
            width: 1,
            height: 1,
            opacity: 0,
          }}
          facing="back"
          onCameraReady={() => {
            console.log("📷 Camera is ready!");
            setCameraReady(true);
            cameraReadyRef.current = true;
          }}
        />
      )}
    </View>
  );
}
