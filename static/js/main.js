// main.js — students will add JavaScript here as features are built

// Toast notifications — auto-dismiss flashed messages and allow manual close
(function () {
    const container = document.getElementById("toast-container");
    if (!container) return;

    function dismiss(toast) {
        toast.classList.add("toast-hide");
        toast.addEventListener("animationend", () => toast.remove(), { once: true });
    }

    container.querySelectorAll(".toast").forEach((toast) => {
        const closeBtn = toast.querySelector("[data-toast-close]");
        if (closeBtn) {
            closeBtn.addEventListener("click", () => dismiss(toast));
        }
        setTimeout(() => dismiss(toast), 4000);
    });
})();
