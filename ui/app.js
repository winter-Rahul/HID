// HID Kiosk Interactive Client Application with Context & Offline Fail-Safe

document.addEventListener('DOMContentLoaded', () => {
  // DOM Elements
  const btnScan = document.getElementById('btnScan');
  const chkAutoScan = document.getElementById('chkAutoScan');
  const scenarioSelect = document.getElementById('scenarioSelect');
  const cameraStream = document.getElementById('cameraStream');

  // Auto-reconnect camera stream if ever interrupted
  cameraStream.onerror = () => {
    console.warn("Camera stream interrupted. Auto-reconnecting in 500ms...");
    setTimeout(() => {
      cameraStream.src = `/api/stream?t=${Date.now()}`;
    }, 500);
  };

  const chkOnlineToggle = document.getElementById('chkOnlineToggle');
  const txtOnlineStatus = document.getElementById('txtOnlineStatus');
  const offlineAlertBanner = document.getElementById('offlineAlertBanner');

  const outcomeCard = document.getElementById('outcomeCard');
  const outcomeIcon = document.getElementById('outcomeIcon');
  const outcomeVerdict = document.getElementById('outcomeVerdict');
  const outcomeSub = document.getElementById('outcomeSub');
  const outcomeReason = document.getElementById('outcomeReason');

  const metricTime = document.getElementById('metricTime');
  const metricConfidence = document.getElementById('metricConfidence');
  const metricUser = document.getElementById('metricUser');

  // Stage Chips
  const stageCaptureVal = document.getElementById('stageCaptureVal');
  const stagePADVal = document.getElementById('stagePADVal');
  const stageIDVal = document.getElementById('stageIDVal');
  const stageScheduleVal = document.getElementById('stageScheduleVal');
  const stageDecisionVal = document.getElementById('stageDecisionVal');

  // Latency Bars
  const latBarCapture = document.getElementById('latBarCapture');
  const latBarPAD = document.getElementById('latBarPAD');
  const latBarID = document.getElementById('latBarID');
  const latBarDecision = document.getElementById('latBarDecision');
  const latValCapture = document.getElementById('latValCapture');
  const latValPAD = document.getElementById('latValPAD');
  const latValID = document.getElementById('latValID');
  const latValTotal = document.getElementById('latValTotal');

  // Modals & Drawers
  const btnEnrollModal = document.getElementById('btnEnrollModal');
  const enrollModal = document.getElementById('enrollModal');
  const btnCloseEnroll = document.getElementById('btnCloseEnroll');
  const txtEnrollName = document.getElementById('txtEnrollName');
  const btnSubmitEnroll = document.getElementById('btnSubmitEnroll');
  const enrollStatus = document.getElementById('enrollStatus');
  const userList = document.getElementById('userList');
  const userCount = document.getElementById('userCount');

  const btnJudgeDrawer = document.getElementById('btnJudgeDrawer');
  const judgeDrawer = document.getElementById('judgeDrawer');
  const btnCloseJudge = document.getElementById('btnCloseJudge');
  const btnRefreshMetrics = document.getElementById('btnRefreshMetrics');
  const btnResetMetrics = document.getElementById('btnResetMetrics');
  const metricsTableBody = document.getElementById('metricsTableBody');

  let isScanning = false;
  let autoScanTimer = null;
  let adminToken = null;
  let stepUpChallenge = null;

  function showSyncStatus(status) {
    document.getElementById('txtSyncStatus').textContent = `Mock audit: ${status.pending_sync_count ?? '?'} pending, ${status.mock_synced_count ?? '?'} synced`;
  }

  async function managementFetch(url, options = {}) {
    if (!adminToken) adminToken = window.prompt('Enter the kiosk management token:');
    if (!adminToken) throw new Error('Management token required');
    const headers = new Headers(options.headers || {});
    headers.set('X-Admin-Token', adminToken);
    const response = await fetch(url, { ...options, headers });
    if (!response.ok) {
      if (response.status === 401) adminToken = null;
      throw new Error(`Management request failed (HTTP ${response.status})`);
    }
    return response;
  }

  // 1. Online / Offline Toggle
  chkOnlineToggle.addEventListener('change', async (e) => {
    const isOnline = e.target.checked;
    txtOnlineStatus.textContent = isOnline ? "Online" : "Offline";
    if (isOnline) {
      offlineAlertBanner.classList.add('hidden');
    } else {
      offlineAlertBanner.classList.remove('hidden');
    }

    const formData = new FormData();
    formData.append('enable_offline', (!isOnline).toString());
    try {
      const response = await managementFetch('/api/toggle_offline', { method: 'POST', body: formData });
      showSyncStatus(await response.json());
    } catch (err) {
      e.target.checked = !isOnline;
      txtOnlineStatus.textContent = isOnline ? 'Offline' : 'Online';
      offlineAlertBanner.classList.toggle('hidden', !isOnline);
      alert(err.message);
    }
  });

  // 2. Authentication Execution
  async function performAuthentication() {
    if (isScanning) return;
    isScanning = true;
    btnScan.disabled = true;
    btnScan.innerHTML = `<span class="btn-icon">⏳</span> Analyzing...`;

    // Reset stages
    stageCaptureVal.textContent = "Capturing burst...";
    stagePADVal.textContent = "Processing...";
    stageIDVal.textContent = "Waiting...";
    stageScheduleVal.textContent = "Waiting...";
    stageDecisionVal.textContent = "Waiting...";

    try {
      const scenario = scenarioSelect.value;
      const request = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario: scenario })
      };
      const resp = scenario === 'schedule_violation' || scenario === 'schedule_denied'
        ? await managementFetch('/api/authenticate', request)
        : await fetch('/api/authenticate', request);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      displayResult(data);
      fetch('/health').then(r => r.ok ? r.json() : Promise.reject()).then(showSyncStatus).catch(() => {});
      if (data.step_up_challenge) {
        stepUpChallenge = data.step_up_challenge;
        document.getElementById('stepUpPin').value = '';
        document.getElementById('stepUpStatus').textContent = '';
        document.getElementById('stepUpModal').classList.remove('hidden');
      }
    } catch (err) {
      console.error(err);
      chkAutoScan.checked = false;
      if (autoScanTimer) clearInterval(autoScanTimer);
      autoScanTimer = null;
      outcomeVerdict.textContent = "CONNECTION ERROR";
      outcomeReason.textContent = "Could not reach kiosk inference service.";
    } finally {
      isScanning = false;
      btnScan.disabled = false;
      btnScan.innerHTML = `<span class="btn-icon">⚡</span> Scan &amp; Authenticate`;
    }
  }

  // 3. Display Decision Result
  function displayResult(res) {
    outcomeCard.className = "outcome-card";

    // Format Decision Time
    const sec = (res.latency_ms / 1000).toFixed(2);
    metricTime.textContent = `${sec} s`;
    metricConfidence.textContent = Number.isFinite(res.liveness_score) ? res.liveness_score.toFixed(2) : '--';
    metricUser.textContent = res.matched_user || "--";
    outcomeReason.textContent = res.message || res.reason_code;

    // Stage updates
    const t = res.timings || {};
    stageCaptureVal.textContent = `✓ ${t.capture_ms || 0} ms`;
    stagePADVal.textContent = Number.isFinite(res.liveness_score) ? `Liveness score: ${res.liveness_score.toFixed(2)}` : 'Unavailable';
    stageIDVal.textContent = Number.isFinite(res.identity_score) ? `Similarity: ${res.identity_score.toFixed(2)}${res.matched_user ? ` (${res.matched_user})` : ''}` : 'Unavailable';
    stageScheduleVal.textContent = res.schedule_allowed ? `✓ Authorized` : `✗ Denied (${res.schedule_details || 'Out of window'})`;
    stageDecisionVal.textContent = `✓ ${res.decision}`;

    // Latency Bars
    const totalMs = Math.max(res.latency_ms, 1);
    const cMs = t.capture_ms || 0;
    const pMs = t.detect_pad_ms || 0;
    const iMs = t.identity_ms || 0;
    const dMs = t.decision_ms || 0;

    latBarCapture.style.width = `${Math.min(100, (cMs / totalMs) * 100)}%`;
    latBarPAD.style.width = `${Math.min(100, (pMs / totalMs) * 100)}%`;
    latBarID.style.width = `${Math.min(100, (iMs / totalMs) * 100)}%`;
    latBarDecision.style.width = `${Math.min(100, (dMs / totalMs) * 100)}%`;

    latValCapture.textContent = `${cMs} ms`;
    latValPAD.textContent = `${pMs} ms`;
    latValID.textContent = `${iMs} ms`;
    latValTotal.textContent = `${res.latency_ms} ms`;

    // Apply State Styles
    if (res.decision === "ALLOW") {
      outcomeCard.classList.add("state-allow");
      outcomeIcon.textContent = "✅";
      outcomeVerdict.textContent = "ALLOW";
      outcomeSub.textContent = res.online_mode ? "Live person detected & identity verified" : "Live person verified via Offline Local Store";
    } else if (res.decision === "STEP_UP_VERIFICATION" || res.decision === "REQUEST_VERIFICATION") {
      outcomeCard.classList.add("state-request");
      outcomeIcon.textContent = "⚠️";
      outcomeVerdict.textContent = "STEP-UP VERIFICATION";
      outcomeSub.textContent = "Borderline confidence or offline verification needed.";
    } else {
      outcomeCard.classList.add("state-deny");
      outcomeIcon.textContent = "⛔";
      outcomeVerdict.textContent = "DENY";
      outcomeSub.textContent = res.reason_code === "SCHEDULE_VIOLATION" ? "Access Denied: Permitted schedule window violation" : "Presentation attack detected or unauthorized identity.";
    }
  }

  // 4. User Enrollment Functions
  async function loadUsers() {
    try {
      const resp = await managementFetch('/api/users');
      const data = await resp.json();
      userCount.textContent = data.users.length;
      userList.innerHTML = '';
      data.users.forEach(u => {
        const sched = (data.schedules && data.schedules[u]) ? data.schedules[u] : null;
        const windowStr = sched ? `${sched.start_hour}:00 - ${sched.end_hour}:00 (${sched.days.join(',')})` : 'No authorized schedule';
        const li = document.createElement('li');
        const info = document.createElement('div');
        info.className = 'user-info';
        const title = document.createElement('b');
        title.textContent = `👤 ${u}`;
        const schedule = document.createElement('small');
        schedule.style.color = '#94a3b8';
        schedule.textContent = `Schedule: ${windowStr}`;
        info.append(title, document.createElement('br'), schedule);
        const button = document.createElement('button');
        button.className = 'btn btn-secondary btn-sm';
        button.textContent = 'Delete';
        button.addEventListener('click', () => window.removeUser(u));
        const pin = document.createElement('input');
        pin.type = 'password';
        pin.inputMode = 'numeric';
        pin.autocomplete = 'new-password';
        pin.placeholder = 'Set PIN (6–12 digits)';
        pin.setAttribute('aria-label', `Set PIN for ${u}`);
        const pinButton = document.createElement('button');
        pinButton.className = 'btn btn-secondary btn-sm';
        pinButton.textContent = 'Save PIN';
        pinButton.addEventListener('click', async () => {
          const form = new FormData();
          form.append('pin', pin.value);
          pin.value = '';
          try {
            await managementFetch(`/api/users/${encodeURIComponent(u)}/pin`, { method: 'POST', body: form });
            alert('PIN saved.');
          } catch (err) { alert(err.message); }
        });
        const actions = document.createElement('div');
        actions.className = 'user-actions';
        actions.append(pin, pinButton, button);
        li.append(info, actions);
        userList.appendChild(li);
      });
    } catch (e) {
      console.error(e);
    }
  }

  window.removeUser = async function(name) {
    try {
      const response = await managementFetch(`/api/users/${encodeURIComponent(name)}`, { method: 'DELETE' });
      const result = await response.json();
      if (!result.success) throw new Error(result.message || `Could not delete ${name}.`);
      await loadUsers();
      alert(result.message || `Deleted ${name}.`);
    } catch (err) { alert(err.message); }
  };

  btnSubmitEnroll.addEventListener('click', async () => {
    const name = txtEnrollName.value.trim();
    if (!name) {
      enrollStatus.textContent = "Please enter an employee name.";
      enrollStatus.style.color = "#f87171";
      return;
    }

    enrollStatus.textContent = "Scanning face from camera...";
    enrollStatus.style.color = "#38bdf8";
    btnSubmitEnroll.disabled = true;

    try {
      const formData = new FormData();
      formData.append('name', name);
      formData.append('pin', document.getElementById('txtEnrollPin').value);
      const weekday = document.getElementById('enrollSchedule').value === 'weekday';
      formData.append('start_hour', weekday ? '8' : '0');
      formData.append('end_hour', weekday ? '18' : '24');
      formData.append('days', weekday ? 'Mon,Tue,Wed,Thu,Fri' : 'Mon,Tue,Wed,Thu,Fri,Sat,Sun');

      const resp = await managementFetch('/api/enroll', { method: 'POST', body: formData });
      if (!resp.ok) {
        throw new Error(`Server returned HTTP ${resp.status}`);
      }
      const data = await resp.json();

      if (data.success) {
        enrollStatus.textContent = `✓ ${data.message}`;
        enrollStatus.style.color = "#4ade80";
        txtEnrollName.value = '';
        document.getElementById('txtEnrollPin').value = '';
        loadUsers();
      } else {
        enrollStatus.textContent = `✗ ${data.message}`;
        enrollStatus.style.color = "#f87171";
      }
    } catch (err) {
      console.error(err);
      enrollStatus.textContent = `✗ Enrollment failed: ${err.message}`;
      enrollStatus.style.color = "#f87171";
    } finally {
      btnSubmitEnroll.disabled = false;
    }
  });

  // 5. Judge Metrics Drawer
  async function refreshMetrics() {
    try {
      const resp = await managementFetch('/api/metrics');
      const raw = await resp.json();
      const data = raw.metrics;
      metricsTableBody.innerHTML = '';

      const labels = {
        "genuine_live": "Genuine Live Person",
        "printed_photo": "Printed Photo (Paper)",
        "screen_replay": "Screen Replay (Phone)",
        "video_replay": "Video Replay (Tablet)",
        "paper_mask": "Paper Mask (Eye Cutout)",
        "schedule_violation": "Schedule Violation (Context Deny)",
        "unknown_person": "Unknown Live Impostor"
      };

      for (const [k, v] of Object.entries(data)) {
        const tr = document.createElement('tr');
        const rateLabel = k === "genuine_live" ? `DENY: ${v.end_to_end_deny_rate ?? 'N/A'}%` : `ALLOW: ${v.end_to_end_allow_rate ?? 'N/A'}%`;
        tr.innerHTML = `
          <td><b>${labels[k] || k}</b></td>
          <td>${v.presentations}</td>
          <td style="color:#10b981">${v.allow}</td>
          <td style="color:#f59e0b">${v.request}</td>
          <td style="color:#ef4444">${v.deny}</td>
          <td><b>${rateLabel}</b></td>
          <td>${v.p50_latency_ms} ms</td>
          <td>${v.p95_latency_ms} ms</td>
        `;
        metricsTableBody.appendChild(tr);
      }
    } catch (e) {
      console.error(e);
    }
  }

  btnResetMetrics.addEventListener('click', async () => {
    if (confirm("Reset all test metrics?")) {
      try {
        await managementFetch('/api/reset_metrics', { method: 'POST' });
        refreshMetrics();
      } catch (err) { alert(err.message); }
    }
  });

  // Event Listeners
  btnScan.addEventListener('click', performAuthentication);

  document.addEventListener('keydown', (e) => {
    if (e.code === 'Space' && !['INPUT', 'SELECT'].includes(document.activeElement.tagName)) {
      e.preventDefault();
      performAuthentication();
    }
  });

  chkAutoScan.addEventListener('change', (e) => {
    if (e.target.checked) {
      autoScanTimer = setInterval(performAuthentication, 3500);
      performAuthentication();
    } else {
      if (autoScanTimer) clearInterval(autoScanTimer);
    }
  });

  btnEnrollModal.addEventListener('click', () => {
    enrollModal.classList.remove('hidden');
    loadUsers();
  });
  btnCloseEnroll.addEventListener('click', () => enrollModal.classList.add('hidden'));

  btnJudgeDrawer.addEventListener('click', () => {
    judgeDrawer.classList.remove('hidden');
    refreshMetrics();
  });
  btnCloseJudge.addEventListener('click', () => judgeDrawer.classList.add('hidden'));
  btnRefreshMetrics.addEventListener('click', refreshMetrics);
  document.getElementById('btnCancelStepUp').addEventListener('click', () => {
    stepUpChallenge = null;
    document.getElementById('stepUpModal').classList.add('hidden');
  });
  document.getElementById('btnVerifyStepUp').addEventListener('click', async () => {
    const pin = document.getElementById('stepUpPin').value;
    document.getElementById('stepUpPin').value = '';
    const challenge = stepUpChallenge;
    stepUpChallenge = null;
    try {
      const resp = await fetch('/api/step-up', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({challenge, pin}) });
      if (!resp.ok) throw new Error('Verification unavailable');
      const result = await resp.json();
      document.getElementById('stepUpModal').classList.add('hidden');
      outcomeCard.className = `outcome-card ${result.decision === 'ALLOW' ? 'state-allow' : 'state-deny'}`;
      outcomeVerdict.textContent = result.decision;
      outcomeReason.textContent = result.message;
      outcomeSub.textContent = result.decision === 'ALLOW' ? 'Secondary credential verified.' : 'Please start a new scan.';
      outcomeIcon.textContent = result.decision === 'ALLOW' ? '✅' : '⛔';
    } catch (err) {
      document.getElementById('stepUpStatus').textContent = 'Verification failed. Start a new scan.';
    }
  });
  fetch('/health').then(response => {
    if (!response.ok) throw new Error('Health check failed');
    return response.json();
  }).then(status => {
    showSyncStatus(status);
    chkOnlineToggle.checked = status.online_mode;
    txtOnlineStatus.textContent = status.online_mode ? 'Online' : 'Offline';
    offlineAlertBanner.classList.toggle('hidden', status.online_mode);
  }).catch(console.error);

});
