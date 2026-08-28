(function () {
  function showToast(msg) {
    var toast = document.createElement("div");
    toast.className = "toast";
    toast.textContent = msg;
    document.body.appendChild(toast);
    requestAnimationFrame(function () {
      toast.classList.add("show");
    });
    setTimeout(function () {
      toast.classList.remove("show");
      setTimeout(function () {
        toast.remove();
      }, 300);
    }, 1800);
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand("copy");
    } catch (e) {}
    document.body.removeChild(ta);
    return Promise.resolve();
  }

  document.addEventListener("click", function (e) {
    var copyBtn = e.target.closest("[data-copy-url]");
    if (copyBtn) {
      copyText(copyBtn.getAttribute("data-copy-url")).then(function () {
        showToast("リンクをコピーしました");
      });
      return;
    }
    var shareBtn = e.target.closest("[data-native-share]");
    if (shareBtn) {
      var url = shareBtn.getAttribute("data-share-url");
      var title = shareBtn.getAttribute("data-share-title");
      if (navigator.share) {
        navigator.share({ title: title, url: url }).catch(function () {});
      } else {
        copyText(url).then(function () {
          showToast("リンクをコピーしました");
        });
      }
    }
  });

  document.querySelectorAll("[data-native-share-only]").forEach(function (el) {
    if (navigator.share) {
      el.style.display = "block";
    }
  });

  // ダークモード切り替え(<head>のtheme_initが初期状態は既に設定済み。ここではトグル操作のみ扱う)
  document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var isDark = document.documentElement.getAttribute("data-theme") === "dark";
      if (isDark) {
        document.documentElement.removeAttribute("data-theme");
        try { localStorage.setItem("mot-theme", "light"); } catch (e) {}
      } else {
        document.documentElement.setAttribute("data-theme", "dark");
        try { localStorage.setItem("mot-theme", "dark"); } catch (e) {}
      }
    });
  });

  // サイト内検索 + 難易度フィルター(記事カードの絞り込み。クライアントサイドのみ、外部送信なし)
  var searchInput = document.getElementById("mot-search");
  var levelFilter = document.getElementById("level-filter");
  var currentLevel = "all";

  function applyCardFilters() {
    var q = searchInput ? searchInput.value.trim().toLowerCase() : "";
    document.querySelectorAll("[data-searchable]").forEach(function (card) {
      var text = (card.getAttribute("data-search-text") || "").toLowerCase();
      var matchesSearch = !q || text.indexOf(q) !== -1;
      var matchesLevel = currentLevel === "all" || card.getAttribute("data-level") === currentLevel;
      card.style.display = matchesSearch && matchesLevel ? "" : "none";
    });
  }

  if (searchInput) {
    searchInput.addEventListener("input", applyCardFilters);
  }
  if (levelFilter) {
    levelFilter.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-filter-level]");
      if (!btn) return;
      currentLevel = btn.getAttribute("data-filter-level");
      levelFilter.querySelectorAll(".level-filter-btn").forEach(function (b) {
        b.classList.toggle("active", b === btn);
      });
      applyCardFilters();
    });
  }

  // モバイルナビの開閉
  var navToggle = document.querySelector("[data-nav-toggle]");
  var navMenu = document.getElementById("mot-nav-menu");
  if (navToggle && navMenu) {
    navToggle.addEventListener("click", function () {
      navMenu.classList.toggle("open");
    });
  }

  // CONTINUE EXPLORING: 閲覧したタグをこの端末のlocalStorageにだけ記録する(サーバー送信なし)。
  // トップページでは、その記録と実際の最新記事日時を比べて「本当に新しい記事がある場合だけ」案内する
  // (架空の緊急性・偽の新着表示は作らない)。
  function pad2(n) { return (n < 10 ? "0" : "") + n; }
  function localStamp(d) {
    return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate()) + " " + pad2(d.getHours()) + ":" + pad2(d.getMinutes());
  }

  if (window.motPageTags && window.motPageTags.length) {
    try {
      var now = localStamp(new Date());
      var visited = JSON.parse(localStorage.getItem("mot-visited-tags") || "[]");
      visited = visited.filter(function (v) { return window.motPageTags.indexOf(v.tag) === -1; });
      window.motPageTags.forEach(function (t) { visited.unshift({ tag: t, at: now }); });
      localStorage.setItem("mot-visited-tags", JSON.stringify(visited.slice(0, 8)));
    } catch (e) {}
  }

  var topicsDataEl = document.getElementById("topics-summary-data");
  var continueMount = document.getElementById("continue-exploring");
  if (topicsDataEl && continueMount) {
    try {
      var topics = JSON.parse(topicsDataEl.textContent || "{}");
      var visitedTags = JSON.parse(localStorage.getItem("mot-visited-tags") || "[]");
      for (var i = 0; i < visitedTags.length; i++) {
        var v = visitedTags[i];
        var t = topics[v.tag];
        if (t && t.latest && t.latest > v.at) {
          var section = document.createElement("section");
          section.className = "continue-exploring";
          var label = document.createElement("p");
          label.className = "section-label";
          label.textContent = "CONTINUE EXPLORING";
          var link = document.createElement("a");
          link.className = "continue-card";
          link.href = "topics/" + t.slug + ".html";
          link.textContent = "前回見ていた「#" + v.tag + "」に新しいニュースがあります →";
          section.appendChild(label);
          section.appendChild(link);
          continueMount.appendChild(section);
          break;
        }
      }
    } catch (e) {}
  }
})();
