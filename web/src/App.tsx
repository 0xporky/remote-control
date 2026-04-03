import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { GoogleOAuthProvider } from '@react-oauth/google';
import { LoginForm } from './components/LoginForm';
import { RemoteDesktop } from './components/RemoteDesktop';
import { AgentSelector } from './components/AgentSelector';
import { StatusBar } from './components/StatusBar';
import { useSignaling } from './hooks/useSignaling';
import { useWebRTC } from './hooks/useWebRTC';
import { useConnectionStats } from './hooks/useConnectionStats';
import { isAuthenticated, logout } from './services/auth';
import './styles/index.css';

function DesktopView() {
  const navigate = useNavigate();
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);

  const {
    isConnected: signalingConnected,
    agents,
    clientId,
    service: signaling,
    connect: connectSignaling,
    disconnect: disconnectSignaling,
    refreshAgents,
  } = useSignaling();

  const {
    stream,
    connectionState,
    isDataChannelOpen,
    peerConnection,
    reconnectAttempts,
    connect: connectWebRTC,
    disconnect: disconnectWebRTC,
    sendInput,
  } = useWebRTC(signaling);

  // Collect connection stats when connected
  const stats = useConnectionStats(
    peerConnection,
    connectionState === 'connected'
  );

  useEffect(() => {
    if (isAuthenticated()) {
      connectSignaling();
    }
    return () => {
      disconnectSignaling();
    };
  }, [connectSignaling, disconnectSignaling]);

  const handleConnect = () => {
    if (selectedAgent) {
      connectWebRTC(selectedAgent);
    }
  };

  const handleLogout = () => {
    disconnectWebRTC();
    disconnectSignaling();
    logout();
    navigate('/login');
  };

  return (
    <div className="desktop-view">
      <StatusBar
        signalingConnected={signalingConnected}
        webrtcState={connectionState}
        clientId={clientId}
        stats={connectionState === 'connected' ? stats : null}
        onLogout={handleLogout}
      />

      <div className="main-content">
        <div className="controls">
          <AgentSelector
            agents={agents}
            selectedAgent={selectedAgent}
            onSelect={setSelectedAgent}
            onRefresh={refreshAgents}
            disabled={connectionState === 'connecting' || connectionState === 'connected'}
          />
        </div>

        <RemoteDesktop
          stream={stream}
          connectionState={connectionState}
          onConnect={handleConnect}
          onDisconnect={disconnectWebRTC}
          isConnected={signalingConnected && !!selectedAgent}
          isDataChannelOpen={isDataChannelOpen}
          onInput={sendInput}
          reconnectAttempts={reconnectAttempts}
        />
      </div>
    </div>
  );
}

function LoginPage() {
  const navigate = useNavigate();

  const handleLoginSuccess = () => {
    navigate('/desktop');
  };

  if (isAuthenticated()) {
    return <Navigate to="/desktop" replace />;
  }

  return <LoginForm onSuccess={handleLoginSuccess} />;
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

function App() {
  const content = (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/desktop"
          element={
            <ProtectedRoute>
              <DesktopView />
            </ProtectedRoute>
          }
        />
        <Route path="/" element={<Navigate to="/desktop" replace />} />
      </Routes>
    </BrowserRouter>
  );

  // Wrap with Google OAuth provider if configured
  if (GOOGLE_CLIENT_ID) {
    return (
      <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>
        {content}
      </GoogleOAuthProvider>
    );
  }

  return content;
}

export default App;
