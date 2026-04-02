import { useChat } from "./hooks/useChat";
import { useHealth } from "./hooks/useHealth";
import ChatWindow from "./components/ChatWindow";
import Header from "./components/Header";

export default function App() {
  const { messages, isLoading, sendMessage, clearChat } = useChat();
  const health = useHealth();

  return (
    <div className="flex h-full flex-col">
      <Header health={health} onNewChat={clearChat} />
      <ChatWindow
        messages={messages}
        isLoading={isLoading}
        onSendMessage={sendMessage}
      />
    </div>
  );
}
