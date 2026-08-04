import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import client from '../../api/client';
import { setProgress as setAiProgress } from '../aiCopilot/aiCopilotSlice';

const initialState = {
  selected: {
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
  },
  loading: false,
  error: null,
};

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
      // ensure progress reaches 100% on successful analysis
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
      state.selected = { ...initialState.selected };
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
      .addCase(analyzeComplaint.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(analyzeComplaint.fulfilled, (state, action) => {
        state.loading = false;
        state.selected = {
          ...state.selected,
          ...action.payload.payload,
          status: action.payload.analysis?.status || 'Pending Triage',
          description: action.payload.analysis?.description || action.payload.payload.description || state.selected.description,
          customerName: action.payload.analysis?.customerName || action.payload.payload.customerName || state.selected.customerName,
          productName: action.payload.analysis?.productName || action.payload.payload.productName || state.selected.productName,
          productStrength: action.payload.analysis?.productStrength || action.payload.payload.productStrength || state.selected.productStrength,
          batchNumber: action.payload.analysis?.batchNumber || action.payload.payload.batchNumber || state.selected.batchNumber,
          manufacturingDate: action.payload.analysis?.manufacturingDate || action.payload.payload.manufacturingDate || state.selected.manufacturingDate,
          expiryDate: action.payload.analysis?.expiryDate || action.payload.payload.expiryDate || state.selected.expiryDate,
          quantityAffected: action.payload.analysis?.quantityAffected || action.payload.payload.quantityAffected || state.selected.quantityAffected,
          complaintType: action.payload.analysis?.complaintType || action.payload.payload.complaintType || state.selected.complaintType,
          complaintDate: action.payload.analysis?.complaintDate || action.payload.payload.complaintDate || state.selected.complaintDate,
          severity: action.payload.analysis?.severity || action.payload.payload.severity || state.selected.severity,
          priority: action.payload.analysis?.priority || action.payload.payload.priority || state.selected.priority,
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
