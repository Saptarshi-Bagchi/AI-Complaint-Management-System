import { useEffect, useRef, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { FlaskConical, Paperclip, Send } from 'lucide-react';
import { processComplaintFile, processComplaintMessage } from '../features/complaints/complaintsSlice';
import { appendAssistantReply, appendMessage, removeMessage, resetProgress, setProcessing, setProgress } from '../features/aiCopilot/aiCopilotSlice';
import ChatBubble from './ChatBubble';

const FIELD_LABELS = {
  source: 'Source',
  customerName: 'Customer name',
  productName: 'Product name',
  productStrength: 'Product strength',
  batchNumber: 'Batch number',
  manufacturingDate: 'Manufacturing date',
  expiryDate: 'Expiry date',
  quantityAffected: 'Quantity affected',
  complaintType: 'Complaint type',
  complaintDate: 'Complaint date',
  description: 'Description',
  severity: 'Severity',
  priority: 'Priority',
  status: 'Status',
};

const ACCEPTED_EXTENSIONS = ['.pdf', '.txt'];
const MAX_FILE_SIZE = 10 * 1024 * 1024;

function AICopilotPanel() {
  const dispatch = useDispatch();
  const aiState = useSelector((state) => state.aiCopilot);
  const isProcessing = useSelector((state) => state.aiCopilot.isProcessing);
  const fileInputRef = useRef(null);
  const messageListRef = useRef(null);
  const progressTimeoutsRef = useRef([]);
  const [isDragging, setIsDragging] = useState(false);
  const [chatInput, setChatInput] = useState('');
  const progressPercent = Math.round(aiState.progress);

  useEffect(() => {
    if (messageListRef.current) {
      messageListRef.current.scrollTop = messageListRef.current.scrollHeight;
    }
  }, [aiState.chatMessages]);

  const simulateProgress = (statusText) => {
    dispatch(setProgress({ progress: 10, statusText }));
    progressTimeoutsRef.current = [
      setTimeout(() => {
      dispatch(setProgress({ progress: 30, statusText: 'Preparing the intake payload...' }));
      }, 450),
      setTimeout(() => {
      dispatch(setProgress({ progress: 60, statusText: 'Analyzing document content and extracting key details...' }));
      }, 900),
      setTimeout(() => {
      dispatch(setProgress({ progress: 90, statusText: 'Finalizing extraction and populating the form...' }));
      }, 1400),
    ];
  };

  const clearProgressSimulation = () => {
    progressTimeoutsRef.current.forEach(clearTimeout);
    progressTimeoutsRef.current = [];
  };

  const handleResult = (result) => {
    clearProgressSimulation();
    dispatch(setProgress({ progress: 100, statusText: 'Extraction complete. The form has been populated with the latest details.' }));
    if (result?.intent === 'out_of_scope' || result?.intent === 'complaint_question') {
      dispatch(appendAssistantReply(result.response));
    } else if (result?.intent === 'update_complaint') {
      const patch = result.patch || {};
      const updatedFields = Object.keys(patch);
      if (updatedFields.length > 0) {
        const updates = updatedFields.map((key) => `${FIELD_LABELS[key] || key} updated to ${patch[key]}.`);
        dispatch(appendAssistantReply(updates.join(' ')));
      } else {
        dispatch(appendAssistantReply('No specific fields were identified to update.'));
      }
    } else {
      dispatch(appendAssistantReply('The complaint text was analyzed and populated into the form.'));
    }
  };

  const handleError = (message) => {
    clearProgressSimulation();
    dispatch(resetProgress());
    dispatch(appendAssistantReply(message));
  };

  const sendMessage = () => {
    if (!chatInput.trim() || isProcessing) return;
    dispatch(setProcessing(true));
    simulateProgress('Processing your message...');
    dispatch(appendMessage({ id: Date.now(), role: 'user', text: chatInput }));
    dispatch(processComplaintMessage({ message: chatInput, source: 'Email' }))
      .unwrap()
      .then((result) => handleResult(result))
      .catch(() => handleError('The message could not be processed. Please try again.'))
      .finally(() => dispatch(setProcessing(false)));
    setChatInput('');
  };

  const validateFile = (file) => {
    if (!file) return 'No file was selected.';
    const lowerName = (file.name || '').toLowerCase();
    const isValidType = ACCEPTED_EXTENSIONS.some((ext) => lowerName.endsWith(ext));
    if (!isValidType) return 'Unsupported file type. Only PDF and TXT files are supported.';
    if (file.size === 0) return 'The selected file is empty.';
    if (file.size > MAX_FILE_SIZE) return 'File is too large. Maximum size is 10MB.';
    return null;
  };

  const handleFileSelection = (file) => {
    if (isProcessing) return;
    const error = validateFile(file);
    if (error) {
      dispatch(appendAssistantReply(error));
      return;
    }

    dispatch(setProcessing(true));
    simulateProgress('Uploading complaint document and preparing AI analysis...');
    dispatch(appendMessage({ id: Date.now(), role: 'user', text: `Uploaded ${file.name}` }));
    const processingMessageId = Date.now() + 1;
    dispatch(appendMessage({ id: processingMessageId, role: 'processing', text: 'Processing document...' }));

    dispatch(processComplaintFile({ file, source: 'Portal' }))
      .unwrap()
      .then((result) => handleResult(result))
      .catch((err) => handleError(err || 'The upload could not be processed. Please try again or paste the complaint text instead.'))
      .finally(() => {
        dispatch(removeMessage(processingMessageId));
        dispatch(setProcessing(false));
      });
  };

  return (
    <section className="panel panel-ai">
      <div className="copilot-header">
        <div className="copilot-title-row">
          <div className="copilot-icon-wrap">
            <FlaskConical size={20} />
          </div>
          <div>
            <div className="copilot-title">AIVOA Copilot</div>
            <div className="copilot-subtitle">Drop complaint files or paste text below.</div>
          </div>
        </div>
        <span className="copilot-status-dot" />
      </div>
      <div className="copilot-divider" />

      <div className="upload-zone" onDrop={(e) => { e.preventDefault(); handleFileSelection(e.dataTransfer.files[0]); }} onDragOver={(e) => e.preventDefault()}>
        <div className="upload-instruction">Drag & drop complaint document here<br />or <span className="browse-link" onClick={() => fileInputRef.current?.click()}>click to browse</span></div>
        <div className="paste-box" style={{ marginTop: 12 }}>
          <button className="textarea-toggle" type="button" onClick={() => document.getElementById('copilot-paste')?.focus()}>Paste Complaint Text / Email</button>
          <textarea id="copilot-paste" placeholder="Paste complaint text or email here..." value={chatInput} onChange={(e) => setChatInput(e.target.value)} style={{ marginTop: 8 }} />
        </div>
        <div className="helper-box">Supported formats: PDF, TXT — Max file size: 10MB</div>
      </div>

      <div className="copilot-progress-card">
        <div className="copilot-progress-header">
          <span>EXTRACTION PROGRESS</span>
          <strong>{progressPercent}%</strong>
        </div>
        <div className="copilot-progress-bar">
          <div className="copilot-progress-fill" style={{ width: `${progressPercent}%` }} />
        </div>
        <p>{aiState.statusText}</p>
      </div>

      <div
        className={`copilot-chat-area ${isDragging ? 'dragging' : ''}`}
        onDragOver={(event) => { event.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(event) => { event.preventDefault(); setIsDragging(false); handleFileSelection(event.dataTransfer.files[0]); }}
      >
        <div className="message-list" ref={messageListRef}>
          {aiState.chatMessages.map((message) => (
            <ChatBubble key={message.id} message={message} isAssistant={message.role === 'assistant'} />
          ))}
        </div>
      </div>

      <div className="copilot-input-wrap">
        <div className="copilot-input-row">
          <button type="button" className="clip-btn" onClick={() => fileInputRef.current?.click()} aria-label="Upload file" disabled={isProcessing}>
            <Paperclip size={16} />
          </button>
          <input
            type="text"
            value={chatInput}
            onChange={(event) => setChatInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                sendMessage();
              }
            }}
            placeholder="Type a message or paste a complaint..."
          />
          <button type="button" className="send-btn" onClick={sendMessage} aria-label="Send message" disabled={isProcessing}>
            <Send size={16} />
          </button>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          hidden
          accept=".pdf,.txt"
          onChange={(event) => handleFileSelection(event.target.files?.[0])}
        />
        <div className="copilot-footer">POWERED BY LANGGRAPH</div>
      </div>
    </section>
  );
}

export default AICopilotPanel;
