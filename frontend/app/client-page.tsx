'use client';
import dynamic from 'next/dynamic';

const LoadingFallback = () => (
  <div style={{
    minHeight: '100vh',
    background: '#0a0f1a',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  }}>
    <div style={{
      width: '48px',
      height: '48px',
      border: '3px solid #2563eb',
      borderTopColor: 'transparent',
      borderRadius: '50%',
      animation: 'spin 0.8s linear infinite',
    }} />
    <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
  </div>
);

const AppWithConfig = dynamic(() => import('@/App'), {
  ssr: false,
  loading: () => <LoadingFallback />,
});

export default function ClientPage() {
  return <AppWithConfig />;
}
