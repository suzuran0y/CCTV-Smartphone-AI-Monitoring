let accessState = {admin: false, csrf: null, viewer_auth_required: true};
let accessReady = false;

function updateAccessUI() {
  const admin = accessState.admin;
  document.body.classList.toggle("visitor-mode", !admin);
  document.getElementById("accessStatus").textContent = admin ? "Administrator" : "Visitor";
  document.getElementById("loginForm").hidden = admin;
  document.getElementById("logoutBtn").hidden = !admin;
  document.getElementById("devicePanel").hidden = !admin;
  document.querySelectorAll("#rightPane input, #rightPane select, #rightPane textarea, #rightPane button, #ingestToggleBtn, #recordToggleBtn, #snapshotBtn, #shutdownBtn")
    .forEach(el => { el.disabled = !admin; });
  document.querySelector(".logs-box").hidden = !admin;
  const canView = admin || !accessState.viewer_auth_required;
  const live = document.getElementById("live");
  live.hidden = !canView;
  document.getElementById("liveLocked").hidden = canView;
  if (canView && !live.getAttribute("src")) live.src = "/stream";
  if (!canView) {
    live.removeAttribute("src");
    document.getElementById("status_readable").textContent = "Privacy mode — administrator login required.";
  }
  document.getElementById("accessStatus").textContent += accessState.viewer_auth_required ? " · Privacy mode" : " · Default mode";
}

async function refreshAccess() {
  try {
    const response = await fetch("/api/auth/status", {cache: "no-store"});
    if (!response.ok) throw new Error("Access check failed");
    const next = await response.json();
    if (accessReady && accessState.admin && !next.admin) {
      location.reload(); // Remove formerly visible private configuration and event data.
      return;
    }
    accessState = next;
    accessReady = true;
    updateAccessUI();
  } catch (_) {
    document.getElementById("accessMessage").textContent = "Server unavailable. Reconnect to check access.";
  }
}

async function refreshDevices() {
  if (!accessState.admin) return;
  const r = await fetchJson("/api/devices");
  const list = document.getElementById("deviceList");
  list.replaceChildren();
  for (const device of r.json?.devices || []) {
    const row = document.createElement("p");
    row.append(document.createTextNode(device.name + " "));
    const button = document.createElement("button");
    button.textContent = "Revoke";
    button.onclick = async () => {
      if (!confirm("Revoke this camera's upload access?")) return;
      await fetchJson("/api/devices/" + encodeURIComponent(device.id), {method: "DELETE"});
      await refreshDevices();
    };
    row.append(button);
    list.append(row);
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  document.getElementById("loginForm").onsubmit = async event => {
    event.preventDefault();
    const input = document.getElementById("adminToken");
    try {
      const r = await fetchJson("/api/auth/login", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({token: input.value})});
      input.value = "";
      if (r.status !== 200) {
        document.getElementById("accessMessage").textContent = r.json?.error || "Login failed";
        return;
      }
      await refreshAccess();
      await refreshConfigForm();
      await refreshDevices();
      document.getElementById("accessMessage").textContent = "Signed in. Log out when finished; session expires after 8 hours.";
    } catch (_) { document.getElementById("accessMessage").textContent = "Cannot reach server."; }
  };
  document.getElementById("logoutBtn").onclick = async () => {
    const r = await fetchJson("/api/auth/logout", {method: "POST"});
    if (r.status === 200) location.reload();
  };
  document.getElementById("pairingBtn").onclick = async () => {
    const r = await fetchJson("/api/devices/pairing-code", {method: "POST"});
    document.getElementById("pairingCode").textContent = r.json?.code ? `${r.json.code} — one use, expires in 5 minutes` : (r.json?.error || "Pairing failed");
  };
  await refreshAccess();
  if (accessState.admin) { await refreshConfigForm(); await refreshDevices(); }
  await refreshStatusOnly();
  setInterval(refreshAccess, 3000);
  setInterval(refreshDevices, 10000);
});
