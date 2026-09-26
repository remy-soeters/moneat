// ---------- Kookmodus: kookwekker en het scherm aan laten ----------
const timer = { total: 0, left: 0, running: false, interval: null };
let wakeLock = null;

// Houd het scherm aan zolang je kookt (werkt op iPhone/iPad met iOS 16.4+ en in moderne browsers).
export async function keepScreenOn(on) {
  try {
    if (on && "wakeLock" in navigator && !wakeLock) {
      wakeLock = await navigator.wakeLock.request("screen");
      wakeLock.addEventListener("release", () => (wakeLock = null));
    } else if (!on && wakeLock) {
      await wakeLock.release();
      wakeLock = null;
    }
  } catch {} // niet ondersteund of geweigerd: dan maar zonder
}

// Na terugkeren naar de app vervalt het schermslot; vraag het opnieuw als de kookmodus nog aan staat.
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && document.querySelector(".recipe-layout.cooking")) keepScreenOn(true);
});

export function timerHtml() {
  return `<div class="cook-timer" id="cook-timer">
    <div class="timer-display" id="timer-display" aria-live="polite">${format(timer.left)}</div>
    <div class="timer-presets">${[5, 10, 15, 20, 30, 45]
      .map((m) => `<button type="button" class="chip" data-timer="${m}">${m} min</button>`)
      .join("")}<button type="button" class="chip" data-timer="+1">+1</button></div>
    <div class="timer-controls">
      <button type="button" class="btn primary" data-timer="toggle" ${timer.left ? "" : "disabled"}>${timer.running ? "Pauze" : "Start"}</button>
      <button type="button" class="btn link" data-timer="reset">Opnieuw</button>
    </div>
  </div>`;
}

function format(seconds) {
  const s = Math.max(0, seconds);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

function paint() {
  const display = document.getElementById("timer-display");
  if (!display) return;
  display.textContent = format(timer.left);
  const toggle = document.querySelector('[data-timer="toggle"]');
  toggle.textContent = timer.running ? "Pauze" : "Start";
  toggle.disabled = !timer.left;
  document.getElementById("cook-timer").classList.toggle("running", timer.running);
}

export function timerAction(action) {
  if (action === "toggle") {
    timer.running ? pause() : start();
  } else if (action === "reset") {
    pause();
    timer.left = timer.total;
  } else if (action === "+1") {
    timer.left += 60;
    timer.total = Math.max(timer.total, timer.left);
  } else {
    pause();
    timer.total = timer.left = Number(action) * 60;
    start();
  }
  document.getElementById("cook-timer")?.classList.remove("ringing");
  paint();
}

function start() {
  if (timer.running || timer.left <= 0) return;
  timer.running = true;
  const end = Date.now() + timer.left * 1000; // op de klok, zodat hij klopt ook als de browser even slaapt
  timer.interval = setInterval(() => {
    timer.left = Math.round((end - Date.now()) / 1000);
    if (timer.left <= 0) {
      timer.left = 0;
      pause();
      ring();
    }
    paint();
  }, 250);
}

function pause() {
  clearInterval(timer.interval);
  timer.running = false;
}

export function stopTimer() {
  pause();
  timer.total = timer.left = 0;
}

// De wekker: drie piepjes, trillen (op telefoons die dat kunnen) en een knipperende wekker.
function ring() {
  document.getElementById("cook-timer")?.classList.add("ringing");
  navigator.vibrate?.([300, 150, 300, 150, 300]);
  try {
    const audio = new AudioContext();
    [0, 0.45, 0.9].forEach((at) => {
      const osc = audio.createOscillator();
      const gain = audio.createGain();
      osc.frequency.value = 880;
      gain.gain.setValueAtTime(0.25, audio.currentTime + at);
      gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + at + 0.35);
      osc.connect(gain).connect(audio.destination);
      osc.start(audio.currentTime + at);
      osc.stop(audio.currentTime + at + 0.36);
    });
  } catch {}
  window.dispatchEvent(new CustomEvent("mp:timer-done"));
}
