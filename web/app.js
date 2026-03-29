/* Think-Pod — Frontend with Supabase Auth + Dashboard */

let supabaseClient = null;
let currentUser = null;
let accessToken = null;

let sessionId = null;
let selectedPodcaster = null;
let hostName = '';
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let isProcessing = false;
let textOnly = false;
let reflectMode = false;
let lastAnalysis = null;
let recordingTimer = null;
let recordingSeconds = 0;
let analyserNode = null;
let animationFrame = null;
let podcastersData = [];
let _viewedSession = null; // stash for download

// Base URL for API calls — works behind reverse proxy subpaths
const BASE = (() => {
  // If served from /thinkpod/, API calls need /thinkpod/api/...
  // Detect by checking where index.html was served from
  const path = window.location.pathname.replace(/\/+$/, '');
  // If path ends with known page paths, strip them; otherwise use as-is
  // For root serving: path = '' or '/', base = ''
  // For /thinkpod/: path = '/thinkpod', base = '/thinkpod'
  return path || '';
})();

// ─── Screens ─────────────────────────────────────────────────────────

const SCREENS = ['login-screen', 'dashboard-screen', 'start-screen', 'interview-screen', 'end-screen', 'transcript-view-screen'];

function showScreen(id) {
  for (const s of SCREENS) {
    document.getElementById(s).style.display = s === id ? 'flex' : 'none';
  }
  // Push a simple history state so back button works
  if (history.state !== id) {
    history.pushState(id, '', '');
  }
}

window.addEventListener('popstate', (e) => {
  if (e.state && SCREENS.includes(e.state)) {
    // Don't allow going back to interview or end if session is done
    if (e.state === 'login-screen' && currentUser) {
      showScreen('dashboard-screen');
      return;
    }
    for (const s of SCREENS) {
      document.getElementById(s).style.display = s === e.state ? 'flex' : 'none';
    }
  }
});

// ─── Init ────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', initApp);

async function initApp() {
  try {
    // Fetch public config from server
    const configResp = await fetch(BASE + '/api/config');
    const config = await configResp.json();

    supabaseClient = window.supabase.createClient(config.supabase_url, config.supabase_anon_key, {
      auth: {
        detectSessionInUrl: true,
        flowType: 'pkce',
      }
    });

    // Check for existing session first (handles page load + OAuth code exchange)
    const { data: { session }, error: sessionError } = await supabaseClient.auth.getSession();
    if (session && !sessionError) {
      currentUser = session.user;
      accessToken = session.access_token;
      onLoggedIn();
    } else {
      showScreen('login-screen');
    }

    // Listen for subsequent auth state changes (token refresh, sign out, etc.)
    supabaseClient.auth.onAuthStateChange((event, session) => {
      if (event === 'SIGNED_IN' || event === 'TOKEN_REFRESHED') {
        if (session) {
          currentUser = session.user;
          accessToken = session.access_token;
          // Only navigate to dashboard if we're on the login screen
          const loginScreen = document.getElementById('login-screen');
          if (loginScreen && loginScreen.style.display !== 'none') {
            onLoggedIn();
          }
        }
      } else if (event === 'SIGNED_OUT') {
        currentUser = null;
        accessToken = null;
        showScreen('login-screen');
      }
    });
  } catch (e) {
    console.error('Init error:', e);
    showScreen('login-screen');
  }
}

// ─── Auth ────────────────────────────────────────────────────────────

function showLogin() {
  document.getElementById('login-form').style.display = '';
  document.getElementById('signup-form').style.display = 'none';
}

function showSignUp() {
  document.getElementById('login-form').style.display = 'none';
  document.getElementById('signup-form').style.display = '';
}

async function signInWithGoogle() {
  const { error } = await supabaseClient.auth.signInWithOAuth({
    provider: 'google',
    options: { redirectTo: window.location.origin + BASE + '/' },
  });
  if (error) {
    document.getElementById('login-error').textContent = error.message;
  }
}

async function signInWithEmail() {
  const email = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value;
  const errEl = document.getElementById('login-error');
  errEl.textContent = '';

  if (!email || !password) {
    errEl.textContent = 'Please enter email and password';
    return;
  }

  const { error } = await supabaseClient.auth.signInWithPassword({ email, password });
  if (error) {
    errEl.textContent = error.message;
  }
}

async function signUpWithEmail() {
  const email = document.getElementById('signup-email').value.trim();
  const password = document.getElementById('signup-password').value;
  const errEl = document.getElementById('signup-error');
  const successEl = document.getElementById('signup-success');
  errEl.textContent = '';
  successEl.textContent = '';

  if (!email || !password) {
    errEl.textContent = 'Please enter email and password';
    return;
  }
  if (password.length < 6) {
    errEl.textContent = 'Password must be at least 6 characters';
    return;
  }

  const { data, error } = await supabaseClient.auth.signUp({ email, password });
  if (error) {
    errEl.textContent = error.message;
  } else if (data.user && !data.session) {
    successEl.textContent = 'Check your email for a confirmation link!';
  }
  // If session is returned, onAuthStateChange will handle it
}

async function logout() {
  await supabaseClient.auth.signOut();
  currentUser = null;
  accessToken = null;
  sessionId = null;
  showScreen('login-screen');
}

function onLoggedIn() {
  showDashboard();
}

// ─── Auth headers ────────────────────────────────────────────────────

function authHeaders(extra) {
  const h = { 'Authorization': 'Bearer ' + accessToken };
  if (extra) Object.assign(h, extra);
  return h;
}

async function authFetch(url, opts) {
  // Refresh token if needed before each request
  const { data: { session } } = await supabaseClient.auth.getSession();
  if (session) {
    accessToken = session.access_token;
  } else {
    // Session expired — force re-login
    showScreen('login-screen');
    throw new Error('Session expired');
  }

  opts = opts || {};
  opts.headers = authHeaders(opts.headers || {});
  const resp = await fetch(url, opts);
  if (resp.status === 401) {
    showScreen('login-screen');
    throw new Error('Unauthorized');
  }
  return resp;
}

// ─── Dashboard ───────────────────────────────────────────────────────

async function showDashboard() {
  showScreen('dashboard-screen');
  sessionId = null;

  // Update user info
  const userInfo = document.getElementById('user-info');
  const meta = currentUser.user_metadata || {};
  const displayName = meta.full_name || meta.name || currentUser.email || '';
  userInfo.textContent = displayName;

  // Load podcasters in background for start screen
  loadPodcasters();

  // Load sessions
  await loadSessions();
}

async function loadSessions() {
  const listEl = document.getElementById('sessions-list');
  listEl.innerHTML = '<div class="loading">Loading sessions...</div>';

  try {
    const resp = await authFetch(BASE + '/api/sessions');
    if (!resp.ok) throw new Error('Failed to load sessions');
    const data = await resp.json();
    const sessions = data.sessions || [];

    if (sessions.length === 0) {
      listEl.innerHTML = '<div class="empty-state">No sessions yet — start your first interview!</div>';
      return;
    }

    listEl.innerHTML = '';
    for (const s of sessions) {
      const card = document.createElement('div');
      card.className = 'session-card';
      const dateStr = new Date(s.created_at).toLocaleDateString('en-US', {
        month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit'
      });
      const statusClass = s.status === 'active' ? 'status-active' : 'status-ended';
      const podcasterInfo = podcastersData.find(p => p.id === s.podcaster);
      const podcasterName = podcasterInfo ? podcasterInfo.name : s.podcaster;
      const avatarSrc = podcasterInfo && podcasterInfo.avatar ? podcasterInfo.avatar : '';
      const avatarHtml = avatarSrc
        ? '<img class="session-avatar" src="' + esc(avatarSrc) + '" alt="">'
        : '<div class="session-avatar-placeholder">🎙️</div>';

      card.innerHTML =
        '<div class="session-card-left">' +
          avatarHtml +
          '<div class="session-card-info">' +
            '<div class="session-card-title">' + esc(podcasterName) + ' × ' + esc(s.guest_name) + '</div>' +
            '<div class="session-card-topic">' + esc(s.topic) + '</div>' +
            '<div class="session-card-meta">' + esc(dateStr) + ' · ' + s.turns + ' turns</div>' +
          '</div>' +
        '</div>' +
        '<div class="session-card-right">' +
          '<span class="status-badge ' + statusClass + '">' + esc(s.status) + '</span>' +
          '<div class="session-card-actions">' +
            '<button class="small-btn" data-action="view" data-id="' + s.id + '">View</button>' +
            '<button class="small-btn reflect-analysis-btn" data-action="analysis" data-id="' + s.id + '" style="display:none">🔍 Analysis</button>' +
            (s.status === 'active' ? '<button class="small-btn accent" data-action="resume" data-id="' + s.id + '">Resume</button>' : '') +
            '<button class="small-btn danger" data-action="delete" data-id="' + s.id + '">Delete</button>' +
          '</div>' +
        '</div>';

      // Check if analysis exists for this session (async, non-blocking)
      if (s.status === 'ended') {
        (function(cardEl, sid) {
          authFetch(BASE + '/api/sessions/' + sid + '/analysis', { method: 'GET' })
            .then(function(r) { if (r.ok) { var btn = cardEl.querySelector('[data-action="analysis"]'); if (btn) btn.style.display = ''; } })
            .catch(function() {});
        })(card, s.id);
      }

      card.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-action]');
        if (!btn) return;
        const action = btn.dataset.action;
        const id = btn.dataset.id;
        if (action === 'view') viewSession(id);
        else if (action === 'resume') resumeSession(id);
        else if (action === 'delete') deleteSession(id);
        else if (action === 'analysis') viewAnalysis(id);
      });

      listEl.appendChild(card);
    }
  } catch (e) {
    listEl.innerHTML = '<div class="auth-error">Error loading sessions: ' + esc(e.message) + '</div>';
  }
}

async function viewSession(id) {
  try {
    const resp = await authFetch(BASE + '/api/sessions/' + id);
    if (!resp.ok) throw new Error('Failed to load session');
    const data = await resp.json();
    const s = data.session;
    const msgs = data.messages || [];

    const podcasterInfo = podcastersData.find(p => p.id === s.podcaster);
    const podcasterName = podcasterInfo ? podcasterInfo.name : s.podcaster;

    document.getElementById('transcript-view-title').textContent =
      podcasterName + ' × ' + s.guest_name;
    document.getElementById('transcript-view-meta').textContent =
      'Topic: ' + s.topic + ' · ' + s.turns + ' turns · ' +
      new Date(s.created_at).toLocaleDateString();

    const contentEl = document.getElementById('transcript-view-content');
    contentEl.innerHTML = '';

    for (const m of msgs) {
      if (m.role === 'system') continue;
      // Skip the initial setup prompt (turn 0, role user, starts with "Your guest today")
      if (m.role === 'user' && m.turn_number === 0) continue;

      const entry = document.createElement('div');
      entry.className = 'transcript-entry';
      const isHost = m.role === 'assistant';
      const speaker = isHost ? podcasterName : s.guest_name;
      entry.innerHTML =
        '<div class="speaker ' + (isHost ? 'speaker-host' : 'speaker-user') + '">' +
        (isHost ? '🎙️' : '🗣️') + ' ' + esc(speaker) + '</div>' +
        '<div class="text">' + esc(m.content) + '</div>';
      contentEl.appendChild(entry);
    }

    _viewedSession = { session: s, messages: msgs, podcasterName };
    showScreen('transcript-view-screen');
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

async function resumeSession(id) {
  try {
    const resp = await authFetch(BASE + '/api/sessions/' + id + '/resume', { method: 'POST' });
    if (!resp.ok) {
      const errText = await resp.text();
      throw new Error(errText);
    }
    const data = await resp.json();
    sessionId = data.session_id;
    hostName = data.podcaster_name;

    const p = podcastersData.find(x => x.id === data.podcaster);
    if (p && p.avatar) document.getElementById('host-avatar').src = p.avatar;
    document.getElementById('host-title').textContent = '🎙️ ' + data.podcaster_name;

    // Clear and rebuild transcript
    const transcriptEl = document.getElementById('transcript');
    transcriptEl.innerHTML = '';
    for (const t of (data.transcript || [])) {
      const isHost = t.speaker === 'Host';
      const speakerName = isHost ? hostName : t.speaker;
      addTranscript(speakerName, t.text, isHost);
    }

    showScreen('interview-screen');
    setStatus('', 'Tap the mic to continue recording');
    document.getElementById('talk-btn').disabled = false;
    document.getElementById('send-btn').disabled = false;
  } catch (e) {
    alert('Error resuming: ' + e.message);
  }
}

async function deleteSession(id) {
  if (!confirm('Delete this session? This cannot be undone.')) return;
  try {
    const resp = await authFetch(BASE + '/api/sessions/' + id, { method: 'DELETE' });
    if (!resp.ok) throw new Error('Failed to delete');
    await loadSessions();
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

// ─── Start Screen ────────────────────────────────────────────────────

function showStartScreen() {
  showScreen('start-screen');
  loadPodcasters();
}

async function loadPodcasters() {
  if (podcastersData.length > 0) {
    populatePodcasterSelect();
    return;
  }
  try {
    const resp = await fetch(BASE + '/api/podcasters');
    podcastersData = await resp.json();
    populatePodcasterSelect();
  } catch (e) {
    const select = document.getElementById('podcaster-select');
    select.innerHTML = '<option disabled>Failed to load</option>';
  }
}

function populatePodcasterSelect() {
  const select = document.getElementById('podcaster-select');
  select.innerHTML = '';
  for (const p of podcastersData) {
    const opt = document.createElement('option');
    opt.value = p.id;
    opt.textContent = p.name + ' — ' + p.show;
    select.appendChild(opt);
  }
  if (podcastersData.length > 0) {
    select.value = podcastersData[0].id;
    onPodcasterChange();
  }
}

function onPodcasterChange() {
  const select = document.getElementById('podcaster-select');
  const p = podcastersData.find(x => x.id === select.value);
  if (!p) return;
  selectedPodcaster = p.id;
  hostName = p.name;
  document.getElementById('start-btn').disabled = false;
  document.getElementById('start-btn').textContent = 'Start Interview with ' + p.name;
}

// ─── Text-Only Toggle ───────────────────────────────────────────────

function toggleTextOnly(source) {
  textOnly = source.checked;
  const startToggle = document.getElementById('text-only-toggle-start');
  const sessionToggle = document.getElementById('text-only-toggle');
  if (startToggle) startToggle.checked = textOnly;
  if (sessionToggle) sessionToggle.checked = textOnly;
  const label = document.getElementById('text-only-label');
  if (label) label.textContent = textOnly ? 'Text only (no audio)' : 'Voice enabled';
}

function toggleReflect(source) {
  reflectMode = source.checked;
}

// ─── Session ─────────────────────────────────────────────────────────

async function startSession() {
  if (!selectedPodcaster) return;
  const name = document.getElementById('guest-name').value.trim() || 'Guest';
  const topic = document.getElementById('topic').value.trim() || 'life, ideas, and the future';
  const btn = document.getElementById('start-btn');
  btn.disabled = true;
  btn.textContent = 'Starting...';

  try {
    const resp = await authFetch(BASE + '/api/session/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ guest_name: name, topic: topic, podcaster: selectedPodcaster, text_only: textOnly, reflect: reflectMode }),
    });
    if (!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();
    sessionId = data.session_id;

    const p = podcastersData.find(x => x.id === selectedPodcaster);
    if (p && p.avatar) document.getElementById('host-avatar').src = p.avatar;
    document.getElementById('host-title').textContent = '🎙️ ' + data.podcaster_name;

    // Clear transcript
    document.getElementById('transcript').innerHTML = '';

    showScreen('interview-screen');
    const sessionToggle = document.getElementById('text-only-toggle');
    if (sessionToggle) sessionToggle.checked = textOnly;
    const label = document.getElementById('text-only-label');
    if (label) label.textContent = textOnly ? 'Text only (no audio)' : 'Voice enabled';

    // Show reflect badge if active
    const reflectBadge = document.getElementById('reflect-badge');
    if (reflectBadge) reflectBadge.style.display = reflectMode ? 'inline-block' : 'none';

    addTranscript(hostName, data.greeting_text, true);
    if (data.greeting_audio && !textOnly) {
      setStatus('speaking', hostName + ' is speaking...');
      await playAudio(data.greeting_audio);
    }
    setStatus('', 'Tap the mic to start recording');

    document.getElementById('talk-btn').disabled = false;
    document.getElementById('send-btn').disabled = false;

    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      try { await navigator.mediaDevices.getUserMedia({ audio: true }); }
      catch (e) { setStatus('', 'Mic unavailable — use text box below'); }
    } else {
      setStatus('', 'Mic unavailable (needs HTTPS) — use text box below');
    }
  } catch (err) {
    alert('Error starting session: ' + err.message);
    btn.disabled = false;
    btn.textContent = 'Start Interview with ' + hostName;
  }
}

async function endSession() {
  if (!sessionId) return;
  if (isRecording) await stopRecording();
  try {
    const resp = await authFetch(BASE + '/api/session/' + sessionId + '/end', { method: 'POST' });
    if (!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();
    showScreen('end-screen');
    document.getElementById('summary').textContent = data.transcript_md;

    // Show analysis if reflect mode produced one
    const analysisSection = document.getElementById('analysis-section');
    const analysisContent = document.getElementById('analysis-content');
    if (data.analysis) {
      lastAnalysis = data.analysis;
      analysisContent.innerHTML = renderAnalysisMarkdown(data.analysis);
      analysisSection.style.display = 'block';
    } else {
      analysisSection.style.display = 'none';
      lastAnalysis = null;
    }
  } catch (err) {
    alert('Error ending session: ' + err.message);
  }
}

// ─── Recording (tap to start / tap to stop) ─────────────────────────

async function toggleRecording() {
  if (isProcessing) return;
  if (isRecording) {
    await stopRecording();
  } else {
    await startRecording();
  }
}

async function startRecording() {
  if (isProcessing || isRecording) return;
  if (!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)) {
    setStatus('', 'Microphone unavailable — use text box below');
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
    audioChunks = [];
    mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunks.push(e.data); };
    mediaRecorder.start();
    isRecording = true;

    const btn = document.getElementById('talk-btn');
    btn.classList.add('recording');
    btn.innerHTML = '⏹ Tap to Stop';

    recordingSeconds = 0;
    updateRecordingTime();
    recordingTimer = setInterval(updateRecordingTime, 1000);

    startAudioVisualizer(stream);
    setStatus('listening', '🔴 Recording...');
  } catch (err) {
    setStatus('', 'Microphone access denied — use text box below');
  }
}

async function stopRecording() {
  if (!isRecording || !mediaRecorder) return;
  isRecording = false;

  const btn = document.getElementById('talk-btn');
  btn.classList.remove('recording');
  btn.innerHTML = '🎤 Tap to Record';

  if (recordingTimer) { clearInterval(recordingTimer); recordingTimer = null; }
  document.getElementById('recording-time').textContent = '';

  stopAudioVisualizer();

  mediaRecorder.stop();
  mediaRecorder.stream.getTracks().forEach(t => t.stop());
  await new Promise(resolve => { mediaRecorder.onstop = resolve; });
  if (audioChunks.length === 0) return;
  const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
  if (audioBlob.size < 5000) { setStatus('', 'Recording too short — try again'); return; }
  await sendAudio(audioBlob);
}

function updateRecordingTime() {
  const el = document.getElementById('recording-time');
  const mins = Math.floor(recordingSeconds / 60);
  const secs = recordingSeconds % 60;
  el.textContent = mins + ':' + secs.toString().padStart(2, '0');
  recordingSeconds++;
}

// ─── Audio Level Visualizer ──────────────────────────────────────────

function startAudioVisualizer(stream) {
  try {
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const source = audioCtx.createMediaStreamSource(stream);
    analyserNode = audioCtx.createAnalyser();
    analyserNode.fftSize = 256;
    source.connect(analyserNode);
    analyserNode._audioCtx = audioCtx;

    const canvas = document.getElementById('audio-visualizer');
    canvas.style.display = 'block';
    const ctx = canvas.getContext('2d');
    const bufferLength = analyserNode.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    function draw() {
      if (!isRecording) return;
      animationFrame = requestAnimationFrame(draw);
      analyserNode.getByteFrequencyData(dataArray);

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const barCount = 32;
      const barWidth = canvas.width / barCount;
      const step = Math.floor(bufferLength / barCount);

      for (let i = 0; i < barCount; i++) {
        const val = dataArray[i * step] / 255;
        const barHeight = Math.max(2, val * canvas.height);
        const x = i * barWidth;
        const y = (canvas.height - barHeight) / 2;

        const r = 220 + Math.floor(val * 35);
        const g = 50 + Math.floor(val * 30);
        const b = 50;
        ctx.fillStyle = 'rgb(' + r + ',' + g + ',' + b + ')';
        ctx.fillRect(x + 1, y, barWidth - 2, barHeight);
      }
    }
    draw();
  } catch (e) {
    // AudioContext not supported
  }
}

function stopAudioVisualizer() {
  if (animationFrame) { cancelAnimationFrame(animationFrame); animationFrame = null; }
  if (analyserNode && analyserNode._audioCtx) {
    analyserNode._audioCtx.close().catch(function() {});
    analyserNode = null;
  }
  var canvas = document.getElementById('audio-visualizer');
  if (canvas) {
    canvas.style.display = 'none';
    var ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }
}

// ─── Send ────────────────────────────────────────────────────────────

async function sendAudio(audioBlob) {
  if (!sessionId) return;
  setProcessing(true);
  setStatus('thinking', hostName + ' is thinking...');
  var formData = new FormData();
  formData.append('audio', audioBlob, 'recording.webm');
  formData.append('text_only', textOnly);
  try {
    var t0 = Date.now();
    // Need auth header for FormData — can't use authFetch easily with FormData content-type
    var { data: { session: sess } } = await supabaseClient.auth.getSession();
    if (sess) accessToken = sess.access_token;
    var resp = await fetch(BASE + '/api/session/' + sessionId + '/chat', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + accessToken },
      body: formData,
    });
    if (!resp.ok) throw new Error(await resp.text());
    var data = await resp.json();
    showResponse(data, Date.now() - t0);
  } catch (err) {
    setStatus('', 'Error: ' + err.message);
  } finally {
    setProcessing(false);
  }
}

async function sendText() {
  if (!sessionId || isProcessing) return;
  var input = document.getElementById('text-input');
  var text = input.value.trim();
  if (!text) return;
  setProcessing(true);
  addTranscript('You', text, false);
  input.value = '';
  setStatus('thinking', hostName + ' is thinking...');
  try {
    var t0 = Date.now();
    var resp = await authFetch(BASE + '/api/session/' + sessionId + '/chat-text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text, text_only: textOnly }),
    });
    if (!resp.ok) throw new Error(await resp.text());
    var data = await resp.json();
    showResponse(data, Date.now() - t0, true);
  } catch (err) {
    setStatus('', 'Error: ' + err.message);
  } finally {
    setProcessing(false);
  }
}

async function showResponse(data, totalMs, skipUser) {
  if (!skipUser) addTranscript('You', data.user_text, false);
  addTranscript(hostName, data.chris_text, true);
  var parts = [];
  if (data.stt_ms) parts.push('STT: ' + data.stt_ms + 'ms');
  parts.push('LLM: ' + data.llm_ms + 'ms');
  if (data.tts_ms) parts.push('TTS: ' + data.tts_ms + 'ms');
  parts.push('Total: ' + totalMs + 'ms');
  document.getElementById('latency').textContent = parts.join(' | ');
  if (data.chris_audio) {
    setStatus('speaking', hostName + ' is speaking...');
    await playAudio(data.chris_audio);
  }
  setStatus('', 'Tap the mic to start recording');
}

function setProcessing(val) {
  isProcessing = val;
  document.getElementById('talk-btn').disabled = val;
  document.getElementById('send-btn').disabled = val;
}

// ─── Audio ───────────────────────────────────────────────────────────

function playAudio(b64) {
  return new Promise(function(resolve) {
    var audio = new Audio('data:audio/mp3;base64,' + b64);
    audio.onended = resolve;
    audio.onerror = resolve;
    audio.play().catch(resolve);
  });
}

// ─── Transcript ──────────────────────────────────────────────────────

function addTranscript(speaker, text, isHost) {
  var el = document.getElementById('transcript');
  var entry = document.createElement('div');
  entry.className = 'transcript-entry';
  entry.innerHTML =
    '<div class="speaker ' + (isHost ? 'speaker-host' : 'speaker-user') + '">' +
    (isHost ? '🎙️' : '🗣️') + ' ' + esc(speaker) + '</div>' +
    '<div class="text">' + esc(text) + '</div>';
  el.appendChild(entry);
  el.scrollTop = el.scrollHeight;
}

function downloadTranscript() {
  var entries = document.querySelectorAll('#transcript .transcript-entry');
  var md = '# Think-Pod Session\n\n';
  entries.forEach(function(e) {
    var speaker = e.querySelector('.speaker').textContent.trim();
    var text = e.querySelector('.text').textContent.trim();
    md += '**' + speaker + ':** ' + text + '\n\n';
  });
  var blob = new Blob([md], { type: 'text/markdown' });
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'thinkpod-session-' + (sessionId || 'draft') + '.md';
  a.click();
}

function downloadViewedTranscript() {
  if (!_viewedSession) return;
  var s = _viewedSession.session;
  var msgs = _viewedSession.messages;
  var name = _viewedSession.podcasterName;
  var md = '# Think-Pod Session — ' + name + ' × ' + s.guest_name + '\n';
  md += '**Topic:** ' + s.topic + '\n';
  md += '**Date:** ' + new Date(s.created_at).toLocaleDateString() + '\n';
  md += '**Turns:** ' + s.turns + '\n\n---\n\n';
  for (var i = 0; i < msgs.length; i++) {
    var m = msgs[i];
    if (m.role === 'system') continue;
    if (m.role === 'user' && m.turn_number === 0) continue;
    var speaker = m.role === 'assistant' ? '🎙️ ' + name : '🗣️ ' + s.guest_name;
    md += '**' + speaker + ':** ' + m.content + '\n\n';
  }
  var blob = new Blob([md], { type: 'text/markdown' });
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'thinkpod-' + s.podcaster + '-' + s.id.slice(0, 8) + '.md';
  a.click();
}

// ─── Helpers ─────────────────────────────────────────────────────────

function setStatus(cls, text) {
  var el = document.getElementById('status');
  el.className = 'status' + (cls ? ' ' + cls : '');
  el.textContent = text;
}

function esc(text) {
  var div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function showDashboard() {
  showScreen('dashboard-screen');
  loadSessions();
}

function renderAnalysisMarkdown(text) {
  // Simple markdown-ish rendering for analysis documents
  var html = esc(text);
  // Bold: **text**
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // Italic: *text*
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // Headers: ## text or ### text
  html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
  html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
  // Horizontal rules
  html = html.replace(/^---$/gm, '<hr>');
  // Paragraphs: double newline
  html = html.replace(/\n\n/g, '</p><p>');
  // Single newlines to <br>
  html = html.replace(/\n/g, '<br>');
  return '<p>' + html + '</p>';
}

function downloadAnalysis() {
  if (!lastAnalysis) return;
  var blob = new Blob([lastAnalysis], { type: 'text/markdown' });
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'thinkpod-reflection-' + (sessionId || 'session') + '.md';
  a.click();
}

async function viewAnalysis(id) {
  try {
    var resp = await authFetch(BASE + '/api/sessions/' + id + '/analysis');
    if (!resp.ok) throw new Error('No analysis found');
    var data = await resp.json();
    lastAnalysis = data.analysis;
    // Show in a simple alert-style or reuse end screen
    var contentEl = document.getElementById('analysis-content');
    var sectionEl = document.getElementById('analysis-section');
    if (contentEl && sectionEl) {
      contentEl.innerHTML = renderAnalysisMarkdown(data.analysis);
      sectionEl.style.display = 'block';
    }
    document.getElementById('summary').textContent = '';
    showScreen('end-screen');
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

document.addEventListener('keydown', function(e) {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) sendText();
});
