import { createSlice } from '@reduxjs/toolkit';

const initialState = {
  progress: 0,
  statusText: 'Waiting for a complaint document or pasted text.',
  chatMessages: [
    {
      id: 1,
      role: 'assistant',
      text: 'Upload a complaint document or paste text above. I will automatically extract the details and populate the form for you.',
    },
  ],
};

const aiCopilotSlice = createSlice({
  name: 'aiCopilot',
  initialState,
  reducers: {
    setProgress: (state, action) => {
      state.progress = action.payload.progress;
      state.statusText = action.payload.statusText || state.statusText;
    },
    resetProgress: (state) => {
      state.progress = 0;
      state.statusText = 'Waiting for a complaint document or pasted text.';
    },
    appendMessage: (state, action) => {
      state.chatMessages.push(action.payload);
    },
    appendAssistantReply: (state, action) => {
      state.chatMessages.push({ id: Date.now(), role: 'assistant', text: action.payload });
    },
  },
});

export const { setProgress, resetProgress, appendMessage, appendAssistantReply } = aiCopilotSlice.actions;
export default aiCopilotSlice.reducer;
