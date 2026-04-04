import { useAuth } from "./hooks/useAuth";
import { useChat } from "./hooks/useChat";
import { useHealth } from "./hooks/useHealth";
import ChatWindow from "./components/ChatWindow";
import Header from "./components/Header";
import LoginPage from "./pages/LoginPage";

function LoadingSpinner() {
  return (
    <div className="flex h-full items-center justify-center bg-surface">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand border-t-transparent" />
    </div>
  );
}

export default function App() {
  const { user, isAuthenticated, isLoading: authLoading, requestOtp, verifyOtp, logout } = useAuth();
  const { messages, isLoading, sendMessage, clearChat, selectClarification } = useChat();
  const health = useHealth();

  if (authLoading) {
    return <LoadingSpinner />;
  }

  if (!isAuthenticated) {
    return (
      <LoginPage
        onRequestOtp={requestOtp}
        onVerifyOtp={verifyOtp}
      />
    );
  }

  return (
    <div className="flex h-full flex-col">
      <Header health={health} onNewChat={clearChat} user={user} onLogout={logout} />
      <ChatWindow
        messages={messages}
        isLoading={isLoading}
        onSendMessage={sendMessage}
        onSelectClarification={selectClarification}
        health={health}
      />
    </div>
  );
}
