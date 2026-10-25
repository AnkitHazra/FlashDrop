(() => {
  const $ = (id) => document.getElementById(id);
  const formatBytes = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    const units = ["KB", "MB", "GB", "TB"];
    let size = bytes / 1024, i = 0;
    while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
    return `${size.toFixed(size >= 10 ? 1 : 2)} ${units[i]}`;
  };
  const setTimer = (expiresAt, countdownEl, barEl, expiredCallback) => {
    const tick = () => {
      const remaining = Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000));
      const minutes = String(Math.floor(remaining / 60)).padStart(2, "0");
      const seconds = String(remaining % 60).padStart(2, "0");
      if (countdownEl) countdownEl.textContent = `${minutes}:${seconds}`;
      if (barEl) barEl.style.width = `${Math.min(100, Math.max(0, remaining / 600 * 100))}%`;
      if (remaining <= 0) {
        clearInterval(timer);
        if (expiredCallback) expiredCallback();
      }
    };
    let timer = null;
    tick();
    if (Date.now() < expiresAt) timer = setInterval(tick, 250);
    return timer;
  };

  // Upload page
  const form = $("upload-form");
  if (form) {
    const input = $("file-input"), dropzone = $("dropzone");
    const selected = $("selected-file"), selectedName = $("selected-name"), selectedSize = $("selected-size");
    const error = $("error-message"), button = $("upload-button");
    const progressWrap = $("progress-wrap"), progressBar = $("progress-bar");
    let chosenFile = null;

    const showError = (message) => { error.textContent = message; error.classList.remove("hidden"); };
    const clearError = () => { error.textContent = ""; error.classList.add("hidden"); };
    const chooseFile = (file) => {
      clearError();
      if (!file) return;
      if (file.size > window.MAX_FILE_BYTES) {
        chosenFile = null; input.value = ""; selected.classList.add("hidden");
        showError(`That file is too large. Maximum size is ${formatBytes(window.MAX_FILE_BYTES)}.`);
        return;
      }
      chosenFile = file;
      selectedName.textContent = file.name;
      selectedSize.textContent = formatBytes(file.size);
      selected.classList.remove("hidden");
      $("drop-title").textContent = "File selected";
    };
    input.addEventListener("change", () => chooseFile(input.files[0]));
    $("clear-file").addEventListener("click", () => {
      chosenFile = null; input.value = ""; selected.classList.add("hidden");
      $("drop-title").textContent = "Drop your file here"; clearError();
    });
    ["dragenter", "dragover"].forEach((eventName) => dropzone.addEventListener(eventName, (e) => {
      e.preventDefault(); dropzone.classList.add("dragging");
    }));
    ["dragleave", "drop"].forEach((eventName) => dropzone.addEventListener(eventName, (e) => {
      e.preventDefault(); dropzone.classList.remove("dragging");
    }));
    dropzone.addEventListener("drop", (e) => chooseFile(e.dataTransfer.files[0]));

    form.addEventListener("submit", (e) => {
      e.preventDefault(); clearError();
      if (!chosenFile) { showError("Choose a file before uploading."); return; }
      const data = new FormData(); data.append("file", chosenFile);
      button.disabled = true; button.querySelector("span").textContent = "Uploading…";
      progressWrap.classList.remove("hidden"); progressBar.style.width = "0%";
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/upload");
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          const pct = Math.round(event.loaded / event.total * 100);
          progressBar.style.width = `${pct}%`; $("progress-percent").textContent = `${pct}%`;
        }
      };
      xhr.onerror = () => finishError("Network error. Check your connection and try again.");
      xhr.onload = () => {
        let result;
        try { result = JSON.parse(xhr.responseText); } catch { result = {}; }
        if (xhr.status < 200 || xhr.status >= 300) {
          finishError(result.detail || "Upload failed. Please try again."); return;
        }
        progressBar.style.width = "100%"; $("progress-percent").textContent = "100%";
        $("result-card").classList.remove("hidden");
        $("share-url").value = result.share_url;
        $("open-link").href = result.share_url;
        $("qr-image").src = result.qr_url;
        $("upload-card").classList.add("upload-complete");
        $("result-card").scrollIntoView({ behavior: "smooth", block: "start" });
        setTimer(result.expires_at * 1000, $("countdown"), $("countdown-bar"), () => {
          $("countdown").textContent = "EXPIRED";
          $("countdown-bar").style.width = "0%";
          $("copy-button").disabled = true;
          $("open-link").classList.add("disabled-link");
          $("copy-feedback").textContent = "This link has expired.";
          $("qr-image").classList.add("expired-image");
        });
        button.disabled = false; button.querySelector("span").textContent = "Upload another file";
        button.onclick = () => window.location.reload();
      };
      xhr.send(data);
    });
    function finishError(message) {
      showError(message); button.disabled = false;
      button.querySelector("span").textContent = "Upload and create link";
      progressWrap.classList.add("hidden");
    }
    $("copy-button").addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText($("share-url").value);
        $("copy-button").textContent = "Copied";
        $("copy-feedback").textContent = "Link copied to clipboard.";
      } catch {
        $("share-url").select();
        const ok = document.execCommand("copy");
        $("copy-feedback").textContent = ok ? "Link copied to clipboard." : "Select and copy the link manually.";
      }
      setTimeout(() => { $("copy-button").textContent = "Copy link"; }, 1800);
    });
  }

  // Download page
  if (window.SHARE_EXPIRES_AT) {
    const size = $("file-size");
    if (size) size.textContent = formatBytes(window.SHARE_SIZE);
    const button = $("download-button");
    setTimer(window.SHARE_EXPIRES_AT, $("countdown"), $("countdown-bar"), () => {
      button.classList.add("disabled-link");
      button.removeAttribute("href");
      button.setAttribute("aria-disabled", "true");
      $("expired-message").classList.remove("hidden");
    });
  }
})();
