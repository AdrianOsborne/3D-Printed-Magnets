const state = {
  data: null,
  selectedImage: null,
  activeTab: "search",
  themeMode: localStorage.getItem("magnet-studio-theme") || "system",
  autoSaveTimer: null,
  autoGenerateTimer: null,
  previewTimer: null,
  saveSequence: 0,
  dirtyImages: new Set(),
  hiddenOutputNames: new Set(),
  modelSettingsDirty: false,
};

const emptyThumb = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 120 120'%3E%3Crect width='120' height='120' rx='18' fill='%23131b30'/%3E%3Cpath d='M36 36h48v48H36z' fill='none' stroke='%236f83b7' stroke-width='6' stroke-dasharray='8 8'/%3E%3C/svg%3E";

const elements = {
  tabButtons: Array.from(document.querySelectorAll(".tab-button")),
  tabPanels: Array.from(document.querySelectorAll(".tab-panel")),
  themeButtons: Array.from(document.querySelectorAll(".theme-button")),
  sidebarLinks: Array.from(document.querySelectorAll(".sidebar-link")),
  revealBlocks: Array.from(document.querySelectorAll(".reveal")),
  searchQuery: document.getElementById("search-query"),
  searchButton: document.getElementById("search-button"),
  searchMeta: document.getElementById("search-meta"),
  searchResults: document.getElementById("search-results"),
  svgrepoUrl: document.getElementById("svgrepo-url"),
  svgrepoImportButton: document.getElementById("svgrepo-import-button"),
  uploadInput: document.getElementById("upload-input"),
  uploadLibrary: document.getElementById("upload-library"),
  urlLibrary: document.getElementById("url-library"),
  svgUrl: document.getElementById("svg-url"),
  svgName: document.getElementById("svg-name"),
  importButton: document.getElementById("import-button"),
  allImages: document.getElementById("all-images"),
  enabledImages: document.getElementById("enabled-images"),
  renameInput: document.getElementById("rename-input"),
  thresholdInput: document.getElementById("threshold-input"),
  thresholdValue: document.getElementById("threshold-value"),
  invertInput: document.getElementById("invert-input"),
  originalPreview: document.getElementById("original-preview"),
  maskPreview: document.getElementById("mask-preview"),
  diameterInput: document.getElementById("diameter-input"),
  baseThicknessInput: document.getElementById("base-thickness-input"),
  imageExtrusionInput: document.getElementById("image-extrusion-input"),
  imageMarginInput: document.getElementById("image-margin-input"),
  pocketDiameterInput: document.getElementById("pocket-diameter-input"),
  pocketDepthInput: document.getElementById("pocket-depth-input"),
  outputList: document.getElementById("output-list"),
  status: document.getElementById("status"),
};

function setStatus(message, tone = "") {
  elements.status.textContent = message;
  elements.status.className = `status ${tone ? `is-${tone}` : ""}`.trim();
}

function currentImage() {
  if (!state.data || !state.selectedImage) return null;
  return state.data.images.find((image) => image.name === state.selectedImage) || null;
}

function effectiveTheme(mode) {
  if (mode === "system") {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return mode;
}

function applyTheme(mode) {
  state.themeMode = mode;
  localStorage.setItem("magnet-studio-theme", mode);
  document.documentElement.dataset.themeMode = mode;
  document.documentElement.setAttribute("data-theme", effectiveTheme(mode));
  for (const button of elements.themeButtons) {
    button.classList.toggle("is-active", button.dataset.themeChoice === mode);
  }
}

function setActiveTab(tab) {
  state.activeTab = tab;
  for (const button of elements.tabButtons) {
    button.classList.toggle("is-active", button.dataset.tab === tab);
  }
  for (const panel of elements.tabPanels) {
    panel.classList.toggle("is-active", panel.dataset.panel === tab);
  }
}

function generationSettings() {
  return {
    diameter: Number(elements.diameterInput.value),
    baseThickness: Number(elements.baseThicknessInput.value),
    imageExtrusion: Number(elements.imageExtrusionInput.value),
    imageMargin: Number(elements.imageMarginInput.value),
    pocketDiameter: Number(elements.pocketDiameterInput.value),
    pocketDepth: Number(elements.pocketDepthInput.value),
  };
}

function previewUrl(image, kind) {
  const threshold = Number(elements.thresholdInput.value || image.threshold);
  const invert = elements.invertInput.checked ? "true" : "false";
  const base = kind === "mask" ? image.maskPreviewUrl : image.originalPreviewUrl;
  return `${base}&threshold=${threshold}&invert=${invert}&t=${Date.now()}`;
}

function syncEditor() {
  const image = currentImage();
  if (!image) {
    elements.renameInput.value = "";
    elements.thresholdInput.value = state.data?.defaults.threshold || 160;
    elements.thresholdValue.textContent = String(state.data?.defaults.threshold || 160);
    elements.invertInput.checked = false;
    elements.originalPreview.removeAttribute("src");
    elements.maskPreview.removeAttribute("src");
    return;
  }
  elements.renameInput.value = image.displayName;
  elements.thresholdInput.value = image.threshold;
  elements.thresholdValue.textContent = String(image.threshold);
  elements.invertInput.checked = Boolean(image.invert);
  refreshPreview(true);
}

function refreshPreview(immediate = false) {
  const image = currentImage();
  if (!image) return;
  clearTimeout(state.previewTimer);
  const run = () => {
    elements.originalPreview.src = previewUrl(image, "original");
    elements.maskPreview.src = previewUrl(image, "mask");
  };
  if (immediate) run();
  else state.previewTimer = window.setTimeout(run, 120);
}

function renderDefaults() {
  if (!state.data) return;
  const defaults = state.data.defaults;
  if (!elements.diameterInput.value) elements.diameterInput.value = defaults.diameter;
  if (!elements.baseThicknessInput.value) elements.baseThicknessInput.value = defaults.baseThickness;
  if (!elements.imageExtrusionInput.value) elements.imageExtrusionInput.value = defaults.imageExtrusion;
  if (!elements.imageMarginInput.value) elements.imageMarginInput.value = defaults.imageMargin;
  if (!elements.pocketDiameterInput.value) elements.pocketDiameterInput.value = defaults.pocketDiameter;
  if (!elements.pocketDepthInput.value) elements.pocketDepthInput.value = defaults.pocketDepth;
}

function createEmptyState(text) {
  const paragraph = document.createElement("p");
  paragraph.className = "asset-empty";
  paragraph.textContent = text;
  return paragraph;
}

function createAssetCard(image, options = {}) {
  const card = document.createElement(options.clickable ? "button" : "div");
  if (options.clickable) {
    card.type = "button";
    card.className = `asset-card asset-clicker ${options.selected ? "is-editing" : ""}`;
  } else {
    card.className = `asset-card ${options.selected ? "is-selected" : ""}`;
  }

  if (options.showToggle) {
    const toggle = document.createElement("input");
    toggle.type = "checkbox";
    toggle.className = "asset-toggle";
    toggle.checked = Boolean(options.checked);
    toggle.addEventListener("click", (event) => event.stopPropagation());
    toggle.addEventListener("change", () => options.onToggle?.(toggle.checked));
    card.appendChild(toggle);
  }

  if (options.clickable) {
    card.addEventListener("click", () => options.onClick?.());
  }

  const preview = document.createElement("img");
  preview.className = "asset-preview";
  preview.alt = image.displayName || image.name;
  preview.src = image.thumbnailUrl || image.originalPreviewUrl || emptyThumb;
  card.appendChild(preview);

  const source = document.createElement("span");
  source.className = "asset-source";
  source.textContent = image.source.toUpperCase();
  card.appendChild(source);

  const title = document.createElement("p");
  title.className = "asset-title";
  title.textContent = image.displayName || image.name;
  card.appendChild(title);

  const meta = document.createElement("p");
  meta.className = "asset-meta";
  meta.textContent = `${image.name}${image.hasOutput ? " | STL ready" : ""}`;
  card.appendChild(meta);

  return card;
}

function renderGrid(target, items, emptyText, mapper) {
  target.innerHTML = "";
  if (!items.length) {
    target.appendChild(createEmptyState(emptyText));
    return;
  }
  for (const item of items) {
    target.appendChild(mapper(item));
  }
}

function renderSearchSection() {
  const searchImages = state.data?.imagesBySource?.search || [];
  renderGrid(
    elements.searchResults,
    searchImages,
    "No SVG Repo images imported yet.",
    (image) => createAssetCard(image, {
      showToggle: true,
      checked: image.enabled,
      onToggle: (enabled) => toggleImage(image.name, enabled),
    }),
  );
}

function renderSourceLibraries() {
  const bySource = state.data?.imagesBySource || { upload: [], url: [] };
  renderGrid(
    elements.uploadLibrary,
    bySource.upload || [],
    "No uploaded images yet.",
    (image) => createAssetCard(image, {
      showToggle: true,
      checked: image.enabled,
      onToggle: (enabled) => toggleImage(image.name, enabled),
    }),
  );
  renderGrid(
    elements.urlLibrary,
    bySource.url || [],
    "No imported image URLs yet.",
    (image) => createAssetCard(image, {
      showToggle: true,
      checked: image.enabled,
      onToggle: (enabled) => toggleImage(image.name, enabled),
    }),
  );
}

function renderAllImages() {
  renderGrid(
    elements.allImages,
    state.data?.images || [],
    "No images have been acquired yet.",
    (image) => createAssetCard(image, {
      showToggle: true,
      checked: image.enabled,
      onToggle: (enabled) => toggleImage(image.name, enabled),
    }),
  );
}

function renderEnabledEditorList() {
  renderGrid(
    elements.enabledImages,
    state.data?.enabledImages || [],
    "Enable some images to edit them here.",
    (image) => createAssetCard(image, {
      clickable: true,
      selected: image.name === state.selectedImage,
      onClick: () => {
        state.selectedImage = image.name;
        syncEditor();
        renderEnabledEditorList();
      },
    }),
  );
}

function renderOutputs() {
  elements.outputList.innerHTML = "";
  const outputs = (state.data?.outputs || []).filter((output) => !state.hiddenOutputNames.has(output.name));
  if (!outputs.length) {
    elements.outputList.appendChild(createEmptyState("No STL files have been generated yet."));
    return;
  }
  for (const output of outputs) {
    const link = document.createElement("a");
    link.className = "output-link";
    link.href = output.downloadUrl;
    link.textContent = output.name;
    elements.outputList.appendChild(link);
  }
}

function render() {
  renderDefaults();
  renderSearchSection();
  renderSourceLibraries();
  renderAllImages();
  renderEnabledEditorList();
  renderOutputs();
  syncEditor();
}

async function refreshState(preferredSelection = null) {
  const response = await fetch("/api/state");
  const payload = await response.json();
  state.data = payload;
  const enabledNames = payload.enabledImages.map((image) => image.name);
  if (preferredSelection && enabledNames.includes(preferredSelection)) state.selectedImage = preferredSelection;
  else if (state.selectedImage && enabledNames.includes(state.selectedImage)) state.selectedImage = state.selectedImage;
  else state.selectedImage = enabledNames[0] || null;
  render();
}

async function toggleImage(name, enabled) {
  const response = await fetch(`/api/images/${encodeURIComponent(name)}/toggle`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  const payload = await response.json();
  if (!response.ok) {
    setStatus(payload.error || "Could not update that image.", "error");
    return;
  }
  state.dirtyImages.add(name);
  if (!enabled) {
    state.hiddenOutputNames.add(`${name.replace(/\.[^.]+$/, "")}.stl`);
  }
  state.data = payload.state;
  if (!state.data.enabledImages.some((image) => image.name === state.selectedImage)) {
    state.selectedImage = state.data.enabledImages[0]?.name || null;
  }
  render();
  setStatus(`${enabled ? "Enabled" : "Disabled"} ${name}.`, "success");
  queueAutoGenerate("Updating STL files...");
}

async function uploadFiles(files) {
  if (!files.length) return;
  const formData = new FormData();
  for (const file of files) formData.append("files", file);
  setStatus("Uploading images...");
  const response = await fetch("/api/images/upload", { method: "POST", body: formData });
  const payload = await response.json();
  if (!response.ok) {
    setStatus(payload.error || "Upload failed.", "error");
    return;
  }
  state.data = payload.state;
  state.selectedImage = payload.imported[0] || state.selectedImage;
  payload.imported.forEach((name) => state.dirtyImages.add(name));
  render();
  setStatus(`Imported ${payload.imported.length} image${payload.imported.length === 1 ? "" : "s"}.`, "success");
  queueAutoGenerate("Generating STL files for imported images...");
}

async function importUrlImage() {
  const url = elements.svgUrl.value.trim();
  if (!url) {
    setStatus("Paste an image URL first.", "error");
    return;
  }
  setStatus("Importing image from URL...");
  const response = await fetch("/api/images/import-url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, name: elements.svgName.value.trim() }),
  });
  const payload = await response.json();
  if (!response.ok) {
    setStatus(payload.error || "URL import failed.", "error");
    return;
  }
  elements.svgUrl.value = "";
  elements.svgName.value = "";
  state.data = payload.state;
  state.selectedImage = payload.imported;
  state.dirtyImages.add(payload.imported);
  render();
  setStatus(`Imported ${payload.imported}.`, "success");
  queueAutoGenerate("Generating STL files for imported image...");
}

function buildSvgrepoSearchUrl() {
  const term = (elements.searchQuery.value.trim() || "dollar").trim().toLowerCase().split(/\s+/).join("-");
  return `https://www.svgrepo.com/vectors/${encodeURIComponent(term)}/monocolor/`;
}

function openSearchWebsite() {
  const url = buildSvgrepoSearchUrl();
  window.open(url, "_blank", "noopener");
  elements.searchMeta.textContent = `Opened ${url}`;
  setStatus("Opened SVG Repo search in a new tab.", "success");
}

async function importSvgRepoUrl() {
  const url = elements.svgrepoUrl.value.trim();
  if (!url) {
    setStatus("Paste an SVG Repo link first.", "error");
    return;
  }
  setStatus("Importing SVG Repo image...");
  const response = await fetch("/api/svgrepo/import-link", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  const payload = await response.json();
  if (!response.ok) {
    setStatus(payload.error || "SVG Repo import failed.", "error");
    return;
  }
  elements.svgrepoUrl.value = "";
  state.data = payload.state;
  state.selectedImage = payload.imported;
  state.dirtyImages.add(payload.imported);
  render();
  setStatus(`Imported ${payload.imported} from SVG Repo.`, "success");
  queueAutoGenerate("Generating STL files for imported SVG Repo image...");
}

async function persistArtworkEdits() {
  const image = currentImage();
  if (!image) return false;
  let activeName = image.name;
  const desiredName = elements.renameInput.value.trim();
  if (desiredName && desiredName !== image.displayName) {
    const renameResponse = await fetch(`/api/images/${encodeURIComponent(image.name)}/rename`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: desiredName }),
    });
    const renamePayload = await renameResponse.json();
    if (!renameResponse.ok) {
      setStatus(renamePayload.error || "Rename failed.", "error");
      return false;
    }
    state.data = renamePayload.state;
    state.selectedImage = renamePayload.newName;
    activeName = renamePayload.newName;
  }

  const settingsResponse = await fetch(`/api/images/${encodeURIComponent(activeName)}/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      threshold: Number(elements.thresholdInput.value),
      invert: elements.invertInput.checked,
    }),
  });
  const settingsPayload = await settingsResponse.json();
  if (!settingsResponse.ok) {
    setStatus(settingsPayload.error || "Could not save artwork settings.", "error");
    return false;
  }
  state.dirtyImages.add(activeName);
  state.data = settingsPayload.state;
  state.selectedImage = activeName;
  render();
  return true;
}

async function autoGenerateNow(statusMessage = "Refreshing STL files...") {
  const enabledImageNames = state.data?.enabledImages.map((image) => image.name) || [];
  const imagesToGenerate = state.modelSettingsDirty
    ? enabledImageNames
    : enabledImageNames.filter((name) => state.dirtyImages.has(name));

  if (!enabledImageNames.length) {
    renderOutputs();
    setStatus("No enabled images to generate.", "error");
    return;
  }
  if (!imagesToGenerate.length && !state.hiddenOutputNames.size) {
    return;
  }
  imagesToGenerate.forEach((name) => state.hiddenOutputNames.add(`${name.replace(/\.[^.]+$/, "")}.stl`));
  renderOutputs();
  setStatus(statusMessage);
  const response = await fetch("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      images: imagesToGenerate,
      settings: generationSettings(),
    }),
  });
  const payload = await response.json();
  if (!response.ok) {
    setStatus(payload.error || "Generation failed.", "error");
    return;
  }
  state.data = payload.state;
  payload.generated.forEach((item) => {
    state.hiddenOutputNames.delete(item.output);
    state.dirtyImages.delete(item.image);
  });
  state.modelSettingsDirty = false;
  for (const image of state.data.images) {
    if (image.enabled) continue;
    state.hiddenOutputNames.add(`${image.name.replace(/\.[^.]+$/, "")}.stl`);
  }
  renderOutputs();
  setStatus(`Updated ${payload.generated.length} STL file${payload.generated.length === 1 ? "" : "s"}.`, "success");
}

function queueAutoGenerate(statusMessage = "Refreshing STL files...") {
  clearTimeout(state.autoGenerateTimer);
  state.autoGenerateTimer = window.setTimeout(() => {
    autoGenerateNow(statusMessage);
  }, 700);
}

function queueArtworkAutosave() {
  clearTimeout(state.autoSaveTimer);
  const sequence = ++state.saveSequence;
  state.autoSaveTimer = window.setTimeout(async () => {
    const saved = await persistArtworkEdits();
    if (saved && sequence === state.saveSequence) {
      queueAutoGenerate("Saving artwork changes and regenerating...");
    }
  }, 650);
}

function queueModelAutosave() {
  state.modelSettingsDirty = true;
  queueAutoGenerate("Applying 3D model settings and regenerating...");
}

function bindEnterAction(input, action) {
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      action();
    }
  });
}

function updateActiveSidebarLink() {
  const sections = Array.from(document.querySelectorAll(".studio-section"));
  let activeId = sections[0]?.id || "";
  for (const section of sections) {
    const rect = section.getBoundingClientRect();
    if (rect.top <= 140) activeId = section.id;
  }
  for (const link of elements.sidebarLinks) {
    link.classList.toggle("is-active", link.getAttribute("href") === `#${activeId}`);
  }
}

function initRevealObserver() {
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) entry.target.classList.add("is-visible");
    }
  }, { threshold: 0.16 });
  for (const block of elements.revealBlocks) observer.observe(block);
}

function bindEvents() {
  for (const button of elements.tabButtons) {
    button.addEventListener("click", () => setActiveTab(button.dataset.tab));
  }
  for (const button of elements.themeButtons) {
    button.addEventListener("click", () => applyTheme(button.dataset.themeChoice));
  }
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (state.themeMode === "system") applyTheme("system");
  });

  elements.searchButton.addEventListener("click", openSearchWebsite);
  elements.svgrepoImportButton.addEventListener("click", importSvgRepoUrl);
  bindEnterAction(elements.searchQuery, openSearchWebsite);
  bindEnterAction(elements.svgrepoUrl, importSvgRepoUrl);
  bindEnterAction(elements.svgUrl, importUrlImage);

  elements.uploadInput.addEventListener("change", async (event) => {
    await uploadFiles(Array.from(event.target.files || []));
    event.target.value = "";
  });

  elements.importButton.addEventListener("click", importUrlImage);

  elements.renameInput.addEventListener("input", queueArtworkAutosave);
  elements.renameInput.addEventListener("blur", queueArtworkAutosave);
  elements.thresholdInput.addEventListener("input", () => {
    elements.thresholdValue.textContent = elements.thresholdInput.value;
    refreshPreview();
    queueArtworkAutosave();
  });
  elements.invertInput.addEventListener("change", () => {
    refreshPreview(true);
    queueArtworkAutosave();
  });

  [
    elements.diameterInput,
    elements.baseThicknessInput,
    elements.imageExtrusionInput,
    elements.imageMarginInput,
    elements.pocketDiameterInput,
    elements.pocketDepthInput,
  ].forEach((input) => {
    input.addEventListener("input", queueModelAutosave);
    input.addEventListener("change", queueModelAutosave);
  });

  window.addEventListener("scroll", updateActiveSidebarLink, { passive: true });
}

async function init() {
  applyTheme(state.themeMode);
  bindEvents();
  initRevealObserver();
  updateActiveSidebarLink();
  try {
    await refreshState();
    setStatus("Workspace ready.");
  } catch (error) {
    setStatus(`Could not load the app: ${error.message}`, "error");
  }
}

init();
