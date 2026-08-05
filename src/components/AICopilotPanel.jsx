import { useEffect, useMemo, useRef, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { FlaskConical, Paperclip, Send } from 'lucide-react';
import { processComplaintMessage } from '../features/complaints/complaintsSlice';
import { appendAssistantReply, appendMessage, resetProgress, setProgress } from '../features/aiCopilot/aiCopilotSlice';
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

function AICopilotPanel() {
  const dispatch = useDispatch();
  const aiState = useSelector((state) => state.aiCopilot);
  const fileInputRef = useRef(null);
  const [isDragging, setIsDragging] = useState(false);
  const [chatInput, setChatInput] = useState('');
  const [progressMessage, setProgressMessage] = useState('');

  const progressPercent = useMemo(() => Math.round(aiState.progress), [aiState.progress]);

  const simulateProgress = (statusText) => {
    setProgressMessage(`${statusText} ${Math.max(10, progressPercent)}%`);
    dispatch(setProgress({ progress: 10, statusText }));
    setTimeout(() => {
      dispatch(setProgress({ progress: 30, statusText: 'Preparing the intake payload...' }));
      setProgressMessage('Preparing the intake payload... 30%');
    }, 450);
    setTimeout(() => {
      dispatch(setProgress({ progress: 60, statusText: 'Analyzing document content and extracting key details...' }));
      setProgressMessage('Analyzing document content and extracting key details... 60%');
    }, 900);
    setTimeout(() => {
      dispatch(setProgress({ progress: 90, statusText: 'Finalizing extraction and populating the form...' }));
      setProgressMessage('Finalizing extraction and populating the form... 90%');
    }, 1400);
  };

  const handleFileSelection = (file) => {
    if (!file) return;
    simulateProgress('Uploading complaint document and preparing AI analysis...');
    dispatch(appendMessage({ id: Date.now(), role: 'user', text: `Uploaded ${file.name}` }));
    dispatch(processComplaintMessage({ message: `Uploaded file: ${file.name}`, source: 'Portal', forceNew: true }))
      .unwrap()
      .then(() => {
        dispatch(setProgress({ progress: 100, statusText: 'Extraction complete. The form has been populated with the latest details.' }));
        setProgressMessage('Extraction complete. The form has been populated with the latest details.');
        dispatch(appendAssistantReply('The complaint details have been extracted and applied to the form.'));
      })
      .catch(() => {
        dispatch(resetProgress());
        setProgressMessage('');
        dispatch(appendAssistantReply('The upload could not be processed. Please try again or paste the complaint text instead.'));
      });
  };

  const sendMessage = () => {
    if (!chatInput.trim()) return;
    simulateProgress('Processing your message...');
    dispatch(appendMessage({ id: Date.now(), role: 'user', text: chatInput }));
    dispatch(processComplaintMessage({ message: chatInput, source: 'Email' }))
      .unwrap()
      .then((result) => {
        dispatch(setProgress({ progress: 100, statusText: 'Extraction complete. The form has been populated with the latest details.' }));
        setProgressMessage('Extraction complete. The form has been populated with the latest details.');
        if (result?.intent === 'update_complaint') {
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
      })
      .catch(() => {
        dispatch(resetProgress());
        setProgressMessage('');
        dispatch(appendAssistantReply('The message could not be processed. Please try again.'));
      });
    setChatInput('');
  };

  useEffect(() => {
    if (!aiState.chatMessages.length) {
      dispatch(appendAssistantReply('Ready to process new complaints. You can paste the raw email from the customer, or upload a PDF of the complaint report. I will extract the data and run the initial risk assessment.'));
    }
  }, [aiState.chatMessages.length, dispatch]);

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
        <div className="helper-box">Supported formats: PDF, DOCX, TXT, EML — Max file size: 10MB</div>
      </div>

      <div className="copilot-progress-card">
        <div className="copilot-progress-header">
          <span>EXTRACTION PROGRESS</span>
          <strong>{progressPercent}%</strong>
        </div>
        <div className="copilot-progress-bar">
          <div className="copilot-progress-fill" style={{ width: `${progressPercent}%` }} />
        </div>
        <p>{aiState.statusText || progressMessage || 'Waiting for analysis...'}</p>
      </div>

      <div
        className={`copilot-chat-area ${isDragging ? 'dragging' : ''}`}
        onDragOver={(event) => { event.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(event) => { event.preventDefault(); setIsDragging(false); handleFileSelection(event.dataTransfer.files[0]); }}
      >
        <div className="message-list">
          {aiState.chatMessages.map((message) => (
            <ChatBubble key={message.id} message={message} isAssistant={message.role === 'assistant'} />
          ))}
        </div>
      </div>

      <div className="copilot-input-wrap">
        <div className="copilot-input-row">
          <button type="button" className="clip-btn" onClick={() => fileInputRef.current?.click()} aria-label="Upload file">
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
          <button type="button" className="send-btn" onClick={sendMessage} aria-label="Send message">
            <Send size={16} />
          </button>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          hidden
          accept=".pdf,.docx,.txt,.eml"
          onChange={(event) => handleFileSelection(event.target.files?.[0])}
        />
        <div className="copilot-footer">POWERED BY LANGGRAPH</div>
      </div>
    </section>
  );
}

export default AICopilotPanel;