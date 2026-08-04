import { configureStore } from '@reduxjs/toolkit';
import complaintsReducer from '../features/complaints/complaintsSlice';
import aiCopilotReducer from '../features/aiCopilot/aiCopilotSlice';

export const store = configureStore({
  reducer: {
    complaints: complaintsReducer,
    aiCopilot: aiCopilotReducer,
  },
});

export default store;
