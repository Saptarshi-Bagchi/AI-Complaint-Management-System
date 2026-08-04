import { useSelector } from 'react-redux';
import ComplaintForm from './components/ComplaintForm';
import AICopilotPanel from './components/AICopilotPanel';

function App() {
  const selectedComplaint = useSelector((state) => state.complaints.selected);

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">Pharmaceutical Quality Assurance</p>
          <h1>Customer Complaint Management</h1>
        </div>
        <div className="status-pill">{selectedComplaint.status || 'Pending Triage'}</div>
      </header>

      <main className="workspace-grid">
        <ComplaintForm />
        <AICopilotPanel />
      </main>
    </div>
  );
}

export default App;
