import { useState, useCallback, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import { SearchIcon, XIcon } from '../utils/icons';
import DashboardLayout from '../components/DashboardLayout';
import { hazardsApi, HazardItem } from '../services/api';

delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
});

const severityColors: Record<string, string> = {
  S1: '#ef4444',
  S2: '#f97316',
  S3: '#eab308',
};

const statusIcons: Record<string, string> = {
  CANDIDATE: '🔵',
  CONFIRMED: '🔴',
  REPAIRED: '🟢',
  FRAUD: '⚫',
};

const ShieldIconLocal = ({ className }: { className?: string }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
  </svg>
);

const ZapIconLocal = ({ className }: { className?: string }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
  </svg>
);

interface MapPageProps {
  onStopDriving?: (score: number) => void;
}

export default function MapPage({ onStopDriving }: MapPageProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedRoute, setSelectedRoute] = useState<'direct' | 'safe' | null>('safe');
  const [isDriving, setIsDriving] = useState(false);
  const [showCameraPopup, setShowCameraPopup] = useState(false);
  const [detectionAlert, setDetectionAlert] = useState<{ detected: boolean; message: string; severity?: string } | null>(null);
  const [potholes, setPotholes] = useState<HazardItem[]>([]);
  const [mapCenter, setMapCenter] = useState<[number, number]>([28.6139, 77.209]);
  const [isLoading, setIsLoading] = useState(true);

  const fetchPotholes = useCallback(async () => {
    try {
      const data = await hazardsApi.getHazards({ limit: 100 });
      setPotholes(data);
      if (data.length > 0) {
        const avgLat = data.reduce((sum, p) => sum + p.latitude, 0) / data.length;
        const avgLon = data.reduce((sum, p) => sum + p.longitude, 0) / data.length;
        setMapCenter([avgLat, avgLon]);
      }
    } catch (error) {
      console.error('Failed to fetch potholes:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPotholes();
    const interval = setInterval(() => {
      fetchPotholes();
    }, 3000);
    return () => clearInterval(interval);
  }, [fetchPotholes]);

  useEffect(() => {
    const handler = (event: any) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "DETECTION_RESULT" && msg.data.status === "CONFIRMED") {
          fetchPotholes();
        }
      } catch (e) {}
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, [fetchPotholes]);

  const handleAllowCamera = useCallback(() => {
    const riderStr = localStorage.getItem('rider');
    const token = localStorage.getItem('access_token');
    
    if ((window as any).ReactNativeWebView && riderStr && token) {
      const rider = JSON.parse(riderStr);
      (window as any).ReactNativeWebView.postMessage(
        JSON.stringify({ 
          type: "SET_RIDER_INFO",
          rider: rider,
          token: token
        })
      );
      
      setTimeout(() => {
        (window as any).ReactNativeWebView.postMessage(
          JSON.stringify({ type: "START_CAMERA" })
        );
      }, 500);
    } else {
      if ((window as any).ReactNativeWebView) {
        (window as any).ReactNativeWebView.postMessage(
          JSON.stringify({ type: "START_CAMERA" })
        );
      }
    }
    setShowCameraPopup(false);
    setIsDriving(true);
  }, []);

  const handleDenyCamera = useCallback(() => {
    setShowCameraPopup(false);
    setIsDriving(true);
  }, []);

  const handleStopClick = useCallback(() => {
    let score = 0;
    if (selectedRoute === 'safe') {
      score = 50;
    } else if (selectedRoute === 'direct') {
      score = 10;
    }
    setIsDriving(false);
    if (score > 0 && onStopDriving) {
      onStopDriving(score);
    }
  }, [selectedRoute, onStopDriving]);

  useEffect(() => {
    const handler = (event: any) => {
      try {
        const msg = JSON.parse(event.data);
        console.log("📲 Message from native:", msg);

        if (msg.type === "CAMERA_STARTED") {
          console.log("📸 Camera started - location & sensors tracking");
        }
        if (msg.type === "CAMERA_STOPPED") {
          console.log("🛑 Camera stopped - all sensors stopped");
        }
        if (msg.type === "CAMERA_DONE") {
          console.log("📸 Camera finished");
        }
        if (msg.type === "LOCATION") {
          const { latitude, longitude, speed } = msg.data;
          const speedKmh = speed ? (speed * 3.6).toFixed(2) : "0";
          console.log(`📍 Location: [${latitude.toFixed(4)}, ${longitude.toFixed(4)}] | Speed: ${speedKmh} km/h`);
        }
        if (msg.type === "ACCEL") {
          const { x, y, z } = msg.data;
          console.log(`⚡ Acceleration: x=${x.toFixed(2)}, y=${y.toFixed(2)}, z=${z.toFixed(2)} m/s²`);
          const harshBraking = x > 0.5;
          const harshAccel = y > 0.5;
          if (harshBraking || harshAccel) {
            console.warn("⚠️ Harsh driving detected!");
          }
        }
        if (msg.type === "PERMISSION_ERROR") {
          console.error("❌ Permission error:", msg.data);
        }
        if (msg.type === "DETECTION_RESULT") {
          console.log("🔍 Detection result:", msg.data);
          const hasYoloDetection = msg.data.yolo_confidence && msg.data.yolo_confidence > 0.3;
          if (hasYoloDetection || (msg.data.status && msg.data.status !== 'not_detected')) {
            setDetectionAlert({
              detected: true,
              message: msg.data.message || `Pothole detected! Confidence: ${Math.round((msg.data.yolo_confidence || 0) * 100)}%`,
              severity: msg.data.severity,
            });
            setTimeout(() => setDetectionAlert(null), 5000);
          }
        }
        if (msg.type === "REFRESH_MAP") {
          console.log("🔄 Refreshing map from mobile app");
          fetchPotholes();
        }
      } catch (e) {
        console.log("Invalid message:", e);
      }
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, []);

  return (
    <DashboardLayout>
      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="flex flex-col w-full relative px-3 pt-2 pb-4"
      >
        {/* Search Bar */}
        <div className="w-full bg-white rounded-full h-[48px] flex items-center px-4 shadow-md border border-gray-200 mb-4 shrink-0">
          <SearchIcon className="w-5 h-5 text-gray-400" />
          <input 
            type="text" 
            placeholder="Enter destination..." 
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="flex-grow bg-transparent border-none focus:outline-none px-3 text-sm text-gray-700 placeholder-gray-400 font-medium" 
          />
          {searchQuery && (
            <button onClick={() => setSearchQuery('')} className="p-1">
              <XIcon className="w-4 h-4 text-gray-400" />
            </button>
          )}
        </div>

        {/* Map View with Leaflet */}
        <div className="w-full h-[280px] bg-gray-200 rounded-[24px] overflow-hidden shadow-sm shrink-0 relative">
          <MapContainer 
            center={mapCenter} 
            zoom={13} 
            style={{ height: '100%', width: '100%', borderRadius: '24px' }}
            scrollWheelZoom={false}
            key={potholes.length}
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            {potholes.map((pothole) => (
              <Marker 
                key={pothole.id} 
                position={[pothole.latitude, pothole.longitude]}
              >
                <Popup>
                  <div className="text-sm">
                    <div className="font-bold">Pothole Detected</div>
                    <div>Severity: <span style={{ color: severityColors[pothole.severity] }}>{pothole.severity}</span></div>
                    <div>Status: {statusIcons[pothole.status]} {pothole.status}</div>
                    <div>Reports: {pothole.report_count}</div>
                    <div>Days Unrepaired: {pothole.days_unrepaired}</div>
                  </div>
                </Popup>
              </Marker>
            ))}
          </MapContainer>
          {isLoading && (
            <div className="absolute inset-0 flex items-center justify-center bg-gray-200/50 rounded-[24px]">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-600"></div>
            </div>
          )}
          <button 
            onClick={fetchPotholes}
            className="absolute top-3 right-3 z-[400] bg-white/90 backdrop-blur-sm rounded-full p-2 shadow hover:bg-white transition-colors"
          >
            <svg className="w-4 h-4 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
          <div className="absolute bottom-3 left-3 z-[400] bg-white/90 backdrop-blur-sm rounded-lg px-2 py-1 text-xs font-medium shadow">
            {potholes.length} potholes detected
          </div>
        </div>

        {/* Route Cards */}
        <div className="mt-4 flex justify-between gap-[12px] shrink-0">
          {/* Direct Route Card */}
          <button 
            onClick={() => setSelectedRoute('direct')}
            className={`w-[48%] h-[100px] rounded-2xl p-[12px] flex flex-col justify-between transition-all border-2 ${
              selectedRoute === 'direct' ? 'border-[#cfec46] bg-[#cfec46]/10' : 'border-transparent bg-white shadow-sm'
            }`}
          >
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-full bg-orange-100 flex items-center justify-center">
                <ZapIconLocal className="w-5 h-5 text-orange-500" />
              </div>
              <span className="text-[18px] font-bold text-black">23 mins</span>
            </div>
            <div className="text-left">
              <span className="text-xs font-bold text-gray-500">Direct Route</span>
              <div className="text-xs font-bold text-red-500 mt-0.5">Risk: 82%</div>
            </div>
          </button>

          {/* Safe Route Card */}
          <button 
            onClick={() => setSelectedRoute('safe')}
            className={`w-[48%] h-[100px] rounded-2xl p-[12px] flex flex-col justify-between transition-all border-2 ${
              selectedRoute === 'safe' ? 'border-[#cfec46] bg-[#cfec46]/10' : 'border-transparent bg-white shadow-sm'
            }`}
          >
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-full bg-green-100 flex items-center justify-center">
                <ShieldIconLocal className="w-5 h-5 text-green-500" />
              </div>
              <span className="text-[18px] font-bold text-black">28 mins</span>
            </div>
            <div className="text-left">
              <span className="text-xs font-bold text-gray-500">Safe Route</span>
              <div className="text-xs font-bold text-green-500 mt-0.5">Risk: 12%</div>
            </div>
          </button>
        </div>

        {/* Start/Stop Button */}
        <div className="mt-6 shrink-0">
          {!isDriving ? (
            <button 
              onClick={() => setShowCameraPopup(true)}
              className="w-full py-4 rounded-full bg-[#cfec46] text-black font-bold text-base shadow-md hover:scale-[1.02] transition-transform"
            >
              Start
            </button>
          ) : (
            <button 
              onClick={handleStopClick}
              className="w-full py-4 rounded-full bg-red-500 text-white font-bold text-base shadow-md hover:scale-[1.02] transition-transform"
            >
              Stop
            </button>
          )}
        </div>

        {/* Extra Scroll Section */}
        <div className="mt-6 pb-4 flex flex-col gap-4">
          <div className="bg-white/50 rounded-2xl p-4 border border-gray-100">
            <h4 className="text-sm font-bold text-black mb-1">Safety Tip</h4>
            <p className="text-xs text-gray-500 font-medium leading-relaxed">
              Always keep your eyes on the road. Our AI will handle pothole detection in the background.
            </p>
          </div>
          <div className="bg-white/50 rounded-2xl p-4 border border-gray-100">
            <h4 className="text-sm font-bold text-black mb-1">Route Info</h4>
            <p className="text-xs text-gray-500 font-medium leading-relaxed">
              Safe routes are calculated based on real-time road condition data from other Saathis.
            </p>
          </div>
        </div>

        {/* Camera Permission Popup */}
        <AnimatePresence>
          {showCameraPopup && (
            <div className="absolute inset-0 z-[60] flex items-center justify-center px-4">
              <div className="absolute -inset-[1000px] bg-black/50 backdrop-blur-sm z-40" onClick={() => setShowCameraPopup(false)} />
              <motion.div
                initial={{ scale: 0.9, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0.9, opacity: 0 }}
                className="relative z-50 bg-white rounded-[24px] w-full max-w-[280px] overflow-hidden shadow-2xl p-6 flex flex-col items-center text-center"
              >
                <div className="w-16 h-16 bg-[#cfec46]/20 rounded-full flex items-center justify-center mb-4">
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-black">
                    <path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"></path>
                    <circle cx="12" cy="13" r="3"></circle>
                  </svg>
                </div>
                <h3 className="text-lg font-bold text-black mb-2">Camera Access</h3>
                <p className="text-sm text-gray-500 mb-4 font-medium">Allow Sadak Saathi to use your camera in the background to detect potholes while you drive?</p>

                <div className="flex w-full gap-3">
                  <button onClick={handleDenyCamera} className="flex-1 py-3 rounded-xl bg-gray-100 text-black font-bold text-sm hover:bg-gray-200 transition-colors">
                    No, thanks
                  </button>
                  <button onClick={handleAllowCamera} className="flex-1 py-3 rounded-xl bg-[#cfec46] text-black font-bold text-sm hover:bg-[#c4e03f] transition-colors">
                    Allow
                  </button>
                </div>
              </motion.div>
            </div>
          )}
        </AnimatePresence>

        {/* Pothole Detection Alert */}
        <AnimatePresence>
          {detectionAlert && detectionAlert.detected && (
            <motion.div
              initial={{ opacity: 0, y: -50 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -50 }}
              className="fixed top-4 left-4 right-4 z-[100]"
            >
              <div className="bg-red-500 text-white rounded-2xl p-4 shadow-lg flex items-center gap-3">
                <div className="w-10 h-10 bg-white/20 rounded-full flex items-center justify-center">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                    <line x1="12" y1="9" x2="12" y2="13"></line>
                    <line x1="12" y1="17" x2="12.01" y2="17"></line>
                  </svg>
                </div>
                <div className="flex-1">
                  <p className="font-bold text-sm">Pothole Detected!</p>
                  <p className="text-xs text-white/80">{detectionAlert.message}</p>
                </div>
                <button onClick={() => setDetectionAlert(null)} className="p-1">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                  </svg>
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </DashboardLayout>
  );
}
