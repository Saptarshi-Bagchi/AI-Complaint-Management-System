import { Loader2, Zap } from 'lucide-react';

function ChatBubble({ message, isAssistant }) {
  if (message.role === 'processing') {
    return (
      <div className="chat-row assistant-row">
        <div className="chat-avatar assistant-avatar">
          <Loader2 size={16} className="spin" />
        </div>
        <div className="chat-card-bubble processing-bubble">
          <p>{message.text}</p>
          <div className="processing-bar" />
        </div>
      </div>
    );
  }

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