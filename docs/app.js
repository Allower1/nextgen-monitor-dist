const tabs = [...document.querySelectorAll(".tab")];
const screens = [...document.querySelectorAll(".screen")];
const toast = document.getElementById("toast");

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.t);
  showToast.t = window.setTimeout(() => toast.classList.remove("show"), 1600);
}

tabs.forEach(tab => {
  tab.addEventListener("click", () => {
    tabs.forEach(x => x.classList.remove("active"));
    screens.forEach(x => x.classList.remove("active"));
    tab.classList.add("active");
    document.querySelector('[data-screen="' + tab.dataset.target + '"]').classList.add("active");
    window.scrollTo({top: 0, behavior: "smooth"});
  });
});

document.getElementById("statusBtn").addEventListener("click", () => {
  showToast("Demo refresh complete · API ONLINE");
});

document.getElementById("pauseBtn").addEventListener("click", () => {
  showToast("Preview only — no command sent");
});

document.querySelector(".icon-btn").addEventListener("click", () => {
  showToast("Settings are disabled in web preview");
});
