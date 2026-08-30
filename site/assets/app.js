/* 客服知識中心的漸進增強腳本。
   沒有這支檔案時，頁面仍可完整閱讀：問答用原生 details 展開，
   導覽與內容皆為靜態 HTML。這裡只負責搜尋、主題切換、
   錨點自動展開與複製連結。 */
(function () {
  "use strict";

  /* 主題切換：跟隨系統 → 淺色 → 深色 → 跟隨系統 */
  var order = ["auto", "light", "dark"];
  var labels = { auto: "跟隨系統", light: "淺色", dark: "深色" };

  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") || "auto";
  }

  function applyTheme(name) {
    if (name === "auto") {
      document.documentElement.removeAttribute("data-theme");
    } else {
      document.documentElement.setAttribute("data-theme", name);
    }
    try {
      if (name === "auto") {
        localStorage.removeItem("kb-theme");
      } else {
        localStorage.setItem("kb-theme", name);
      }
    } catch (e) {
      /* 無痕模式或封鎖儲存時忽略，主題僅在本次瀏覽有效。 */
    }
    var button = document.querySelector("[data-theme-toggle]");
    if (button) {
      button.setAttribute("aria-label", "目前主題為" + labels[name] + "，點擊切換");
      var text = button.querySelector(".theme-toggle-text");
      if (text) text.textContent = labels[name];
    }
  }

  var toggle = document.querySelector("[data-theme-toggle]");
  if (toggle) {
    applyTheme(currentTheme());
    toggle.addEventListener("click", function () {
      var next = order[(order.indexOf(currentTheme()) + 1) % order.length];
      applyTheme(next);
    });
  }

  /* 由網址錨點自動展開對應的問答，並捲動到位。 */
  function openFromHash() {
    if (!location.hash) return;
    var target;
    try {
      target = document.querySelector(location.hash);
    } catch (e) {
      return;
    }
    if (!target) return;
    var node = target;
    while (node) {
      if (node.tagName === "DETAILS") node.open = true;
      node = node.parentElement;
    }
    target.scrollIntoView({ block: "start" });
  }
  openFromHash();
  window.addEventListener("hashchange", openFromHash);

  /* 複製單題連結。 */
  document.addEventListener("click", function (event) {
    var link = event.target.closest("[data-copy-link]");
    if (!link) return;
    var url = link.href;
    if (!navigator.clipboard) return;
    event.preventDefault();
    navigator.clipboard.writeText(url).then(function () {
      var original = link.textContent;
      link.textContent = "已複製連結";
      setTimeout(function () {
        link.textContent = original;
      }, 1600);
    });
  });

  /* 列印前強制展開所有問答。closed 的 details 內容不會被渲染，
     純 CSS 無法在列印時攤開，必須由腳本處理。對應 design/brief.md 第 10 節。 */
  function expandForPrint() {
    document.querySelectorAll("details.qa-item").forEach(function (node) {
      if (!node.open) {
        node.dataset.printAutoOpen = "1";
        node.open = true;
      }
    });
  }
  function restoreAfterPrint() {
    document.querySelectorAll('details.qa-item[data-print-auto-open="1"]').forEach(function (node) {
      node.open = false;
      delete node.dataset.printAutoOpen;
    });
  }
  window.addEventListener("beforeprint", expandForPrint);
  window.addEventListener("afterprint", restoreAfterPrint);
  if (window.matchMedia) {
    var printQuery = window.matchMedia("print");
    if (printQuery.addEventListener) {
      printQuery.addEventListener("change", function (event) {
        if (event.matches) { expandForPrint(); } else { restoreAfterPrint(); }
      });
    }
  }

  /* 前端搜尋。 */
  var root = document.querySelector("[data-search-root]");
  if (!root) return;
  var input = root.querySelector("#kb-search");
  var results = root.querySelector("[data-search-results]");
  var hint = root.querySelector("[data-search-hint]");
  var entries = null;
  var loading = false;

  function load() {
    if (entries || loading) return Promise.resolve();
    loading = true;
    return fetch("search-index.json")
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        entries = data;
        loading = false;
      })
      .catch(function () {
        loading = false;
        entries = [];
        if (hint) hint.textContent = "搜尋索引載入失敗，請直接瀏覽上方主題。";
      });
  }

  function escapeHtml(text) {
    return text.replace(/[&<>"]/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch];
    });
  }

  function highlight(text, query) {
    var idx = text.toLowerCase().indexOf(query);
    if (idx < 0) return escapeHtml(text);
    return (
      escapeHtml(text.slice(0, idx)) +
      "<mark>" +
      escapeHtml(text.slice(idx, idx + query.length)) +
      "</mark>" +
      escapeHtml(text.slice(idx + query.length))
    );
  }

  function score(entry, query) {
    var title = entry.t.toLowerCase();
    if (title.indexOf(query) === 0) return 3;
    if (title.indexOf(query) >= 0) return 2;
    if ((entry.s || "").toLowerCase().indexOf(query) >= 0) return 1;
    return 0;
  }

  function render(query) {
    var hits = (entries || [])
      .map(function (entry) {
        return { entry: entry, score: score(entry, query) };
      })
      .filter(function (hit) {
        return hit.score > 0;
      })
      .sort(function (a, b) {
        return b.score - a.score;
      })
      .slice(0, 12);

    results.innerHTML = "";
    if (!hits.length) {
      var empty = document.createElement("li");
      empty.className = "search-empty";
      empty.innerHTML =
        '找不到相符的問題。您可以換個關鍵字，或 <a href="about.html">聯絡客服</a>。';
      results.appendChild(empty);
    } else {
      hits.forEach(function (hit) {
        var li = document.createElement("li");
        li.innerHTML =
          '<a href="' +
          escapeHtml(hit.entry.u) +
          '">' +
          highlight(hit.entry.t, query) +
          "</a>" +
          '<p class="search-crumb">' +
          escapeHtml(hit.entry.p || "") +
          "</p>" +
          "<p>" +
          highlight(hit.entry.s || "", query) +
          "</p>";
        results.appendChild(li);
      });
    }
    results.hidden = false;
    if (hint) hint.textContent = "找到 " + hits.length + " 筆結果。";
  }

  var defaultHint = hint ? hint.textContent : "";
  input.addEventListener("input", function () {
    var query = input.value.trim().toLowerCase();
    if (query.length < 2) {
      results.hidden = true;
      results.innerHTML = "";
      if (hint) hint.textContent = defaultHint;
      return;
    }
    load().then(function () {
      render(query);
    });
  });
  input.addEventListener("focus", load);
})();
