import { CameraView, useCameraPermissions } from "expo-camera";
import * as Location from "expo-location";
import { Accelerometer } from "expo-sensors";
import { useRef, useState } from "react";
import { View } from "react-native";
import { WebView } from "react-native-webview";

export default function App() {
  const webRef = useRef(null);

  const [permission, requestPermission] = useCameraPermissions();
  const [cameraActive, setCameraActive] = useState(false);

  // ✅ FIXED: useRef (no reset issue)
  const locationSubscription = useRef(null);
  const accelSubscription = useRef(null);

  // 📍 START LOCATION (WITH SPEED FILTER)
  const startLocationTracking = async () => {
    const { status } = await Location.requestForegroundPermissionsAsync();

    if (status !== "granted") {
      console.log("❌ Location permission denied");
      return;
    }

    locationSubscription.current = await Location.watchPositionAsync(
      {
        accuracy: Location.Accuracy.High,
        timeInterval: 2000,
        distanceInterval: 1,
      },
      (loc) => {
        const coords = loc.coords;

        // 🔥 SPEED FILTER (IMPORTANT)
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

  // 🛑 STOP LOCATION
  const stopLocationTracking = () => {
    locationSubscription.current?.remove();
    locationSubscription.current = null;
  };

  // 📡 START ACCELEROMETER
  const startAccelerometer = () => {
    Accelerometer.setUpdateInterval(500);

    accelSubscription.current = Accelerometer.addListener((data) => {
      console.log("⚡ ACCEL:", data);

      webRef.current?.postMessage(
        JSON.stringify({
          type: "ACCEL",
          data,
        }),
      );
    });
  };

  // 🛑 STOP ACCELEROMETER
  const stopAccelerometer = () => {
    accelSubscription.current?.remove();
    accelSubscription.current = null;
  };

  // 📩 HANDLE MESSAGES FROM WEBVIEW
  const handleMessage = async (event) => {
    try {
      const msg = JSON.parse(event.nativeEvent.data);

      // 📍 START LOCATION ONLY
      if (msg.type === "GET_LOCATION") {
        startLocationTracking();
      }

      // 🚀 START EVERYTHING (from START button)
      if (msg.type === "START_CAMERA") {
        if (!permission?.granted) {
          const res = await requestPermission();
          if (!res.granted) return;
        }

        setCameraActive(true);

        // 🔥 START ALL SENSORS
        startLocationTracking();
        startAccelerometer();

        webRef.current?.postMessage(JSON.stringify({ type: "CAMERA_STARTED" }));
      }

      // 🛑 STOP EVERYTHING
      if (msg.type === "STOP_CAMERA") {
        setCameraActive(false);

        stopLocationTracking();
        stopAccelerometer();

        webRef.current?.postMessage(JSON.stringify({ type: "CAMERA_STOPPED" }));
      }
    } catch (e) {
      console.log("Invalid message");
    }
  };

  return (
    <View style={{ flex: 1 }}>
      {/* 🌐 WEBVIEW */}
      <WebView
        ref={webRef}
        source={{ uri: "http://192.168.31.44:3000/" }}
        onMessage={handleMessage}
      />

      {/* 📸 HIDDEN CAMERA */}
      {cameraActive && (
        <CameraView
          style={{
            position: "absolute",
            width: 1,
            height: 1,
            opacity: 0,
          }}
        />
      )}
    </View>
  );
}
