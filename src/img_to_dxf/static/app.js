(() => {
  const form = document.getElementById("form");
  const fileInput = document.getElementById("file");
  const drop = document.getElementById("drop");
  const fileName = document.getElementById("file-name");
  const statusEl = document.getElementById("status");
  const convertBtn = document.getElementById("convert-btn");
  const downloadBtn = document.getElementById("download-btn");
  const empty = document.getElementById("empty");
  const viewSvg = document.getElementById("view-svg");
  const viewPng = document.getElementById("view-png");
  const viewSource = document.getElementById("view-source");
  const meta = document.getElementById("meta");
  const thRange = document.getElementById("threshold");
  const thLabel = document.getElementById("th-label");
  const thAuto = document.getElementById("th-auto");
  const simRange = document.getElementById("simplify");
  const simLabel = document.getElementById("sim-label");
  const areaRange = document.getElementById("min_area");
  const areaLabel = document.getElementById("area-label");
  const blurRange = document.getElementById("blur");
  const blurLabel = document.getElementById("blur-label");

  let autoThreshold = true;
  let sourceUrl = null;
  let activeTab = "svg";

  function setStatus(text, kind = "") {
    statusEl.textContent = text;
    statusEl.className = "status" + (kind ? ` ${kind}` : "");
  }

  function syncLabels() {
    thLabel.textContent = autoThreshold ? "auto" : String(thRange.value);
    const simplify = (Number(simRange.value) / 1000).toFixed(3);
    simLabel.textContent = simplify;
    const area = (Number(areaRange.value) / 10).toFixed(1);
    areaLabel.textContent = area;
    blurLabel.textContent = String(blurRange.value);
  }

  thRange.addEventListener("input", () => {
    autoThreshold = false;
    syncLabels();
  });
  thAuto.addEventListener("click", () => {
    autoThreshold = true;
    syncLabels();
  });
  simRange.addEventListener("input", syncLabels);
  areaRange.addEventListener("input", syncLabels);
  blurRange.addEventListener("input", syncLabels);
  syncLabels();

  ;["dragenter", "dragover"].forEach((ev) => {
    drop.addEventListener(ev, (e) => {
      e.preventDefault();
      drop.classList.add("dragover");
    });
  });
  ;["dragleave", "drop"].forEach((ev) => {
    drop.addEventListener(ev, (e) => {
      e.preventDefault();
      drop.classList.remove("dragover");
    });
  });
  drop.addEventListener("drop", (e) => {
    const files = e.dataTransfer?.files;
    if (files?.length) {
      fileInput.files = files;
      onFilePicked();
    }
  });
  fileInput.addEventListener("change", onFilePicked);

  function onFilePicked() {
    const file = fileInput.files?.[0];
    if (!file) return;
    fileName.hidden = false;
    fileName.textContent = file.name;
    if (sourceUrl) URL.revokeObjectURL(sourceUrl);
    sourceUrl = URL.createObjectURL(file);
    viewSource.src = sourceUrl;
    setStatus("Hazır — Önizle’ye bas");
  }

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      activeTab = tab.dataset.tab;
      document.querySelectorAll(".tab").forEach((t) => {
        const on = t === tab;
        t.classList.toggle("active", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
      });
      showTab();
    });
  });

  function showTab() {
    const hasSvg = viewSvg.innerHTML.trim().length > 0;
    const hasPng = Boolean(viewPng.getAttribute("src"));

    viewSvg.hidden = true;
    viewPng.hidden = true;
    viewSource.hidden = true;
    empty.hidden = true;

    if (activeTab === "source") {
      if (sourceUrl) viewSource.hidden = false;
      else empty.hidden = false;
      return;
    }
    if (activeTab === "png") {
      if (hasPng) viewPng.hidden = false;
      else empty.hidden = false;
      return;
    }
    if (hasSvg) viewSvg.hidden = false;
    else empty.hidden = false;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const file = fileInput.files?.[0];
    if (!file) {
      setStatus("Önce bir görüntü seç", "error");
      return;
    }

    const fd = new FormData();
    fd.append("file", file);
    fd.append("width_mm", document.getElementById("width_mm").value);
    fd.append("invert", document.getElementById("invert").checked ? "true" : "false");
    fd.append("blur", blurRange.value);
    fd.append("simplify", (Number(simRange.value) / 1000).toFixed(4));
    fd.append("min_area", (Number(areaRange.value) / 10).toFixed(2));
    if (!autoThreshold) {
      fd.append("threshold", thRange.value);
    }

    convertBtn.disabled = true;
    setStatus("Dönüştürülüyor…");

    try {
      const res = await fetch("/api/convert", { method: "POST", body: fd });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = payload.detail || res.statusText || "Hata";
        throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      }

      viewSvg.innerHTML = payload.preview_svg;
      viewSvg.hidden = activeTab !== "svg";
      viewPng.src = `data:image/png;base64,${payload.preview_png}`;
      viewPng.hidden = activeTab !== "png";
      empty.hidden = true;

      document.getElementById("meta-size").textContent =
        `${payload.width_mm} × ${payload.height_mm} mm`;
      document.getElementById("meta-count").textContent = String(payload.contour_count);
      document.getElementById("meta-px").textContent =
        `${payload.image_size.width}×${payload.image_size.height}`;
      meta.hidden = false;

      downloadBtn.href = payload.download_url;
      downloadBtn.setAttribute("download", payload.filename);
      downloadBtn.setAttribute("aria-disabled", "false");

      activeTab = "svg";
      document.querySelectorAll(".tab").forEach((t) => {
        const on = t.dataset.tab === "svg";
        t.classList.toggle("active", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
      });
      showTab();

      setStatus(`${payload.contour_count} kesim yolu hazır`, "ok");
    } catch (err) {
      setStatus(err.message || String(err), "error");
      downloadBtn.setAttribute("aria-disabled", "true");
      downloadBtn.removeAttribute("href");
    } finally {
      convertBtn.disabled = false;
    }
  });
})();
