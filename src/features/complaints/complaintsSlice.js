import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import client from '../../api/client';
import { setProgress as setAiProgress } from '../aiCopilot/aiCopilotSlice';

const emptySelected = {
  source: '',
  customerName: '',
  productName: '',
  productStrength: '',
  batchNumber: '',
  manufacturingDate: '',
  expiryDate: '',
  quantityAffected: '',
  complaintType: '',
  complaintDate: '',
  description: '',
  severity: '',
  priority: '',
  status: 'Pending Triage',
  riskScore: null,
  riskSummary: '',
  nextAction: '',
  capaSuggestion: '',
};

const initialState = {
  selected: { ...emptySelected },
  complaintId: null,
  loading: false,
  error: null,
};

/**
 * Unified AI copilot entry point.
 *
 * Sends the user's message together with the current in-memory complaint
 * object to the backend, which detects the intent (new complaint vs. update)
 * and returns either a full extraction or a field-level patch.
 *
 * `forceNew` should be true for file uploads / explicit "new complaint"
 * actions so the backend always runs the full extraction pipeline.
 */
export const processComplaintMessage = createAsyncThunk(
  'complaints/processComplaintMessage',
  async ({ message, source, forceNew = false }, { dispatch, getState, rejectWithValue }) => {
    try {
      dispatch(setAiProgress({ progress: 5, statusText: 'Detecting your intent...' }));

      const currentSelected = getState().complaints.selected;
      const currentComplaintId = getState().complaints.complaintId;

      const response = await client.post('/complaints/process-message', {
        message,
        source: source || 'manual',
        existing_complaint: { ...currentSelected, complaintId: currentComplaintId },
        force_new: forceNew,
      });

      dispatch(setAiProgress({ progress: 90, statusText: 'Finalizing extraction and populating the form...' }));
      dispatch(setAiProgress({ progress: 100, statusText: 'Extraction complete. The form has been populated with the latest details.' }));

      return response.data;
    } catch (error) {
      return rejectWithValue(error.response?.data || error.message || 'Processing failed');
    }
  }
);

/**
 * Legacy thunk retained for backward compatibility with file-upload flows
 * that still use the two-step ingest + analyze pipeline.
 */
export const analyzeComplaint = createAsyncThunk(
  'complaints/analyzeComplaint',
  async ({ payload, text }, { dispatch, rejectWithValue }) => {
    try {
      dispatch(setAiProgress({ progress: 5, statusText: 'Preparing the intake payload...' }));
      const ingestResponse = await client.post('/complaints/ingest', {
        source: payload.source || 'manual',
        complaint_text: text || payload.description || 'No text provided',
      });

      const complaintId = ingestResponse.data.id;
      dispatch(setAiProgress({ progress: 35, statusText: 'Submitting the complaint for AI analysis...' }));

      const analysisResponse = await client.post(`/complaints/${complaintId}/analyze`, {
        complaint_id: complaintId,
        complaint_text: text || payload.description || 'No text provided',
      });

      dispatch(setAiProgress({ progress: 90, statusText: 'Finalizing extraction and populating the form...' }));
      dispatch(setAiProgress({ progress: 100, statusText: 'Extraction complete. The form has been populated with the latest details.' }));
      return { complaintId, analysis: analysisResponse.data, payload };
    } catch (error) {
      return rejectWithValue(error.response?.data || error.message || 'Analysis failed');
    }
  }
);

const complaintsSlice = createSlice({
  name: 'complaints',
  initialState,
  reducers: {
    updateField: (state, action) => {
      const { field, value } = action.payload;
      state.selected[field] = value;
    },
    resetForm: (state) => {
      state.selected = { ...emptySelected };
      state.complaintId = null;
      state.error = null;
    },
    setProgress: (state, action) => {
      state.loading = action.payload < 100;
    },
    hydrateSelected: (state, action) => {
      state.selected = { ...state.selected, ...action.payload };
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(processComplaintMessage.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(processComplaintMessage.fulfilled, (state, action) => {
        state.loading = false;
        const { intent, complaintId, analysis, patch } = action.payload;

        if (intent === 'new_complaint') {
          // New complaint: replace the entire in-memory object.
          state.complaintId = complaintId ?? state.complaintId;
          state.selected = {
            ...emptySelected,
            ...analysis,
          };
        } else {
          // Update: merge ONLY the patch onto the existing object so that
          // every field the user did not mention is preserved exactly.
          state.complaintId = complaintId ?? state.complaintId;
          if (patch && Object.keys(patch).length > 0) {
            state.selected = { ...state.selected, ...patch };
          }
        }
      })
      .addCase(processComplaintMessage.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Unable to process message';
      })
      .addCase(analyzeComplaint.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(analyzeComplaint.fulfilled, (state, action) => {
        state.loading = false;
        const analysis = action.payload.analysis || {};
        state.complaintId = action.payload.complaintId;
        state.selected = {
          ...state.selected,
          ...action.payload.payload,
          status: analysis.status || state.selected.status,
          description: analysis.description ?? state.selected.description,
          customerName: analysis.customerName ?? state.selected.customerName,
          productName: analysis.productName ?? state.selected.productName,
          productStrength: analysis.productStrength ?? state.selected.productStrength,
          batchNumber: analysis.batchNumber ?? state.selected.batchNumber,
          manufacturingDate: analysis.manufacturingDate ?? state.selected.manufacturingDate,
          expiryDate: analysis.expiryDate ?? state.selected.expiryDate,
          quantityAffected: analysis.quantityAffected ?? state.selected.quantityAffected,
          complaintType: analysis.complaintType ?? state.selected.complaintType,
          complaintDate: analysis.complaintDate ?? state.selected.complaintDate,
          severity: analysis.severity ?? state.selected.severity,
          priority: analysis.priority ?? state.selected.priority,
          riskScore: analysis.riskScore ?? state.selected.riskScore,
          riskSummary: analysis.riskSummary ?? state.selected.riskSummary,
          nextAction: analysis.nextAction ?? state.selected.nextAction,
          capaSuggestion: analysis.capaSuggestion ?? state.selected.capaSuggestion,
        };
      })
      .addCase(analyzeComplaint.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || 'Unable to analyze complaint';
      });
  },
});

export const { updateField, resetForm, setProgress, hydrateSelected } = complaintsSlice.actions;
export default complaintsSlice.reducer;