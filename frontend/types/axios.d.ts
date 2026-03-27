import 'axios';

declare module 'axios' {
  interface InternalAxiosRequestConfig {
    metadata?: { startTime: number };
    _retry?: boolean;
  }
}
