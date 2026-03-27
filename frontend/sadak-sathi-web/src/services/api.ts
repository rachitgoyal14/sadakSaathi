const API_URL = 'http://10.191.82.154:8000/api/v1';

export interface RiderData {
  name: string;
  phone: string;
  email?: string;
  password: string;
  platform?: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  rider: {
    id: string;
    name: string;
    phone: string;
    email?: string;
    platform?: string;
    total_reports: number;
    accuracy_score: number;
  };
}

export interface ApiError {
  detail: string;
}

class ApiService {
  private getHeaders(): HeadersInit {
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    };
    const token = localStorage.getItem('access_token');
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
  }

  async register(riderData: RiderData): Promise<TokenResponse> {
    const response = await fetch(`${API_URL}/auth/register`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify(riderData),
    });

    if (!response.ok) {
      const error: ApiError = await response.json();
      throw new Error(error.detail || 'Registration failed');
    }

    return response.json();
  }

  async login(phone: string, password: string): Promise<TokenResponse> {
    const response = await fetch(`${API_URL}/auth/login`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ phone, password }),
    });

    if (!response.ok) {
      const error: ApiError = await response.json();
      throw new Error(error.detail || 'Login failed');
    }

    return response.json();
  }

  async getCurrentUser(): Promise<TokenResponse['rider']> {
    const response = await fetch(`${API_URL}/auth/me`, {
      method: 'GET',
      headers: this.getHeaders(),
    });

    if (!response.ok) {
      const error: ApiError = await response.json();
      throw new Error(error.detail || 'Failed to get user');
    }

    return response.json();
  }

  saveToken(token: string): void {
    localStorage.setItem('access_token', token);
  }

  clearToken(): void {
    localStorage.removeItem('access_token');
  }

  getToken(): string | null {
    return localStorage.getItem('access_token');
  }

  async detectPothole(
    imageBase64: string,
    riderId: string,
    latitude: number,
    longitude: number,
    speedKmh: number,
    frameTimestampMs: number,
    accuracyMeters?: number,
    altitudeMeters?: number,
    headingDegrees?: number,
    videoSegmentId?: string,
    rideId?: string,
    isNightMode?: boolean,
    weatherCondition?: string,
    roadType?: string,
    sensorReadingsJson?: string
  ): Promise<DetectionResponse> {
    const formData = new FormData();
    formData.append('rider_id', riderId);
    formData.append('latitude', latitude.toString());
    formData.append('longitude', longitude.toString());
    formData.append('speed_kmh', speedKmh.toString());
    formData.append('frame_timestamp_ms', frameTimestampMs.toString());
    
    if (accuracyMeters) formData.append('accuracy_meters', accuracyMeters.toString());
    if (altitudeMeters) formData.append('altitude_meters', altitudeMeters.toString());
    if (headingDegrees) formData.append('heading_degrees', headingDegrees.toString());
    if (videoSegmentId) formData.append('video_segment_id', videoSegmentId);
    if (rideId) formData.append('ride_id', rideId);
    if (isNightMode) formData.append('is_night_mode', 'true');
    if (weatherCondition) formData.append('weather_condition', weatherCondition);
    if (roadType) formData.append('road_type', roadType);
    if (sensorReadingsJson) formData.append('sensor_readings_json', sensorReadingsJson);

    const blob = this.base64ToBlob(imageBase64);
    formData.append('image', blob, 'frame.jpg');

    const response = await fetch(`${API_URL}/detect/mobile`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.getToken()}`,
      },
      body: formData,
    });

    if (!response.ok) {
      const error: ApiError = await response.json();
      throw new Error(error.detail || 'Detection failed');
    }

    return response.json();
  }

  private base64ToBlob(base64: string): Blob {
    const byteCharacters = atob(base64);
    const byteNumbers = new Array(byteCharacters.length);
    for (let i = 0; i < byteCharacters.length; i++) {
      byteNumbers[i] = byteCharacters.charCodeAt(i);
    }
    const byteArray = new Uint8Array(byteNumbers);
    return new Blob([byteArray], { type: 'image/jpeg' });
  }
}

export interface DetectionResponse {
  pothole_id: string;
  status: string;
  report_count: number;
  severity: string;
  message: string;
  yolo_confidence?: number;
  lstm_severity?: string;
  fused_confidence?: number;
}

export const api = new ApiService();
