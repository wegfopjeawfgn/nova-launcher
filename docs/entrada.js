// Nova Launcher · sitio. La entrada de la estrella, la ventana del launcher con su portal Minecraft/Roblox y la barra que sigue
// la sección actual. Cada parte va aparte y sin poder romper el contenido: si algo falla, la página queda como si no existiera.
(() => {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const ACCENT = [143, 214, 232];
  const smooth = (x) => { x = Math.min(Math.max(x, 0), 1); return x < 0.5 ? 4 * x ** 3 : 1 - (-2 * x + 2) ** 3 / 2; };
  const easeOut = (x) => 1 - (1 - Math.min(Math.max(x, 0), 1)) ** 3;

  // La estrella de cuatro puntas del logo: lados curvados hacia el centro.
  function starPath(ctx, cx, cy, r) {
    const tips = [[0, -1], [1, 0], [0, 1], [-1, 0]], pull = [[0.18, -0.18], [0.18, 0.18], [-0.18, 0.18], [-0.18, -0.18]];
    ctx.beginPath();
    ctx.moveTo(cx + tips[0][0] * r, cy + tips[0][1] * r);
    for (let i = 0; i < 4; i++) {
      const to = tips[(i + 1) % 4], c = pull[i];
      ctx.quadraticCurveTo(cx + c[0] * r, cy + c[1] * r, cx + to[0] * r, cy + to[1] * r);
    }
    ctx.closePath();
  }

  function fit(canvas) {
    const ratio = Math.min(devicePixelRatio || 1, 2), box = canvas.getBoundingClientRect();
    canvas.width = Math.round(box.width * ratio);
    canvas.height = Math.round(box.height * ratio);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    return { ctx, width: box.width, height: box.height };
  }

  // ---- Entrada: la estrella cae, rebota tres veces, suelta anillos y chispas, y el velo se disuelve.
  function intro() {
    const root = document.documentElement, veil = document.querySelector("[data-intro]");
    if (!veil || !root.classList.contains("has-intro")) return;
    const canvas = veil.querySelector("canvas");
    let { ctx, width, height } = fit(canvas);
    const R = Math.min(46, width * 0.1), hops = [[0.30, 0.22, 150], [0.52, 0.14, 62], [0.66, 0.09, 22]], impacts = [0.30, 0.52, 0.66, 0.75];
    const TOTAL = 1650;
    let begun = performance.now(), finished = false;
    const rgba = (a) => `rgba(${ACCENT[0]}, ${ACCENT[1]}, ${ACCENT[2]}, ${Math.max(a, 0)})`;

    function offset(p, drop) {
      if (p < 0.30) { const u = p / 0.30; return [drop * (1 - u * u), u]; }
      for (const [start, length, h] of hops) {
        if (p >= start && p < start + length) { const u = (p - start) / length; return [h * 4 * u * (1 - u), Math.abs(1 - 2 * u) * 0.5]; }
      }
      return [0, 0];
    }

    function draw(p) {
      ctx.clearRect(0, 0, width, height);
      const cx = width / 2, ground = height / 2 + R - 6;
      const [high, fast] = offset(p, ground + 80);
      const hit = Math.min(...impacts.filter((i) => p >= i).map((i) => p - i), 9);
      const squash = 0.3 * Math.exp(-hit * 38) * Math.cos(hit * 60) * (p < 0.75 ? 1 : 0.6);
      const sy = 1 - squash + 0.18 * fast, sx = 1 + squash * 0.9 - 0.08 * fast;
      const spin = 4 * Math.PI * (1 - Math.min(p / 0.75, 1)) ** 2;
      const y = ground - high - R * sy;
      const glow = ctx.createRadialGradient(cx, ground - R, 0, cx, ground - R, 230);
      glow.addColorStop(0, rgba(0.22 * Math.min(p * 3, 1)));
      glow.addColorStop(1, rgba(0));
      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, width, height);
      // sombra: ajustada cuando la estrella está baja, ancha y tenue cuando está alta
      const near = Math.max(0, 1 - high / 260);
      ctx.fillStyle = `rgba(0, 0, 0, ${0.1 + 0.22 * near})`;
      ctx.beginPath();
      ctx.ellipse(cx, ground + 8, R * (0.5 + 0.9 * near), R * (0.5 + 0.9 * near) * 0.16, 0, 0, Math.PI * 2);
      ctx.fill();
      // anillo y chispas en cada aterrizaje
      impacts.forEach((at, k) => {
        const u = (p - at) / (k === 0 ? 0.34 : 0.22);
        if (!(u > 0 && u < 1)) return;
        const strength = [1, 0.6, 0.4, 0.9][k];
        ctx.strokeStyle = rgba(0.55 * (1 - u) ** 2 * strength);
        ctx.lineWidth = 2.4 - 1.4 * u;
        const reach = 30 + (k === 0 || k === 3 ? 260 : 120) * easeOut(u);
        ctx.beginPath();
        ctx.ellipse(cx, ground + 4, reach, reach * 0.32, 0, 0, Math.PI * 2);
        ctx.stroke();
        if (k === 0 || k === 3) {
          const n = k ? 12 : 9;
          for (let i = 0; i < n; i++) {
            const angle = (i * 2 * Math.PI) / n + k, dist = (60 + (70 * ((i * 7) % 5)) / 4) * easeOut(u) * (k ? 1.3 : 1);
            ctx.fillStyle = rgba((1 - u) * 0.95);
            starPath(ctx, cx + dist * Math.cos(angle), ground - 10 - dist * Math.abs(Math.sin(angle)) * 0.9 + 80 * u * u, 3 + 3 * ((i * 3) % 3) * (1 - u));
            ctx.fill();
          }
        }
      });
      ctx.save();
      ctx.translate(cx, y);
      ctx.scale(sx, sy);
      ctx.rotate(spin);
      starPath(ctx, 0, 0, R);
      ctx.fillStyle = rgba(1);
      ctx.fill();
      ctx.restore();
    }

    function finish() {
      if (finished) return;
      finished = true;
      try { sessionStorage.setItem("nova-intro", "1"); } catch { /* sin almacenamiento: la entrada se repite, nada más */ }
      veil.classList.add("is-leaving");
      root.classList.add("intro-done");
      setTimeout(() => { veil.hidden = true; root.classList.remove("has-intro"); }, 700);
    }

    function frame(now) {
      if (finished) return;
      const p = Math.min((now - begun) / TOTAL, 1);
      try { draw(p); } catch (error) { console.error('intro', error); return finish(); }
      if (p > 0.72) veil.classList.add("word");
      if (now - begun > TOTAL + 220) return finish();
      requestAnimationFrame(frame);
    }
    const frozen = /intro-frame=([\d.]+)/.exec(location.hash); // #intro-frame=0.4 deja un cuadro fijo, para revisar la entrada
    if (frozen) { draw(Number(frozen[1])); if (Number(frozen[1]) > 0.72) veil.classList.add("word"); return; }
    requestAnimationFrame((now) => { begun = now; frame(now); });
    addEventListener("keydown", finish, { once: true });
    veil.addEventListener("pointerdown", finish, { once: true });
    setTimeout(finish, 4200); // por si el navegador pausa los cuadros
  }

  // ---- Ventana del launcher: el selector Minecraft/Roblox con su portal.
  function windowMock() {
    const win = document.querySelector("[data-win]");
    if (!win) return;
    const buttons = [...win.querySelectorAll(".seg-btn")], pill = win.querySelector(".seg-pill");
    const body = win.querySelector(".win-body"), canvas = win.querySelector(".portal");
    const views = Object.fromEntries([...win.querySelectorAll("[data-view]")].map((v) => [v.dataset.view, v]));
    let busy = false, current = "minecraft";
    const looks = { minecraft: [[34, 92, 46], [107, 189, 77]], roblox: [[140, 20, 28], [237, 69, 69]] };

    function place(button) {
      pill.style.width = `${button.offsetWidth}px`;
      pill.style.transform = `translateX(${button.offsetLeft - 3}px)`;
    }
    const set = (game) => {
      current = game;
      buttons.forEach((b) => { const on = b.dataset.game === game; b.classList.toggle("is-on", on); b.setAttribute("aria-selected", String(on)); });
      for (const [key, view] of Object.entries(views)) view.classList.toggle("is-off", key !== game);
      place(buttons.find((b) => b.dataset.game === game));
    };

    function glyph(ctx, game, size, alpha) {
      if (game === "minecraft") {
        const k = size * 0.87, top = [0, -size], ur = [k, -size / 2], bottom = [0, size], ll = [-k, size / 2], ul = [-k, -size / 2], mid = [0, 0];
        const grass = [[107, 194, 69], [92, 173, 56], [122, 209, 79]], dirt = [[140, 97, 64], [122, 82, 51], [153, 110, 74], [107, 71, 46]];
        let seed = 7;
        const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
        const face = (o, u, v, shade, palette, fringe) => {
          ctx.save();
          ctx.transform(u[0] - o[0], u[1] - o[1], v[0] - o[0], v[1] - o[1], o[0], o[1]);
          for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) {
            const pick = r >= fringe + (c * 5 % 3 === 0 ? 1 : 0) ? palette : grass, col = pick[Math.floor(rnd() * pick.length)];
            ctx.fillStyle = `rgba(${col[0] * shade | 0}, ${col[1] * shade | 0}, ${col[2] * shade | 0}, ${alpha})`;
            ctx.fillRect(c / 8, r / 8, 1 / 8 + 0.012, 1 / 8 + 0.012);
          }
          ctx.restore();
        };
        face(ul, top, mid, 1, grass, 8);
        face(ul, mid, ll, 0.8, dirt, 2);
        face(mid, ur, bottom, 0.62, dirt, 2);
      } else {
        ctx.save();
        ctx.rotate((15 * Math.PI) / 180);
        ctx.fillStyle = `rgba(255, 255, 255, ${alpha})`;
        ctx.beginPath();
        ctx.rect(-size * 0.82, -size * 0.82, size * 1.64, size * 1.64);
        ctx.rect(-size * 0.3, -size * 0.3, size * 0.6, size * 0.6);
        ctx.fill("evenodd");
        ctx.restore();
      }
    }

    // El color del juego se expande desde el clic, aparece su símbolo, cambia la vista y se drena desde el mismo punto.
    function portal(game, x, y) {
      busy = true;
      const { ctx, width, height } = fit(canvas);
      canvas.classList.add("on");
      const [deep, light] = looks[game], far = Math.hypot(Math.max(x, width - x), Math.max(y, height - y)) * 1.02, TOTAL = 820;
      let begun = performance.now(), swapped = false, over = false;
      // si el navegador pausa los cuadros (pestaña en segundo plano), el cambio igual ocurre y el portal no queda trabado
      const guard = setTimeout(() => { if (!swapped) { swapped = true; set(game); } over = true; canvas.classList.remove("on"); busy = false; }, TOTAL + 600);
      const rgb = (c, a = 1) => `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${a})`;
      function frame(now) {
        if (over) return;
        const t = Math.min((now - begun) / TOTAL, 1);
        ctx.clearRect(0, 0, width, height);
        const flood = t < 0.5 ? smooth(t / 0.5) : 1, drain = smooth((t - 0.52) / 0.48);
        const paint = ctx.createRadialGradient(x, y, 0, x, y, Math.max(far * flood, 1));
        paint.addColorStop(0, rgb(light)); paint.addColorStop(0.55, rgb(deep)); paint.addColorStop(1, rgb(deep));
        ctx.fillStyle = paint;
        ctx.beginPath();
        if (drain <= 0) {
          ctx.arc(x, y, far * flood, 0, Math.PI * 2);
          ctx.fill();
          if (flood < 1) { ctx.strokeStyle = rgb(light, 0.7 * (1 - flood)); ctx.lineWidth = 4; ctx.stroke(); }
        } else {
          ctx.rect(0, 0, width, height);
          ctx.arc(x, y, far * drain, 0, Math.PI * 2);
          ctx.fill("evenodd");
          ctx.strokeStyle = rgb(light, 0.6 * (1 - drain)); ctx.lineWidth = 3;
          ctx.beginPath(); ctx.arc(x, y, far * drain, 0, Math.PI * 2); ctx.stroke();
        }
        const peak = Math.sin(Math.PI * Math.min(Math.max((t - 0.18) / 0.6, 0), 1));
        if (peak > 0) {
          ctx.save();
          ctx.translate(width / 2, height / 2);
          const scale = (0.7 + 0.4 * smooth((t - 0.18) / 0.6)) * Math.min(width / 640, 1);
          ctx.scale(scale, scale);
          glyph(ctx, game, 46, Math.min(peak * 1.4, 1));
          ctx.restore();
        }
        if (t >= 0.5 && !swapped) { swapped = true; set(game); }
        if (t < 1) return requestAnimationFrame(frame);
        clearTimeout(guard);
        canvas.classList.remove("on");
        ctx.clearRect(0, 0, width, height);
        busy = false;
      }
      requestAnimationFrame((now) => { begun = now; frame(now); });
    }

    buttons.forEach((button) => button.addEventListener("click", (event) => {
      const game = button.dataset.game;
      if (busy || game === current) return;
      if (reduce) return set(game);
      place(button); // la píldora sale al instante; el contenido cambia en el pico del portal
      const box = body.getBoundingClientRect(), at = button.getBoundingClientRect();
      const x = (event.clientX || at.left + at.width / 2) - box.left, y = (event.clientY || at.top + at.height / 2) - box.top;
      portal(game, Math.min(Math.max(x, 0), box.width), Math.min(Math.max(y, 0), box.height));
    }));
    set("minecraft");
    addEventListener("resize", () => place(buttons.find((b) => b.classList.contains("is-on"))));
    document.fonts && document.fonts.ready.then(() => place(buttons.find((b) => b.classList.contains("is-on"))));
  }

  // ---- La barra marca la sección que estás viendo, como la barra lateral del launcher.
  function spy() {
    const links = [...document.querySelectorAll(".bar nav a[href^='#']")];
    if (!links.length || !("IntersectionObserver" in window)) return;
    const byId = new Map(links.map((a) => [a.getAttribute("href").slice(1), a]));
    const sections = [...byId.keys()].map((id) => document.getElementById(id)).filter(Boolean);
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        links.forEach((a) => a.classList.toggle("is-active", a === byId.get(entry.target.id)));
      }
    }, { rootMargin: "-45% 0px -50% 0px" });
    sections.forEach((section) => observer.observe(section));
  }

  // ---- Las tarjetas de una misma fila entran una tras otra.
  function stagger() {
    document.querySelectorAll("[data-stagger]").forEach((group) => {
      [...group.children].forEach((child, index) => child.style.setProperty("--i", index));
    });
  }

  for (const part of [intro, windowMock, spy, stagger]) {
    try { part(); } catch { /* decoración: si falla, la página sigue igual */ }
  }
  // Si la entrada no corrió, el contenido arranca igual.
  if (!document.documentElement.classList.contains("has-intro")) document.documentElement.classList.add("intro-done");
})();
