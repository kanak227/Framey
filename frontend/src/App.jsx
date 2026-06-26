import { useState, useEffect, useRef } from 'react';
import { createClient } from '@supabase/supabase-js';
import './App.css';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

// Initialize Supabase client
const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || '';
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || '';
export const supabase = createClient(supabaseUrl, supabaseAnonKey);

function App() {
  // Authentication states
  const [session, setSession] = useState(null);
  const [authEmail, setAuthEmail] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authMode, setAuthMode] = useState('login'); // 'login' | 'signup'
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState(null);

  // Main UI states
  const [view, setView] = useState('upload'); // 'upload' | 'progress' | 'results'
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadType, setUploadType] = useState('file'); // 'file' | 'url'
  const [youtubeUrl, setYoutubeUrl] = useState('');
  
  // Job & Progress states
  const [jobId, setJobId] = useState(null);
  const [progress, setProgress] = useState(0);
  const [step, setStep] = useState('');
  const [error, setError] = useState(null);
  
  // Results states
  const [clips, setClips] = useState([]);
  const [selectedClipIdx, setSelectedClipIdx] = useState(0);
  const [downloading, setDownloading] = useState(false);
  
  // Historical jobs
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const realtimeChannelRef = useRef(null);
  const fileInputRef = useRef(null);

  // 1. Subscribe to Auth changes
  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      if (session) {
        fetchHistory(session.user.id);
      }
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
      if (session) {
        fetchHistory(session.user.id);
      } else {
        setHistory([]);
      }
    });

    return () => {
      subscription.unsubscribe();
      if (realtimeChannelRef.current) {
        realtimeChannelRef.current.unsubscribe();
      }
    };
  }, []);

  // 2. Fetch user's historical jobs
  const fetchHistory = async (userId) => {
    if (!userId) return;
    setHistoryLoading(true);
    try {
      const { data, error } = await supabase
        .from('jobs')
        .select('*')
        .eq('user_id', userId)
        .order('created_at', { ascending: false });

      if (error) throw error;
      setHistory(data || []);
    } catch (err) {
      console.error('Error fetching history:', err);
    } finally {
      setHistoryLoading(false);
    }
  };

  // 3. User Authentication handlers
  const handleAuthSubmit = async (e) => {
    e.preventDefault();
    if (!authEmail || !authPassword) return;

    setAuthLoading(true);
    setAuthError(null);

    try {
      if (authMode === 'login') {
        const { error } = await supabase.auth.signInWithPassword({
          email: authEmail,
          password: authPassword,
        });
        if (error) throw error;
      } else {
        const { error } = await supabase.auth.signUp({
          email: authEmail,
          password: authPassword,
        });
        if (error) throw error;
        alert('Check your email for confirmation link if email verification is enabled!');
      }
    } catch (err) {
      setAuthError(err.message || 'Auth action failed.');
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogout = async () => {
    await supabase.auth.signOut();
    handleReset();
  };

  // 4. Live updates from Supabase Realtime
  const startProgressSubscription = (id) => {
    if (realtimeChannelRef.current) {
      realtimeChannelRef.current.unsubscribe();
    }

    setProgress(0);
    setStep('Initializing pipeline...');

    // Polling fallback in case Supabase Realtime replication is not enabled
    const pollInterval = setInterval(async () => {
      try {
        const response = await fetch(`${API_BASE}/status/${id}`);
        if (response.ok) {
          const data = await response.json();
          if (data.status === 'processing') {
            setProgress(data.progress || 0);
            setStep(data.step || 'Processing...');
          } else if (data.status === 'done') {
            setProgress(100);
            setStep('Complete!');
            setClips(data.clips || []);
            setSelectedClipIdx(0);
            setView('results');
            clearInterval(pollInterval);
            if (session?.user?.id) fetchHistory(session.user.id);
          } else if (data.status === 'failed') {
            setError(data.error || 'Pipeline execution failed.');
            setView('upload');
            clearInterval(pollInterval);
            if (session?.user?.id) fetchHistory(session.user.id);
          }
        }
      } catch (err) {
        console.error('Error polling status:', err);
      }
    }, 2000);

    const channel = supabase
      .channel(`job-updates-${id}`)
      .on(
        'postgres_changes',
        {
          event: 'UPDATE',
          schema: 'public',
          table: 'jobs',
          filter: `id=eq.${id}`,
        },
        (payload) => {
          const data = payload.new;
          if (data.status === 'processing') {
            setProgress(data.progress || 0);
            setStep(data.step || 'Processing...');
          } else if (data.status === 'done') {
            setProgress(100);
            setStep('Complete!');
            setClips(data.clips || []);
            setSelectedClipIdx(0);
            setView('results');
            channel.unsubscribe();
            clearInterval(pollInterval);
            if (session?.user?.id) fetchHistory(session.user.id);
          } else if (data.status === 'failed') {
            setError(data.error || 'Pipeline execution failed.');
            setView('upload');
            channel.unsubscribe();
            clearInterval(pollInterval);
            if (session?.user?.id) fetchHistory(session.user.id);
          }
        }
      )
      .subscribe();

    realtimeChannelRef.current = {
      unsubscribe: () => {
        channel.unsubscribe();
        clearInterval(pollInterval);
      }
    };
  };

  // 5. Upload video directly to backend API
  const handleUploadFile = async (file) => {
    if (!file || !session) return;
    
    const validExtensions = ['.mp4', '.mov', '.mkv', '.avi', '.webm'];
    const fileExtension = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    if (!validExtensions.includes(fileExtension)) {
      alert('Invalid video format. Please upload an MP4, MOV, MKV, AVI, or WEBM file.');
      return;
    }

    setUploading(true);
    setError(null);
    setProgress(0);
    setStep('Uploading video to backend server...');

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch(`${API_BASE}/upload`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${session.access_token}`
        },
        body: formData,
      });

      if (!response.ok) {
        const errDetail = await response.json();
        throw new Error(errDetail.detail || 'Failed to upload video to backend.');
      }

      const result = await response.json();
      const finalJobId = result.job_id;

      setJobId(finalJobId);
      setView('progress');
      startProgressSubscription(finalJobId);
    } catch (err) {
      console.error('Upload flow error:', err);
      setError(err.message || 'Video upload or pipeline initialization failed.');
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

  // 6. Submit external YouTube URL
  const handleUploadUrl = async (e) => {
    e.preventDefault();
    if (!youtubeUrl || !session) return;

    setUploading(true);
    setError(null);
    setProgress(0);
    setStep('Submitting video link...');

    try {
      const response = await fetch(`${API_BASE}/upload-url`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${session.access_token}`
        },
        body: JSON.stringify({ url: youtubeUrl }),
      });

      if (!response.ok) {
        const errDetail = await response.json();
        throw new Error(errDetail.detail || 'Failed to submit URL');
      }

      const result = await response.json();
      const newJobId = result.job_id;
      
      setJobId(newJobId);
      setView('progress');
      startProgressSubscription(newJobId);
    } catch (err) {
      console.error('URL submit error:', err);
      setError(err.message || 'Failed to connect to the backend server.');
    } finally {
      setUploading(false);
    }
  };

  const loadJobFromHistory = (job) => {
    if (job.status === 'done') {
      setJobId(job.id);
      setClips(job.clips || []);
      setSelectedClipIdx(0);
      setView('results');
    } else if (job.status === 'processing' || job.status === 'pending') {
      setJobId(job.id);
      setProgress(job.progress || 0);
      setStep(job.step || 'Processing...');
      setView('progress');
      startProgressSubscription(job.id);
    } else {
      alert(`Job status: ${job.status.toUpperCase()}. Error details: ${job.error || 'N/A'}`);
    }
  };

  const handleDownloadClip = async (url, start, end) => {
    if (!url) return;
    setDownloading(true);
    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const blob = await response.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = blobUrl;
      const filename = `clip_${start.toFixed(1)}s-${end.toFixed(1)}s.mp4`;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(blobUrl);
    } catch (err) {
      console.error('Failed to download clip via blob, falling back to window.open:', err);
      window.open(url, '_blank');
    } finally {
      setDownloading(false);
    }
  };

  const handleReset = () => {
    setView('upload');
    setJobId(null);
    setProgress(0);
    setStep('');
    setClips([]);
    setError(null);
    setYoutubeUrl('');
    if (session?.user?.id) fetchHistory(session.user.id);
  };

  // SVG circular loader variables
  const radius = 70;
  const stroke = 8;
  const normalizedRadius = radius - stroke * 2;
  const circumference = normalizedRadius * 2 * Math.PI;
  const strokeDashoffset = circumference - (progress / 100) * circumference;

  // Render Login / Signup view if unauthenticated
  if (!session) {
    return (
      <div className="app-container" style={{ justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <div style={{ maxWidth: '400px', width: '100%', padding: '2rem', background: '#111827', border: '1px solid #1f2937', borderRadius: '16px', boxShadow: '0 8px 32px rgba(0,0,0,0.4)', textAlign: 'center' }}>
          <div className="logo-container" style={{ justifyContent: 'center', marginBottom: '1.5rem' }}>
            <span className="logo-icon">F</span>
            <span className="logo-text">Framey</span>
          </div>
          <h2 style={{ fontSize: '1.5rem', color: '#fff', marginBottom: '0.5rem' }}>
            {authMode === 'login' ? 'Welcome Back' : 'Create Account'}
          </h2>
          <p style={{ color: '#9ca3af', fontSize: '0.9rem', marginBottom: '1.5rem' }}>
            {authMode === 'login' ? 'Log in to generate viral video clips' : 'Sign up to start transforming videos'}
          </p>

          <form onSubmit={handleAuthSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <input
              type="email"
              placeholder="Email address"
              value={authEmail}
              onChange={(e) => setAuthEmail(e.target.value)}
              style={{ padding: '0.8rem', background: '#1f2937', border: '1px solid #374151', borderRadius: '8px', color: '#fff', fontSize: '0.95rem' }}
              required
            />
            <input
              type="password"
              placeholder="Password"
              value={authPassword}
              onChange={(e) => setAuthPassword(e.target.value)}
              style={{ padding: '0.8rem', background: '#1f2937', border: '1px solid #374151', borderRadius: '8px', color: '#fff', fontSize: '0.95rem' }}
              required
            />

            {authError && (
              <p style={{ color: '#ef4444', fontSize: '0.85rem', textAlign: 'left', margin: 0 }}>
                ❌ {authError}
              </p>
            )}

            <button
              type="submit"
              disabled={authLoading}
              style={{ padding: '0.85rem', background: 'linear-gradient(135deg, #6366f1, #a78bfa)', border: 'none', borderRadius: '8px', color: '#fff', fontWeight: 'bold', fontSize: '1rem', cursor: 'pointer', transition: 'opacity 0.2s' }}
            >
              {authLoading ? 'Loading...' : authMode === 'login' ? 'Log In' : 'Sign Up'}
            </button>
          </form>

          <div style={{ marginTop: '1.5rem', borderTop: '1px solid #1f2937', paddingTop: '1.2rem', fontSize: '0.9rem', color: '#9ca3af' }}>
            {authMode === 'login' ? (
              <p>
                Don't have an account?{' '}
                <span onClick={() => setAuthMode('signup')} style={{ color: '#a78bfa', cursor: 'pointer', fontWeight: 'bold' }}>
                  Sign Up
                </span>
              </p>
            ) : (
              <p>
                Already have an account?{' '}
                <span onClick={() => setAuthMode('login')} style={{ color: '#a78bfa', cursor: 'pointer', fontWeight: 'bold' }}>
                  Log In
                </span>
              </p>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-container">
      {/* HEADER NAVBAR */}
      <header className="app-header">
        <div className="logo-container" onClick={handleReset} style={{ cursor: 'pointer' }}>
          <span className="logo-icon">F</span>
          <span className="logo-text">Framey</span>
        </div>
        
        <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
          <span style={{ color: '#9ca3af', fontSize: '0.9rem', display: 'none', '@media (min-width: 640px)': { display: 'inline' } }}>
            👤 {session.user.email}
          </span>
          <button 
            onClick={handleLogout}
            style={{ padding: '0.5rem 1rem', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: '#ef4444', fontSize: '0.85rem', fontWeight: '600', cursor: 'pointer', transition: 'all 0.2s' }}
          >
            Log Out
          </button>
        </div>
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
                Upload your podcast, interview, or tutorial. Our pipeline extracts, evaluates, and cuts the most engaging standalone moments in seconds.
              </p>
            </div>

            <div className="upload-tabs">
              <button 
                type="button"
                className={`tab-btn ${uploadType === 'file' ? 'active' : ''}`}
                onClick={() => setUploadType('file')}
                disabled={uploading}
              >
                📁 Upload File
              </button>
              <button 
                type="button"
                className={`tab-btn ${uploadType === 'url' ? 'active' : ''}`}
                onClick={() => setUploadType('url')}
                disabled={uploading}
              >
                🔗 Import via Link
              </button>
            </div>

            {uploadType === 'file' ? (
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
                <button type="button" className="btn-upload" disabled={uploading}>
                  {uploading ? 'Uploading...' : 'Choose File ->'}
                </button>
              </div>
            ) : (
              <div className="url-container">
                <form className="url-form" onSubmit={handleUploadUrl}>
                  <div className="upload-icon-wrapper">
                    {uploading ? '⏳' : '🔗'}
                  </div>
                  <p className="upload-text">
                    {uploading ? 'Processing Link...' : 'Import from YouTube or Web URL'}
                  </p>
                  <div className="url-input-wrapper">
                    <input
                      type="url"
                      className="url-input"
                      placeholder="https://www.youtube.com/watch?v=..."
                      value={youtubeUrl}
                      onChange={(e) => setYoutubeUrl(e.target.value)}
                      required
                      disabled={uploading}
                    />
                  </div>
                  <button type="submit" className="btn-process" disabled={uploading || !youtubeUrl}>
                    {uploading ? 'Submitting...' : 'Process Video Link ->'}
                  </button>
                </form>
              </div>
            )}

            {error && (
              <div style={{ marginTop: '1.5rem', color: '#ef4444', fontWeight: '500', fontSize: '0.95rem' }}>
                ❌ Error: {error}
              </div>
            )}

            {/* JOB HISTORY LOG INTERFACE */}
            <div style={{ marginTop: '3rem', width: '100%', maxWidth: '640px', textAlign: 'left' }}>
              <h3 style={{ fontSize: '1.3rem', color: '#fff', borderBottom: '1px solid #1f2937', paddingBottom: '0.5rem', marginBottom: '1rem', fontFamily: 'var(--font-display)', fontWeight: 700 }}>
                Your Video History 🎬
              </h3>
              
              {historyLoading ? (
                <p style={{ color: '#9ca3af', fontSize: '0.95rem' }}>Loading past projects...</p>
              ) : history.length === 0 ? (
                <p style={{ color: '#4b5563', fontSize: '0.95rem' }}>No past projects found. Upload a video to see your history here!</p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  {history.map((job) => (
                    <div
                      key={job.id}
                      onClick={() => loadJobFromHistory(job)}
                      style={{ padding: '1rem', background: '#111827', border: '1px solid #1f2937', borderRadius: '12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer', transition: 'all 0.2s', ':hover': { borderColor: '#6366f1' } }}
                      className="history-item-row"
                    >
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <span style={{ fontWeight: 'bold', color: '#fff', fontSize: '0.95rem' }}>Job: {job.id.replace('job_', '')}</span>
                          <span style={{ fontSize: '0.8rem', padding: '0.15rem 0.5rem', borderRadius: '100px', fontWeight: 'bold', background: job.status === 'done' ? 'rgba(16,185,129,0.1)' : job.status === 'failed' ? 'rgba(239,68,68,0.1)' : 'rgba(245,158,11,0.1)', color: job.status === 'done' ? '#10b981' : job.status === 'failed' ? '#ef4444' : '#f59e0b' }}>
                            {job.status.toUpperCase()}
                          </span>
                        </div>
                        <div style={{ color: '#6b7280', fontSize: '0.8rem', marginTop: '0.25rem' }}>
                          Created at: {new Date(job.created_at).toLocaleString()}
                        </div>
                      </div>
                      <div style={{ color: '#a78bfa', fontSize: '0.9rem', fontWeight: 'bold' }}>
                        {job.status === 'done' ? 'Open Studio ➡️' : 'Track ➡️'}
                      </div>
                    </div>
                  ))}
                </div>
              )}
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
                        src={clips[selectedClipIdx].path} 
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
                      onClick={() => handleDownloadClip(
                        clips[selectedClipIdx].path, 
                        clips[selectedClipIdx].start, 
                        clips[selectedClipIdx].end
                      )}
                      disabled={downloading}
                    >
                      {downloading ? (
                        <>
                          <span className="spinner-small"></span>
                          Downloading...
                        </>
                      ) : (
                        <>
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                            <polyline points="7 10 12 15 17 10" />
                            <line x1="12" y1="15" x2="12" y2="3" />
                          </svg>
                          Download Clip
                        </>
                      )}
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
