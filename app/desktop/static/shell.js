"use strict";
const key = location.hash.slice(1) || sessionStorage.getItem("desktop-key") || "";
if (key) sessionStorage.setItem("desktop-key", key);
history.replaceState(null, "", "/");
const el = id => document.getElementById(id);
const labels = { stopped: "Stopped", starting: "Starting…", running: "Running",
  stopping: "Finalizing recordings and stopping…", resetting: "Resetting administrator token…",
  failed: "Service failed" };
let selectedTheme = "modern";
let dashboardUrl = "";
let refreshing = false;
let actionInFlight = false;

async function request(path, method = "GET", data) {
  const response = await fetch("/control/" + path, {
    method, cache: "no-store", headers: {
      "X-Sentinel-Desktop": key, "Content-Type": "application/json"
    }, body: data === undefined ? undefined : JSON.stringify(data)
  });
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).error || "Local operation failed.");
  return response.json();
}

function updateTheme(theme) {
  selectedTheme = theme;
  document.documentElement.dataset.theme = theme;
  el("theme").value = theme;
  if (dashboardUrl) el("dashboard").contentWindow.postMessage(
    { type: "sentinel-desktop-theme", theme }, new URL(dashboardUrl).origin);
}

async function refresh() {
  if (refreshing || actionInFlight) return;
  refreshing = true;
  try {
    const state = await request("status");
    const ready = state.status === "stopped" || state.status === "failed";
    el("status").textContent = labels[state.status] || state.status;
    el("lan").textContent = state.lan ? "CamFlow: " + state.lan : "";
    el("error").textContent = state.error;
    el("start").disabled = el("reset").disabled = !ready;
    el("stop").disabled = !["starting", "running"].includes(state.status);
    el("token-panel").hidden = !state.token;
    if (el("token").value !== state.token) {
      el("token").type = "password";
      el("token").value = state.token;
      el("reveal").textContent = "Show token";
    }
    if (state.url !== dashboardUrl) {
      dashboardUrl = state.url;
      el("welcome").hidden = Boolean(dashboardUrl);
      el("dashboard").hidden = !dashboardUrl;
      if (dashboardUrl) el("dashboard").src = dashboardUrl;
      else el("dashboard").removeAttribute("src");
    }
    updateTheme(state.theme);
  } catch (error) {
    el("status").textContent = "Control service unavailable";
    el("error").textContent = error.message;
  } finally { refreshing = false; }
}

async function action(name, data) {
  if (actionInFlight) return;
  actionInFlight = true;
  try {
    await request(name, "POST", data);
    if (name === "theme") updateTheme(data.theme);
  } catch (error) { window.alert(error.message); }
  finally { actionInFlight = false; refresh(); }
}
el("dashboard").addEventListener("load", () => updateTheme(selectedTheme));
el("start").onclick = () => action("start");
el("stop").onclick = () => action("stop");
el("reset").onclick = () => {
  if (window.confirm("Reset the administrator token and sign out all administrators? Paired cameras will stay connected.")) action("reset");
};
el("reveal").onclick = () => {
  const reveal = el("token").type === "password";
  el("token").type = reveal ? "text" : "password";
  el("reveal").textContent = reveal ? "Hide token" : "Show token";
};
el("forget").onclick = () => action("forget-token");
el("theme").onchange = event => action("theme", { theme: event.target.value });
refresh();
setInterval(refresh, 500);
