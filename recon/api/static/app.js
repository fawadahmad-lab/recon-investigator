"use strict";

const COLUMN_FIELDS = [
  "date",
  "amount",
  "debit",
  "credit",
  "reference",
  "description",
  "currency",
  "counterparty",
];
const STAGES = ["parse", "normalize", "match", "investigate", "report"];
const KPI_FIELDS = [
  ["matched", "Matched"],
  ["discrepancies", "Discrepancies"],
  ["high_severity", "High severity"],
  ["ai_verified", "AI verified"],
  ["fallback", "Verifier fallback"],
];
const ALL_VALUE = "all";
const DASH = "—";

const els = {
  stepper: document.getElementById("stepper"),
  runMeta: document.getElementById("run-meta"),
  errorAlert: document.getElementById("error-alert"),
  runButton: document.getElementById("run-button"),
  demoButton: document.getElementById("demo-button"),
  mappingFields: document.getElementById("mapping-fields"),
  results: document.getElementById("results"),
  kpiGrid: document.getElementById("kpi-grid"),
  showMatched: document.getElementById("show-matched"),
  typeFilter: document.getElementById("type-filter"),
  severityFilter: document.getElementById("severity-filter"),
  rowCount: document.getElementById("row-count"),
  findingsBody: document.getElementById("findings-body"),
  emptyState: document.getElementById("empty-state"),
  reportLink: document.getElementById("report-link"),
};

let findings = [];

function setStepper(status, stage, skipped) {
  const index = stage ? STAGES.indexOf(stage) : -1;
  STAGES.forEach((name, position) => {
    const step = els.stepper.querySelector(`[data-stage="${name}"]`);
    let className = "step";
    if (status === "running") {
      className += position === 0 ? " is-current" : "";
    } else if (status === "done") {
      className += skipped && name === "investigate" ? " is-skipped" : " is-done";
    } else if (status === "failed" && index >= 0) {
      if (position < index) {
        className += " is-done";
      } else if (position === index) {
        className += " is-failed";
      }
    }
    step.className = className;
  });
}

function showError(message) {
  els.errorAlert.textContent = message;
  els.errorAlert.hidden = false;
}

function clearError() {
  els.errorAlert.textContent = "";
  els.errorAlert.hidden = true;
}

function setBusy(busy) {
  els.runButton.disabled = busy;
  els.demoButton.disabled = busy;
}

function formatBytes(size) {
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function selectedFile(side) {
  return document.getElementById(`${side}-file`).files[0] || null;
}

function paintZone(side) {
  const zone = document.getElementById(`${side}-zone`);
  const text = document.getElementById(`${side}-file-text`);
  const file = selectedFile(side);
  zone.classList.toggle("has-file", Boolean(file));
  zone.classList.toggle("is-error", Boolean(file) && file.size === 0);
  if (file) {
    text.textContent = `${file.name} · ${formatBytes(file.size)}`;
  } else {
    text.textContent = "No file selected";
  }
}

function setupZone(side) {
  const zone = document.getElementById(`${side}-zone`);
  const input = document.getElementById(`${side}-file`);
  input.addEventListener("change", () => paintZone(side));
  zone.addEventListener("dragover", (event) => {
    event.preventDefault();
    zone.classList.add("is-drag");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("is-drag"));
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("is-drag");
    if (event.dataTransfer && event.dataTransfer.files.length) {
      input.files = event.dataTransfer.files;
      paintZone(side);
    }
  });
}

function buildMappingFields() {
  COLUMN_FIELDS.forEach((field) => {
    const wrap = document.createElement("div");
    wrap.className = "field";
    const label = document.createElement("label");
    label.className = "label";
    label.htmlFor = `map-${field}`;
    label.textContent = field;
    const input = document.createElement("input");
    input.id = `map-${field}`;
    input.autocomplete = "off";
    input.spellcheck = false;
    wrap.append(label, input);
    els.mappingFields.append(wrap);
  });
}

function columnMapJson() {
  const mapping = {};
  COLUMN_FIELDS.forEach((field) => {
    const value = document.getElementById(`map-${field}`).value.trim();
    if (value) {
      mapping[field] = value;
    }
  });
  return Object.keys(mapping).length ? JSON.stringify(mapping) : null;
}

class RunFailure extends Error {
  constructor(message, stage) {
    super(message);
    this.name = "RunFailure";
    this.stage = stage;
  }
}

async function postRun(url, body) {
  let response;
  try {
    response = await fetch(url, { method: "POST", body });
  } catch (error) {
    console.error(error);
    throw new RunFailure("The reconciliation service is unreachable.", STAGES[0]);
  }
  let payload;
  try {
    payload = await response.json();
  } catch (error) {
    console.error(error);
    throw new RunFailure(`The service returned an unreadable response (${response.status}).`, null);
  }
  if (!response.ok) {
    const problem = payload.error || {};
    const stage = problem.details ? problem.details.stage : null;
    throw new RunFailure(problem.message || `The run failed (${response.status}).`, stage);
  }
  return payload;
}

function option(value, label) {
  const node = document.createElement("option");
  node.value = value;
  node.textContent = label;
  return node;
}

function renderKpis(totals) {
  els.kpiGrid.textContent = "";
  KPI_FIELDS.forEach(([key, label]) => {
    const card = document.createElement("div");
    card.className = "kpi";
    const value = document.createElement("span");
    value.className = "kpi-value";
    value.textContent = String(totals[key]);
    const name = document.createElement("span");
    name.className = "kpi-label";
    name.textContent = label;
    card.append(value, name);
    els.kpiGrid.append(card);
  });
}

function titleCase(value) {
  return value.replace(/_/g, " ").replace(/^./, (first) => first.toUpperCase());
}

function renderFilterOptions(filters) {
  els.typeFilter.textContent = "";
  els.typeFilter.append(
    option(ALL_VALUE, "All"),
    ...filters.types.map((type) => option(type, titleCase(type)))
  );
  els.severityFilter.textContent = "";
  els.severityFilter.append(
    option(ALL_VALUE, "All"),
    ...filters.severities.map((severity) => option(severity, titleCase(severity)))
  );
}

function idsCell(ids, total) {
  const cell = document.createElement("td");
  const list = document.createElement("span");
  list.className = "cell-ids";
  list.textContent = ids.length ? ids.join(", ") : DASH;
  cell.append(list);
  if (total) {
    const amount = document.createElement("span");
    amount.className = "cell-amount";
    amount.textContent = total;
    cell.append(amount);
  }
  return cell;
}

function explanationCell(explanation) {
  const cell = document.createElement("td");
  if (!explanation) {
    cell.textContent = DASH;
    return cell;
  }
  const wrap = document.createElement("div");
  wrap.className = "explanation";
  const badge = document.createElement("span");
  const isAi = explanation.source === "ai_verified";
  badge.className = `badge ${isAi ? "badge-ai" : "badge-neutral"}`;
  badge.textContent = explanation.badge;
  const summary = document.createElement("span");
  summary.textContent = explanation.summary;
  const detail = document.createElement("span");
  detail.className = "explanation-detail";
  detail.textContent = `${explanation.likely_cause} · ${explanation.confidence} · ${explanation.recommended_action}`;
  wrap.append(badge, summary, detail);
  cell.append(wrap);
  return cell;
}

function visibleFindings() {
  const type = els.typeFilter.value;
  const severity = els.severityFilter.value;
  const showMatched = els.showMatched.checked;
  return findings.filter(
    (row) =>
      (showMatched || row.status !== "matched") &&
      (type === ALL_VALUE || row.type === type) &&
      (severity === ALL_VALUE || row.severity === severity)
  );
}

function renderRows() {
  els.findingsBody.textContent = "";
  const rows = visibleFindings();
  rows.forEach((row) => {
    const tr = document.createElement("tr");

    const idCell = document.createElement("th");
    idCell.scope = "row";
    idCell.className = "cell-ids";
    idCell.textContent = row.id;
    tr.append(idCell);

    const typeCell = document.createElement("td");
    const typeBadge = document.createElement("span");
    typeBadge.className = `badge ${row.status === "matched" ? "badge-matched" : "badge-neutral"}`;
    typeBadge.textContent = row.type_label;
    typeCell.append(typeBadge);
    const rule = document.createElement("span");
    rule.className = "explanation-detail";
    rule.textContent = row.rule;
    typeCell.append(rule);
    tr.append(typeCell);

    const severityCell = document.createElement("td");
    const severityBadge = document.createElement("span");
    severityBadge.className = `badge badge-${row.severity}`;
    severityBadge.textContent = row.severity_label;
    severityCell.append(severityBadge);
    tr.append(severityCell);

    tr.append(idsCell(row.ledger_ids, row.ledger_total), idsCell(row.bank_ids, row.bank_total));
    tr.append(explanationCell(row.explanation));
    els.findingsBody.append(tr);
  });
  els.emptyState.hidden = rows.length > 0;
  els.rowCount.textContent = `${rows.length} of ${findings.length} findings`;
}

function renderRunMeta(summary) {
  const bank = summary.inputs.bank;
  const ledger = summary.inputs.ledger;
  els.runMeta.textContent =
    `${summary.run_id} · bank ${bank.valid_rows}/${bank.valid_rows + bank.invalid_rows} rows` +
    ` · ledger ${ledger.valid_rows}/${ledger.valid_rows + ledger.invalid_rows} rows` +
    ` · llm ${summary.llm.provider}`;
}

function showResults(summary) {
  findings = summary.findings;
  renderKpis(summary.totals);
  renderFilterOptions(summary.filters);
  renderRows();
  els.reportLink.href = summary.report_url;
  els.results.hidden = false;
  renderRunMeta(summary);
}

function startRun(url, body) {
  clearError();
  setBusy(true);
  setStepper("running", STAGES[0], false);
  postRun(url, body)
    .then((summary) => {
      setStepper("done", null, summary.llm.provider === "none");
      showResults(summary);
    })
    .catch((error) => {
      if (!(error instanceof RunFailure)) {
        throw error;
      }
      setStepper("failed", error.stage, false);
      els.results.hidden = true;
      els.runMeta.textContent = "";
      showError(error.message);
    })
    .finally(() => setBusy(false));
}

function runFiles() {
  const bank = selectedFile("bank");
  const ledger = selectedFile("ledger");
  if (!bank || !ledger) {
    clearError();
    setStepper("idle", null, false);
    showError("Both a bank file and a ledger file are required.");
    return;
  }
  const body = new FormData();
  body.append("bank", bank, bank.name);
  body.append("ledger", ledger, ledger.name);
  const mapping = columnMapJson();
  if (mapping) {
    body.append("column_map", mapping);
  }
  startRun("/api/run", body);
}

function loadDemo() {
  startRun("/api/demo", new FormData());
}

function main() {
  ["bank", "ledger"].forEach(setupZone);
  buildMappingFields();
  els.runButton.addEventListener("click", runFiles);
  els.demoButton.addEventListener("click", loadDemo);
  els.typeFilter.addEventListener("change", renderRows);
  els.severityFilter.addEventListener("change", renderRows);
  els.showMatched.addEventListener("change", renderRows);
  setStepper("idle", null, false);
}

main();
