import { useState, useEffect, useRef } from 'react';
import './App.css';

const API_BASE = 'http://localhost:8000';

function App() {
  const [view, setView] = useState('upload'); // 'upload' | 'progress' | 'results'
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  
  // Job & Progress states
  const [jobId, setJobId] = useState(null);
  const [progress, setProgress] = useState(0);
  const [step, setStep] = useState('');
  const [error, setError] = useState(null);
  
  // Results states
  const [clips, setClips] = useState([]);
  const [selectedClipIdx, setSelectedClipIdx] = useState(0);
  
  const eventSourceRef = useRef(null);
  const fileInputRef = useRef(null);

  // Clean up SSE connection on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  // Listen to SSE progress stream
  const startProgressStream = (id) => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const sseUrl = `${API_BASE}/status/stream/${id}`;
    const source = new EventSource(sseUrl);
    eventSourceRef.current = source;

    source.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        if (data.status === 'processing') {
          setProgress(data.progress || 0);
          setStep(data.step || 'Processing...');
        } else if (data.status === 'done') {
          setProgress(100);
          setStep('Complete!');
          setClips(data.clips || []);
          setSelectedClipIdx(0);
          setView('results');
          source.close();
        } else if (data.status === 'failed') {
          setError(data.error || 'Pipeline execution failed.');
          setView('upload');
          source.close();
        }
      } catch (err) {
        console.error('Error parsing SSE event:', err);
      }
    };

    source.onerror = (err) => {
      console.error('SSE connection error:', err);
      // Don't immediately crash, but close connection
      source.close();
    };
  };

  // Upload file API call
  const handleUploadFile = async (file) => {
    if (!file) return;
    
    // Validate file type
    const validExtensions = ['.mp4', '.mov', '.mkv', '.avi', '.webm'];
    const fileExtension = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    if (!validExtensions.includes(fileExtension)) {
      alert('Invalid video format. Please upload an MP4, MOV, MKV, AVI, or WEBM file.');
      return;
    }

    setUploading(true);
    setError(null);
    setProgress(0);
    setStep('Uploading video...');

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`${API_BASE}/upload`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errDetail = await response.json();
        throw new Error(errDetail.detail || 'Upload failed');
      }

      const result = await response.json();
      const newJobId = result.job_id;
      
      setJobId(newJobId);
      setView('progress');
      startProgressStream(newJobId);
    } catch (err) {
      console.error('Upload error:', err);
      setError(err.message || 'Failed to connect to the backend server.');
    } finally {
      setUploading(false);
    }
  };

  // Drag and drop handlers
  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleUploadFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileInput = (e) => {
    if (e.target.files && e.target.files[0]) {
      handleUploadFile(e.target.files[0]);
    }
  };

  const triggerFileInput = () => {
    fileInputRef.current.click();
  };

  const handleReset = () => {
    setView('upload');
    setJobId(null);
    setProgress(0);
    setStep('');
    setClips([]);
    setError(null);
  };

  // SVG circular loader variables
  const radius = 70;
  const stroke = 8;
  const normalizedRadius = radius - stroke * 2;
  const circumference = normalizedRadius * 2 * Math.PI;
  const strokeDashoffset = circumference - (progress / 100) * circumference;

  return (
    <div className="app-container">
      {/* HEADER NAVBAR */}
      <header className="app-header">
        <div className="logo-container" onClick={handleReset} style={{ cursor: 'pointer' }}>
          <span className="logo-icon">F</span>
          <span className="logo-text">Framey</span>
        </div>
        <a 
          href="https://github.com" 
          target="_blank" 
          rel="noopener noreferrer" 
          className="github-link"
        >
          <svg className="github-icon" viewBox="0 0 24 24">
            <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
          </svg>
          Star on GitHub
        </a>
      </header>

      {/* MAIN CONTENT PORT */}
      <main className="main-content">
        
        {/* SCREEN 1: HERO & UPLOAD */}
        {view === 'upload' && (
          <>
            <div className="hero-section">
              <h1 className="hero-title">
                Turn long videos into <span>viral shorts</span>
              </h1>
              <p className="hero-subtitle">
                Upload your podcast, interview, or tutorial. Our pipeline extracts, evaluations, and cuts the most engaging standalone moments in seconds.
              </p>
            </div>

            <div 
              className={`upload-container ${dragActive ? 'drag-active' : ''}`}
              onDragEnter={handleDrag}
              onDragOver={handleDrag}
              onDragLeave={handleDrag}
              onDrop={handleDrop}
              onClick={triggerFileInput}
            >
              <input 
                type="file" 
                ref={fileInputRef}
                onChange={handleFileInput}
                className="file-input"
                accept=".mp4,.mov,.mkv,.avi,.webm"
                disabled={uploading}
              />
              <div className="upload-icon-wrapper">
                {uploading ? '⏳' : '📥'}
              </div>
              <p className="upload-text">
                {uploading ? 'Processing File...' : 'Drag & drop your video here'}
              </p>
              <p className="upload-subtext">Supports MP4, MOV, MKV, AVI, and WEBM (Max 500MB)</p>
              <button className="btn-upload" disabled={uploading}>
                {uploading ? 'Uploading...' : 'Choose File ->'}
              </button>
            </div>

            {error && (
              <div style={{ marginTop: '1.5rem', color: '#ef4444', fontWeight: '500', fontSize: '0.95rem' }}>
                ❌ Error: {error}
              </div>
            )}

            <div className="star-banner">
              <span>Liked the product? A star on github would do the job. 🌟</span>
            </div>
          </>
        )}

        {/* SCREEN 2: PROGRESS LOADER */}
        {view === 'progress' && (
          <div className="progress-card">
            <div className="circle-progress-wrapper">
              <svg width="160" height="160">
                <circle
                  className="progress-ring-circle-bg"
                  r={normalizedRadius}
                  cx="80"
                  cy="80"
                />
                <circle
                  className="progress-ring-circle"
                  strokeDasharray={circumference + ' ' + circumference}
                  style={{ strokeDashoffset }}
                  r={normalizedRadius}
                  cx="80"
                  cy="80"
                />
              </svg>
              <div className="progress-percentage">{progress}%</div>
              <div className="circle-pulse"></div>
            </div>

            <h2 className="progress-step-title">{step}</h2>
            <p className="progress-step-desc">
              Wait for a minute or two to get the best outputs
            </p>

            {/* Simulated log outputs */}
            <div className="progress-logs">
              <div className={`log-item ${progress >= 10 ? 'completed' : progress > 0 ? 'active' : ''}`}>
                <div className="log-dot"></div>
                <span>Extracting master audio track</span>
              </div>
              <div className={`log-item ${progress >= 30 ? 'completed' : progress >= 10 ? 'active' : ''}`}>
                <div className="log-dot"></div>
                <span>Groq Cloud Whisper transcription</span>
              </div>
              <div className={`log-item ${progress >= 60 ? 'completed' : progress >= 30 ? 'active' : ''}`}>
                <div className="log-dot"></div>
                <span>Evaluating narrative & grading blocks</span>
              </div>
              <div className={`log-item ${progress >= 85 ? 'completed' : progress >= 60 ? 'active' : ''}`}>
                <div className="log-dot"></div>
                <span>Finding exact viral sentence moments</span>
              </div>
              <div className={`log-item ${progress >= 100 ? 'completed' : progress >= 85 ? 'active' : ''}`}>
                <div className="log-dot"></div>
                <span>Slicing video clips & polishing audio</span>
              </div>
            </div>
          </div>
        )}

        {/* SCREEN 3: RESULTS / CLIP STUDIO */}
        {view === 'results' && (
          <>
            <h2 style={{ fontSize: '2rem', marginBottom: '1rem', fontFamily: 'var(--font-display)', fontWeight: 800 }}>
              Your Generated Viral Clips 🎬
            </h2>
            
            {clips.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '3rem' }}>
                <p style={{ color: 'var(--color-muted)', marginBottom: '1.5rem' }}>No viral moments met the grading threshold criteria.</p>
                <button className="btn-upload" onClick={handleReset}>Try Another Video</button>
              </div>
            ) : (
              <div className="workspace-container">
                {/* Left Sidebar List */}
                <div className="workspace-sidebar">
                  <span className="sidebar-title">Moments Detected</span>
                  {clips.map((clip, index) => (
                    <button
                      key={index}
                      className={`clip-list-item ${selectedClipIdx === index ? 'selected' : ''}`}
                      onClick={() => setSelectedClipIdx(index)}
                    >
                      <div className="clip-item-header">
                        <span className="clip-item-name">Clip {index + 1}</span>
                        <span className="clip-item-duration">{clip.duration}s</span>
                      </div>
                      <span className="clip-item-excerpt">
                        {clip.reason || 'Viral segment excerpt...'}
                      </span>
                    </button>
                  ))}
                </div>

                {/* Right Panel View */}
                <div className="studio-panel">
                  <div className="studio-header">
                    <span className="studio-title">
                      Clip {selectedClipIdx + 1}: Timestamp {clips[selectedClipIdx].start}s - {clips[selectedClipIdx].end}s
                    </span>
                    <span className="badge-viral">
                      🔥 Viral Moment
                    </span>
                  </div>

                  <div className="studio-body">
                    {/* Portrait Video Player */}
                    <div className="player-wrapper">
                      <video 
                        src={`${API_BASE}/${clips[selectedClipIdx].path}`} 
                        controls 
                        className="shorts-player"
                        key={clips[selectedClipIdx].path}
                        autoPlay
                      />
                    </div>

                    <div className="clip-details">
                      <div className="details-row">
                        <span><strong>Start:</strong> {clips[selectedClipIdx].start}s</span>
                        <span><strong>End:</strong> {clips[selectedClipIdx].end}s</span>
                        <span><strong>Duration:</strong> {clips[selectedClipIdx].duration}s</span>
                      </div>
                      <p className="clip-reasoning">
                        <strong>AI Analysis:</strong> {clips[selectedClipIdx].reason}
                      </p>
                    </div>
                  </div>

                  <div className="studio-footer">
                    <button 
                      className="btn-export"
                      onClick={() => window.open(`${API_BASE}/${clips[selectedClipIdx].path}`)}
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                        <polyline points="7 10 12 15 17 10" />
                        <line x1="12" y1="15" x2="12" y2="3" />
                      </svg>
                      Download Clip
                    </button>
                  </div>
                </div>
              </div>
            )}

            <button className="btn-reset" onClick={handleReset}>
              Upload a New Video
            </button>
          </>
        )}

      </main>
    </div>
  );
}

export default App;
