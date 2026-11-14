/**
 * Azentio Loan Intake Agent, Review Queue & Audit Ledger UI Controller
 */

document.addEventListener("DOMContentLoaded", () => {
  // Navigation Tabs
  const navTabs = document.querySelectorAll(".nav-tab");
  const tabPanes = document.querySelectorAll(".tab-pane");

  navTabs.forEach(tab => {
    tab.addEventListener("click", () => {
      const targetId = tab.dataset.tab;
      navTabs.forEach(t => t.classList.remove("active"));
      tabPanes.forEach(p => {
        p.classList.remove("active");
        p.style.display = "none";
      });

      tab.classList.add("active");
      const targetPane = document.getElementById(targetId);
      if (targetPane) {
        targetPane.classList.add("active");
        targetPane.style.display = "block";
      }

      if (targetId === "reviewTab") {
        fetchReviewQueue();
      } else if (targetId === "auditTab") {
        fetchAuditLog();
      }
    });
  });

  // Intake Elements
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

  const borrowerMsgSection = document.getElementById("borrowerMsgSection");
  const borrowerMsgText = document.getElementById("borrowerMsgText");
  const copyBorrowerMsgBtn = document.getElementById("copyBorrowerMsgBtn");

  const docRequestsSection = document.getElementById("docRequestsSection");
  const requestsList = document.getElementById("requestsList");

  const lowConfSection = document.getElementById("lowConfSection");
  const lowConfList = document.getElementById("lowConfList");

  const fieldsTableBody = document.getElementById("fieldsTableBody");
  const traceTimeline = document.getElementById("traceTimeline");

  // Review Queue Elements
  const openReviewCountBadge = document.getElementById("openReviewCountBadge");
  const reviewTableBody = document.getElementById("reviewTableBody");
  const queueEmptyState = document.getElementById("queueEmptyState");
  const reviewStatusFilter = document.getElementById("reviewStatusFilter");
  const refreshQueueBtn = document.getElementById("refreshQueueBtn");

  // Audit Elements
  const auditTableBody = document.getElementById("auditTableBody");
  const refreshAuditBtn = document.getElementById("refreshAuditBtn");

  // Modal Elements
  const resolveModal = document.getElementById("resolveModal");
  const closeModalBtn = document.getElementById("closeModalBtn");
  const cancelModalBtn = document.getElementById("cancelModalBtn");
  const submitResolveBtn = document.getElementById("submitResolveBtn");
  const modalPacketId = document.getElementById("modalPacketId");
  const modalFieldsContainer = document.getElementById("modalFieldsContainer");
  const reviewerNameInput = document.getElementById("reviewerNameInput");
  const reviewerDecisionSelect = document.getElementById("reviewerDecisionSelect");
  const reviewerNotesInput = document.getElementById("reviewerNotesInput");
  const modalErrorMsg = document.getElementById("modalErrorMsg");

  let currentActiveReviewItem = null;

  // Initialize Packets Dropdown & Open Count
  fetchPackets();
  updateOpenReviewCount();

  // Load packet dropdown
  async function fetchPackets() {
    try {
      const res = await fetch("/api/packets");
      if (!res.ok) return;
      const packets = await res.json();
      packets.forEach(pid => {
        const opt = document.createElement("option");
        opt.value = pid;
        opt.textContent = `${pid}.json`;
        packetDropdown.appendChild(opt);
      });
      if (packets.length > 0) {
        packetDropdown.value = packets[0];
        loadPacket(packets[0]);
      }
    } catch (e) {
      console.warn("Could not load sample packets list:", e);
    }
  }

  loadPacketBtn.addEventListener("click", () => {
    const sel = packetDropdown.value;
    if (sel) loadPacket(sel);
  });

  async function loadPacket(pid) {
    try {
      const res = await fetch(`/api/packets/${pid}`);
      if (!res.ok) throw new Error("Packet not found");
      const data = await res.json();
      packetJsonEditor.value = JSON.stringify(data, null, 2);
    } catch (err) {
      alert("Failed to load packet: " + err.message);
    }
  }

  // Run Intake Agent
  runAgentBtn.addEventListener("click", async () => {
    const rawJson = packetJsonEditor.value.trim();
    if (!rawJson) {
      alert("Please provide valid packet JSON.");
      return;
    }

    let packetObj;
    try {
      packetObj = JSON.parse(rawJson);
    } catch (e) {
      alert("Invalid JSON format. Please verify syntax.");
      return;
    }

    runAgentBtn.disabled = true;
    runAgentBtn.innerHTML = "<span>⏳ Running Agent Loop...</span>";
    const startTime = performance.now();

    try {
      const res = await fetch("/v1/packets/intake", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(packetObj),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Agent intake failed");
      }

      const decisionData = await res.json();
      const latency = Math.round(performance.now() - startTime);

      renderDecisionResults(decisionData, latency);

      if (decisionData.trace_id) {
        fetchTraceTimeline(decisionData.trace_id);
      }

      updateOpenReviewCount();
    } catch (err) {
      alert("Error: " + err.message);
    } finally {
      runAgentBtn.disabled = false;
      runAgentBtn.innerHTML = "<span>⚡ Run Intake Agent</span>";
    }
  });

  function renderDecisionResults(data, latency) {
    emptyState.style.display = "none";
    resultsContainer.style.display = "flex";
    decisionTimestamp.textContent = new Date().toLocaleTimeString();

    // Decision Banner
    decisionBanner.className = "decision-banner";
    const decision = data.decision || "HUMAN_REVIEW";
    decisionBanner.classList.add(decision.toLowerCase());
    decisionTitle.textContent = decision.replace("_", " ");
    latencyBadge.textContent = `${latency} ms`;

    if (data.overridden) {
      overrideBadge.style.display = "inline-block";
    } else {
      overrideBadge.style.display = "none";
    }

    // Borrower Notice Letter
    if (data.borrower_message) {
      borrowerMsgSection.style.display = "block";
      borrowerMsgText.textContent = data.borrower_message;
    } else {
      borrowerMsgSection.style.display = "none";
    }

    // Document Requests
    requestsList.innerHTML = "";
    if (data.document_requests && data.document_requests.length > 0) {
      docRequestsSection.style.display = "block";
      data.document_requests.forEach(req => {
        const li = document.createElement("li");
        li.innerHTML = `<strong>${req.requirement_id}</strong> <span>Reason: ${req.reason_code}</span>`;
        requestsList.appendChild(li);
      });
    } else {
      docRequestsSection.style.display = "none";
    }

    // Low confidence warnings
    if (data.low_confidence_fields && data.low_confidence_fields.length > 0) {
      lowConfSection.style.display = "block";
      lowConfList.textContent = `Flagged Fields: ${data.low_confidence_fields.join(", ")}`;
    } else {
      lowConfSection.style.display = "none";
    }

    // Fields Table
    fieldsTableBody.innerHTML = "";
    const fields = data.fields || {};
    Object.keys(fields).forEach(k => {
      const tr = document.createElement("tr");
      const tdKey = document.createElement("td");
      tdKey.textContent = k;
      const tdVal = document.createElement("td");
      tdVal.textContent = fields[k] !== null && fields[k] !== undefined ? fields[k] : "—";
      tr.appendChild(tdKey);
      tr.appendChild(tdVal);
      fieldsTableBody.appendChild(tr);
    });
  }

  async function fetchTraceTimeline(traceId) {
    traceTimeline.innerHTML = "<p class='text-muted'>Loading trace steps...</p>";
    try {
      const res = await fetch(`/v1/traces/${traceId}`);
      if (!res.ok) return;
      const traceData = await res.json();

      traceTimeline.innerHTML = "";
      (traceData.steps || []).forEach(step => {
        const item = document.createElement("div");
        item.className = "timeline-step" + (step.error ? " error" : "");
        item.innerHTML = `
          <div class="step-header">
            <span>Step ${step.step_number}: ${step.tool}</span>
            <span>${step.latency_ms} ms</span>
          </div>
          <div class="step-summary">${step.result_summary}</div>
        `;
        traceTimeline.appendChild(item);
      });
    } catch (e) {
      traceTimeline.innerHTML = "<p class='text-muted'>Trace details unavailable.</p>";
    }
  }

  if (copyBorrowerMsgBtn) {
    copyBorrowerMsgBtn.addEventListener("click", () => {
      const text = borrowerMsgText.textContent;
      navigator.clipboard.writeText(text).then(() => {
        copyBorrowerMsgBtn.textContent = "Copied!";
        setTimeout(() => copyBorrowerMsgBtn.textContent = "Copy Notice", 2000);
      });
    });
  }

  // -------------------------------------------------------------
  // Review Queue Operations
  // -------------------------------------------------------------
  async function updateOpenReviewCount() {
    try {
      const res = await fetch("/v1/review-items?status=open");
      if (!res.ok) return;
      const items = await res.json();
      openReviewCountBadge.textContent = items.length;
    } catch (e) {}
  }

  async function fetchReviewQueue() {
    const status = reviewStatusFilter.value;
    const url = status ? `/v1/review-items?status=${status}` : "/v1/review-items";
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error("Failed to fetch review queue");
      const items = await res.json();

      reviewTableBody.innerHTML = "";
      if (items.length === 0) {
        queueEmptyState.style.display = "block";
      } else {
        queueEmptyState.style.display = "none";
        items.forEach(item => {
          const tr = document.createElement("tr");
          const isResolved = item.status === "resolved";
          tr.innerHTML = `
            <td><code>${item.id}</code></td>
            <td><strong>${item.packet_id}</strong></td>
            <td><span class="badge ${isResolved ? 'badge-resolved' : 'badge-open'}">${item.status.toUpperCase()}</span></td>
            <td>${(item.low_confidence_fields || []).join(", ") || "—"}</td>
            <td>${new Date(item.created_at).toLocaleString()}</td>
            <td>
              ${isResolved ? 
                `<em>Resolved (${item.decision})</em>` : 
                `<button class="btn btn-sm btn-primary resolve-btn" data-id="${item.id}">Review & Resolve</button>`
              }
            </td>
          `;
          reviewTableBody.appendChild(tr);
        });

        document.querySelectorAll(".resolve-btn").forEach(btn => {
          btn.addEventListener("click", () => {
            const id = btn.dataset.id;
            const item = items.find(i => i.id === id);
            if (item) openResolveModal(item);
          });
        });
      }
      updateOpenReviewCount();
    } catch (err) {
      alert("Error fetching queue: " + err.message);
    }
  }

  refreshQueueBtn.addEventListener("click", fetchReviewQueue);
  reviewStatusFilter.addEventListener("change", fetchReviewQueue);

  function openResolveModal(item) {
    currentActiveReviewItem = item;
    modalPacketId.textContent = item.packet_id;
    modalErrorMsg.style.display = "none";
    modalFieldsContainer.innerHTML = "";

    const lowConfFields = item.low_confidence_fields || [];
    const pktData = item.packet_data || {};
    const appForm = pktData.application_form || "";

    if (lowConfFields.length === 0) {
      modalFieldsContainer.innerHTML = "<p class='modal-desc'>No specific low confidence fields flagged. You may verify and submit resolution.</p>";
    } else {
      lowConfFields.forEach(field => {
        const group = document.createElement("div");
        group.className = "modal-form-group";
        group.innerHTML = `
          <label>Field: <strong>${field}</strong> (Low Confidence)</label>
          <input type="text" class="corrected-field-input" data-field="${field}" placeholder="Enter corrected value...">
        `;
        modalFieldsContainer.appendChild(group);
      });
    }

    resolveModal.style.display = "flex";
  }

  function closeResolveModal() {
    resolveModal.style.display = "none";
    currentActiveReviewItem = null;
  }

  closeModalBtn.addEventListener("click", closeResolveModal);
  cancelModalBtn.addEventListener("click", closeResolveModal);

  submitResolveBtn.addEventListener("click", async () => {
    if (!currentActiveReviewItem) return;

    const reviewer = reviewerNameInput.value.trim();
    if (!reviewer) {
      alert("Reviewer name is required.");
      return;
    }

    const correctedFields = {};
    document.querySelectorAll(".corrected-field-input").forEach(input => {
      const field = input.dataset.field;
      const val = input.value.trim();
      if (val) correctedFields[field] = val;
    });

    const decision = reviewerDecisionSelect.value || null;
    const notes = reviewerNotesInput.value.trim() || null;

    submitResolveBtn.disabled = true;
    submitResolveBtn.textContent = "Resolving...";

    try {
      const res = await fetch(`/v1/review-items/${currentActiveReviewItem.id}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reviewer,
          decision,
          corrected_fields: correctedFields,
          notes,
        }),
      });

      if (res.status === 409) {
        const err = await res.json();
        modalErrorMsg.style.display = "block";
        modalErrorMsg.textContent = "409 Conflict: " + (err.detail || "Item is already resolved.");
        return;
      }

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to resolve item");
      }

      alert(`Application ${currentActiveReviewItem.packet_id} successfully resolved!`);
      closeResolveModal();
      fetchReviewQueue();
      updateOpenReviewCount();
    } catch (e) {
      modalErrorMsg.style.display = "block";
      modalErrorMsg.textContent = e.message;
    } finally {
      submitResolveBtn.disabled = false;
      submitResolveBtn.textContent = "Submit Resolution";
    }
  });

  // -------------------------------------------------------------
  // Regulatory Audit Log Operations
  // -------------------------------------------------------------
  async function fetchAuditLog() {
    try {
      const res = await fetch("/v1/audit-log?limit=50");
      if (!res.ok) throw new Error("Failed to fetch audit log");
      const logs = await res.json();

      auditTableBody.innerHTML = "";
      logs.forEach(log => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${log.id}</td>
          <td>${new Date(log.timestamp).toLocaleString()}</td>
          <td><span class="badge badge-provider">${log.actor.toUpperCase()}</span></td>
          <td><strong>${log.packet_id}</strong></td>
          <td><span class="badge">${log.decision}</span></td>
          <td>${(log.reason_codes || []).join(", ") || "—"}</td>
          <td><small><code>${JSON.stringify(log.details)}</code></small></td>
        `;
        auditTableBody.appendChild(tr);
      });
    } catch (err) {
      alert("Error fetching audit log: " + err.message);
    }
  }

  refreshAuditBtn.addEventListener("click", fetchAuditLog);
});
