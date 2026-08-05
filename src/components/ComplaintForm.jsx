import { useMemo } from 'react';
import { useSelector } from 'react-redux';

const fieldOptions = {
  severity: ['Critical', 'Major', 'Minor'],
  priority: ['High', 'Medium', 'Low'],
};

function ComplaintForm() {
  const selected = useSelector((state) => state.complaints.selected);
  const aiState = useSelector((state) => state.aiCopilot);

  const statusClass = useMemo(() => {
    const status = (selected.status || 'Pending Triage').toLowerCase();
    if (status.includes('triage')) return 'status-badge pending';
    if (status.includes('review')) return 'status-badge review';
    return 'status-badge resolved';
  }, [selected.status]);

  const renderInput = ({ label, field, type = 'text', placeholder, options }) => {
    const value = selected[field] ?? '';
    const commonProps = {
      value,
      readOnly: true,
      placeholder: placeholder || 'Awaiting AI extraction...',
    };

    return (
      <label className="field">
        <span className="field-label">{label}</span>
        {options ? (
          <select {...commonProps}>
            <option value="">Select</option>
            {options.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        ) : type === 'textarea' ? (
          <textarea {...commonProps} rows="4" />
        ) : type === 'date' ? (
          <input type="date" {...commonProps} />
        ) : (
          <input type={type} {...commonProps} />
        )}
      </label>
    );
  };

  return (
    <section className="panel panel-form">
      <div className="panel-header">
        <div>
          <h2>Log Customer Complaint</h2>
          <p>API &amp; FDF Quality Assurance Module</p>
        </div>
        <span className={statusClass}>{selected.status || 'Pending Triage'}</span>
      </div>

      <div className="section-block">
        <h3>1. ORIGIN &amp; CUSTOMER DETAILS</h3>
        <div className="grid two-columns">
          {renderInput({ label: 'Complaint Source', field: 'source' })}
          {renderInput({ label: 'Customer Name', field: 'customerName' })}
        </div>
      </div>

      <div className="section-block">
        <h3>2. PRODUCT &amp; BATCH IDENTIFICATION</h3>
        <div className="grid two-columns">
          {renderInput({ label: 'Product Name', field: 'productName' })}
          {renderInput({ label: 'Product Strength/Grade', field: 'productStrength' })}
          {renderInput({ label: 'Batch/Lot Number', field: 'batchNumber' })}
          {renderInput({ label: 'Manufacturing Date', field: 'manufacturingDate', type: 'date' })}
          {renderInput({ label: 'Expiry Date', field: 'expiryDate', type: 'date' })}
          {renderInput({ label: 'Quantity Affected', field: 'quantityAffected' })}
        </div>
      </div>

      <div className="section-block">
        <h3>3. COMPLAINT CATEGORY &amp; DESCRIPTION</h3>
        <div className="grid two-columns">
          {renderInput({ label: 'Complaint Category', field: 'complaintType' })}
          {renderInput({ label: 'Complaint Date', field: 'complaintDate', type: 'date' })}
        </div>
        {renderInput({ label: 'Complaint Description', field: 'description', type: 'textarea' })}

        <div className="ai-risk-card" role="group" aria-label="AI copilot risk assessment" style={{ marginTop: 12 }}>
          <div className="ai-risk-header">
            <div className="ai-risk-title">AI copilot risk assessment</div>
          </div>
          <div className="ai-risk-grid">
            <div className="ai-risk-field">
              <div className="ai-field-label">Severity (Suggested)</div>
              <div className="ai-field-value" aria-readonly="true">{aiState.severity || selected.severity || 'Awaiting AI extraction...'}</div>
            </div>
            <div className="ai-risk-field">
              <div className="ai-field-label">Suggested Next Action</div>
              <div className="ai-field-value" aria-readonly="true">{aiState.nextAction || selected.nextAction || 'Awaiting AI extraction...'}</div>
            </div>
            <div className="ai-risk-full">
              <div className="ai-field-label">Initial Risk Assessment</div>
              <div className="ai-field-value ai-multiline" aria-readonly="true">{aiState.summary || selected.riskSummary || aiState.statusText || 'Awaiting AI extraction...'}</div>
            </div>
          </div>
        </div>

        <div className="ai-insights-card" role="group" aria-label="AI complaint insights">
          <div className="ai-insights-title">AI complaint insights</div>
          <div className="ai-insights-grid">
            <div className="ai-insight-item ai-insight-wide">
              <span>Complaint Summary</span>
              <p>{selected.complaintSummary || 'Awaiting AI extraction...'}</p>
            </div>
            <div className="ai-insight-item">
              <span>Completeness</span>
              <p>{selected.completenessScore != null ? `${Math.round(selected.completenessScore)}% complete` : 'Awaiting AI extraction...'}</p>
            </div>
            <div className="ai-insight-item">
              <span>Missing Information</span>
              <p>{selected.completenessMissing || 'None identified'}</p>
            </div>
            <div className="ai-insight-item ai-insight-wide">
              <span>Root Cause Recommendation</span>
              <p>{selected.rootCauseRecommendation || 'Awaiting AI extraction...'}</p>
            </div>
            <div className="ai-insight-item ai-insight-wide">
              <span>CAPA Recommendation</span>
              <p>{selected.capaSuggestion || 'Awaiting AI extraction...'}</p>
            </div>
            <div className={`ai-insight-item ai-insight-wide ${selected.duplicateComplaint ? 'duplicate-warning' : ''}`}>
              <span>Duplicate Complaint Detection</span>
              <p>{selected.duplicateComplaint ? selected.duplicateReason : 'No similar complaint found.'}</p>
            </div>
          </div>
        </div>
      </div>

      <div className="form-actions compact-actions">
        <span className="ai-summary">AI-generated complaint record</span>
        <button type="button" className="primary-btn">
          <span className="save-icon">⧉</span> Save Complaint
        </button>
      </div>
    </section>
  );
}

export default ComplaintForm;
