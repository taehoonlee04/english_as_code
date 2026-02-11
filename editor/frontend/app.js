(function () {
  "use strict";

  // ========== CONSTANTS ==========

  const EAC_KEYWORDS = new Set([
    "Open", "workbook", "In", "sheet", "treat", "range", "as", "table",
    "Set", "to", "Add", "column", "Filter", "where", "Sort", "by",
    "ascending", "descending", "Export", "For", "each", "row", "in",
    "If", "Otherwise", "On", "error", "Use", "system", "version",
    "Log", "Go", "page", "Enter", "Click", "Extract", "from",
    "Define", "Call", "result", "date", "not", "and", "or",
    "Group", "Join", "Download", "Select", "Lookup", "Wait", "until",
    "Verify", "credential"
  ]);

  const OP_LABELS = {
    "excel.open_workbook": "Opened workbook",
    "excel.read_table": "Read table from sheet",
    "excel.export": "Exported to file",
    "table.add_column": "Added column",
    "table.filter": "Filtered rows",
    "table.sort": "Sorted table",
    "table.group": "Grouped table",
    "table.join": "Joined tables",
    "set_var": "Set variable",
    "call_result": "Called result",
    "web.use_system": "Connected to system",
    "web.login": "Logged in",
    "web.logout": "Logged out",
    "web.goto_page": "Navigated to page",
    "web.enter": "Entered value",
    "web.click": "Clicked element",
    "web.extract": "Extracted value",
    "control.for_each": "Repeated for each row",
  };

  const EXAMPLE_PROMPTS = {
    aging: 'Open the accounts receivable workbook at "data/accounts_receivable.xlsx", read the "Open Items" sheet from range A1G999 as a table called OpenItems, set today to today\'s date, add a DaysPastDue column, filter for items where the balance is greater than USD 0.00, and export the results to "output/aging_summary.csv".',
    reconcile: 'Open the bank statement workbook at "data/bank_statement.xlsx", read the "Transactions" sheet from A1E1000 as a table called BankTxns, filter for transactions where the amount is greater than USD 0.00, sort by date ascending, and export to "output/unmatched_items.csv".',
    invoice: 'Open "data/invoices.xlsx", read the "Invoices" sheet from A1F500 as a table called Invoices, filter for invoices where the amount is greater than USD 1000.00, sort by amount descending, and export to "output/large_invoices.csv".',
  };

  const STEP_SCHEMAS = {
    open_workbook: [
      { name: "path", label: "Workbook path", default: "data/file.xlsx" },
    ],
    treat_range: [
      { name: "sheet", label: "Sheet name", default: "Sheet1" },
      { name: "range", label: "Range (e.g. A1G999)", default: "A1G999" },
      { name: "table", label: "Table name", default: "T" },
    ],
    set_var: [
      { name: "var", label: "Variable name", default: "today" },
      { name: "value", label: 'Value (e.g. date "2026-02-11", a number, or a name)', default: 'date "2026-02-11"' },
    ],
    add_column: [
      { name: "col", label: "Column name", default: "NewCol" },
      { name: "table", label: "Table name", default: "T" },
      { name: "expr", label: "Expression (e.g. today or 0)", default: "today" },
    ],
    filter: [
      { name: "table", label: "Table name", default: "T" },
      { name: "condition", label: "Condition (e.g. T.Balance > USD 0.00)", default: "T.Balance > USD 0.00" },
    ],
    sort: [
      { name: "table", label: "Table name", default: "T" },
      { name: "by", label: "By column (e.g. T.Amount)", default: "T.Column1" },
      { name: "dir", label: "Direction", default: "ascending" },
    ],
    export: [
      { name: "table", label: "Table or expression", default: "T" },
      { name: "path", label: "Output path", default: "output/out.csv" },
    ],
  };

  // ========== DOM REFERENCES ==========

  const heroSection = document.getElementById("heroSection");
  const workspaceSection = document.getElementById("workspaceSection");
  const appNav = document.getElementById("appNav");
  const appStatus = document.getElementById("appStatus");
  const aiPromptEl = document.getElementById("aiPrompt");
  const btnGenerate = document.getElementById("btnGenerate");
  const generateIcon = document.getElementById("generateIcon");
  const sourceEl = document.getElementById("source");
  const codeDisplay = document.getElementById("codeDisplay");
  const lineCountEl = document.getElementById("lineCount");
  const editToggleLabel = document.getElementById("editToggleLabel");
  const resultsEmpty = document.getElementById("resultsEmpty");
  const traceTimeline = document.getElementById("traceTimeline");
  const tablePreview = document.getElementById("tablePreview");
  const rawOutput = document.getElementById("rawOutput");
  const btnRawOutput = document.getElementById("btnRawOutput");
  const toastContainer = document.getElementById("toastContainer");
  const wizardOverlay = document.getElementById("wizardOverlay");
  const wizardTypeGrid = document.getElementById("wizardTypeGrid");
  const wizardFieldsContainer = document.getElementById("wizardFieldsContainer");
  const wizardFooter = document.getElementById("wizardFooter");
  const wizardPreviewCode = document.getElementById("wizardPreviewCode");
  const stepFieldsEl = document.getElementById("stepFields");
  const btnRun = document.getElementById("btnRun");
  const runIcon = document.getElementById("runIcon");
  const acWrapper = document.getElementById("acWrapper");
  const acDropdown = document.getElementById("acDropdown");
  const fileInput = document.getElementById("fileInput");
  const fileCardsLanding = document.getElementById("fileCardsLanding");
  const fileCardsWorkspace = document.getElementById("fileCardsWorkspace");
  const aiPromptHint = document.getElementById("aiPromptHint");

  // ========== STATE ==========

  let appState = "landing"; // "landing" | "workspace"
  let isEditing = false;
  let lastTrace = null;
  let selectedWizardType = null;
  let showingRaw = false;
  let uploadedFiles = []; // {filename, size, path}
  let uploadContext = "landing"; // "landing" | "workspace"

  // ========== UTILITIES ==========

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = String(str);
    return div.innerHTML;
  }

  function escapeAttr(s) {
    return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
  }

  // ========== API LAYER ==========

  async function api(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const raw = await res.text();
    const data = raw
      ? (function () {
          try { return JSON.parse(raw); }
          catch (e) { return { detail: raw }; }
        })()
      : {};
    if (!res.ok) {
      const msg =
        data.detail != null
          ? Array.isArray(data.detail)
            ? data.detail.map((d) => d.msg || d.message || JSON.stringify(d)).join("; ")
            : String(data.detail)
          : data.error || raw || res.statusText;
      throw new Error(msg || "Request failed");
    }
    return data;
  }

  // ========== TOAST SYSTEM ==========

  function showToast(message, type, duration) {
    if (type === undefined) type = "info";
    if (duration === undefined) duration = 4000;
    const toast = document.createElement("div");
    toast.className = "toast" + (type !== "info" ? " toast-" + type : "");
    toast.textContent = message;
    toast.setAttribute("role", "status");
    toastContainer.appendChild(toast);
    setTimeout(function () {
      toast.classList.add("toast-out");
      toast.addEventListener("animationend", function () { toast.remove(); });
    }, duration);
  }

  // ========== FRIENDLY ERRORS ==========

  function friendlyError(errorMsg) {
    var msg = String(errorMsg);

    // Extract line number: formats like "3:12: ...", "editor:3:12: ...", or just the message
    var locMatch = msg.match(/^(?:\w+:)?(\d+)(?::(\d+))?:\s*(.*)/);
    var line = locMatch ? parseInt(locMatch[1]) : null;
    var detail = locMatch ? locMatch[3] : msg;

    // Expected X, got Y
    var expectedMatch = detail.match(/Expected (\w+)(?: '([^']*)')?, got (\w+) '([^']*)'/i);
    if (expectedMatch) {
      var expectedVal = expectedMatch[2];
      var gotVal = expectedMatch[4];
      if (expectedVal === ".") {
        return {
          line: line,
          message: "Line" + (line ? " " + line : "") + " is missing a period at the end. Every step needs to end with a period.",
          suggestion: "Add a period (.) at the end of this line."
        };
      }
      if (expectedMatch[1] === "STRING") {
        return {
          line: line,
          message: "Line" + (line ? " " + line : "") + " needs a quoted value (in double quotes) here, but found \"" + gotVal + "\" instead.",
          suggestion: 'Try wrapping the value in double quotes, like "' + gotVal + '".'
        };
      }
      if (expectedVal) {
        return {
          line: line,
          message: "Line" + (line ? " " + line : "") + ': expected the word "' + expectedVal + '" but found "' + gotVal + '".',
          suggestion: 'Check the spelling. The correct keyword is "' + expectedVal + '".'
        };
      }
    }

    // "is" used instead of "=" (common natural-language mistake)
    if (detail.match(/got IDENT 'is'/i) || detail.match(/got KEYWORD 'is'/i)) {
      return {
        line: line,
        message: "Line" + (line ? " " + line : "") + ' uses "is" which isn\'t supported. Use "=" for comparisons instead.',
        suggestion: 'Replace "is" with "=". For example: Filter T where T.Paid = false.'
      };
    }

    // Unexpected token
    if (detail.toLowerCase().includes("unexpected token") || detail.toLowerCase().includes("unexpected keyword")) {
      return {
        line: line,
        message: "We couldn't understand line" + (line ? " " + line : "") + ". It doesn't match any known step pattern.",
        suggestion: "Each line should start with a keyword like Open, Set, Filter, Export, etc. Try the Add Step wizard for help."
      };
    }

    // Expected expression
    if (detail.toLowerCase().includes("expected expression")) {
      return {
        line: line,
        message: "Line" + (line ? " " + line : "") + " seems incomplete. A value or expression is missing.",
        suggestion: 'Make sure you have a value after keywords like "to", "as", or "where".'
      };
    }

    // Undeclared / undefined
    if (detail.match(/undeclared|unknown|not defined|not declared/i)) {
      return {
        line: line,
        message: "Line" + (line ? " " + line : "") + " references something that hasn't been defined yet.",
        suggestion: "Make sure you've defined all tables and variables in earlier steps before using them."
      };
    }

    // Fallback
    return {
      line: line,
      message: "There was a problem" + (line ? " on line " + line : "") + ": " + detail,
      suggestion: null
    };
  }

  // ========== UI STATE MANAGEMENT ==========

  function transitionToWorkspace() {
    appState = "workspace";
    heroSection.classList.add("fade-out");
    appNav.classList.remove("hidden");
    setTimeout(function () {
      heroSection.classList.add("hidden");
      workspaceSection.classList.remove("hidden");
      requestAnimationFrame(function () {
        workspaceSection.classList.add("visible");
      });
      renderFileCards();
    }, 260);
  }

  function transitionToLanding() {
    appState = "landing";
    workspaceSection.classList.remove("visible");
    appNav.classList.add("hidden");
    setTimeout(function () {
      workspaceSection.classList.add("hidden");
      heroSection.classList.remove("hidden", "fade-out");
      sourceEl.value = "";
      renderCodeDisplay("");
      clearResults();
      aiPromptEl.value = "";
      aiPromptEl.focus();
      appStatus.textContent = "";
      uploadedFiles = [];
      renderFileCards();
      updatePromptHint();
    }, 260);
  }

  function setEditing(editing) {
    isEditing = editing;
    if (editing) {
      codeDisplay.classList.add("hidden");
      acWrapper.classList.remove("hidden");
      sourceEl.focus();
      editToggleLabel.textContent = "Done";
    } else {
      acWrapper.classList.add("hidden");
      acDropdown.classList.add("hidden");
      codeDisplay.classList.remove("hidden");
      renderCodeDisplay(sourceEl.value);
      editToggleLabel.textContent = "Edit";
    }
  }

  function clearResults() {
    lastTrace = null;
    showingRaw = false;
    resultsEmpty.classList.remove("hidden");
    traceTimeline.classList.add("hidden");
    traceTimeline.innerHTML = "";
    tablePreview.classList.add("hidden");
    tablePreview.innerHTML = "";
    rawOutput.classList.add("hidden");
    rawOutput.textContent = "";
    btnRawOutput.classList.add("hidden");
  }

  function showSkeletonLoading() {
    resultsEmpty.classList.add("hidden");
    traceTimeline.classList.remove("hidden");
    traceTimeline.innerHTML =
      '<div class="skeleton-line" style="width:80%"></div>' +
      '<div class="skeleton-line" style="width:60%"></div>' +
      '<div class="skeleton-line" style="width:70%"></div>' +
      '<div class="skeleton-line" style="width:50%"></div>';
    tablePreview.classList.add("hidden");
    tablePreview.innerHTML = "";
  }

  // ========== CODE DISPLAY RENDERING ==========

  function renderCodeDisplay(source) {
    var lines = source.split("\n");
    var stepNum = 0;
    var html = lines
      .map(function (line) {
        var trimmed = line.trim();
        if (!trimmed) {
          return '<div class="code-blank-line"></div>';
        }
        if (trimmed.startsWith("--")) {
          return '<div class="code-sentence code-comment">' +
            '<span class="code-sentence-number">&mdash;</span>' +
            '<span class="code-sentence-text" style="color:var(--text-tertiary);font-style:italic">' + escapeHtml(trimmed) + '</span>' +
            '</div>';
        }
        stepNum++;
        return '<div class="code-sentence">' +
          '<span class="code-sentence-number">' + stepNum + '</span>' +
          '<span class="code-sentence-text">' + highlightSentence(trimmed) + '</span>' +
          '</div>';
      })
      .join("");
    codeDisplay.innerHTML = html;
    lineCountEl.textContent = stepNum + " step" + (stepNum !== 1 ? "s" : "");
  }

  function highlightSentence(text) {
    var html = escapeHtml(text);
    // Highlight quoted strings
    html = html.replace(/&quot;([^&]*?)&quot;/g, '<span class="code-string">&quot;$1&quot;</span>');
    html = html.replace(/"([^"]*?)"/g, '<span class="code-string">"$1"</span>');
    // Highlight money: USD/EUR/GBP followed by number
    html = html.replace(/\b(USD|EUR|GBP)\s+([\d,.]+)/g, '<span class="code-number">$1 $2</span>');
    // Highlight keywords (case-sensitive)
    var kwArr = Array.from(EAC_KEYWORDS);
    var kwPattern = new RegExp("\\b(" + kwArr.join("|") + ")\\b", "g");
    html = html.replace(kwPattern, '<span class="code-kw">$1</span>');
    return html;
  }

  // ========== TRACE RENDERING ==========

  function isTableResult(result) {
    return Array.isArray(result) && result.length > 0 && typeof result[0] === "object" && result[0] !== null;
  }

  function formatCellValue(val) {
    if (val === null || val === undefined) return '<span style="color:var(--text-tertiary)">&mdash;</span>';
    if (typeof val === "number") return escapeHtml(val.toLocaleString());
    return escapeHtml(String(val));
  }

  function formatArgValue(val) {
    if (val === null || val === undefined) return "null";
    if (typeof val === "object") return JSON.stringify(val);
    return String(val);
  }

  function renderTrace(trace) {
    if (!trace || !trace.length) {
      traceTimeline.classList.remove("hidden");
      resultsEmpty.classList.add("hidden");
      traceTimeline.innerHTML = '<p style="color:var(--text-tertiary);font-size:var(--text-sm)">No trace data returned.</p>';
      return;
    }
    lastTrace = trace;
    traceTimeline.classList.remove("hidden");
    resultsEmpty.classList.add("hidden");
    btnRawOutput.classList.remove("hidden");

    var html = trace.map(function (entry, i) { return renderTraceStep(entry, i); }).join("");
    traceTimeline.innerHTML = html;

    // Show last table result as a preview
    var tableSteps = trace.filter(function (e) { return isTableResult(e.result); });
    if (tableSteps.length > 0) {
      var last = tableSteps[tableSteps.length - 1];
      renderTablePreview(last.result, OP_LABELS[last.op] || last.op);
    }

    // Store raw output
    rawOutput.textContent = JSON.stringify(trace, null, 2);

    // Bind table view buttons
    traceTimeline.querySelectorAll(".trace-step-table-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var idx = parseInt(btn.dataset.stepIndex);
        if (trace[idx] && isTableResult(trace[idx].result)) {
          renderTablePreview(trace[idx].result, OP_LABELS[trace[idx].op] || trace[idx].op);
        }
      });
    });
  }

  function renderTraceStep(entry, index) {
    var label = OP_LABELS[entry.op] || entry.op;
    var isErr = !!entry.error;
    var statusClass = isErr ? "error" : "success";
    var icon = isErr ? "&#10006;" : "&#10003;";
    var detail = "";

    if (entry.op === "excel.open_workbook") {
      detail = "File: " + (entry.args.path || "");
    } else if (entry.op === "excel.read_table") {
      detail = 'Sheet: "' + (entry.args.sheet || "") + '", range: ' + (entry.args.range || entry.args.range_spec || "");
      if (isTableResult(entry.result)) {
        detail += " \u2014 " + entry.result.length + " rows";
      }
    } else if (entry.op === "table.filter") {
      if (isTableResult(entry.result)) {
        detail = entry.result.length + " rows remaining";
      }
    } else if (entry.op === "table.add_column") {
      detail = "Column: " + (entry.args.name || "");
    } else if (entry.op === "table.sort") {
      var sortBy = entry.args.by;
      if (sortBy && typeof sortBy === "object") sortBy = sortBy.field || JSON.stringify(sortBy);
      detail = "By: " + (sortBy || "") + " " + (entry.args.ascending !== false ? "ascending" : "descending");
    } else if (entry.op === "excel.export") {
      detail = "Saved to: " + (entry.args.path || "");
    } else if (entry.op === "set_var") {
      detail = (entry.args.name || "") + " = " + formatArgValue(entry.args.value);
    }

    var tableLink = "";
    if (isTableResult(entry.result)) {
      tableLink = '<button class="trace-step-table-btn" data-step-index="' + index + '">View table (' + entry.result.length + ' rows)</button>';
    }

    return '<div class="trace-step ' + statusClass + '">' +
      '<div class="trace-step-indicator">' + icon + '</div>' +
      '<div class="trace-step-content">' +
        '<div class="trace-step-op">' + escapeHtml(label) + '</div>' +
        (detail ? '<div class="trace-step-detail">' + escapeHtml(detail) + '</div>' : '') +
        tableLink +
      '</div>' +
    '</div>';
  }

  function renderTablePreview(rows, title) {
    if (!rows || !rows.length) return;
    tablePreview.classList.remove("hidden");
    var headers = Object.keys(rows[0]);
    var maxRows = 20;
    var displayRows = rows.slice(0, maxRows);

    var html = '<div class="table-preview-wrapper">' +
      '<div class="table-preview-header">' +
        '<span style="font-weight:600">' + escapeHtml(title || "Table") + '</span>' +
        '<span class="table-row-count">' + rows.length + ' row' + (rows.length !== 1 ? 's' : '') +
          (rows.length > maxRows ? ' (showing first ' + maxRows + ')' : '') +
        '</span>' +
      '</div>' +
      '<div style="overflow-x:auto">' +
        '<table class="data-table">' +
          '<thead><tr>' + headers.map(function (h) { return '<th>' + escapeHtml(String(h)) + '</th>'; }).join('') + '</tr></thead>' +
          '<tbody>' + displayRows.map(function (row) {
            return '<tr>' + headers.map(function (h) { return '<td>' + formatCellValue(row[h]) + '</td>'; }).join('') + '</tr>';
          }).join('') + '</tbody>' +
        '</table>' +
      '</div>' +
    '</div>';
    tablePreview.innerHTML = html;
  }

  function showErrorInResults(friendlyObj) {
    resultsEmpty.classList.add("hidden");
    traceTimeline.classList.remove("hidden");
    traceTimeline.innerHTML =
      '<div class="error-card">' +
        '<div class="error-card-icon">&#9888;</div>' +
        '<div>' +
          '<p class="error-card-message">' + escapeHtml(friendlyObj.message) + '</p>' +
          (friendlyObj.suggestion ? '<p class="error-card-suggestion">' + escapeHtml(friendlyObj.suggestion) + '</p>' : '') +
          (friendlyObj.line ? '<p class="error-card-line">Line ' + friendlyObj.line + '</p>' : '') +
        '</div>' +
      '</div>';
  }

  // ========== CORE ACTIONS ==========

  async function generate() {
    var prompt = aiPromptEl.value.trim();
    if (!prompt) {
      showToast("Please describe what you want to automate first.", "warning");
      aiPromptEl.focus();
      return;
    }

    btnGenerate.disabled = true;
    btnGenerate.classList.add("loading");
    generateIcon.innerHTML = "&#8987;";
    showToast("Generating your workflow...", "info", 10000);

    // Augment prompt with uploaded file paths
    var augmentedPrompt = prompt;
    if (uploadedFiles.length > 0) {
      var filePaths = uploadedFiles.map(function (f) { return '"' + f.path + '"'; }).join(", ");
      augmentedPrompt += "\n\nThe user has uploaded these spreadsheet files: " + filePaths + ". Use these file paths in Open workbook statements.";
    }

    try {
      var data = await api("/api/ai-author", {
        prompt: augmentedPrompt,
        retry_on_parse_error: true,
        max_retries: 2,
      });

      if (data.ok && data.source) {
        sourceEl.value = data.source;
        renderCodeDisplay(data.source);
        transitionToWorkspace();
        showToast("Workflow generated! Review it below, then click Run.", "success");
      } else {
        if (data.source) {
          sourceEl.value = data.source;
          renderCodeDisplay(data.source);
          transitionToWorkspace();
          showToast("Generated with warnings. Please review and fix any issues.", "warning", 6000);
        } else {
          showToast("Couldn't generate a workflow. Try rephrasing your description.", "error", 6000);
        }
      }
    } catch (e) {
      showToast("Failed to reach the AI service. Please try again.", "error");
    } finally {
      btnGenerate.disabled = false;
      btnGenerate.classList.remove("loading");
      generateIcon.innerHTML = "&#10024;";
    }
  }

  async function check() {
    var source = sourceEl.value.trim();
    if (!source) {
      showToast("No workflow to check. Write or generate one first.", "warning");
      return;
    }

    appStatus.innerHTML = '<span class="status-spinner"></span> Checking...';

    try {
      var data = await api("/api/check", { source: sourceEl.value });
      if (data.ok) {
        showToast("No errors found.", "success");
        appStatus.textContent = "Valid";
      } else {
        var friendly = friendlyError(data.error || "Check failed");
        showErrorInResults(friendly);
        showToast(friendly.message, "error", 6000);
        appStatus.textContent = "Error";
      }
    } catch (e) {
      var friendly = friendlyError(e.message);
      showErrorInResults(friendly);
      showToast("Check failed.", "error");
      appStatus.textContent = "Error";
    }
  }

  async function run() {
    var source = sourceEl.value.trim();
    if (!source) {
      showToast("No workflow to run. Write or generate one first.", "warning");
      return;
    }

    // If in edit mode, switch to display first
    if (isEditing) setEditing(false);

    btnRun.disabled = true;
    btnRun.classList.add("loading");
    appStatus.innerHTML = '<span class="status-spinner"></span> Running...';
    showSkeletonLoading();

    try {
      var data = await api("/api/run", { source: sourceEl.value });
      if (data.ok) {
        renderTrace(data.trace);
        showToast("Completed " + (data.trace ? data.trace.length : 0) + " steps successfully.", "success");
        appStatus.textContent = "Completed";
      } else {
        var friendly = friendlyError(data.error || data.message || "Run failed");
        showErrorInResults(friendly);
        showToast(friendly.message, "error", 6000);
        appStatus.textContent = "Error";
      }
    } catch (e) {
      var friendly = friendlyError(e.message);
      showErrorInResults(friendly);
      showToast("Something went wrong while running.", "error");
      appStatus.textContent = "Error";
    } finally {
      btnRun.disabled = false;
      btnRun.classList.remove("loading");
    }
  }

  // ========== STEP WIZARD ==========

  function openWizard() {
    wizardOverlay.classList.remove("hidden");
    wizardTypeGrid.classList.remove("hidden");
    wizardFieldsContainer.classList.add("hidden");
    wizardFooter.classList.add("hidden");
    selectedWizardType = null;
    var firstCard = wizardOverlay.querySelector(".wizard-type-card");
    if (firstCard) firstCard.focus();
  }

  function closeWizard() {
    wizardOverlay.classList.add("hidden");
    selectedWizardType = null;
  }

  function selectWizardType(type) {
    selectedWizardType = type;
    wizardTypeGrid.classList.add("hidden");
    wizardFieldsContainer.classList.remove("hidden");
    wizardFooter.classList.remove("hidden");
    renderWizardFields(type);
    updateWizardPreview();
    var firstInput = stepFieldsEl.querySelector("input");
    if (firstInput) firstInput.focus();
  }

  function renderWizardFields(type) {
    var schema = STEP_SCHEMAS[type] || [];
    stepFieldsEl.innerHTML = schema
      .map(function (f) {
        if (f.name === "dir") {
          return '<div class="wizard-field-group">' +
            '<label for="wiz-' + f.name + '">' + escapeHtml(f.label) + '</label>' +
            '<select id="wiz-' + f.name + '" data-name="' + escapeAttr(f.name) + '">' +
              '<option value="ascending"' + (f.default === "ascending" ? " selected" : "") + '>Ascending</option>' +
              '<option value="descending"' + (f.default === "descending" ? " selected" : "") + '>Descending</option>' +
            '</select></div>';
        }
        return '<div class="wizard-field-group">' +
          '<label for="wiz-' + f.name + '">' + escapeHtml(f.label) + '</label>' +
          '<input type="text" id="wiz-' + f.name + '" data-name="' + escapeAttr(f.name) + '" value="' + escapeAttr(f.default) + '" />' +
          '</div>';
      })
      .join("");
  }

  function getWizardValues() {
    var vals = {};
    stepFieldsEl.querySelectorAll("input, select").forEach(function (el) {
      vals[el.dataset.name] = el.value.trim();
    });
    return vals;
  }

  function getStepLine() {
    if (!selectedWizardType) return "";
    var vals = getWizardValues();
    switch (selectedWizardType) {
      case "open_workbook":
        return 'Open workbook "' + (vals.path || "data/file.xlsx") + '".';
      case "treat_range":
        return 'In sheet "' + (vals.sheet || "Sheet1") + '", treat range ' + (vals.range || "A1G999") + " as table " + (vals.table || "T") + ".";
      case "set_var":
        return "Set " + (vals.var || "x") + " to " + (vals.value || "0") + ".";
      case "add_column":
        return "Add column " + (vals.col || "NewCol") + " to " + (vals.table || "T") + " as " + (vals.expr || "0") + ".";
      case "filter":
        return "Filter " + (vals.table || "T") + " where " + (vals.condition || "T.x > 0") + ".";
      case "sort":
        var dir = (vals.dir || "ascending").toLowerCase();
        return "Sort " + (vals.table || "T") + " by " + (vals.by || "T.Column1") + " " + (dir === "descending" ? "descending" : "ascending") + ".";
      case "export":
        return 'Export ' + (vals.table || "T") + ' to "' + (vals.path || "out.csv") + '".';
      default:
        return "";
    }
  }

  function updateWizardPreview() {
    var line = getStepLine();
    wizardPreviewCode.textContent = line || "(fill in the fields above)";
  }

  function insertStep() {
    var line = getStepLine();
    if (!line) return;
    var cur = sourceEl.value;
    var end = cur.trimEnd();
    sourceEl.value = (end ? end + "\n" : "") + line + "\n";
    renderCodeDisplay(sourceEl.value);
    closeWizard();
    showToast("Step added.", "success", 2000);
  }

  // ========== COPY TO CLIPBOARD ==========

  function copySource() {
    var text = sourceEl.value;
    if (!text.trim()) {
      showToast("Nothing to copy.", "warning", 2000);
      return;
    }
    navigator.clipboard.writeText(text).then(function () {
      showToast("Copied to clipboard.", "success", 2000);
    }).catch(function () {
      showToast("Could not copy.", "error", 2000);
    });
  }

  // ========== FILE UPLOAD ==========

  function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  async function uploadFile(file) {
    var formData = new FormData();
    formData.append("file", file);
    var res = await fetch("/api/upload", { method: "POST", body: formData });
    var data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload failed");
    return data;
  }

  async function handleFileSelect(files) {
    var fileList = Array.from(files);
    for (var i = 0; i < fileList.length; i++) {
      var f = fileList[i];
      var ext = f.name.substring(f.name.lastIndexOf(".")).toLowerCase();
      if (ext !== ".xlsx" && ext !== ".xls" && ext !== ".csv") {
        showToast("Only .xlsx, .xls, and .csv files are supported.", "error");
        continue;
      }
      try {
        var result = await uploadFile(f);
        uploadedFiles.push({ filename: result.filename, size: result.size, path: result.path });
        showToast("Uploaded " + result.filename, "success", 3000);
        if (uploadContext === "workspace") {
          autoInsertOpenWorkbook(result.path);
        }
      } catch (e) {
        showToast("Upload failed: " + e.message, "error");
      }
    }
    renderFileCards();
    updatePromptHint();
    fileInput.value = "";
  }

  function renderFileCards() {
    var html = uploadedFiles.map(function (f, i) {
      return '<span class="file-card">' +
        '<span class="file-card-name" title="' + escapeAttr(f.filename) + '">' + escapeHtml(f.filename) + '</span>' +
        '<span class="file-card-size">' + formatFileSize(f.size) + '</span>' +
        '<button type="button" class="file-card-remove" data-file-index="' + i + '" title="Remove">&times;</button>' +
        '</span>';
    }).join("");
    fileCardsLanding.innerHTML = html;
    fileCardsWorkspace.innerHTML = html;
    // Bind remove buttons
    document.querySelectorAll(".file-card-remove").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        removeFile(parseInt(btn.dataset.fileIndex));
      });
    });
  }

  async function removeFile(index) {
    if (index < 0 || index >= uploadedFiles.length) return;
    var f = uploadedFiles[index];
    try {
      await fetch("/api/files/" + encodeURIComponent(f.filename), { method: "DELETE" });
    } catch (e) {
      // ignore delete errors
    }
    uploadedFiles.splice(index, 1);
    renderFileCards();
    updatePromptHint();
    showToast("Removed " + f.filename, "success", 2000);
  }

  function updatePromptHint() {
    if (uploadedFiles.length === 0) {
      aiPromptHint.textContent = "Tip: Be specific about file names, sheet names, and what you want to filter or calculate.";
    } else {
      var names = uploadedFiles.map(function (f) { return f.filename; }).join(", ");
      aiPromptHint.textContent = "Attached: " + names + ". Your description can reference these files.";
    }
  }

  function autoInsertOpenWorkbook(filePath) {
    var line = 'Open workbook "' + filePath + '".';
    var src = sourceEl.value;
    // Skip if this exact line already exists
    if (src.indexOf(line) !== -1) return;
    // Insert after existing Open lines, or at the top
    var lines = src.split("\n");
    var insertAt = 0;
    for (var i = 0; i < lines.length; i++) {
      if (lines[i].trim().match(/^Open\s+workbook\s+/)) {
        insertAt = i + 1;
      }
    }
    lines.splice(insertAt, 0, line);
    sourceEl.value = lines.join("\n");
    renderCodeDisplay(sourceEl.value);
  }

  async function loadExistingFiles() {
    try {
      var res = await fetch("/api/files");
      var data = await res.json();
      if (data.files && data.files.length) {
        uploadedFiles = data.files.map(function (f) {
          return { filename: f.name, size: f.size, path: f.path };
        });
        renderFileCards();
        updatePromptHint();
      }
    } catch (e) {
      // ignore load errors
    }
  }

  // ========== AUTOCOMPLETE ENGINE ==========

  // All statement starters with descriptions
  var STATEMENT_STARTERS = [
    { text: "Open", hint: 'Open workbook "path".', badge: "template", badgeLabel: "stmt" },
    { text: "In", hint: 'In sheet "name", treat range ...', badge: "template", badgeLabel: "stmt" },
    { text: "Set", hint: "Set variable to value.", badge: "template", badgeLabel: "stmt" },
    { text: "Add", hint: "Add column name to table as expr.", badge: "template", badgeLabel: "stmt" },
    { text: "Filter", hint: "Filter table where condition.", badge: "template", badgeLabel: "stmt" },
    { text: "Sort", hint: "Sort table by column asc/desc.", badge: "template", badgeLabel: "stmt" },
    { text: "Export", hint: 'Export table to "path".', badge: "template", badgeLabel: "stmt" },
    { text: "Call", hint: "Call result name.", badge: "template", badgeLabel: "stmt" },
    { text: "For", hint: "For each row in table:", badge: "template", badgeLabel: "stmt" },
    { text: "If", hint: "If condition:", badge: "template", badgeLabel: "stmt" },
    { text: "Otherwise", hint: "Otherwise:", badge: "template", badgeLabel: "stmt" },
    { text: "Use", hint: 'Use system "name" version "ver".', badge: "template", badgeLabel: "stmt" },
    { text: "Log", hint: 'Log in/out.', badge: "template", badgeLabel: "stmt" },
    { text: "Go", hint: 'Go to page "name".', badge: "template", badgeLabel: "stmt" },
    { text: "Enter", hint: 'Enter "field" = value.', badge: "template", badgeLabel: "stmt" },
    { text: "Click", hint: 'Click "element".', badge: "template", badgeLabel: "stmt" },
    { text: "Extract", hint: 'Extract var from field "sel".', badge: "template", badgeLabel: "stmt" },
    { text: "Define", hint: "Define name as type.", badge: "template", badgeLabel: "stmt" },
    { text: "On", hint: "On error: action.", badge: "template", badgeLabel: "stmt" },
  ];

  // Contextual keywords: what follows what
  var KEYWORD_CHAINS = {
    "Open": [{ text: "workbook", hint: '"path"', badge: "keyword" }],
    "In": [{ text: "sheet", hint: '"name"', badge: "keyword" }],
    "treat": [{ text: "range", hint: "A1G999", badge: "keyword" }],
    "as": [{ text: "table", hint: "TableName", badge: "keyword" }],
    "Set": [],  // next is IDENT (variable name)
    "Add": [{ text: "column", hint: "ColumnName", badge: "keyword" }],
    "Filter": [],  // next is IDENT (table name)
    "where": [],  // next is expression
    "Sort": [],  // next is IDENT (table name)
    "by": [],  // next is expression
    "Export": [],  // next is expression
    "to": [],  // context-dependent
    "Call": [{ text: "result", hint: "name", badge: "keyword" }],
    "For": [{ text: "each", hint: "row in table:", badge: "keyword" }],
    "each": [{ text: "row", hint: "in collection:", badge: "keyword" }],
    "Use": [{ text: "system", hint: '"name"', badge: "keyword" }],
    "system": [],  // next is STRING
    "version": [],  // next is STRING
    "Log": [
      { text: "in", hint: 'as credential "name"', badge: "keyword" },
      { text: "out", hint: ".", badge: "keyword" },
    ],
    "Go": [{ text: "to", hint: 'page "name"', badge: "keyword" }],
    "page": [],  // next is STRING
    "Extract": [],  // next is IDENT
    "from": [
      { text: "field", hint: '"selector"', badge: "keyword" },
      { text: "element", hint: '"selector"', badge: "keyword" },
    ],
    "On": [{ text: "error", hint: ": action", badge: "keyword" }],
    "credential": [],  // next is STRING
  };

  // Comparison operators
  var COMPARISON_OPS = [
    { text: "=", hint: "equals", badge: "operator" },
    { text: "!=", hint: "not equals", badge: "operator" },
    { text: ">", hint: "greater than", badge: "operator" },
    { text: "<", hint: "less than", badge: "operator" },
    { text: ">=", hint: "greater or equal", badge: "operator" },
    { text: "<=", hint: "less or equal", badge: "operator" },
    { text: "and", hint: "logical and", badge: "operator" },
    { text: "or", hint: "logical or", badge: "operator" },
    { text: "not", hint: "logical not", badge: "operator" },
  ];

  // Sort direction keywords
  var SORT_DIRECTIONS = [
    { text: "ascending", hint: "sort low to high", badge: "keyword" },
    { text: "descending", hint: "sort high to low", badge: "keyword" },
  ];

  // Literal helpers
  var LITERAL_SUGGESTIONS = [
    { text: "date", hint: 'date "YYYY-MM-DD"', badge: "keyword" },
    { text: "USD", hint: "USD 100.00", badge: "keyword" },
    { text: "EUR", hint: "EUR 100.00", badge: "keyword" },
    { text: "GBP", hint: "GBP 100.00", badge: "keyword" },
    { text: "true", hint: "boolean true", badge: "keyword" },
    { text: "false", hint: "boolean false", badge: "keyword" },
  ];

  var acActiveIndex = -1;
  var acItems = [];
  var acCurrentPrefix = "";

  // Parse source up to a line to extract defined table names and variable names
  function extractDefinedSymbols(source, upToLine) {
    var lines = source.split("\n");
    var tables = [];
    var variables = [];
    for (var i = 0; i < Math.min(lines.length, upToLine); i++) {
      var line = lines[i].trim();
      // "treat range ... as table TableName."
      var tableMatch = line.match(/as\s+table\s+(\w+)/i);
      if (tableMatch) tables.push(tableMatch[1]);
      // "Set varName to ..."
      var setMatch = line.match(/^Set\s+(\w+)\s+to\b/);
      if (setMatch) variables.push(setMatch[1]);
      // "Call result varName."
      var callMatch = line.match(/^Call\s+result\s+(\w+)/);
      if (callMatch) variables.push(callMatch[1]);
    }
    return { tables: tables, variables: variables };
  }

  // Get cursor position info
  function getCursorContext() {
    var pos = sourceEl.selectionStart;
    var text = sourceEl.value;
    var textBefore = text.substring(0, pos);
    var lineStart = textBefore.lastIndexOf("\n") + 1;
    var currentLine = textBefore.substring(lineStart);
    var lineNumber = textBefore.split("\n").length;

    // Split current line into tokens (simplified)
    var tokens = currentLine.match(/\S+/g) || [];
    // Get the word being typed (partial word at cursor)
    var wordMatch = currentLine.match(/(\S+)$/);
    var currentWord = wordMatch ? wordMatch[1] : "";
    var isLineStart = currentLine.trim() === currentWord;

    // Get the previous completed token
    var prevTokens = [];
    if (currentWord) {
      var beforeWord = currentLine.substring(0, currentLine.length - currentWord.length).trim();
      prevTokens = beforeWord.match(/\S+/g) || [];
    } else {
      prevTokens = tokens;
    }
    var lastToken = prevTokens.length > 0 ? prevTokens[prevTokens.length - 1] : "";

    // Remove trailing punctuation from lastToken for matching
    var lastTokenClean = lastToken.replace(/[.,;:!?]+$/, "");

    return {
      pos: pos,
      currentLine: currentLine,
      currentWord: currentWord,
      isLineStart: isLineStart,
      lastToken: lastTokenClean,
      prevTokens: prevTokens,
      lineNumber: lineNumber,
      firstToken: prevTokens.length > 0 ? prevTokens[0].replace(/[.,;:!?]+$/, "") : (currentWord || ""),
    };
  }

  // Build suggestion list based on context
  function getSuggestions(ctx) {
    var suggestions = [];
    var word = ctx.currentWord;
    var wordLower = word.toLowerCase();

    // If typing after a dot (e.g., "TableName."), suggest column-style completions
    if (word.includes(".")) {
      var parts = word.split(".");
      var base = parts[0];
      var partial = parts.slice(1).join(".");
      var symbols = extractDefinedSymbols(sourceEl.value, ctx.lineNumber);
      // If base is a known table, suggest "TableName.ColumnName" style
      if (symbols.tables.indexOf(base) !== -1) {
        // We can't know column names from source alone, so suggest the pattern
        suggestions.push({ text: base + ".Column", hint: "column reference", badge: "table" });
      }
      return suggestions; // Don't mix with other suggestions when typing after a dot
    }

    // Line start: suggest statement starters
    if (ctx.isLineStart) {
      suggestions = suggestions.concat(STATEMENT_STARTERS);
    }

    // After specific keywords, suggest next keyword in chain
    if (ctx.lastToken && KEYWORD_CHAINS[ctx.lastToken]) {
      suggestions = suggestions.concat(KEYWORD_CHAINS[ctx.lastToken]);
    }

    // After "Sort ... by expr" — suggest ascending/descending
    if (ctx.firstToken === "Sort" && ctx.prevTokens.length >= 3) {
      var hasByIdx = ctx.prevTokens.indexOf("by");
      if (hasByIdx !== -1 && hasByIdx < ctx.prevTokens.length - 1) {
        suggestions = suggestions.concat(SORT_DIRECTIONS);
      }
    }

    // In a "where" clause or after comparison target: suggest operators
    var inWhere = ctx.prevTokens.indexOf("where") !== -1;
    if (inWhere && ctx.prevTokens.length > ctx.prevTokens.indexOf("where") + 1) {
      suggestions = suggestions.concat(COMPARISON_OPS);
    }

    // Add defined table names and variable names
    var symbols = extractDefinedSymbols(sourceEl.value, ctx.lineNumber);
    symbols.tables.forEach(function (t) {
      suggestions.push({ text: t, hint: "table", badge: "table" });
    });
    symbols.variables.forEach(function (v) {
      suggestions.push({ text: v, hint: "variable", badge: "variable" });
    });

    // Add literal suggestions in expression contexts
    if (inWhere || ctx.lastToken === "to" || ctx.lastToken === "as" || ctx.lastToken === "=" ||
        ctx.lastToken === ">" || ctx.lastToken === "<" || ctx.lastToken === ">=" || ctx.lastToken === "<=") {
      suggestions = suggestions.concat(LITERAL_SUGGESTIONS);
    }

    // Filter by current word prefix
    if (word) {
      suggestions = suggestions.filter(function (s) {
        return s.text.toLowerCase().indexOf(wordLower) === 0 && s.text.toLowerCase() !== wordLower;
      });
    }

    // Deduplicate by text
    var seen = {};
    suggestions = suggestions.filter(function (s) {
      if (seen[s.text]) return false;
      seen[s.text] = true;
      return true;
    });

    return suggestions.slice(0, 8);
  }

  // Position the dropdown near the cursor in the textarea
  function positionDropdown() {
    // Create a mirror div to measure cursor position
    var mirror = document.createElement("div");
    var computed = window.getComputedStyle(sourceEl);
    var props = [
      "fontFamily", "fontSize", "fontWeight", "lineHeight", "letterSpacing",
      "wordSpacing", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
      "borderTopWidth", "borderRightWidth", "borderBottomWidth", "borderLeftWidth",
      "whiteSpace", "wordWrap", "overflowWrap", "tabSize", "textIndent"
    ];
    mirror.style.position = "absolute";
    mirror.style.visibility = "hidden";
    mirror.style.whiteSpace = "pre-wrap";
    mirror.style.wordWrap = "break-word";
    mirror.style.width = computed.width;
    props.forEach(function (p) { mirror.style[p] = computed[p]; });

    var textBefore = sourceEl.value.substring(0, sourceEl.selectionStart);
    mirror.textContent = textBefore;

    // Add a span to mark the cursor position
    var marker = document.createElement("span");
    marker.textContent = "|";
    mirror.appendChild(marker);

    document.body.appendChild(mirror);

    var markerRect = marker.getBoundingClientRect();
    var mirrorRect = mirror.getBoundingClientRect();

    // Calculate position relative to the textarea
    var relativeTop = markerRect.top - mirrorRect.top - sourceEl.scrollTop;
    var relativeLeft = markerRect.left - mirrorRect.left - sourceEl.scrollLeft;

    // Line height for offset below
    var lineHeight = parseFloat(computed.lineHeight) || parseFloat(computed.fontSize) * 1.6;

    acDropdown.style.top = (relativeTop + lineHeight + 4) + "px";
    acDropdown.style.left = Math.min(relativeLeft, sourceEl.offsetWidth - 240) + "px";

    document.body.removeChild(mirror);
  }

  // Render the dropdown
  function renderDropdown(suggestions) {
    if (!suggestions.length) {
      acDropdown.classList.add("hidden");
      acItems = [];
      acActiveIndex = -1;
      return;
    }
    acItems = suggestions;
    acActiveIndex = 0;

    var html = suggestions.map(function (s, i) {
      var badgeClass = "ac-badge-" + (s.badge || "keyword");
      var badgeLabel = s.badgeLabel || s.badge || "kw";
      return '<div class="ac-item' + (i === 0 ? ' active' : '') + '" data-index="' + i + '" role="option">' +
        '<span class="ac-item-text">' + escapeHtml(s.text) + '</span>' +
        (s.hint ? '<span class="ac-item-hint">' + escapeHtml(s.hint) + '</span>' : '') +
        '<span class="ac-item-badge ' + badgeClass + '">' + escapeHtml(badgeLabel) + '</span>' +
        '</div>';
    }).join("");

    acDropdown.innerHTML = html;
    positionDropdown();
    acDropdown.classList.remove("hidden");
  }

  // Apply a completion
  function applyCompletion(index) {
    if (index < 0 || index >= acItems.length) return;
    var item = acItems[index];
    var pos = sourceEl.selectionStart;
    var text = sourceEl.value;
    var textBefore = text.substring(0, pos);

    // Find the word being replaced
    var wordMatch = textBefore.match(/(\S+)$/);
    var wordLen = wordMatch ? wordMatch[1].length : 0;
    var insertText = item.text;

    // Build new text
    var before = text.substring(0, pos - wordLen);
    var after = text.substring(pos);

    // Add a space after the completion unless next char is already space/newline/dot
    var needsSpace = after.length === 0 || (after[0] !== " " && after[0] !== "\n" && after[0] !== ".");
    sourceEl.value = before + insertText + (needsSpace ? " " : "") + after;

    // Move cursor to after the inserted text + space
    var newPos = before.length + insertText.length + (needsSpace ? 1 : 0);
    sourceEl.selectionStart = newPos;
    sourceEl.selectionEnd = newPos;
    sourceEl.focus();

    acDropdown.classList.add("hidden");
    acItems = [];
    acActiveIndex = -1;
  }

  // Update active item highlight
  function updateActiveItem(newIndex) {
    if (newIndex < 0) newIndex = acItems.length - 1;
    if (newIndex >= acItems.length) newIndex = 0;
    acActiveIndex = newIndex;
    var items = acDropdown.querySelectorAll(".ac-item");
    items.forEach(function (el, i) {
      if (i === acActiveIndex) {
        el.classList.add("active");
        el.scrollIntoView({ block: "nearest" });
      } else {
        el.classList.remove("active");
      }
    });
  }

  // Handle input in textarea to trigger autocomplete
  function onSourceInput() {
    var ctx = getCursorContext();
    var suggestions = getSuggestions(ctx);
    acCurrentPrefix = ctx.currentWord;
    renderDropdown(suggestions);
  }

  // Handle keydown in textarea for autocomplete navigation
  function onSourceKeydown(e) {
    if (acDropdown.classList.contains("hidden") || !acItems.length) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      updateActiveItem(acActiveIndex + 1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      updateActiveItem(acActiveIndex - 1);
    } else if (e.key === "Enter" || e.key === "Tab") {
      if (acActiveIndex >= 0) {
        e.preventDefault();
        applyCompletion(acActiveIndex);
      }
    } else if (e.key === "Escape") {
      acDropdown.classList.add("hidden");
      acItems = [];
      acActiveIndex = -1;
    }
  }

  // Handle click on dropdown item
  function onDropdownClick(e) {
    var item = e.target.closest(".ac-item");
    if (item) {
      var idx = parseInt(item.dataset.index);
      applyCompletion(idx);
    }
  }

  // Dismiss dropdown when clicking outside
  function onDocumentClickForAC(e) {
    if (!acDropdown.contains(e.target) && e.target !== sourceEl) {
      acDropdown.classList.add("hidden");
      acItems = [];
      acActiveIndex = -1;
    }
  }

  // ========== EVENT BINDING ==========

  function init() {
    // Generate button
    btnGenerate.addEventListener("click", generate);

    // Enter key in AI prompt triggers generate
    aiPromptEl.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        generate();
      }
    });

    // Start from scratch
    document.getElementById("btnStartScratch").addEventListener("click", function () {
      sourceEl.value = "";
      renderCodeDisplay("");
      transitionToWorkspace();
      setEditing(true);
    });

    // Example chips
    document.querySelectorAll(".chip[data-example]").forEach(function (chip) {
      chip.addEventListener("click", function () {
        var key = chip.dataset.example;
        if (EXAMPLE_PROMPTS[key]) {
          aiPromptEl.value = EXAMPLE_PROMPTS[key];
          aiPromptEl.focus();
        }
      });
    });

    // Nav buttons
    document.getElementById("btnNew").addEventListener("click", transitionToLanding);
    document.getElementById("btnCheck").addEventListener("click", check);
    btnRun.addEventListener("click", run);
    document.getElementById("btnAddStep").addEventListener("click", openWizard);

    // File upload buttons
    document.getElementById("btnUploadLanding").addEventListener("click", function () {
      uploadContext = "landing";
      fileInput.click();
    });
    document.getElementById("btnAddFile").addEventListener("click", function () {
      uploadContext = "workspace";
      fileInput.click();
    });
    fileInput.addEventListener("change", function () {
      if (fileInput.files.length) handleFileSelect(fileInput.files);
    });

    // Drag-and-drop on AI prompt card
    var aiCard = document.querySelector(".ai-prompt-card");
    if (aiCard) {
      aiCard.addEventListener("dragover", function (e) { e.preventDefault(); e.stopPropagation(); aiCard.style.borderColor = "var(--accent)"; });
      aiCard.addEventListener("dragleave", function (e) { e.preventDefault(); e.stopPropagation(); aiCard.style.borderColor = ""; });
      aiCard.addEventListener("drop", function (e) {
        e.preventDefault();
        e.stopPropagation();
        aiCard.style.borderColor = "";
        uploadContext = "landing";
        if (e.dataTransfer.files.length) handleFileSelect(e.dataTransfer.files);
      });
    }

    // Load existing files on page load
    loadExistingFiles();

    // Code display: click to edit
    codeDisplay.addEventListener("click", function () { setEditing(true); });
    codeDisplay.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setEditing(true); }
    });

    // Edit toggle button
    document.getElementById("btnToggleEdit").addEventListener("click", function () { setEditing(!isEditing); });

    // Copy button
    document.getElementById("btnCopySource").addEventListener("click", copySource);

    // Raw output toggle
    btnRawOutput.addEventListener("click", function () {
      showingRaw = !showingRaw;
      if (showingRaw) {
        rawOutput.classList.remove("hidden");
        traceTimeline.classList.add("hidden");
        tablePreview.classList.add("hidden");
        btnRawOutput.textContent = "View timeline";
      } else {
        rawOutput.classList.add("hidden");
        traceTimeline.classList.remove("hidden");
        if (lastTrace) {
          var tableSteps = lastTrace.filter(function (e) { return isTableResult(e.result); });
          if (tableSteps.length > 0) tablePreview.classList.remove("hidden");
        }
        btnRawOutput.textContent = "View raw";
      }
    });

    // Wizard: type card selection
    wizardTypeGrid.addEventListener("click", function (e) {
      var card = e.target.closest(".wizard-type-card");
      if (card) selectWizardType(card.dataset.type);
    });

    // Wizard: back button
    document.getElementById("btnWizardBack").addEventListener("click", function () {
      wizardTypeGrid.classList.remove("hidden");
      wizardFieldsContainer.classList.add("hidden");
      wizardFooter.classList.add("hidden");
      selectedWizardType = null;
    });

    // Wizard: live preview on input
    stepFieldsEl.addEventListener("input", updateWizardPreview);
    stepFieldsEl.addEventListener("change", updateWizardPreview);

    // Wizard: insert and cancel
    document.getElementById("btnInsertStep").addEventListener("click", insertStep);
    document.getElementById("btnCancelWizard").addEventListener("click", closeWizard);
    document.getElementById("btnCloseWizard").addEventListener("click", closeWizard);

    // Wizard: close on overlay click or Escape
    wizardOverlay.addEventListener("click", function (e) {
      if (e.target === wizardOverlay) closeWizard();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !wizardOverlay.classList.contains("hidden")) closeWizard();
    });

    // Autocomplete: input triggers suggestion refresh
    sourceEl.addEventListener("input", onSourceInput);
    // Autocomplete: keydown for arrow/enter/tab/escape navigation
    sourceEl.addEventListener("keydown", onSourceKeydown);
    // Autocomplete: click on dropdown item
    acDropdown.addEventListener("mousedown", onDropdownClick);
    // Autocomplete: dismiss when clicking outside
    document.addEventListener("click", onDocumentClickForAC);
    // Autocomplete: also trigger on cursor movement (click or arrow keys without input)
    sourceEl.addEventListener("click", function () {
      // Small delay so selectionStart is updated
      setTimeout(onSourceInput, 10);
    });

    // Keyboard shortcuts in workspace
    document.addEventListener("keydown", function (e) {
      if (appState !== "workspace") return;
      // Ctrl/Cmd + Enter = Run
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && !e.shiftKey) {
        e.preventDefault();
        run();
      }
      // Ctrl/Cmd + Shift + Enter = Check
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && e.shiftKey) {
        e.preventDefault();
        check();
      }
    });
  }

  init();
})();
