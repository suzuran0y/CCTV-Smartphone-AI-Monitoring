"use strict";
// Only the actual desktop parent may change this view. No navigation or form reset.
const desktopParentOrigin = document.querySelector('meta[name="sentinel-desktop-origin"]').content;
window.addEventListener("message", event => {
  if (window.parent === window || event.source !== window.parent || event.origin !== desktopParentOrigin) return;
  const data = event.data;
  if (data?.type === "sentinel-desktop-theme" && ["modern", "dark", "luna"].includes(data.theme)) {
    document.documentElement.dataset.desktop = "";
    document.documentElement.dataset.theme = data.theme;
  }
});
