// HID Kiosk Interactive Client Application with Context & Offline Fail-Safe

document.addEventListener('DOMContentLoaded', () => {
  // DOM Elements
  const btnScan = document.getElementById('btnScan');
  const chkAutoScan = document.getElementById('chkAutoScan');
  const scenarioSelect = document.getElementById('scenarioSelect');

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
    await fetch('/api/toggle_offline', { method: 'POST', body: formData });
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
      const resp = await fetch('/api/authenticate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario: scenario })
      });
      const data = await resp.json();
      displayResult(data);
    } catch (err) {
      console.error(err);
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
    metricConfidence.textContent = (res.confidence || 0.0).toFixed(2);
    metricUser.textContent = res.matched_user || "--";
    outcomeReason.textContent = res.message || res.reason_code;

    // Stage updates
    const t = res.timings || {};
    stageCaptureVal.textContent = `✓ ${t.capture_ms || 0} ms`;
    stagePADVal.textContent = `p_live: ${(res.liveness_score || 0).toFixed(2)}`;
    stageIDVal.textContent = res.matched_user ? `✓ ${res.matched_user} (${(res.identity_score || 0).toFixed(2)})` : `No Match`;
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
      const resp = await fetch('/api/users');
      const data = await resp.json();
      userCount.textContent = data.users.length;
      userList.innerHTML = '';
      data.users.forEach(u => {
        const sched = (data.schedules && data.schedules[u]) ? data.schedules[u] : null;
        const windowStr = sched ? `${sched.start_hour}:00 - ${sched.end_hour}:00 (${sched.days.join(',')})` : '08:00 - 18:00 (Standard)';
        const li = document.createElement('li');
        li.innerHTML = `
          <div>
            <b>👤 ${u}</b><br>
            <small style="color:#94a3b8">Schedule: ${windowStr}</small>
          </div>
          <button class="btn btn-secondary btn-sm" onclick="removeUser('${u}')">Delete</button>
        `;
        userList.appendChild(li);
      });
    } catch (e) {
      console.error(e);
    }
  }

  window.removeUser = async function(name) {
    await fetch(`/api/users/${encodeURIComponent(name)}`, { method: 'DELETE' });
    loadUsers();
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

    const formData = new FormData();
    formData.append('name', name);

    const resp = await fetch('/api/enroll', { method: 'POST', body: formData });
    const data = await resp.json();

    if (data.success) {
      enrollStatus.textContent = `✓ ${data.message}`;
      enrollStatus.style.color = "#4ade80";
      txtEnrollName.value = '';
      loadUsers();
    } else {
      enrollStatus.textContent = `✗ ${data.message}`;
      enrollStatus.style.color = "#f87171";
    }
  });

  // 5. Judge Metrics Drawer
  async function refreshMetrics() {
    try {
      const resp = await fetch('/api/metrics');
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
        const rateLabel = k === "genuine_live" ? `BPCER: ${v.bpcer}%` : `APCER: ${v.apcer}%`;
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
      await fetch('/api/reset_metrics', { method: 'POST' });
      refreshMetrics();
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

  // Initial load
  loadUsers();
});
