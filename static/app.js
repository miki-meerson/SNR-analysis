const state = {
  folderPath: "",
  experimentPath: "",
  traceTypes: [],
  snrMethods: [],
  spikeRoiIndices: new Set(),
  activeView: "traces",
  lastTracePayload: null,
  lastSnrPayload: null,
};

const el = {
  upBtn: document.getElementById("upBtn"),
  currentFolder: document.getElementById("currentFolder"),
  folderList: document.getElementById("folderList"),
  traceType: document.getElementById("traceType"),
  roiSelect: document.getElementById("roiSelect"),
  normalize: document.getElementById("normalize"),
  showSpikes: document.getElementById("showSpikes"),
  offsetInput: document.getElementById("offsetInput"),
  startFrameInput: document.getElementById("startFrameInput"),
  highpassCutoffInput: document.getElementById("highpassCutoffInput"),
  highpassCutoffValue: document.getElementById("highpassCutoffValue"),
  plotBtn: document.getElementById("plotBtn"),
  snrMethod: document.getElementById("snrMethod"),
  snrSignalSource: document.getElementById("snrSignalSource"),
  snrPaddingBefore: document.getElementById("snrPaddingBefore"),
  snrPaddingAfter: document.getElementById("snrPaddingAfter"),
  snrBinSeconds: document.getElementById("snrBinSeconds"),
  snrBtn: document.getElementById("snrBtn"),
  snrResults: document.getElementById("snrResults"),
  traceViewBtn: document.getElementById("traceViewBtn"),
  snrViewBtn: document.getElementById("snrViewBtn"),
  experimentName: document.getElementById("experimentName"),
  plotTitle: document.getElementById("plotTitle"),
  traceMeta: document.getElementById("traceMeta"),
  plot: document.getElementById("plot"),
  status: document.getElementById("status"),
};

let plotRequestId = 0;
let snrRequestId = 0;

function setStatus(message) {
  el.status.textContent = message;
}

async function getJson(url) {
  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok || payload.error) {
    throw new Error(payload.error || response.statusText);
  }
  return payload;
}

function params(values) {
  return new URLSearchParams(values).toString();
}

function renderMeta(items) {
  el.traceMeta.innerHTML = "";
  for (const item of items) {
    const chip = document.createElement("div");
    chip.className = "meta-chip";
    chip.textContent = item;
    el.traceMeta.appendChild(chip);
  }
}

function formatMetric(value, digits = 4) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "n/a";
  }
  return Number(value).toFixed(digits);
}

function populateSnrMethods(methods) {
  state.snrMethods = methods || [];
  el.snrMethod.innerHTML = "";
  for (const method of state.snrMethods) {
    const option = document.createElement("option");
    option.value = method.key;
    option.textContent = method.label;
    el.snrMethod.appendChild(option);
  }
}

function renderSnrResults(payload) {
  const resultGroups = payload.signal_results || { [payload.signal_source]: payload };
  const summaryCards = Object.values(resultGroups)
    .map(
      (group) => `
        <div>
          <span>${group.signal_source_label}</span>
          <strong>${formatMetric(group.summary.mean_snr, 3)}</strong>
        </div>`,
    )
    .join("");
  const tables = Object.values(resultGroups)
    .map((group) => {
      const rows = group.results
        .map(
          (item) => `
            <tr>
              <td>${item.cell_id}</td>
              <td>${formatMetric(item.snr, 3)}</td>
              <td>${formatMetric(item.average_spike_height, 4)}</td>
              <td>${formatMetric(item.noise_std, 4)}</td>
              <td>${item.spike_count}</td>
              <td>${item.noise_frame_count}</td>
            </tr>`,
        )
        .join("");

      return `
        <div class="snr-table-title">${group.signal_source_label}</div>
        <div class="snr-table-wrap">
          <table class="snr-table">
            <thead>
              <tr>
                <th>Cell</th>
                <th>SNR</th>
                <th>Spike avg</th>
                <th>Noise SD</th>
                <th>Spikes</th>
                <th>Noise</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>`;
    })
    .join("");

  el.snrResults.className = "snr-results";
  el.snrResults.innerHTML = `
    <div class="snr-summary">
      ${summaryCards}
    </div>
    <div class="snr-context">
      ${payload.method_label} on ${payload.signal_source_label}; HP cutoff ${payload.highpass_cutoff_hz} Hz; start ${payload.start_frame}; bin ${payload.bin_seconds}s; pad ${payload.padding_before}/${payload.padding_after}
    </div>
    ${tables}`;
}

function clearSnrResults() {
  state.lastSnrPayload = null;
  el.snrResults.className = "snr-results muted";
  el.snrResults.textContent = "No SNR calculated";
}

function setActiveView(view) {
  state.activeView = view;
  el.traceViewBtn.classList.toggle("active", view === "traces");
  el.snrViewBtn.classList.toggle("active", view === "snr");
}

function clearExperiment() {
  state.experimentPath = "";
  state.traceTypes = [];
  state.spikeRoiIndices = new Set();
  state.lastTracePayload = null;
  state.lastSnrPayload = null;
  el.experimentName.textContent = "No experiment selected";
  el.plotTitle.textContent = "Browse to an experiment folder";
  el.traceType.innerHTML = "";
  el.roiSelect.innerHTML = "";
  renderMeta([]);
  clearSnrResults();
  Plotly.purge(el.plot);
}

async function browse(path) {
  setStatus("Browsing folders...");
  const payload = await getJson(`/api/browse?${params({ path })}`);
  state.folderPath = payload.path;
  el.currentFolder.textContent = payload.path;
  el.folderList.innerHTML = "";
  el.upBtn.disabled = !payload.parent;
  el.upBtn.dataset.parent = payload.parent || "";

  for (const child of payload.children) {
    const button = document.createElement("button");
    button.className = "folder-item";
    button.innerHTML = `<span>${child.name}</span>${child.has_traces ? '<span class="badge">traces</span>' : ""}`;
    button.addEventListener("click", () => browse(child.path));
    el.folderList.appendChild(button);
  }

  if (payload.is_experiment) {
    await loadExperiment(payload.path);
    return;
  }

  clearExperiment();
  setStatus("Browse to an experiment folder");
}

function populateTraceTypes(traceTypes) {
  el.traceType.innerHTML = "";
  for (const traceType of traceTypes) {
    const option = document.createElement("option");
    option.value = traceType.key;
    option.disabled = !traceType.available;
    option.textContent = traceType.available
      ? `${traceType.label} (${traceType.columns} cells)`
      : `${traceType.label} (missing)`;
    el.traceType.appendChild(option);
  }

  const firstAvailable = traceTypes.find((item) => item.key === "mcsf" && item.available) || traceTypes.find((item) => item.available);
  if (firstAvailable) {
    el.traceType.value = firstAvailable.key;
  }
}

function getSelectedTraceTypeInfo() {
  return state.traceTypes.find((item) => item.key === el.traceType.value);
}

function populateRois() {
  const selectedTraceType = getSelectedTraceTypeInfo();
  const previousValue = el.roiSelect.value || "all";
  el.roiSelect.innerHTML = "";

  if (!selectedTraceType || !selectedTraceType.available) {
    return;
  }

  const allOption = document.createElement("option");
  allOption.value = "all";
  allOption.textContent = `All cells (${selectedTraceType.columns})`;
  el.roiSelect.appendChild(allOption);

  for (let roi = 0; roi < selectedTraceType.columns; roi += 1) {
    const cellId = roi + 1;
    const option = document.createElement("option");
    option.value = String(cellId);
    option.textContent = state.spikeRoiIndices.has(roi) ? `Cell ${cellId} (spikes)` : `Cell ${cellId}`;
    el.roiSelect.appendChild(option);
  }

  const previousStillValid =
    previousValue === "all" ||
    (Number.isInteger(Number(previousValue)) &&
      Number(previousValue) >= 1 &&
      Number(previousValue) <= selectedTraceType.columns);
  el.roiSelect.value = previousStillValid ? previousValue : "all";
}

async function loadExperiment(path) {
  const experimentPath = path;
  if (!experimentPath) {
    return;
  }

  setStatus("Loading experiment traces...");
  const payload = await getJson(`/api/experiment?${params({ experiment_path: experimentPath })}`);
  state.experimentPath = payload.experiment_path;
  state.traceTypes = payload.trace_types;
  state.spikeRoiIndices = new Set(payload.spike_roi_indices || []);
  el.experimentName.textContent = payload.name;
  el.plotTitle.textContent = "Available trace types";
  populateTraceTypes(payload.trace_types);
  populateRois();

  const meta = payload.trace_types.map((item) => {
    if (!item.available) {
      return `${item.label}: missing`;
    }
    const file = item.files[0];
    return `${item.label}: ${item.columns} cells, ${file.size_mb} MB`;
  });
  renderMeta(meta);

  const firstAvailable = payload.trace_types.find((item) => item.key === "mcsf" && item.available) || payload.trace_types.find((item) => item.available);
  setStatus(firstAvailable ? "Ready to plot" : "No standard trace CSVs found");
  if (firstAvailable) {
    await plotTraces();
  }
}

function buildPlot(payload) {
  const showLegend = payload.traces.length <= 12;
  const traces = payload.traces.map((trace) => ({
    x: payload.x,
    y: trace.y,
    type: "scattergl",
    mode: "lines",
    name: trace.name,
    line: { width: 1.35, color: "#ff2f75" },
    xaxis: "x",
    yaxis: "y",
    showlegend: showLegend,
    legendgroup: trace.name,
  }));
  for (const hpTrace of payload.highpass_traces || []) {
    traces.push({
      x: payload.x,
      y: hpTrace.y,
      type: "scattergl",
      mode: "lines",
      name: hpTrace.name,
      line: { width: 1.15, color: "#00f0a8" },
      xaxis: "x2",
      yaxis: "y2",
      showlegend: showLegend,
      legendgroup: hpTrace.name.replace(" HP", ""),
    });
  }
  for (const spikeTrace of payload.spikes || []) {
    traces.push({
      x: spikeTrace.x,
      y: spikeTrace.y,
      type: "scattergl",
      mode: "markers",
      name: spikeTrace.name,
      marker: {
        color: "#22c7ff",
        size: 7,
        symbol: "circle",
        line: { width: 1.4, color: "#d5f6ff" },
      },
      xaxis: "x",
      yaxis: "y",
      showlegend: false,
      hovertemplate: `${spikeTrace.name}<br>Frame %{x}<extra></extra>`,
    });
    traces.push({
      x: spikeTrace.x,
      y: spikeTrace.hp_y,
      type: "scattergl",
      mode: "markers",
      name: `${spikeTrace.name} HP`,
      marker: {
        color: "#22c7ff",
        size: 7,
        symbol: "circle",
        line: { width: 1.4, color: "#d5f6ff" },
      },
      xaxis: "x2",
      yaxis: "y2",
      showlegend: false,
      hovertemplate: `${spikeTrace.name}<br>Frame %{x}<extra></extra>`,
    });
  }

  const layout = {
    autosize: true,
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "#080c14",
    font: { color: "#dbe6f7" },
    margin: { l: 58, r: 24, t: 22, b: 48 },
    xaxis: {
      domain: [0, 1],
      anchor: "y",
      matches: "x2",
      gridcolor: "rgba(255,255,255,0.07)",
      zerolinecolor: "rgba(255,255,255,0.12)",
      showticklabels: false,
    },
    yaxis: {
      title: payload.normalized ? "Trace norm. + offset" : "Trace + offset",
      domain: [0.55, 1],
      anchor: "x",
      gridcolor: "rgba(255,255,255,0.07)",
      zerolinecolor: "rgba(255,255,255,0.12)",
    },
    xaxis2: {
      title: "Frame",
      domain: [0, 1],
      anchor: "y2",
      gridcolor: "rgba(255,255,255,0.07)",
      zerolinecolor: "rgba(255,255,255,0.12)",
    },
    yaxis2: {
      title: payload.normalized ? "HP norm. + offset" : "High-pass + offset",
      domain: [0, 0.45],
      anchor: "x2",
      gridcolor: "rgba(255,255,255,0.07)",
      zerolinecolor: "rgba(255,255,255,0.12)",
    },
    legend: {
      orientation: "h",
      yanchor: "bottom",
      y: 1.02,
      xanchor: "right",
      x: 1,
      bgcolor: "rgba(8,12,20,0.72)",
    },
    showlegend: showLegend,
    hovermode: "closest",
  };

  Plotly.react(el.plot, traces, layout, {
    responsive: true,
    displaylogo: false,
    modeBarButtonsToRemove: ["lasso2d", "select2d"],
  }).then(() => Plotly.Plots.resize(el.plot));
}

function buildSnrPlot(payload) {
  const colors = {
    trace: "#ff2f75",
    highpass: "#00f0a8",
  };
  const resultGroups = payload.signal_results || { [payload.signal_source]: payload };
  const traces = [];
  const selectedCellCount = payload.selected_cell_ids.length;

  for (const [source, group] of Object.entries(resultGroups)) {
    const color = colors[source] || "#22c7ff";
    const meanName = selectedCellCount === 1 ? `${group.signal_source_label} SNR` : `${group.signal_source_label} mean`;
    traces.push({
      x: group.time_summary.map((item) => item.center_seconds),
      y: group.time_summary.map((item) => item.mean_snr),
      type: "scatter",
      mode: "lines+markers",
      name: meanName,
      line: { width: 2.4, color },
      marker: { size: 6, color },
      hovertemplate: `${meanName}<br>Time %{x:.1f}s<br>SNR %{y:.3f}<extra></extra>`,
    });

    if (group.binned_results.length > 1 && group.binned_results.length <= 6) {
      for (const cell of group.binned_results) {
        traces.push({
          x: cell.bins.map((item) => item.center_seconds),
          y: cell.bins.map((item) => item.snr),
          type: "scatter",
          mode: "lines",
          name: `${group.signal_source_label} Cell ${cell.cell_id}`,
          line: { width: 1.1, color, dash: "dot" },
          opacity: 0.42,
          hovertemplate: `${group.signal_source_label} Cell ${cell.cell_id}<br>Time %{x:.1f}s<br>SNR %{y:.3f}<extra></extra>`,
        });
      }
    }
  }

  const layout = {
    autosize: true,
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "#080c14",
    font: { color: "#dbe6f7" },
    margin: { l: 58, r: 24, t: 22, b: 52 },
    xaxis: {
      title: "Time (s)",
      gridcolor: "rgba(255,255,255,0.07)",
      zerolinecolor: "rgba(255,255,255,0.12)",
    },
    yaxis: {
      title: "SNR",
      gridcolor: "rgba(255,255,255,0.07)",
      zerolinecolor: "rgba(255,255,255,0.12)",
    },
    legend: {
      orientation: "h",
      yanchor: "bottom",
      y: 1.02,
      xanchor: "right",
      x: 1,
      bgcolor: "rgba(8,12,20,0.72)",
    },
    hovermode: "closest",
  };

  Plotly.react(el.plot, traces, layout, {
    responsive: true,
    displaylogo: false,
    modeBarButtonsToRemove: ["lasso2d", "select2d"],
  }).then(() => Plotly.Plots.resize(el.plot));
}

async function plotTraces() {
  if (!state.experimentPath) {
    setStatus("Browse to an experiment folder first");
    return;
  }

  const requestId = ++plotRequestId;
  setStatus("Loading trace CSV...");
  el.plotBtn.disabled = true;
  try {
    const payload = await getJson(
      `/api/traces?${params({
        experiment_path: state.experimentPath,
        trace_type: el.traceType.value,
        roi: el.roiSelect.value,
        normalize: String(el.normalize.checked),
        show_spikes: String(el.showSpikes.checked),
        offset: el.offsetInput.value,
        start_frame: el.startFrameInput.value,
        highpass_cutoff_hz: el.highpassCutoffInput.value,
      })}`,
    );
    if (requestId !== plotRequestId) {
      return;
    }

    buildPlot(payload);
    state.lastTracePayload = payload;
    setActiveView("traces");
    el.plotTitle.textContent = payload.trace_type;
    renderMeta([
      `${payload.selected_cell_ids.length} selected of ${payload.total_columns} cells`,
      payload.start_frame > 0 ? `Showing from frame ${payload.start_frame}` : "Showing full trace",
      `${payload.plotted_points} plotted of ${payload.original_points} frames`,
      `High-pass cutoff: ${payload.highpass_cutoff_hz} Hz`,
      payload.normalized ? `Normalized: ${payload.normalization_method}` : "Raw signal",
      payload.spikes_available && payload.spikes_match_displayed_trace
        ? `${(payload.spikes || []).length} cell spike overlays`
        : payload.spikes_available
          ? "Spikes detected on MCSF traces"
          : "No detected peaks file",
      payload.cache_hit ? "Loaded from memory cache" : "Loaded from CSV",
      payload.file,
    ]);
    setStatus("Plot updated");
  } finally {
    if (requestId === plotRequestId) {
      el.plotBtn.disabled = false;
    }
  }
}

async function calculateSnr() {
  if (!state.experimentPath) {
    setStatus("Browse to an experiment folder first");
    return;
  }

  const requestId = ++snrRequestId;
  setStatus("Calculating SNR...");
  el.snrBtn.disabled = true;
  try {
    const payload = await getJson(
      `/api/snr?${params({
        experiment_path: state.experimentPath,
        trace_type: el.traceType.value,
        roi: el.roiSelect.value,
        method: el.snrMethod.value || "basic",
        signal_source: el.snrSignalSource.value,
        highpass_cutoff_hz: el.highpassCutoffInput.value,
        padding_before: el.snrPaddingBefore.value,
        padding_after: el.snrPaddingAfter.value,
        start_frame: el.startFrameInput.value,
        bin_seconds: el.snrBinSeconds.value,
      })}`,
    );
    if (requestId !== snrRequestId) {
      return;
    }
    state.lastSnrPayload = payload;
    renderSnrResults(payload);
    buildSnrPlot(payload);
    setActiveView("snr");
    el.plotTitle.textContent = `SNR over time - ${payload.trace_type}`;
    setStatus("SNR calculated");
  } finally {
    if (requestId === snrRequestId) {
      el.snrBtn.disabled = false;
    }
  }
}

function updateHighpassCutoffLabel() {
  el.highpassCutoffValue.value = `${el.highpassCutoffInput.value} Hz`;
}

function handleHighpassCutoffChange() {
  updateHighpassCutoffLabel();
  if (state.lastSnrPayload || state.activeView === "snr") {
    calculateSnr().catch((error) => setStatus(error.message));
    return;
  }
  clearSnrResults();
  plotTraces().catch((error) => setStatus(error.message));
}

async function boot() {
  try {
    const defaults = await getJson("/api/defaults");
    populateSnrMethods(defaults.snr_methods);
    el.snrPaddingBefore.value = defaults.default_snr_padding_before;
    el.snrPaddingAfter.value = defaults.default_snr_padding_after;
    el.snrBinSeconds.value = defaults.default_snr_bin_seconds;
    el.highpassCutoffInput.value = defaults.default_highpass_cutoff_hz;
    updateHighpassCutoffLabel();
    await browse(defaults.data_root);
  } catch (error) {
    setStatus(error.message);
  }
}

el.plotBtn.addEventListener("click", () => plotTraces().catch((error) => setStatus(error.message)));
el.snrBtn.addEventListener("click", () => calculateSnr().catch((error) => setStatus(error.message)));
el.traceViewBtn.addEventListener("click", () => {
  if (!state.lastTracePayload) {
    setStatus("Plot traces first");
    return;
  }
  buildPlot(state.lastTracePayload);
  setActiveView("traces");
  el.plotTitle.textContent = state.lastTracePayload.trace_type;
});
el.snrViewBtn.addEventListener("click", () => {
  if (!state.lastSnrPayload) {
    setStatus("Calculate SNR first");
    return;
  }
  buildSnrPlot(state.lastSnrPayload);
  setActiveView("snr");
  el.plotTitle.textContent = `SNR over time - ${state.lastSnrPayload.trace_type}`;
});
el.upBtn.addEventListener("click", () => browse(el.upBtn.dataset.parent).catch((error) => setStatus(error.message)));
el.traceType.addEventListener("change", () => {
  populateRois();
  clearSnrResults();
  plotTraces().catch((error) => setStatus(error.message));
});
el.roiSelect.addEventListener("change", () => {
  clearSnrResults();
  plotTraces().catch((error) => setStatus(error.message));
});
el.normalize.addEventListener("change", () => plotTraces().catch((error) => setStatus(error.message)));
el.showSpikes.addEventListener("change", () => plotTraces().catch((error) => setStatus(error.message)));
el.startFrameInput.addEventListener("change", () => {
  clearSnrResults();
  plotTraces().catch((error) => setStatus(error.message));
});
el.highpassCutoffInput.addEventListener("input", updateHighpassCutoffLabel);
el.highpassCutoffInput.addEventListener("change", handleHighpassCutoffChange);
el.snrMethod.addEventListener("change", clearSnrResults);
el.snrSignalSource.addEventListener("change", clearSnrResults);
el.snrPaddingBefore.addEventListener("change", clearSnrResults);
el.snrPaddingAfter.addEventListener("change", clearSnrResults);
el.snrBinSeconds.addEventListener("change", clearSnrResults);

window.addEventListener("resize", () => Plotly.Plots.resize(el.plot));
updateHighpassCutoffLabel();
boot();
