import { Zap } from 'lucide-react';

function ChatBubble({ message, isAssistant }) {
  if (isAssistant) {
    return (
      <div className="chat-row assistant-row">
        <div className="chat-avatar assistant-avatar">
          <Zap size={16} />
        </div>
        <div className="chat-card-bubble">
          <p>{message.text}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-row user-row">
      <div className="chat-card-bubble user-bubble">
        <p>{message.text}</p>
      </div>
    </div>
  );
}

export default ChatBubble;
