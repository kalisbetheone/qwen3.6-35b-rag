import React from 'react';
import ReactDOM from 'react-dom/client';
// Font đóng gói cục bộ (không tải từ CDN) — nhất quán với nguyên tắc chạy nội bộ
import '@fontsource/be-vietnam-pro/400.css';
import '@fontsource/be-vietnam-pro/500.css';
import '@fontsource/be-vietnam-pro/600.css';
import '@fontsource/be-vietnam-pro/700.css';
import './index.css';
import App from './App';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
