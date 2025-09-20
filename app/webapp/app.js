const tg = window.Telegram.WebApp || null;
const initData = tg ? tg.initData : "";

const statusEl = document.getElementById("status");
const form = document.getElementById("treatment-form");
const eventTypeEl = document.getElementById("event-type");
const insulinEl = document.getElementById("insulin");
const carbsEl = document.getElementById("carbs");
const caloriesEl = document.getElementById("calories");
const proteinEl = document.getElementById("protein");
const mealEl = document.getElementById("meal");
const photoInput = document.getElementById("photo");
const photoUrlInput = document.getElementById("photo-url");
const photoPreview = document.getElementById("photo-preview");
const photoImg = document.getElementById("photo-img");
const idInput = document.getElementById("treatment-id");
const submitButton = form.querySelector("button[type=submit]");

function setStatus(message, variant = "info") {
  statusEl.textContent = message || "";
  statusEl.dataset.variant = variant;
}

function setPhotoPreview(url) {
  if (url) {
    photoPreview.classList.remove("hidden");
    photoImg.src = url;
  } else {
    photoPreview.classList.add("hidden");
    photoImg.removeAttribute("src");
  }
}

async function loadTreatment() {
  const params = new URLSearchParams(window.location.search);
  const cid = params.get("cid");
  if (!cid) {
    setStatus("Не указан идентификатор записи", "error");
    submitButton.disabled = true;
    return;
  }
  if (!initData) {
    setStatus("initData недоступен", "error");
    submitButton.disabled = true;
    return;
  }

  try {
    setStatus("Загрузка...");
    const url = `/api/treatment?cid=${encodeURIComponent(cid)}&initData=${encodeURIComponent(initData)}`;
    const resp = await fetch(url, { method: "GET" });
    if (!resp.ok) {
      throw new Error(`Ошибка загрузки: ${resp.status}`);
    }
    const data = await resp.json();
    idInput.value = data.id;
    eventTypeEl.value = data.eventType || "None";
    insulinEl.value = data.insulin ?? "";
    carbsEl.value = data.carbs ?? "";
    caloriesEl.value = data.calories ?? "";
    proteinEl.value = data.protein ?? "";
    mealEl.value = data.meal ?? "";
    photoUrlInput.value = data.photoUrl ?? "";
    setPhotoPreview(data.photoUrl);
    setStatus("Данные загружены", "success");
  } catch (err) {
    console.error(err);
    setStatus("Не удалось загрузить запись", "error");
    submitButton.disabled = true;
  }
}

photoInput.addEventListener("change", async (event) => {
  const file = event.target.files?.[0];
  if (!file) {
    return;
  }
  if (!initData) {
    setStatus("initData недоступен", "error");
    return;
  }
  const formData = new FormData();
  formData.append("initData", initData);
  formData.append("image", file);

  try {
    setStatus("Загружаем фото...");
    submitButton.disabled = true;
    const resp = await fetch("/api/upload", {
      method: "POST",
      body: formData,
    });
    if (!resp.ok) {
      throw new Error(`Upload failed ${resp.status}`);
    }
    const payload = await resp.json();
    photoUrlInput.value = payload.url;
    setPhotoPreview(payload.url);
    setStatus("Фото загружено", "success");
  } catch (err) {
    console.error(err);
    setStatus("Не удалось загрузить фото", "error");
    photoUrlInput.value = "";
    setPhotoPreview(null);
  } finally {
    submitButton.disabled = false;
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!initData) {
    setStatus("initData недоступен", "error");
    return;
  }
  const formData = new FormData(form);
  formData.append("initData", initData);
  try {
    setStatus("Сохраняем...");
    submitButton.disabled = true;
    const resp = await fetch("/api/treatment", {
      method: "PUT",
      body: formData,
    });
    if (!resp.ok) {
      throw new Error(`Save failed ${resp.status}`);
    }
    const payload = await resp.json();
    setStatus("Сохранено", "success");
    if (tg) {
      tg.HapticFeedback?.notificationOccurred?.("success");
      setTimeout(() => tg.close(), 600);
    }
  } catch (err) {
    console.error(err);
    setStatus("Не удалось сохранить", "error");
    submitButton.disabled = false;
  }
});

if (tg) {
  tg.ready();
  tg.expand();
}

loadTreatment();
