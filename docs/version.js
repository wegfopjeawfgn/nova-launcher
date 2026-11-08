(() => {
  const repo = "wegfopjeawfgn/nova-launcher";
  const version = document.getElementById("release-version");
  const download = document.getElementById("release-rpm");
  const checksum = document.getElementById("release-checksum");

  function assetUrl(asset, tag) {
    if (asset && /^[A-Za-z0-9._-]+$/.test(asset.name)) {
      return `https://github.com/${repo}/releases/download/${tag}/${asset.name}`;
    }
    return null;
  }

  async function refreshRelease() {
    const response = await fetch(`https://api.github.com/repos/${repo}/releases/latest`, {
      headers: { Accept: "application/vnd.github+json" },
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) return;
    const release = await response.json();
    const tag = release.tag_name;
    if (release.draft || release.prerelease || !/^v?\d+\.\d+\.\d+$/.test(tag)) return;

    const number = tag.replace(/^v/, "");
    const assets = release.assets ?? [];
    const windows = assets.find(({ name }) => name === `nova-launcher-${number}-windows-x64-setup.exe`);
    const windowsSum = windows && assets.find(({ name }) => name === `${windows.name}.sha256`);
    if (windows && windowsSum) {
      document.getElementById("windows-installer").href = assetUrl(windows, tag);
      const link = document.getElementById("windows-checksum");
      link.href = assetUrl(windowsSum, tag);
      link.hidden = false;
      document.getElementById("windows-download").hidden = false;
    }
    const rpm = assets.find(({ name }) => {
      if (!name.startsWith(`nova-launcher-${number}-`)) return false;
      const suffix = name.slice(`nova-launcher-${number}-`.length);
      return /^\d+\.noarch\.rpm$/.test(suffix);
    });
    const rpmUrl = assetUrl(rpm, tag);
    if (!rpmUrl) return;

    const sum = assets.find(({ name }) => name === `${rpm.name}.sha256`);
    const sumUrl = assetUrl(sum, tag);
    version.textContent = number;
    download.href = rpmUrl;
    checksum.hidden = !sumUrl;
    if (sumUrl) checksum.href = sumUrl;
    document.getElementById("install-downloads").textContent =
      `sudo dnf install "$(xdg-user-dir DOWNLOAD)/${rpm.name}"`;
    document.getElementById("install-current").textContent = `sudo dnf install ./${rpm.name}`;
  }

  if (navigator.clipboard) {
    for (const button of document.querySelectorAll("[data-copy-command]")) {
      button.hidden = false;
      button.addEventListener("click", async () => {
        const command = document.getElementById(button.dataset.copyCommand);
        const status = document.getElementById("copy-status");
        try {
          await navigator.clipboard.writeText(command.textContent);
          status.textContent = "Comando copiado.";
        } catch {
          status.textContent = "Seleccioná el comando y copialo manualmente.";
        }
      });
    }
  }

  refreshRelease().catch(() => {
    // Keep the bundled installer usable if GitHub is unavailable.
  });
})();
