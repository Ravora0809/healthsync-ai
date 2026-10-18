import axios from 'axios';

// OCR and document summarization can take longer than a typical JSON request.
const api = axios.create({ baseURL: '/api', timeout: 150000 });
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('healthsync_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export function errorText(error) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg).join(', ');
  if (error?.code === 'ECONNABORTED') return 'The request took too long. For large scans, check backend logs and try a clearer/smaller image.';
  if (!error?.response) return 'Could not reach the backend. Make sure Docker Compose is running and try again.';
  return error?.message || 'Request failed';
}

export default api;
