// Nova Launcher · sitio. Cielo de estrellas, barra con fondo al desplazarse y entrada suave de las secciones.
// Sin JavaScript o con "menos movimiento" todo se ve de inmediato y el cielo queda quieto.
(() => {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Generador determinista: el cielo es idéntico en cada visita.
  function rng(seed) {
    let a = seed >>> 0;
    return () => {
      a = (a + 0x6d2b79f5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  const bar = document.querySelector("[data-bar]");
  if (bar) {
    const update = () => bar.classList.toggle("is-scrolled", scrollY > 24);
    update();
    addEventListener("scroll", update, { passive: true });
  }

  const canvas = document.querySelector("[data-sky]");
  if (canvas && canvas.getContext) {
    const random = rng(1987);
    const count = innerWidth < 700 ? 130 : 300;
    const stars = Array.from({ length: count }, () => {
      const depth = random();
      return { x: random(), y: random(), size: depth * depth * 1.5 + 0.35, alpha: 0.25 + random() * 0.6,
               phase: random() * Math.PI * 2, speed: 0.4 + random() * 1.2, depth };
    });
    let context, width, height, running = false, frame = 0;
    const pointer = { x: 0, y: 0, tx: 0, ty: 0 };

    function size() {
      const ratio = Math.min(devicePixelRatio || 1, 2);
      const box = canvas.getBoundingClientRect();
      canvas.width = Math.round(box.width * ratio);
      canvas.height = Math.round(box.height * ratio);
      context = canvas.getContext("2d");
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      width = box.width;
      height = box.height;
    }

    function draw(time) {
      context.clearRect(0, 0, width, height);
      for (const star of stars) {
        const twinkle = time ? 0.75 + 0.25 * Math.sin(time * 0.001 * star.speed + star.phase) : 1;
        context.globalAlpha = star.alpha * twinkle;
        context.fillStyle = "#e8ecf7";
        context.beginPath();
        context.arc(star.x * width + pointer.x * -16 * star.depth, star.y * height + pointer.y * -10 * star.depth, star.size, 0, Math.PI * 2);
        context.fill();
      }
      context.globalAlpha = 1;
      // La estrella de Nova Launcher: un destello cian sobre la captura.
      const small = width < 700;
      const x = width * (small ? 0.86 : 0.9), y = small ? 112 : height * 0.16;
      const halo = context.createRadialGradient(x, y, 0, x, y, small ? 56 : 90);
      halo.addColorStop(0, "rgba(220, 246, 252, 0.95)");
      halo.addColorStop(0.12, "rgba(143, 214, 232, 0.5)");
      halo.addColorStop(1, "rgba(143, 214, 232, 0)");
      context.fillStyle = halo;
      context.beginPath();
      context.arc(x, y, small ? 56 : 90, 0, Math.PI * 2);
      context.fill();
      context.strokeStyle = "rgba(220, 246, 252, 0.7)";
      context.lineWidth = 1;
      const reach = small ? 38 : 70;
      context.beginPath();
      context.moveTo(x - reach, y); context.lineTo(x + reach, y);
      context.moveTo(x, y - reach * 0.8); context.lineTo(x, y + reach * 0.8);
      context.stroke();
    }

    function loop(now) {
      pointer.x += (pointer.tx - pointer.x) * 0.06;
      pointer.y += (pointer.ty - pointer.y) * 0.06;
      draw(now);
      if (running) frame = requestAnimationFrame(loop);
    }

    size();
    if (reduce) {
      draw(0);
    } else {
      const play = () => { if (!running) { running = true; frame = requestAnimationFrame(loop); } };
      const pause = () => { running = false; cancelAnimationFrame(frame); };
      new IntersectionObserver(([entry]) => (entry.isIntersecting ? play() : pause())).observe(canvas);
      document.addEventListener("visibilitychange", () => (document.hidden ? pause() : play()));
      if (matchMedia("(hover: hover) and (pointer: fine)").matches) {
        addEventListener("pointermove", (event) => {
          pointer.tx = event.clientX / innerWidth - 0.5;
          pointer.ty = event.clientY / innerHeight - 0.5;
        }, { passive: true });
      }
    }
    let timer;
    addEventListener("resize", () => { clearTimeout(timer); timer = setTimeout(() => { size(); if (reduce) draw(0); }, 120); });
  }

  const items = document.querySelectorAll(".reveal");
  if (!items.length) return;
  if (!("IntersectionObserver" in window) || reduce) {
    items.forEach((item) => item.classList.add("visible"));
    return;
  }
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        entry.target.classList.add("visible");
        observer.unobserve(entry.target);
      }
    }
  }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
  items.forEach((item) => observer.observe(item));
})();
