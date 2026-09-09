/* Sidebar defaults for the Sphinx RTD theme used by xstar-tools. */
(function () {
  function textOf(anchor) {
    return (anchor.textContent || "").replace(/\s+/g, " ").trim().toLowerCase();
  }

  function findTopLevelItem(label) {
    var anchors = document.querySelectorAll(".wy-menu-vertical li.toctree-l1 > a.reference.internal");
    for (var i = 0; i < anchors.length; i += 1) {
      if (textOf(anchors[i]).indexOf(label) !== -1) return anchors[i].parentElement;
    }
    return null;
  }

  function setExpanded(li, expanded) {
    if (!li || li.classList.contains("current")) return;
    var nested = li.querySelectorAll(":scope > ul");
    for (var i = 0; i < nested.length; i += 1) {
      nested[i].style.display = expanded ? "block" : "none";
    }
    li.classList.toggle("collapsed", !expanded);
  }

  function isLandingPage() {
    var path = window.location.pathname || "";
    return path === "" || path.endsWith("/") || path.endsWith("/index.html");
  }

  function applySidebarDefaults() {
    if (!isLandingPage()) return;
    setExpanded(findTopLevelItem("user guide"), true);
    setExpanded(findTopLevelItem("python guide"), false);
    setExpanded(findTopLevelItem("python api"), false);
    setExpanded(findTopLevelItem("c++ and cli"), false);
    setExpanded(findTopLevelItem("developer guide"), false);
    setExpanded(findTopLevelItem("science guide"), false);
    setExpanded(findTopLevelItem("history"), false);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applySidebarDefaults);
  } else {
    applySidebarDefaults();
  }
})();
