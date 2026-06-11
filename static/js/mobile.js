/* ============================================================
   SentimentQuant Mobile - 公共 JavaScript
   ============================================================ */

// Toast 提示
function showToast(msg) {
    const toast = document.getElementById("toast");
    toast.textContent = msg;
    toast.classList.add("show");
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => toast.classList.remove("show"), 2500);
}

// Loading 遮罩
function showLoading(msg) {
    const overlay = document.getElementById("loading-overlay");
    if (msg) overlay.querySelector(".loading-text").textContent = msg;
    else overlay.querySelector(".loading-text").textContent = "加载中...";
    overlay.style.display = "flex";
}

function hideLoading() {
    document.getElementById("loading-overlay").style.display = "none";
}

// 当前页面导航高亮
document.addEventListener("DOMContentLoaded", function() {
    const path = window.location.pathname;
    document.querySelectorAll(".nav-item").forEach(item => {
        const href = item.getAttribute("href");
        if (href === path) item.classList.add("active");
        else item.classList.remove("active");
    });
});
