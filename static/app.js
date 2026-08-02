const state = {
  folderPath: "",
  experimentPath: "",
  traceTypes: [],
  spikeRoiIndices: new Set(),
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
  experimentName: document.getElementById("experimentName"),
  plotTitle: document.getElementById("plotTitle"),
  traceMeta: document.getElementById("traceMeta"),
  plot: document.getElementById("plot"),
  status: document.getElementById("status"),
};

let plotRequestId = 0;

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

function clearExperiment() {
  state.experimentPath = "";
  state.traceTypes = [];
  state.spikeRoiIndices = new Set();
  el.experimentName.textContent = "No experiment selected";
  el.plotTitle.textContent = "Browse to an experiment folder";
  el.traceType.innerHTML = "";
  el.roiSelect.innerHTML = "";
  renderMeta([]);
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

function updateHighpassCutoffLabel() {
  el.highpassCutoffValue.value = `${el.highpassCutoffInput.value} Hz`;
}

async function boot() {
  try {
    const defaults = await getJson("/api/defaults");
    await browse(defaults.data_root);
  } catch (error) {
    setStatus(error.message);
  }
}

el.plotBtn.addEventListener("click", () => plotTraces().catch((error) => setStatus(error.message)));
el.upBtn.addEventListener("click", () => browse(el.upBtn.dataset.parent).catch((error) => setStatus(error.message)));
el.traceType.addEventListener("change", () => {
  populateRois();
  plotTraces().catch((error) => setStatus(error.message));
});
el.roiSelect.addEventListener("change", () => plotTraces().catch((error) => setStatus(error.message)));
el.normalize.addEventListener("change", () => plotTraces().catch((error) => setStatus(error.message)));
el.showSpikes.addEventListener("change", () => plotTraces().catch((error) => setStatus(error.message)));
el.startFrameInput.addEventListener("change", () => plotTraces().catch((error) => setStatus(error.message)));
el.highpassCutoffInput.addEventListener("input", updateHighpassCutoffLabel);
el.highpassCutoffInput.addEventListener("change", () => plotTraces().catch((error) => setStatus(error.message)));

window.addEventListener("resize", () => Plotly.Plots.resize(el.plot));
updateHighpassCutoffLabel();
boot();
