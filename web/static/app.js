// Azentio Loan Intake Agent - Web Console Controller

document.addEventListener("DOMContentLoaded", () => {
  const packetDropdown = document.getElementById("packetDropdown");
  const loadPacketBtn = document.getElementById("loadPacketBtn");
  const packetJsonEditor = document.getElementById("packetJsonEditor");
  const runAgentBtn = document.getElementById("runAgentBtn");

  const emptyState = document.getElementById("emptyState");
  const resultsContainer = document.getElementById("resultsContainer");

  const decisionBanner = document.getElementById("decisionBanner");
  const decisionTitle = document.getElementById("decisionTitle");
  const overrideBadge = document.getElementById("overrideBadge");
  const latencyBadge = document.getElementById("latencyBadge");
  const decisionTimestamp = document.getElementById("decisionTimestamp");

  const docRequestsSection = document.getElementById("docRequestsSection");
  const requestsList = document.getElementById("requestsList");

  const lowConfSection = document.getElementById("lowConfSection");
  const lowConfList = document.getElementById("lowConfList");

  const fieldsTableBody = document.getElementById("fieldsTableBody");
  const traceIdLabel = document.getElementById("traceIdLabel");
  const traceTimeline = document.getElementById("traceTimeline");

  // 1. Fetch available packets list
  fetch("/api/packets")
    .then(r => r.json())
    .then(packets => {
      packets.forEach(pid => {
        const opt = document.createElement("option");
        opt.value = pid;
        opt.textContent = `${pid}.json`;
        packetDropdown.appendChild(opt);
      });
      // Pre-select first packet if available
      if (packets.length > 0) {
        packetDropdown.value = packets[0];
        loadPacket(packets[0]);
      }
    })
    .catch(err => console.error("Error loading packets list:", err));

  // 2. Load packet into editor
  function loadPacket(pid) {
    if (!pid) return;
    fetch(`/api/packets/${pid}`)
      .then(r => r.json())
      .then(data => {
        packetJsonEditor.value = JSON.stringify(data, null, 2);
      })
      .catch(err => console.error("Error loading packet content:", err));
  }

  loadPacketBtn.addEventListener("click", () => {
    loadPacket(packetDropdown.value);
  });

  packetDropdown.addEventListener("change", () => {
    loadPacket(packetDropdown.value);
  });

  // 3. Run Agent Execution
  runAgentBtn.addEventListener("click", async () => {
    const rawJson = packetJsonEditor.value.trim();
    if (!rawJson) {
      alert("Please provide or load a packet JSON first.");
      return;
    }

    let parsedPacket;
    try {
      parsedPacket = JSON.parse(rawJson);
    } catch (e) {
      alert("Invalid JSON format in packet editor. Please correct syntax.");
      return;
    }

    runAgentBtn.disabled = true;
    runAgentBtn.textContent = "Processing...";

    try {
      const res = await fetch("/v1/packets/intake", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsedPacket)
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Agent execution failed");
      }

      const decisionData = await res.json();
      displayResults(decisionData);

      // Fetch trace details
      if (decisionData.trace_id) {
        const traceRes = await fetch(`/v1/traces/${decisionData.trace_id}`);
        if (traceRes.ok) {
          const traceData = await traceRes.json();
          displayTrace(traceData);
        }
      }

    } catch (err) {
      alert(`Error: ${err.message}`);
    } finally {
      runAgentBtn.disabled = false;
      runAgentBtn.textContent = "⚡ Run Intake Agent";
    }
  });

  function displayResults(data) {
    emptyState.style.display = "none";
    resultsContainer.style.display = "flex";
    decisionTimestamp.textContent = new Date().toLocaleTimeString();

    // Decision Title & Color Banner
    decisionTitle.textContent = data.decision;
    decisionBanner.className = "decision-banner";
    if (data.decision === "COMPLETE") {
      decisionBanner.classList.add("decision-complete");
    } else if (data.decision === "REQUEST_DOCUMENTS") {
      decisionBanner.classList.add("decision-request");
    } else {
      decisionBanner.classList.add("decision-review");
    }

    // Override badge
    if (data.overridden) {
      overrideBadge.style.display = "inline-block";
    } else {
      overrideBadge.style.display = "none";
    }

    // Requests List
    if (data.document_requests && data.document_requests.length > 0) {
      docRequestsSection.style.display = "block";
      requestsList.innerHTML = "";
      data.document_requests.forEach(req => {
        const li = document.createElement("li");
        li.className = "request-item";
        li.innerHTML = `
          <span>Requirement: <strong>${req.requirement_id}</strong></span>
          <span class="reason-tag">${req.reason_code}</span>
        `;
        requestsList.appendChild(li);
      });
    } else {
      docRequestsSection.style.display = "none";
    }

    // Low Confidence Warnings
    if (data.low_confidence_fields && data.low_confidence_fields.length > 0) {
      lowConfSection.style.display = "block";
      lowConfList.textContent = `The following fields had low confidence or unparseable values: ${data.low_confidence_fields.join(", ")}`;
    } else {
      lowConfSection.style.display = "none";
    }

    // Fields Table
    fieldsTableBody.innerHTML = "";
    const fields = data.fields || {};
    Object.keys(fields).forEach(key => {
      const tr = document.createElement("tr");
      const val = fields[key] !== null ? fields[key] : "<span style='color: #ef4444;'>null (unresolved)</span>";
      tr.innerHTML = `
        <td style="font-family: 'JetBrains Mono', monospace; font-weight: 500;">${key}</td>
        <td>${val}</td>
      `;
      fieldsTableBody.appendChild(tr);
    });

    traceIdLabel.textContent = `Trace ID: ${data.trace_id}`;
  }

  function displayTrace(trace) {
    latencyBadge.textContent = `${trace.total_latency_ms || 0} ms`;
    traceTimeline.innerHTML = "";

    const steps = trace.steps || [];
    steps.forEach(step => {
      const div = document.createElement("div");
      div.className = "trace-step";
      div.innerHTML = `
        <div>
          <span class="trace-step-name">Step ${step.step_number}: ${step.tool}</span>
          <div style="font-size: 0.75rem; color: #cbd5e1; margin-top: 0.2rem;">${step.result_summary}</div>
        </div>
        <div class="trace-step-meta">
          <span>${step.latency_ms} ms</span>
        </div>
      `;
      traceTimeline.appendChild(div);
    });
  }
});

