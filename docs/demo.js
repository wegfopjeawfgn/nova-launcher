/* Maqueta interactiva de Nova Launcher. Todo el contenido es de ejemplo y vive en este archivo; no se envía nada a ningún lado.
   Sin JavaScript queda la captura que está dentro de #demo. */
(function () {
  var root = document.getElementById("demo");
  if (!root) return;
  var reduce = false;
  try { reduce = matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (e) {}

  var ICON = {
    inst: '<path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z"/>',
    news: '<path d="M12 3 4 7v10l8 4 8-4V7zM4 7l8 4 8-4M12 11v10"/>',
    explore: '<circle cx="11" cy="11" r="6"/><path d="m20 20-4.2-4.2"/>',
    skins: '<path d="M4 20l1-4L16 5l3 3L8 19zM14 7l3 3"/>',
    servers: '<rect x="4" y="4" width="16" height="7" rx="2"/><rect x="4" y="13" width="16" height="7" rx="2"/><path d="M8 7.5h.01M8 16.5h.01"/>',
    backups: '<path d="M12 4a8 8 0 1 0 8 8M12 8v4l3 2M20 4v4h-4"/>',
    games: '<rect x="3" y="7" width="18" height="11" rx="4"/><path d="M8 10v5M5.5 12.5h5M16 11h.01M18 14h.01"/>',
    fav: '<path d="m12 4 2.4 5 5.6.7-4.1 3.8 1.1 5.5L12 16.2 7 19l1.1-5.5L4 9.7 9.6 9z"/>',
    gear: '<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/>'
  };
  var ico = function (k) { return '<svg viewBox="0 0 24 24" aria-hidden="true">' + ICON[k] + "</svg>"; };
  var STAR = '<svg class="dm-lstar" viewBox="0 0 100 100" aria-hidden="true"><path fill="currentColor" d="M50 4C54 30 70 46 96 50 70 54 54 70 50 96 46 70 30 54 4 50 30 46 46 30 50 4Z"/></svg>';

  var NAV = {
    minecraft: [["BIBLIOTECA"], ["inst", "Instancias"], ["news", "Novedades"], ["DESCUBRIR"], ["explore", "Explorar"], ["HERRAMIENTAS"], ["skins", "Skins"], ["backups", "Respaldos"], ["servers", "Servidores"]],
    roblox: [["JUEGOS"], ["games", "Explorar"], ["fav", "Favoritos"], ["DESCUBRIR"], ["servers", "Servidores"]]
  };
  var INSTANCES = [
    { name: "Supervivencia", v: "1.21.11", loader: "Fabric 0.19.3", ram: "4 GB", time: "11 h 45 min", mods: 6, shaders: 1, tex: 2, hue: "#2e6b4f" },
    { name: "Creativo con amigos", v: "1.21.4", loader: "Vanilla", ram: "2 GB", time: "3 h 10 min", mods: 0, shaders: 0, tex: 1, hue: "#3b4f8c" },
    { name: "Pack de aventura", v: "1.20.1", loader: "Forge 47.3", ram: "6 GB", time: "27 h 02 min", mods: 42, shaders: 2, tex: 3, hue: "#8c4b3b" }
  ];
  var MODS = {
    Modrinth: [["Sodium", "Motor de renderizado que sube los FPS.", "Rendimiento"], ["Lithium", "Optimiza la lógica del juego sin cambiar nada.", "Rendimiento"], ["Iris Shaders", "Shaders compatibles con Sodium.", "Gráficos"], ["Mod Menu", "Lista tus mods dentro del juego.", "Utilidad"]],
    CurseForge: [["JEI", "Ver recetas y usos de cada objeto.", "Utilidad"], ["Create", "Máquinas y engranajes, para tu fábrica.", "Tecnología"], ["Biomes O' Plenty", "Más de 80 biomas nuevos.", "Mundo"], ["Journeymap", "Mapa en vivo del mundo.", "Utilidad"]]
  };
  var NEWS = [
    ["1.15.0", "Interfaz nueva, portal al elegir juego y ajustes de animaciones."],
    ["1.14.1", "Editor de skins con vista previa 3D y pantalla de inicio al jugar."],
    ["1.14.0", "Actualizaciones en segundo plano con SHA-256 comprobado."]
  ];
  var SERVERS = [["Survival de amigos", "Paper 1.21.4", "4 jugadores"], ["Mundo creativo", "Vanilla 1.21.11", "0 jugadores"]];
  var GAMES = [
    ["Carrera de autos", "18,4 mil jugando", "#c0392b", "🏎"], ["Mi granja", "9,1 mil jugando", "#3f9b57", "🌾"], ["Torre de obstáculos", "22,7 mil jugando", "#6a4fc0", "🗼"],
    ["Pizzería tycoon", "5,6 mil jugando", "#d98a1f", "🍕"], ["Escape del laberinto", "12,3 mil jugando", "#2a7fa8", "🌀"], ["Isla de piratas", "7,8 mil jugando", "#a8553b", "🏴"]
  ];
  var FRIENDS = [["Fran", "#c0392b"], ["Lu", "#3f9b57"], ["Mati", "#6a4fc0"]];
  var PALETTE = ["#e0ac86", "#8a5a3c", "#3a2a22", "#ffffff", "#1c1c24", "#3868c8", "#2a3f8f", "#5fd38a", "#2e7d4f", "#e0524d", "#f2a93b", "#f2e06b", "#8e5bd9", "#e96fb0", "#44c7d6", "#9aa3b2"];
  var STEPS = [["Preparar", "Preparando la instancia…"], ["Archivos", "Descargando recursos de Minecraft…"], ["Iniciar Java", "Iniciando Java 21…"], ["En juego", "¡Listo! Minecraft se abre."]];

  var S = { game: "minecraft", view: "inst", theme: "dark", speed: "medium", inst: 0, source: "Modrinth", installed: {}, backups: [["Supervivencia · automático", "Hace 2 días · 412 MB"], ["Antes de actualizar mods", "Hace 6 días · 398 MB"]], fav: {}, query: "", color: PALETTE[5], tool: "pen", tab: "all", running: {} };
  var K = { soft: 1.45, medium: 1, fast: 0.55, off: 0 };
  var ms = function (v) { return reduce ? 0 : v * K[S.speed]; };
  var done = {};

  /* Lienzo de skin (16×16: la cara y el cuerpo de frente, sin pretensiones de ser el editor real) */
  var G = 16, grid = [];
  function seedSkin() {
    grid = [];
    for (var y = 0; y < G; y++) { grid[y] = []; for (var x = 0; x < G; x++) grid[y][x] = null; }
    var set = function (x0, y0, x1, y1, c) { for (var y = y0; y <= y1; y++) for (var x = x0; x <= x1; x++) grid[y][x] = c; };
    set(5, 1, 10, 6, "#e0ac86"); set(5, 1, 10, 2, "#3a2a22"); set(5, 3, 5, 4, "#3a2a22"); set(10, 3, 10, 4, "#3a2a22");
    grid[4][6] = "#ffffff"; grid[4][9] = "#ffffff"; grid[4][7] = "#3868c8"; grid[4][8] = "#3868c8";
    set(5, 7, 10, 12, "#3868c8"); set(3, 7, 4, 12, "#3868c8"); set(11, 7, 12, 12, "#3868c8"); set(3, 11, 4, 12, "#e0ac86"); set(11, 11, 12, 12, "#e0ac86");
    set(5, 13, 7, 15, "#2a3f8f"); set(8, 13, 10, 15, "#2a3f8f");
  }
  seedSkin();

  /* Estructura fija */
  root.innerHTML =
    '<div class="dm-top"><span class="dm-brand"><img src="assets/nova.svg" width="18" height="18" alt=""> Nova Launcher</span>' +
    '<div class="dm-seg" role="tablist" aria-label="Elegí un juego"><span class="dm-pill" aria-hidden="true"></span>' +
    '<button type="button" role="tab" data-game="minecraft">Minecraft</button><button type="button" role="tab" data-game="roblox">Roblox</button></div>' +
    '<input class="dm-search" type="search" placeholder="Buscar instancias" aria-label="Buscar" autocomplete="off"><span class="dm-user">Alex ▾</span></div>' +
    '<div class="dm-body"><nav class="dm-side" aria-label="Menú de la maqueta"></nav><main class="dm-main" tabindex="-1"></main></div>' +
    '<div class="dm-launch" role="dialog" aria-modal="false" aria-label="Iniciando"><div class="dm-lcard">' + STAR +
    '<h4></h4><small></small><ol class="dm-steps"></ol><p class="dm-lmsg" role="status"></p><p class="dm-lfoot">Esto es una maqueta: en Nova se abre el juego de verdad.</p>' +
    '<button type="button" class="dm-btn" data-close>Cerrar</button></div></div>';
  root.classList.add("dm"); root.setAttribute("data-theme", "dark"); root.setAttribute("data-speed", "medium");

  var side = root.querySelector(".dm-side"), main = root.querySelector(".dm-main"), search = root.querySelector(".dm-search");
  var pill = root.querySelector(".dm-pill"), seg = root.querySelector(".dm-seg"), launch = root.querySelector(".dm-launch");
  var timers = [];
  var later = function (fn, t) { var id = setTimeout(fn, t); timers.push(id); return id; };
  var clearTimers = function () { timers.forEach(clearTimeout); timers = []; };

  function mark(key) {
    if (done[key]) return; done[key] = 1;
    var b = document.querySelector('[data-try="' + key + '"]'); if (b) b.classList.add("done");
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }

  function movePill() {
    var on = seg.querySelector("button.on"); if (!on) return;
    pill.style.width = on.offsetWidth + "px"; pill.style.transform = "translateX(" + on.offsetLeft + "px)";
  }
  function drawSide() {
    var html = "";
    NAV[S.game].forEach(function (n) {
      if (n.length === 1) html += "<h4>" + n[0] + "</h4>";
      else html += '<button type="button" class="dm-nav' + (S.view === n[0] ? " on" : "") + '" data-view="' + n[0] + '">' + ico(n[0]) + n[1] + "</button>";
    });
    html += '<div class="dm-me"><img src="assets/nova.svg" width="30" height="30" alt=""><span><b>Nova 1.15.0</b><span>Al día</span></span>' +
      '<button type="button" data-view="set" aria-label="Ajustes">' + ico("gear") + "</button></div>";
    side.innerHTML = html;
  }
  function setGameUI() {
    seg.querySelectorAll("button").forEach(function (b) { var on = b.dataset.game === S.game; b.classList.toggle("on", on); b.setAttribute("aria-selected", on); });
    search.placeholder = S.game === "roblox" ? "Buscar un juego de Roblox" : "Buscar instancias";
    movePill();
  }

  /* Vistas */
  var V = {};
  V.inst = function () {
    var cur = INSTANCES[S.inst], q = S.query.toLowerCase();
    var list = INSTANCES.map(function (x, i) { return [x, i]; }).filter(function (p) { return !q || p[0].name.toLowerCase().indexOf(q) >= 0; });
    return '<div class="dm-view"><div class="dm-head"><div><h3>Mis instancias</h3><p class="dm-sub">' + INSTANCES.length + ' instancias · 19 h 58 min jugadas</p></div>' +
      '<button type="button" class="dm-btn pri" data-act="new">+ Nueva instancia</button></div>' +
      '<div class="dm-hero" style="background-color:' + cur.hue + '"><span class="art"></span><div><h3>' + esc(cur.name) + '</h3><div class="dm-tags"><span>' + cur.v + "</span><span>" + cur.loader + "</span><span>" + cur.ram + "</span></div>" +
      '<div class="dm-acts"><button type="button" class="dm-btn pri" data-act="play">▶ Jugar</button><button type="button" class="dm-btn" data-act="edit">Editar</button><button type="button" class="dm-btn" data-act="srv">Servidores</button></div></div></div>' +
      '<div class="dm-stats"><div><small>Mods</small><b>' + cur.mods + "</b></div><div><small>Shaders</small><b>" + cur.shaders + "</b></div><div><small>Texturas</small><b>" + cur.tex + "</b></div><div><small>Tiempo jugado</small><b>" + cur.time + "</b></div></div>" +
      '<div class="dm-list">' + (list.length ? list.map(function (p) {
        return '<button type="button" class="dm-row' + (p[1] === S.inst ? " on" : "") + '" data-inst="' + p[1] + '"><span class="ico" style="background:' + p[0].hue + '"></span><span><b>' + esc(p[0].name) + "</b><small>" + p[0].v + " · " + p[0].loader + "</small></span></button>";
      }).join("") : '<p class="dm-empty">Ninguna instancia coincide con «' + esc(S.query) + "».</p>") + "</div></div>";
  };
  V.news = function () {
    return '<div class="dm-view"><div class="dm-head"><div><h3>Novedades</h3><p class="dm-sub">Lo último de Nova</p></div></div>' +
      NEWS.map(function (n) { return '<div class="dm-card"><span class="ver">' + n[0] + "</span><h5>Versión " + n[0] + "</h5><p>" + n[1] + "</p></div>"; }).join("") + "</div>";
  };
  V.explore = function () {
    var q = S.query.toLowerCase(), src = S.source;
    var items = MODS[src].filter(function (m) { return !q || m[0].toLowerCase().indexOf(q) >= 0 || m[1].toLowerCase().indexOf(q) >= 0; });
    return '<div class="dm-view"><div class="dm-head"><div><h3>Explorar</h3><p class="dm-sub">Mods para ' + esc(INSTANCES[S.inst].name) + "</p></div></div>" +
      '<div class="dm-seg dm-pick" role="tablist">' + ["Modrinth", "CurseForge"].map(function (s) { return '<button type="button" class="' + (s === src ? "on" : "") + '" style="' + (s === src ? "background:var(--sel);box-shadow:inset 0 0 0 1px var(--sel-line)" : "") + '" data-source="' + s + '">' + s + "</button>"; }).join("") + "</div>" +
      '<div class="dm-list">' + (items.length ? items.map(function (m) {
        var key = src + m[0], on = S.installed[key];
        return '<div class="dm-row"><span class="ico" style="background:linear-gradient(135deg,#2a5f6e,#8fd6e8)"></span><span><b>' + esc(m[0]) + "</b><small>" + esc(m[1]) + " · " + m[2] + '</small></span><button type="button" class="dm-btn' + (on ? " ok" : "") + '" data-mod="' + esc(key) + '">' + (on ? "✓ Instalado" : "Instalar") + "</button></div>";
      }).join("") : '<p class="dm-empty">No hay resultados para «' + esc(S.query) + "».</p>") + "</div></div>";
  };
  V.skins = function () {
    return '<div class="dm-view"><div class="dm-head"><div><h3>Skins</h3><p class="dm-sub">Perfil · Alex</p></div><button type="button" class="dm-btn pri" data-act="equip">Equipar</button></div>' +
      '<div class="dm-skins"><div><canvas class="dm-cv" width="16" height="16" aria-label="Lienzo para pintar tu skin"></canvas>' +
      '<div class="dm-pal" role="group" aria-label="Paleta">' + PALETTE.map(function (c) { return '<button type="button" data-color="' + c + '" style="background:' + c + '" aria-label="Color ' + c + '"' + (c === S.color && S.tool === "pen" ? ' class="on"' : "") + "></button>"; }).join("") + "</div>" +
      '<div class="dm-tools"><button type="button" class="dm-btn' + (S.tool === "pen" ? " ok" : "") + '" data-tool="pen">Lápiz</button><button type="button" class="dm-btn' + (S.tool === "erase" ? " ok" : "") + '" data-tool="erase">Borrar</button><button type="button" class="dm-btn" data-act="clear">Limpiar</button></div></div>' +
      '<div><div class="dm-3d"><canvas width="16" height="16" aria-label="Vista previa en 3D"></canvas></div><p class="dm-hint">Arrastrá para girarla</p></div></div></div>';
  };
  V.servers = function () {
    return '<div class="dm-view"><div class="dm-head"><div><h3>Servidores</h3><p class="dm-sub">Tus mundos en línea, gratis y desde Nova</p></div></div><div class="dm-list">' +
      SERVERS.map(function (s, i) {
        var up = S.running[i];
        return '<div class="dm-row"><span class="ico" style="background:linear-gradient(135deg,#2e6b4f,#5fd38a)"></span><span><b>' + s[0] + "</b><small>" + s[1] + ' · <span class="dm-state' + (up ? " up" : "") + '"><i></i>' + (up ? "En línea · " + s[2] : "Detenido") + "</span></small></span>" +
          '<button type="button" class="dm-btn' + (up ? "" : " pri") + '" data-srv="' + i + '">' + (up ? "Detener" : "Iniciar") + "</button></div>";
      }).join("") + "</div></div>";
  };
  V.backups = function () {
    return '<div class="dm-view"><div class="dm-head"><div><h3>Respaldos</h3><p class="dm-sub">Cada copia se verifica con SHA-256 antes de restaurarla</p></div>' +
      '<button type="button" class="dm-btn pri" data-act="backup">+ Crear respaldo</button></div><div class="dm-list">' +
      S.backups.map(function (b, i) {
        return '<div class="dm-row"><span class="ico" style="background:linear-gradient(135deg,#3b4f8c,#8fd6e8)"></span><span><b>' + esc(b[0]) + "</b><small>" + esc(b[1]) +
          ' · <span class="dm-state up"><i></i>Verificado</span></small></span><button type="button" class="dm-btn' + (S.restored === i ? " ok" : "") + '" data-restore="' + i + '">' + (S.restored === i ? "✓ Restaurado como instancia nueva" : "Restaurar") + "</button></div>";
      }).join("") + "</div></div>";
  };
  V.set = function () {
    var seg2 = function (name, opts, cur) { return '<div class="dm-seg">' + opts.map(function (o) { return '<button type="button" class="' + (o[0] === cur ? "on" : "") + '" style="' + (o[0] === cur ? "background:var(--sel);box-shadow:inset 0 0 0 1px var(--sel-line)" : "") + '" data-set="' + name + '" data-val="' + o[0] + '">' + o[1] + "</button>"; }).join("") + "</div>"; };
    return '<div class="dm-view"><div class="dm-head"><div><h3>Ajustes</h3><p class="dm-sub">Se aplican al instante, como en Nova</p></div></div>' +
      '<div class="dm-set"><span><b>Apariencia</b><small>Tema oscuro o claro.</small></span>' + seg2("theme", [["dark", "Oscuro"], ["light", "Claro"]], S.theme) + "</div>" +
      '<div class="dm-set"><span><b>Animaciones</b><small>Lentas: más fluidas. Rápidas: casi instantáneas. Apagadas: sin movimiento.</small></span>' +
      seg2("speed", [["soft", "Lentas"], ["medium", "Normales"], ["fast", "Rápidas"], ["off", "Apagadas"]], S.speed) + "</div></div>";
  };
  V.games = function () {
    var q = S.query.toLowerCase();
    var items = GAMES.map(function (g, i) { return [g, i]; }).filter(function (p) { return (!q || p[0][0].toLowerCase().indexOf(q) >= 0) && (S.view !== "fav" || S.fav[p[1]]); });
    return '<div class="dm-view"><div class="dm-head"><div><h3>' + (S.view === "fav" ? "Favoritos" : "Roblox") + '</h3><p class="dm-sub">Juegos de ejemplo, sin marcas reales</p></div></div>' +
      '<div class="dm-friends" aria-label="Amigos">' + FRIENDS.map(function (f) { return '<button type="button" data-friend="' + f[0] + '"><i style="background:' + f[1] + '">' + f[0][0] + "</i>" + f[0] + "</button>"; }).join("") + "</div>" +
      '<div class="dm-games">' + (items.length ? items.map(function (p) {
        var g = p[0];
        return '<div class="dm-game"><div class="th" style="background:' + g[2] + '">' + g[3] + '<button type="button" class="star' + (S.fav[p[1]] ? " on" : "") + '" data-fav="' + p[1] + '" aria-label="Favorito" aria-pressed="' + !!S.fav[p[1]] + '">★</button></div>' +
          '<div class="in"><b>' + g[0] + "</b><small>" + g[1] + '</small><button type="button" class="dm-btn pri" data-playr="' + p[1] + '">Jugar</button></div></div>';
      }).join("") : '<p class="dm-empty">' + (S.view === "fav" ? "Marcá una ★ y aparece acá." : "Ningún juego coincide con «" + esc(S.query) + "».") + "</p>") + "</div></div>";
  };
  V.fav = V.games;

  function render(keepScroll) {
    var y = main.scrollTop;
    main.innerHTML = (V[S.view] || V.inst)();
    if (keepScroll) main.scrollTop = y;
    if (S.view === "skins") initSkin();
  }
  function goView(v) { S.view = v; S.query = ""; search.value = ""; drawSide(); render(); }

  /* Portal al cambiar de juego */
  function switchGame(game, ev) {
    if (game === S.game) return;
    var rect = root.getBoundingClientRect(), x = ev && ev.clientX ? ev.clientX - rect.left : rect.width / 2, y = ev && ev.clientY ? ev.clientY - rect.top : 40;
    var swapped = false;
    var swap = function () {
      if (swapped) return; swapped = true;
      S.game = game; S.view = game === "roblox" ? "games" : "inst"; S.query = ""; search.value = "";
      setGameUI(); drawSide(); render();
    };
    var t = ms(560);
    if (!t || !root.animate) { swap(); return; }
    var p = document.createElement("div"); p.className = "dm-portal"; p.style.background = game === "roblox" ? "#c0392b" : "#3f9b57"; root.appendChild(p);
    var rr = Math.hypot(rect.width, rect.height) + 40, from = "circle(0px at " + x + "px " + y + "px)", to = "circle(" + rr + "px at " + x + "px " + y + "px)";
    var end = function () { swap(); p.remove(); };
    p.animate([{ clipPath: from }, { clipPath: to }], { duration: t * 0.55, easing: "cubic-bezier(0.55, 0, 0.3, 1)", fill: "forwards" }).onfinish = function () {
      swap();
      p.animate([{ opacity: 1 }, { opacity: 0 }], { duration: t * 0.55, easing: "ease-out", fill: "forwards" }).onfinish = end;
    };
    setTimeout(end, t * 1.5 + 400);   // red de seguridad: si el navegador pausa las animaciones (pestaña oculta), igual cambia
  }

  /* Lanzamiento */
  function startLaunch(title, sub, steps) {
    clearTimers();
    var card = launch.querySelector(".dm-lcard");
    card.querySelector("h4").textContent = title; card.querySelector("small").textContent = sub;
    var ol = card.querySelector("ol"); ol.innerHTML = steps.map(function (s) { return "<li><i>✓</i>" + s[0] + "</li>"; }).join("");
    var lis = ol.querySelectorAll("li"), msg = card.querySelector(".dm-lmsg");
    launch.classList.remove("on"); void launch.offsetWidth; launch.classList.add("on");
    var step = function (i) {
      if (i > 0) lis[i - 1].className = "ok";
      if (i >= lis.length) { msg.textContent = steps[steps.length - 1][1]; return; }
      lis[i].className = i === lis.length - 1 ? "ok" : "now"; msg.textContent = steps[i][1];
      later(function () { step(i + 1); }, ms(850) || 1);
    };
    later(function () { step(0); }, ms(700) || 1);
  }
  function stopLaunch() { clearTimers(); launch.classList.remove("on"); }

  /* Lienzo de skin y vista 3D */
  var cv, pv, rot = 18, drag = null, spin = 0;
  function paintAll() {
    if (!cv) return;
    [cv, pv].forEach(function (c) {
      var g = c.getContext("2d"); g.clearRect(0, 0, G, G);
      for (var y = 0; y < G; y++) for (var x = 0; x < G; x++) if (grid[y][x]) { g.fillStyle = grid[y][x]; g.fillRect(x, y, 1, 1); }
    });
  }
  function initSkin() {
    cv = main.querySelector(".dm-cv"); pv = main.querySelector(".dm-3d canvas"); paintAll();
    var down = false;
    var put = function (e) {
      var r = cv.getBoundingClientRect(), x = Math.floor((e.clientX - r.left) / r.width * G), y = Math.floor((e.clientY - r.top) / r.height * G);
      if (x < 0 || y < 0 || x >= G || y >= G) return;
      var v = S.tool === "erase" ? null : S.color; if (grid[y][x] === v) return;
      grid[y][x] = v; paintAll(); mark("skin");
    };
    cv.addEventListener("pointerdown", function (e) { down = true; cv.setPointerCapture(e.pointerId); put(e); });
    cv.addEventListener("pointermove", function (e) { if (down) put(e); });
    cv.addEventListener("pointerup", function () { down = false; });
    cv.addEventListener("pointercancel", function () { down = false; });
    var box = main.querySelector(".dm-3d");
    box.addEventListener("pointerdown", function (e) { drag = { x: e.clientX, r: rot }; box.setPointerCapture(e.pointerId); spin = 0; });
    box.addEventListener("pointermove", function (e) { if (drag) { rot = drag.r + (e.clientX - drag.x) * 0.9; pv.style.transform = "rotateY(" + rot + "deg)"; mark("skin"); } });
    box.addEventListener("pointerup", function () { drag = null; });
    pv.style.transform = "rotateY(" + rot + "deg)";
  }
  (function sway() {
    if (pv && pv.isConnected && !drag && !reduce && S.speed !== "off") { spin += 0.012; pv.style.transform = "rotateY(" + (rot + Math.sin(spin) * 24) + "deg)"; }
    requestAnimationFrame(sway);
  })();

  /* Eventos */
  seg.addEventListener("click", function (e) { var b = e.target.closest("[data-game]"); if (b) { switchGame(b.dataset.game, e); if (b.dataset.game === "roblox") mark("roblox"); } });
  search.addEventListener("input", function () { S.query = search.value; render(true); });
  side.addEventListener("click", function (e) { var b = e.target.closest("[data-view]"); if (b) goView(b.dataset.view); });
  launch.addEventListener("click", function (e) { if (e.target === launch || e.target.closest("[data-close]")) stopLaunch(); });
  root.addEventListener("keydown", function (e) { if (e.key === "Escape") stopLaunch(); });

  main.addEventListener("click", function (e) {
    var t = e.target.closest("button"); if (!t) return;
    var d = t.dataset;
    if (d.act === "play") { var c = INSTANCES[S.inst]; startLaunch(c.name, "Minecraft " + c.v + " · " + c.loader + " · Alex", STEPS); mark("play"); }
    else if (d.act === "new") { t.textContent = "¡Eso es en la app real!"; }
    else if (d.act === "edit" || d.act === "srv") { goView(d.act === "srv" ? "servers" : "set"); }
    else if (d.inst) { S.inst = +d.inst; render(true); }
    else if (d.source) { S.source = d.source; render(true); }
    else if (d.mod) { S.installed[d.mod] = !S.installed[d.mod]; render(true); mark("mods"); }
    else if (d.color) { S.color = d.color; S.tool = "pen"; render(true); }
    else if (d.tool) { S.tool = d.tool; render(true); }
    else if (d.act === "clear") { grid.forEach(function (r) { r.fill(null); }); paintAll(); }
    else if (d.act === "equip") { t.textContent = "✓ Equipada"; t.classList.add("ok"); mark("skin"); }
    else if (d.act === "backup") { S.backups.unshift(["Supervivencia · manual", "Ahora · 415 MB"]); S.restored = -1; render(true); mark("backup"); }
    else if (d.restore) { S.restored = +d.restore; render(true); }
    else if (d.srv) { S.running[d.srv] = !S.running[d.srv]; render(true); }
    else if (d.set === "theme") { S.theme = d.val; root.setAttribute("data-theme", d.val); render(true); mark("theme"); }
    else if (d.set === "speed") { S.speed = d.val; root.setAttribute("data-speed", d.val); render(true); setGameUI(); }
    else if (d.fav !== undefined) { S.fav[d.fav] = !S.fav[d.fav]; render(true); }
    else if (d.playr !== undefined) { var g = GAMES[+d.playr]; startLaunch(g[0], "Roblox · Alex", [["Preparar", "Abriendo Roblox…"], ["Servidor", "Buscando un servidor con lugar…"], ["En juego", "¡Listo! Roblox se abre."]]); mark("play"); }
    else if (d.friend) { startLaunch("Unirte a " + d.friend, "Roblox · con el enlace oficial", [["Preparar", "Abriendo Roblox…"], ["En juego", "Te unís a la partida de " + d.friend + "."]]); }
  });

  /* Guía: atajos que hacen la acción por vos */
  document.querySelectorAll("[data-try]").forEach(function (b) {
    b.addEventListener("click", function () {
      var k = b.dataset.try;
      stopLaunch();
      var go = function () {
        if (k === "play") { if (S.game !== "minecraft") switchGame("minecraft"); setTimeout(function () { goView("inst"); setTimeout(function () { var p = main.querySelector('[data-act="play"]'); if (p) p.click(); }, ms(200) + 60); }, ms(620) + 40); }
        else if (k === "roblox") { if (S.game !== "roblox") switchGame("roblox", { clientX: b.getBoundingClientRect().left, clientY: b.getBoundingClientRect().top }); mark("roblox"); }
        else if (k === "skin") { if (S.game !== "minecraft") { switchGame("minecraft"); setTimeout(function () { goView("skins"); }, ms(620) + 40); } else goView("skins"); }
        else if (k === "theme") { if (S.game !== "minecraft") { switchGame("minecraft"); setTimeout(function () { goView("set"); }, ms(620) + 40); } else goView("set"); }
        else if (k === "mods") { if (S.game !== "minecraft") { switchGame("minecraft"); setTimeout(function () { goView("explore"); }, ms(620) + 40); } else goView("explore"); }
      };
      root.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" });
      go();
    });
  });

  setGameUI(); drawSide(); render();
  window.addEventListener("resize", movePill);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(movePill);
  setTimeout(movePill, 50);
  if (window.ResizeObserver) new ResizeObserver(movePill).observe(seg);
})();
