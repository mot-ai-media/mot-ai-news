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
})();
