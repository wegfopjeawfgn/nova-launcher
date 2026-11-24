/* Maqueta interactiva de Nova Launcher. Todo el contenido es de ejemplo (inventado) y vive en este archivo; no se envía nada a ningún lado.
   Sin JavaScript queda la captura que está dentro de #demo. Réplica de la interfaz real (nova.css / nova-light.css). */
(function () {
  var root = document.getElementById("demo");
  if (!root) return;
  var reduce = false;
  try { reduce = matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (e) {}

  var P = {
    grid: '<path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z"/>', cube: '<path d="M12 3 4 7v10l8 4 8-4V7zM4 7l8 4 8-4M12 11v10"/>',
    search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>', pen: '<path d="M4 20l1-4L16 5l3 3L8 19zM14 7l3 3"/>',
    server: '<rect x="4" y="4" width="16" height="7" rx="2"/><rect x="4" y="13" width="16" height="7" rx="2"/><path d="M8 7.5h.01M8 16.5h.01"/>',
    folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>', plus: '<path d="M12 5v14M5 12h14"/>',
    dots: '<path d="M12 5h.01M12 12h.01M12 19h.01" stroke-width="2.6"/>', clock: '<path d="M12 4a8 8 0 1 0 8 8M12 8v4l3 2M20 4v4h-4"/>',
    play: '<path d="M8 5v14l11-7z"/>', gear: '<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/>',
    back: '<path d="m15 5-7 7 7 7"/>', list: '<path d="M5 7h14M5 12h14M5 17h9"/>', chart: '<path d="M5 20V10M12 20V4M19 20v-7"/>'
  };
  var ico = function (k) { return '<svg class="i" width="17" height="17" viewBox="0 0 24 24" aria-hidden="true">' + P[k] + "</svg>"; };
  var STAR = '<svg width="40" height="40" viewBox="0 0 100 100" aria-hidden="true"><path fill="currentColor" d="M50 4C54 30 70 46 96 50 70 54 54 70 50 96 46 70 30 54 4 50 30 46 46 30 50 4Z"/></svg>';
  var G1 = "-XX:+UseG1GC -XX:+ParallelRefProcEnabled -XX:MaxGCPauseMillis=200";

  var NAV = [["BIBLIOTECA"], ["inst", "Instancias", "grid"], ["news", "Novedades", "cube"], ["DESCUBRIR"], ["explore", "Explorar", "search"], ["curse", "CurseForge", "search"], ["packs", "Modpacks", "cube"], ["import", "Importar", "folder"],
    ["HERRAMIENTAS"], ["skins", "Skins", "pen"], ["servers", "Servidores", "server"], ["myserver", "Mi servidor", "server"]];
  var MORE = [["backups", "Respaldos", "folder"], ["sessions", "Sesiones", "play"], ["stats", "Estadísticas", "chart"]];
  var ALIAS = { mods: "inst", health: "inst", edit: "inst", fav: "games" };

  var INSTANCES = [
    { name: "Supervivencia", v: "1.21.11", loader: "Fabric 0.19.3", ram: 4, min: 705, mods: 6, shaders: 1, tex: 2, fav: true, f: "none", pos: "50% 38%" },
    { name: "Create Nova", v: "1.21.1", loader: "NeoForge 21.1", ram: 8, min: 190, mods: 14, shaders: 0, tex: 2, f: "hue-rotate(150deg) saturate(1.1)", pos: "50% 60%" },
    { name: "Servidor de amigos", v: "1.20.1", loader: "Forge 47.3", ram: 6, min: 170, mods: 5, shaders: 0, tex: 3, f: "hue-rotate(-70deg)", pos: "30% 40%" },
    { name: "Vanilla limpio", v: "1.21.4", loader: "Vanilla", ram: 3, min: 70, mods: 0, shaders: 0, tex: 0, f: "grayscale(0.7) brightness(0.9)", pos: "70% 50%" },
    { name: "Pack de aventura", v: "1.20.1", loader: "Forge 47.3", ram: 6, min: 60, mods: 42, shaders: 2, tex: 3, f: "hue-rotate(35deg) saturate(1.2)", pos: "60% 30%" }
  ];
  var fmt = function (m) { var h = Math.floor(m / 60); return (h ? h + " h " : "") + (m % 60) + " min"; };
  var MODLIST = [
    { n: "Sodium", cur: "0.6.2", nw: "0.6.5", on: true, c: "#2e6b4f" }, { n: "Lithium", cur: "0.14.1", on: true, c: "#3b4f8c" }, { n: "Iris Shaders", cur: "1.8.0", nw: "1.8.4", on: true, c: "#8c4b3b" },
    { n: "Mod Menu", cur: "11.0.1", on: true, c: "#6a4fc0" }, { n: "Fabric API", cur: "0.110.0", nw: "0.112.2", on: true, c: "#2a7fa8" }, { n: "Sound Physics", cur: "1.4.9", on: false, c: "#a8553b" }
  ];
  var CAT = {
    Modrinth: [["Sodium", "Motor de renderizado que sube los FPS.", "Rendimiento", "#2e6b4f"], ["Lithium", "Optimiza la lógica del juego sin cambiar nada.", "Rendimiento", "#3b4f8c"], ["Iris Shaders", "Shaders compatibles con Sodium.", "Gráficos", "#8c4b3b"], ["Mod Menu", "Lista tus mods dentro del juego.", "Utilidad", "#6a4fc0"], ["Xaero's Minimap", "Un minimapa pequeño y claro.", "Utilidad", "#2a7fa8"], ["Sound Physics", "El sonido rebota en las cuevas.", "Ambiente", "#a8553b"]],
    CurseForge: [["JEI", "Ver recetas y usos de cada objeto.", "Utilidad", "#6a4fc0"], ["Create", "Máquinas y engranajes para tu fábrica.", "Tecnología", "#d98a1f"], ["Biomes O' Plenty", "Más de 80 biomas nuevos.", "Mundo", "#3f9b57"], ["Journeymap", "Mapa en vivo del mundo.", "Utilidad", "#2a7fa8"], ["Farmer's Delight", "Cocina y cultivos nuevos.", "Comida", "#c0392b"], ["Waystones", "Teletransportate entre puntos.", "Aventura", "#3b4f8c"]]
  };
  var PACKS = [["Mejoras visuales", "Rendimiento y gráficos listos para jugar", "38 mods · 1.21.1", 38, "#3b4f8c"], ["Mundo de máquinas", "Automatización y fábricas", "64 mods · 1.20.1", 64, "#d98a1f"], ["Supervivencia suave", "Vanilla+ con pequeñas mejoras", "12 mods · 1.21.4", 12, "#3f9b57"]];
  var NEWS = [["1.17.1", "Perfil de rendimiento al editar una instancia, y Salud con avisos más claros."], ["1.16.0", "Nova en inglés, Java automático y diagnóstico de cierres con botón Corregir."], ["1.15.0", "Interfaz nueva, portal al elegir juego y ajustes de animaciones."], ["1.14.1", "Editor de skins con vista previa 3D y pantalla de inicio al jugar."]];
  var PUB = [["Mundo de ejemplo", "juega.ejemplo.test", "Vanilla 1.21.4", "28 ms", "12 jugadores"], ["Aventuras de prueba", "aventura.ejemplo.test", "Paper 1.21.11", "41 ms", "5 jugadores"], ["Creativo abierto", "creativo.ejemplo.test", "Fabric 1.21.1", "35 ms", "0 jugadores"]];
  var SESSIONS = [["Hoy", "Supervivencia", "1 h 12 min"], ["Ayer", "Create Nova", "48 min"], ["Hace 3 días", "Servidor de amigos", "2 h 05 min"], ["Hace 6 días", "Supervivencia", "3 h 20 min"]];
  var FINDINGS = [
    { sev: "confirmado", cls: "err", mod: "Iris Shaders", title: "Pide una versión de Sodium más nueva", reason: "Iris 1.8.0 necesita Sodium 0.6.5 o superior y esta instancia tiene 0.6.2.", fix: "Actualizá Sodium desde Mods.", act: "upd" },
    { sev: "posible", cls: "warm", mod: "Sound Physics", title: "Puede chocar con otro mod de sonido", reason: "Dos mods cambian el mismo motor de audio. Nova no lo pudo comprobar.", fix: "Si el juego se cierra al sonar algo, desactivalo.", act: "off", file: "sound-physics-1.4.9.jar" },
    { sev: "aviso", cls: "", mod: "Java", title: "Se usará el Java 21 de Nova", reason: "Es el que pide Minecraft 1.21.11; no hay que instalar nada.", fix: "Nada que hacer." }
  ];
  var GAMES = [
    ["Carrera de autos", "18,4 mil jugando · 91 % positivo", "#c0392b,#e8913a", "🏎", "t m"], ["Mi granja", "9,1 mil jugando · 88 % positivo", "#3f9b57,#9bd16a", "🌾", "t g"], ["Torre de obstáculos", "22,7 mil jugando · 94 % positivo", "#6a4fc0,#d96fb0", "🗼", "t m e"],
    ["Pizzería tycoon", "5,6 mil jugando · 86 % positivo", "#d98a1f,#f2cf6b", "🍕", "t m"], ["Escape del laberinto", "12,3 mil jugando · 90 % positivo", "#2a7fa8,#7fd6e8", "🌀", "t e g"], ["Isla de piratas", "7,8 mil jugando · 87 % positivo", "#a8553b,#e0ac86", "🏴", "t g r"],
    ["Ciudad en construcción", "3,1 mil jugando · 89 % positivo", "#3b4f8c,#8fd6e8", "🏙", "e r"], ["Duelo de espadas", "14,0 mil jugando · 92 % positivo", "#5a2a5a,#c0392b", "⚔", "m"]
  ];
  var RTABS = [["t", "Tendencias"], ["m", "Más jugados"], ["e", "Emergentes"], ["g", "En grupo"], ["f", "Favoritos"], ["r", "Recientes"]];
  var FRIENDS = [["Fran", "#c0392b"], ["Lu", "#3f9b57"], ["Mati", "#6a4fc0"]];
  var PALETTE = ["#e0ac86", "#c98e66", "#8a5a3c", "#3a2a22", "#f5d9bd", "#ffffff", "#c8ccd4", "#6f7480", "#1c1c24", "#3868c8", "#2a3f8f", "#44c7d6", "#5fd38a", "#2e7d4f", "#f2e06b", "#f2a93b", "#e0524d", "#8e5bd9", "#e96fb0", "#6b3a2a"];
  var STEPS = [["Preparar", "Preparando la instancia…"], ["Archivos", "Descargando recursos de Minecraft…"], ["Iniciar Java", "Iniciando Java 21…"], ["En juego", "¡Listo! Minecraft se abre."]];
  var PROFILES = { ahorro: 2, equilibrado: 4, maximo: 8 };

  var S = { game: "minecraft", view: "inst", prev: "inst", theme: "dark", speed: "medium", inst: 0, query: "", filter: "all", installed: {}, backups: [["Supervivencia · automático", "Hace 2 días · 412 MB"], ["Antes de actualizar mods", "Hace 6 días · 398 MB"]], restored: -1,
    fav: { 1: true }, rtab: "t", color: PALETTE[9], tool: "pen", sym: false, sk: 0, more: false, srv: "off", con: [], conOpen: false, health: "idle", off: {}, menu: false, imp: null, packs: {}, skin3: "classic", E: null };
  var K = { soft: 1.45, medium: 1, fast: 0.55, off: 0 };
  var ms = function (v) { return reduce ? 0 : v * K[S.speed]; };
  var done = {};

  /* Skins (16×16: figura de frente) */
  var G = 16;
  function makeSkin(hair, skin, shirt, pants, eye) {
    var g = []; for (var y = 0; y < G; y++) { g[y] = []; for (var x = 0; x < G; x++) g[y][x] = null; }
    var set = function (x0, y0, x1, y1, c) { for (var y = y0; y <= y1; y++) for (var x = x0; x <= x1; x++) g[y][x] = c; };
    set(5, 1, 10, 6, skin); set(5, 1, 10, 2, hair); set(5, 3, 5, 4, hair); set(10, 3, 10, 4, hair);
    g[4][6] = "#ffffff"; g[4][9] = "#ffffff"; g[4][7] = eye; g[4][8] = eye;
    set(5, 7, 10, 12, shirt); set(3, 7, 4, 12, shirt); set(11, 7, 12, 12, shirt); set(3, 11, 4, 12, skin); set(11, 11, 12, 12, skin); set(5, 13, 7, 15, pants); set(8, 13, 10, 15, pants);
    return g;
  }
  var SK = [{ n: "Caballero azul", g: makeSkin("#3a2a22", "#e0ac86", "#3868c8", "#2a3f8f", "#3868c8") }, { n: "Explorador", g: makeSkin("#6b3a2a", "#c98e66", "#2e7d4f", "#6f4a2a", "#3a2a22") }, { n: "Mago violeta", g: makeSkin("#c8ccd4", "#f5d9bd", "#8e5bd9", "#2a1f5a", "#8e5bd9") }];
  var grid = SK[0].g, undo = [], redo = [];

  /* Estructura fija */
  root.innerHTML =
    '<div class="dm-top"><span class="dm-brand"><img src="assets/nova.svg" width="20" height="20" alt=""> Nova Launcher</span>' +
    '<div class="dm-seg" role="tablist" aria-label="Elegí un juego"><span class="dm-pill" aria-hidden="true"></span>' +
    '<button type="button" role="tab" data-game="minecraft">Minecraft</button><button type="button" role="tab" data-game="roblox">Roblox</button></div>' +
    '<label class="dm-search">' + ico("search") + '<span class="vh">Buscar</span><input type="search" autocomplete="off"></label>' +
    '<button type="button" class="dm-user" data-view="set"><i></i>Alex ▾<span class="vh"> · Ajustes</span></button><span class="dm-wc" aria-hidden="true"><i></i><i></i><i></i></span></div>' +
    '<div class="dm-body"><nav class="dm-side" aria-label="Menú de la maqueta"></nav><main class="dm-main" tabindex="-1" aria-live="off"></main></div>' +
    '<div class="dm-status" role="status">Listo</div>' +
    '<div class="dm-launch" role="dialog" aria-modal="true" aria-label="Iniciando"><div class="dm-lcard"><div class="dm-lcover dm-cover"></div><div class="dm-orb">' + STAR + '<i></i></div>' +
    '<h4></h4><small></small><ol class="dm-steps"></ol><p class="dm-lmsg" role="status"></p><p class="dm-lfoot">Esto es una maqueta: en Nova se abre el juego de verdad.</p>' +
    '<button type="button" class="dm-btn ghost" data-close>Ocultar</button></div></div>' +
    '<div class="dm-modal" role="dialog" aria-modal="true" aria-label="Diálogo"><div class="dm-mcard"></div></div>';
  root.classList.add("dm"); root.setAttribute("data-theme", "dark"); root.setAttribute("data-speed", "medium");

  var $ = function (s) { return root.querySelector(s); };
  var side = $(".dm-side"), main = $(".dm-main"), search = $(".dm-search input"), pill = $(".dm-pill"), seg = $(".dm-seg"), launch = $(".dm-launch"), modal = $(".dm-modal"), mcard = $(".dm-mcard"), body = $(".dm-body"), statusEl = $(".dm-status");
  var timers = [], opener = null;
  var later = function (fn, t) { var id = setTimeout(fn, t); timers.push(id); return id; };
  var clearTimers = function () { timers.forEach(clearTimeout); timers = []; };
  function status(t) { statusEl.textContent = t || "Listo"; }
  function mark(key) { if (done[key]) return; done[key] = 1; var b = document.querySelector('[data-try="' + key + '"]'); if (b) b.classList.add("done"); }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  var cur = function () { return INSTANCES[S.inst]; };
  var cover = function (x, cls) { return '<span class="' + cls + ' dm-cover" style="filter:' + x.f + ";background-position:" + x.pos + '"></span>'; };
  var btn = function (cls, a, label, extra) { return '<button type="button" class="dm-btn ' + cls + '" data-a="' + a + '"' + (extra || "") + ">" + label + "</button>"; };
  var back = function (to) { return '<button type="button" class="dm-back" data-a="go" data-v="' + to + '">' + ico("back") + "Volver</button>"; };

  function movePill() { var on = seg.querySelector("button.on"); if (!on) return; pill.style.width = on.offsetWidth + "px"; pill.style.transform = "translateX(" + on.offsetLeft + "px)"; }
  function drawSide() {
    var act = ALIAS[S.view] || S.view, html = "";
    NAV.forEach(function (n) {
      if (n.length === 1) html += "<h4>" + n[0] + "</h4>";
      else html += '<button type="button" class="dm-nav' + (act === n[0] ? " on" : "") + '" data-view="' + n[0] + '"' + (act === n[0] ? ' aria-current="page"' : "") + ">" + ico(n[2]) + n[1] + "</button>";
    });
    var inMore = MORE.some(function (m) { return m[0] === act; }), open = S.more || inMore;
    html += '<button type="button" class="dm-nav" data-a="more" aria-expanded="' + open + '">' + ico("dots") + "Más</button><div class=\"dm-sub-nav" + (open ? " open" : "") + '">' +
      MORE.map(function (m) { return '<button type="button" class="dm-nav' + (act === m[0] ? " on" : "") + '" data-view="' + m[0] + '"' + (open ? "" : ' tabindex="-1"') + ">" + ico(m[2]) + m[1] + "</button>"; }).join("") + "</div>";
    html += '<div class="dm-me"><img src="assets/nova.svg" width="30" height="30" alt=""><span><b>Nova 1.17.1</b><small>Al día</small></span><button type="button" data-view="set" class="' + (S.view === "set" ? "on" : "") + '" aria-label="Ajustes">' + ico("gear") + "</button></div>";
    side.innerHTML = html;
  }
  function setGameUI() {
    seg.querySelectorAll("button").forEach(function (b) { var on = b.dataset.game === S.game; b.classList.toggle("on", on); b.setAttribute("aria-selected", on); });
    body.classList.toggle("solo", S.game === "roblox");
    var ph = S.game === "roblox" ? "Buscar un juego o pegar un enlace de Roblox" : S.view === "explore" || S.view === "curse" ? "Buscar mods" : S.view === "packs" ? "Buscar modpacks" : "Buscar instancias";
    search.placeholder = ph; search.setAttribute("aria-label", ph);
    movePill();
  }

  /* Vistas */
  var V = {};
  V.inst = function () {
    {
      var c = cur(), q = S.query.toLowerCase(), total = INSTANCES.reduce(function (a, x) { return a + x.min; }, 0);
      var list = INSTANCES.map(function (x, i) { return [x, i]; }).filter(function (p) { return (!q || p[0].name.toLowerCase().indexOf(q) >= 0) && (S.filter === "all" || p[0].loader.toLowerCase().indexOf(S.filter) === 0); });
      return '<div class="dm-head"><div><h3>Mis instancias</h3><p class="dm-sub">' + INSTANCES.length + " instancias · " + fmt(total) + " jugadas</p></div><div>" +
        btn("", "go", ico("folder") + "Importar", ' data-v="import"') + btn("pri", "new", ico("plus") + "Nueva instancia") + "</div></div>" +
        '<div class="dm-strip"><div><small>Última partida</small><b>' + esc(c.name) + " · " + (done.play ? "hace un momento" : "hace 2 días") + "</b></div><div><small>Descargas</small><b>Sin descargas</b></div><div><small>Cuenta</small><b>Cuenta offline · Alex</b></div><div><small>Nova</small><b>Al día</b></div></div>" +
        '<section class="dm-hero' + (S.swap ? " swap" : "") + '" aria-label="Instancia elegida">' + cover(c, "art") + "<div>" + (c.fav ? '<span class="dm-chip dark">★ Favorita</span>' : "") + "<h3>" + esc(c.name) + '</h3><div class="dm-tags"><span class="dm-chip acc">' + c.v + '</span><span class="dm-chip">' + esc(c.loader) + '</span><span class="dm-chip">' + c.ram + ' GB</span><span class="dm-chip dark">◷ ' + fmt(c.min) + "</span></div>" +
        '<div class="dm-acts">' + btn("play", "play", ico("play") + "Jugar") + btn("", "edit", "Editar") + btn("", "go", "Servidores", ' data-v="servers"') + btn("more", "menu", ico("dots"), ' aria-label="Más acciones" aria-haspopup="menu" aria-expanded="' + S.menu + '"') +
        (S.menu ? '<div class="dm-menu" role="menu"><button role="menuitem" data-a="go" data-v="mods">Mods y actualizaciones</button><button role="menuitem" data-a="go" data-v="health">Salud y mods</button><button role="menuitem" data-a="backup">Crear respaldo</button><button role="menuitem" data-a="favtog">' + (c.fav ? "Quitar de favoritas" : "Marcar como favorita") + "</button></div>" : "") + "</div></div></section>" +
        '<h4 class="sec">Contenido</h4><div class="dm-shelf"><div class="dm-tile"><button type="button" class="body" data-a="go" data-v="mods"><div><small>Mods</small><b>' + c.mods + "<span>instalados</span></b></div></button><footer><button type=\"button\" data-a=\"go\" data-v=\"explore\">Explorar</button><button type=\"button\" data-a=\"go\" data-v=\"import\">Importar</button></footer></div>" +
        '<div class="dm-tile"><div><small>Shaders</small><b>' + c.shaders + "<span>" + (c.shaders === 1 ? "instalado" : "instalados") + '</span></b></div><footer><button type="button" data-a="go" data-v="explore">Explorar</button><button type="button" data-a="go" data-v="import">Importar</button></footer></div>' +
        '<div class="dm-tile"><div><small>Texturas</small><b>' + c.tex + "<span>" + (c.tex === 1 ? "instalada" : "instaladas") + '</span></b></div><footer><button type="button" data-a="go" data-v="explore">Explorar</button><button type="button" data-a="go" data-v="import">Importar</button></footer></div>' +
        '<div class="dm-tile"><div><small>Tiempo jugado</small><b>' + fmt(c.min) + "</b></div></div></div>" +
        '<div class="dm-bar"><h4>Tus instancias</h4><select class="dm-select" data-f="filter" aria-label="Filtrar por cargador"><option value="all">Todas</option><option value="fabric">Fabric</option><option value="forge">Forge</option><option value="neoforge">NeoForge</option><option value="vanilla">Vanilla</option></select></div>' +
        '<div class="dm-grid">' + (list.length ? list.map(function (p) {
          return '<button type="button" class="dm-card' + (p[1] === S.inst ? " on" : "") + '" data-a="inst" data-i="' + p[1] + '" aria-pressed="' + (p[1] === S.inst) + '">' + cover(p[0], "th") + '<span class="tx"><b>' + esc(p[0].name) + "</b><small>" + p[0].v + " · " + esc(p[0].loader) + "</small></span></button>";
        }).join("") : '<p class="dm-empty">Ninguna instancia coincide.</p>') + "</div>";
    }
  };
  V.mods = function () {
    var c = cur(), n = Math.min(c.mods, MODLIST.length), pend = MODLIST.slice(0, n).filter(function (m) { return m.nw; }).length;
    return back("inst") + '<div class="dm-head"><div><h3>Mods de ' + esc(c.name) + '</h3><p class="dm-sub">' + c.mods + " instalados" + (pend ? " · " + pend + " con actualización" : " · todos al día") + (c.mods > n ? ". Se muestran " + n + " de ejemplo." : "") + "</p></div><div>" +
      btn("", "go", "Salud", ' data-v="health"') + btn("pri", "upd", pend ? "Revisar actualizaciones" : "Buscar actualizaciones") + "</div></div>" +
      (n ? '<div class="dm-list">' + MODLIST.slice(0, n).map(function (m, i) {
        var open = S.msel === i;
        return '<div class="dm-row"><span class="ic" style="background:linear-gradient(135deg,' + m.c + ',#8fd6e8)"></span><button type="button" class="tx" data-a="mdet" data-i="' + i + '" aria-expanded="' + open + '"><b>' + m.n + "</b><small>" + m.cur + "</small></button>" + (m.nw ? '<span class="dm-chip warm">→ ' + m.nw + "</span>" : '<span class="dm-chip good">Al día</span>') +
          '<button type="button" class="dm-sw" role="switch" aria-checked="' + m.on + '" aria-label="' + m.n + ' activado" data-a="sw" data-i="' + i + '"></button></div>' +
          (open ? '<div class="dm-mdet"><span><small>Versión</small><b>' + m.cur + "</b></span><span><small>Cargador</small><b>" + esc(c.loader) + "</b></span><span><small>Estado</small><b>" + (m.on ? "Activado" : "Desactivado") + (m.nw ? " · hay " + m.nw : " · al día") + "</b></span>" + btn("sm", "mtog", m.on ? "Desactivar" : "Activar", ' data-i="' + i + '"') + "</div>" : "");
      }).join("") + "</div>" : '<p class="dm-empty">Esta instancia no tiene mods.</p>');
  };
  V.health = function () {
    var run = S.health === "run", fs = FINDINGS.filter(function (f) { return !S.off[f.mod]; });
    return back("inst") + '<div class="dm-head"><div><h3>Salud de la instancia</h3><p class="dm-sub">Nova lee los metadatos de cada mod y revisa la instalación. Solo avisa de problemas que puede comprobar; no cambia nada sin que lo confirmes.</p></div><div>' + btn("", "reheal", "Volver a analizar") + "</div></div>" +
      '<p class="dm-sub" role="status" style="margin:0 0 12px">' + (run ? "Analizando…" : fs.length + " resultados · " + fs.filter(function (f) { return f.cls === "err"; }).length + " confirmado") + "</p>" +
      (run ? '<div class="dm-prog"><i style="width:' + (S.hp || 0) + '%"></i></div>' : '<div class="dm-list">' + fs.map(function (f, i) {
        return '<div class="dm-row" style="align-items:flex-start;flex-direction:column;gap:6px"><div style="display:flex;gap:10px;align-items:center;width:100%"><span class="tx"><b>' + f.mod + "</b><small>" + f.title + '</small></span><span class="dm-chip ' + f.cls + '">' + f.sev[0].toUpperCase() + f.sev.slice(1) + "</span></div><small>" + f.reason + "</small><small><b style=\"display:inline\">Solución:</b> " + f.fix + "</small>" +
          (f.act === "off" ? btn("sm", "off", "Desactivar " + f.file, ' data-m="' + f.mod + '"') : f.act === "upd" ? btn("sm", "upd", "Actualizar mods") : "") + "</div>";
      }).join("") + "</div>");
  };
  V.edit = function () {
    var E = S.E;
    var row = function (t, h, ctl) { return '<div class="dm-row"><span class="tx"><b>' + t + "</b>" + (h ? "<small>" + h + "</small>" : "") + '</span><span class="ctl">' + ctl + "</span></div>"; };
    return back("inst") + '<div class="dm-form"><h3 style="font-size:1.6rem">Editar instancia</h3><p class="dm-sub">Nombre, versión, memoria y portada de esta instancia.</p>' +
      '<h4 class="cap">Instancia</h4><div class="dm-list">' + row("Nombre", "", '<input class="dm-field" data-f="name" value="' + esc(E.name) + '" aria-label="Nombre">') + row("Nota", "Un recordatorio corto. Se ve debajo del banner.", '<input class="dm-field" data-f="note" placeholder="Ej. Mundo cooperativo con amigos" value="' + esc(E.note) + '" aria-label="Nota">') +
      row("Portada", "Se ve en la biblioteca y en el banner.", '<span class="dm-card" style="width:130px;flex:none;pointer-events:none">' + cover(cur(), "th") + '</span><span style="display:grid;gap:6px">' + btn("sm", "say", "Elegir imagen", ' data-t="Esto abre el selector de archivos en la app real."') + btn("sm ghost", "say", "Usar la original", ' data-t="Se vuelve a la portada original."') + "</span>") + "</div>" +
      '<h4 class="cap">Minecraft</h4><div class="dm-list">' + row("Cliente", "", '<select class="dm-select" aria-label="Cliente"><option>Java (Minecraft normal)</option></select>') + row("Versión de Minecraft", "Esta instancia tiene mods o mundos: la versión no se puede cambiar.", '<select class="dm-select" disabled aria-label="Versión"><option>' + cur().v + "</option></select>") + "</div>" +
      '<h4 class="cap">Rendimiento</h4><div class="dm-list">' + row("Memoria máxima", "En GB. Los modpacks grandes suelen pedir 6 u 8.", '<input class="dm-field" type="number" min="1" max="32" data-f="memMax" value="' + E.memMax + '" aria-label="Memoria máxima en GB">') +
      row("Memoria mínima", "En GB. 0 deja que Java decida.", '<input class="dm-field" type="number" min="0" max="32" data-f="memMin" value="' + E.memMin + '" aria-label="Memoria mínima en GB">') +
      row("Perfil de rendimiento", "Rellena la memoria y los argumentos de Java; después podés ajustarlos.", '<select class="dm-select" data-f="profile" aria-label="Perfil de rendimiento">' + [["manual", "Manual"], ["ahorro", "Ahorro"], ["equilibrado", "Equilibrado"], ["maximo", "Máximo"]].map(function (o) { return '<option value="' + o[0] + '"' + (E.profile === o[0] ? " selected" : "") + ">" + o[1] + "</option>"; }).join("") + "</select>") +
      row("Argumentos de Java", "Solo para quien sabe qué hace cada uno.", '<input class="dm-field" data-f="jvm" value="' + esc(E.jvm) + '" aria-label="Argumentos de Java" spellcheck="false">') + "</div>" +
      '<div class="dm-btns" style="justify-content:flex-end;margin-top:20px">' + btn("", "go", "Cancelar", ' data-v="inst"') + btn("pri", "save", "Guardar") + "</div></div>";
  };
  V.news = function () {
    return '<div class="dm-head"><div><h3>Novedades</h3><p class="dm-sub">Lo último de Nova</p></div></div><div class="dm-list">' + NEWS.map(function (n) { return '<div class="dm-row"><span class="tx"><b>Versión ' + n[0] + "</b><small>" + n[1] + "</small></span></div>"; }).join("") + "</div>";
  };
  function catalog(src) {
    var q = S.query.toLowerCase(), items = CAT[src].filter(function (m) { return !q || m[0].toLowerCase().indexOf(q) >= 0 || m[1].toLowerCase().indexOf(q) >= 0; });
    return '<div class="dm-head"><div><h3>' + (src === "Modrinth" ? "Explorar" : "CurseForge") + '</h3><p class="dm-sub">Mods para ' + esc(cur().name) + ' · catálogo de ejemplo</p></div></div><div class="dm-grid">' + (items.length ? items.map(function (m) {
      var key = src + m[0], st = S.installed[key];
      return '<div class="dm-card" style="cursor:default"><span class="th" style="background:linear-gradient(135deg,' + m[3] + ',#8fd6e8)"></span><span class="tx"><b>' + esc(m[0]) + "</b><small>" + esc(m[1]) + '</small><span style="display:flex;justify-content:space-between;align-items:center;margin-top:10px"><span class="dm-chip">' + m[2] + "</span>" +
        '<button type="button" class="dm-btn sm' + (st === 2 ? " ok" : "") + '" data-a="install" data-k="' + esc(key) + '"' + (st ? " disabled" : "") + ">" + (st === 2 ? "✓ Instalado" : st === 1 ? "Instalando…" : "Instalar") + "</button></span></span></div>";
    }).join("") : '<p class="dm-empty">No hay resultados para «' + esc(S.query) + "».</p>") + "</div>";
  }
  V.explore = function () { return catalog("Modrinth"); };
  V.curse = function () { return catalog("CurseForge"); };
  V.packs = function () {
    var q = S.query.toLowerCase();
    return '<div class="dm-head"><div><h3>Modpacks</h3><p class="dm-sub">Cada modpack se instala como una instancia nueva.</p></div></div><div class="dm-list">' + PACKS.filter(function (p) { return !q || p[0].toLowerCase().indexOf(q) >= 0; }).map(function (p, i) {
      var st = S.packs[p[0]];
      return '<div class="dm-row"><span class="ic" style="background:linear-gradient(135deg,' + p[4] + ',#8fd6e8)"></span><span class="tx"><b>' + p[0] + "</b><small>" + p[1] + " · " + p[2] + '</small></span><button type="button" class="dm-btn sm' + (st === 2 ? " ok" : "") + '" data-a="pack" data-i="' + i + '"' + (st ? " disabled" : "") + ">" + (st === 2 ? "✓ Instancia creada" : st === 1 ? "Instalando…" : "Instalar") + "</button></div>";
    }).join("") + "</div>";
  };
  V.import = function () {
    var imp = S.imp, files = [["mejoras-visuales.mrpack", "Modpack", "38 MB", 1], ["texturas-16x.zip", "Texturas", "12 MB", 1], ["mapa-aventura.zip", "Mundo", "85 MB", 1], ["ajustes.dat", "No reconocido", "2 KB", 0]];
    return '<div class="dm-head"><div><h3>Importar</h3><p class="dm-sub">Soltá archivos acá: Nova los revisa antes de tocar nada.</p></div></div>' +
      (!imp ? '<div class="dm-drop"><b>Soltá tus archivos acá</b><small>Modpacks, mods, shaders, texturas y mundos</small><span style="margin-top:12px">' + btn("pri", "imp", "Usar archivos de ejemplo") + "</span></div>"
        : '<div class="dm-list">' + files.map(function (f, i) {
          return '<label class="dm-ck"><input type="checkbox" data-f="imp" data-i="' + i + '"' + (f[3] ? (imp[i] ? " checked" : "") : " disabled") + '><span class="tx" style="flex:1"><b>' + f[0] + "</b><small>" + f[1] + " · " + f[2] + (f[3] ? "" : " · no se importa: Nova no sabe qué es este archivo") + "</small></span>" + (f[3] ? "" : '<span class="dm-chip warm">Rechazado</span>') + "</label>";
        }).join("") + "</div>" + '<div class="dm-btns" style="justify-content:flex-end;margin-top:14px">' + btn("", "impx", "Cancelar") + btn("pri", "impgo", "Importar " + imp.filter(Boolean).length + " archivos", imp.some(Boolean) ? "" : " disabled") + "</div>");
  };
  V.skins = function () {
    return '<div class="dm-head"><div><h3>Skins</h3><p class="dm-sub">Perfil · Alex</p></div><div>' + btn("", "say", "Importar PNG", ' data-t="Importar PNG abre el selector de archivos en la app real."') + btn("", "say", "Exportar PNG", ' data-t="Exportar PNG guarda la skin en tu carpeta."') + "</div></div>" +
      '<div class="dm-sk"><div class="dm-box"><h4>Mis skins</h4><div class="dm-skl">' + SK.map(function (s, i) { return '<button type="button" data-a="skin" data-i="' + i + '" class="' + (i === S.sk ? "on" : "") + '"><canvas width="16" height="16" data-th="' + i + '"></canvas>' + s.n + "</button>"; }).join("") + "</div>" +
      btn("", "say", "Nueva", ' data-t="Se crea una skin en blanco."') + btn("pri", "say", "Guardar", ' data-t="Skin guardada en tu biblioteca."') + "</div>" +
      '<div class="dm-box"><div class="dm-tools" role="group" aria-label="Herramientas">' + [["pen", "Lápiz"], ["erase", "Borrar"], ["pick", "Gotero"], ["fill", "Relleno"]].map(function (t) { return '<button type="button" class="dm-btn' + (S.tool === t[0] ? " ok" : "") + '" data-tool="' + t[0] + '" aria-pressed="' + (S.tool === t[0]) + '">' + t[1] + "</button>"; }).join("") +
      '<button type="button" class="dm-btn' + (S.sym ? " ok" : "") + '" data-a="sym" aria-pressed="' + S.sym + '">Simetría</button><button type="button" class="dm-btn" data-a="undo"' + (undo.length ? "" : " disabled") + '>Deshacer</button><button type="button" class="dm-btn" data-a="redo"' + (redo.length ? "" : " disabled") + ">Rehacer</button></div>" +
      '<canvas class="dm-cv" width="16" height="16" aria-label="Lienzo para pintar tu skin"></canvas><div class="dm-pal" role="group" aria-label="Paleta">' + PALETTE.map(function (c) { return '<button type="button" data-color="' + c + '" style="background:' + c + '" aria-label="Color ' + c + '"' + (c === S.color ? ' class="on"' : "") + "></button>"; }).join("") + "</div></div>" +
      '<div class="dm-box"><h4>Vista previa</h4><div class="dm-3d"><canvas width="16" height="16" tabindex="0" aria-label="Vista previa en 3D: arrastrá o usá las flechas para girarla"></canvas></div><p class="dm-hint">Arrastrá para girarla</p>' +
      '<div class="dm-two"><button type="button" class="dm-btn" data-a="rot" data-d="-45" aria-label="Girar a la izquierda">‹</button><button type="button" class="dm-btn" data-a="rot" data-d="0">De frente</button></div><div class="dm-two" style="margin-top:8px"><button type="button" class="dm-btn" data-a="rot" data-d="45" aria-label="Girar a la derecha">›</button><button type="button" class="dm-btn' + (S.skin3 === "slim" ? " ok" : "") + '" data-a="slim" aria-pressed="' + (S.skin3 === "slim") + '">' + (S.skin3 === "slim" ? "Delgado" : "Clásico") + "</button></div>" +
      '<p class="dm-hint" style="margin:12px 0 0">Se equipa a Alex en «' + esc(cur().name) + '».</p>' + btn("pri", "equip", "Equipar") + "</div></div>";
  };
  V.servers = function () {
    return '<div class="dm-head"><div><h3>Servidores</h3><p class="dm-sub">Servidores de ejemplo para unirte con «' + esc(cur().name) + '».</p></div></div><div class="dm-list">' + PUB.map(function (s, i) {
      return '<div class="dm-row"><span class="ic" style="background:linear-gradient(135deg,#2e6b4f,#5fd38a)"></span><span class="tx"><b>' + s[0] + "</b><small>" + s[1] + " · " + s[2] + " · " + s[3] + " · " + s[4] + "</small></span>" + btn("sm", "join", "Unirse", ' data-i="' + i + '"') + "</div>";
    }).join("") + "</div>";
  };
  V.myserver = function () {
    var on = S.srv === "on", boot = S.srv === "boot";
    return '<div class="dm-head"><div><h3>Mi servidor</h3><p class="dm-sub">Servidores de Minecraft Java que corren en este equipo. Gratis y sin cuentas.</p></div><div>' + btn("", "say", "Importar servidor", ' data-t="Importar servidor trae uno que ya tenías."') + btn("pri", "say", "Crear servidor", ' data-t="Crear servidor te deja elegir Vanilla, Paper, Fabric o Forge."') + "</div></div>" +
      '<div class="dm-notice">' + ico("server") + "<span>Estos servidores son locales: corren en tu computadora, no en la nube. Solo están disponibles mientras tu PC esté encendida y el servidor prendido, y gastan memoria y procesador mientras juegan.</span></div>" +
      '<div class="dm-list" style="margin-top:16px"><div class="dm-row"><span class="tx"><b>Mundo de ejemplo</b><small>Paper (plugins) · 1.21.11 · puerto 25565 · 4 GB</small></span><span class="dm-chip ' + (on ? "acc" : boot ? "warm" : "") + '">' + (on ? "Encendido" : boot ? "Iniciando…" : "Apagado") + "</span>" +
      btn("sm", "srv", on ? "Apagar" : "Encender", boot ? " disabled" : "") + btn("sm", "con", S.conOpen ? "Cerrar" : "Abrir", ' aria-expanded="' + S.conOpen + '"') + "</div></div>" +
      (S.conOpen ? '<div class="dm-con" role="log" aria-label="Consola del servidor">' + (S.con.length ? S.con.map(function (l) { return "<p>" + l + "</p>"; }).join("") : "<p>El servidor está apagado.</p>") + "</div>" : "");
  };
  V.backups = function () {
    return '<div class="dm-head"><div><h3>Respaldos</h3><p class="dm-sub">Cada copia se verifica con SHA-256 antes de restaurarla.</p></div><div>' + btn("pri", "backup", ico("plus") + "Crear respaldo") + "</div></div><div class=\"dm-list\">" +
      S.backups.map(function (b, i) {
        return '<div class="dm-row' + (b.fresh ? " dm-flash" : "") + '"><span class="ic" style="background:linear-gradient(135deg,#3b4f8c,#8fd6e8)"></span><span class="tx"><b>' + esc(b[0]) + "</b><small>" + esc(b[1]) + "</small>" + (b.pend ? '<div class="dm-prog"><i style="width:' + (b.w || 0) + '%"></i></div>' : "") + "</span>" +
          (b.pend ? '<span class="dm-chip warm">Copiando…</span>' : '<span class="dm-chip good">Verificado</span>' + btn("sm" + (S.restored === i ? " ok" : ""), "restore", S.restored === i ? "✓ Restaurado como instancia nueva" : "Restaurar", ' data-i="' + i + '"')) + "</div>";
      }).join("") + "</div>";
  };
  V.sessions = function () {
    return '<div class="dm-head"><div><h3>Sesiones</h3><p class="dm-sub">Tus partidas recientes, de ejemplo.</p></div></div><div class="dm-list">' + SESSIONS.map(function (s) { return '<div class="dm-row"><span class="tx"><b>' + s[1] + "</b><small>" + s[0] + '</small></span><span class="dm-chip">' + s[2] + "</span></div>"; }).join("") + "</div>";
  };
  V.stats = function () {
    var max = Math.max.apply(null, INSTANCES.map(function (x) { return x.min; }));
    return '<div class="dm-head"><div><h3>Estadísticas</h3><p class="dm-sub">Tiempo jugado por instancia (datos de ejemplo).</p></div></div><div class="dm-bars">' + INSTANCES.map(function (x) { return "<div><span>" + esc(x.name) + '</span><span class="tr"><i style="width:' + Math.round(x.min / max * 100) + '%"></i></span><span>' + fmt(x.min) + "</span></div>"; }).join("") + "</div>";
  };
  V.set = function () {
    var seg2 = function (name, opts, c) { return '<div class="dm-seg flat" role="group">' + opts.map(function (o) { return '<button type="button" class="' + (o[0] === c ? "on" : "") + '" data-set="' + name + '" data-val="' + o[0] + '" aria-pressed="' + (o[0] === c) + '">' + o[1] + "</button>"; }).join("") + "</div>"; };
    return back(S.prev) + '<div class="dm-head"><div><h3>Ajustes</h3><p class="dm-sub">Se aplican al instante, como en Nova.</p></div></div><div class="dm-list">' +
      '<div class="dm-row"><span class="tx"><b>Apariencia</b><small>Tema oscuro o claro.</small></span>' + seg2("theme", [["dark", "Oscuro"], ["light", "Claro"]], S.theme) + "</div>" +
      '<div class="dm-row" style="flex-wrap:wrap"><span class="tx"><b>Animaciones</b><small>Lentas: más fluidas. Rápidas: casi instantáneas. Apagadas: sin movimiento.</small></span>' + seg2("speed", [["soft", "Lentas"], ["medium", "Normales"], ["fast", "Rápidas"], ["off", "Apagadas"]], S.speed) + "</div></div>";
  };
  V.games = function () {
    var q = S.query.toLowerCase(), t = S.rtab;
    var items = GAMES.map(function (g, i) { return [g, i]; }).filter(function (p) { return (!q || p[0][0].toLowerCase().indexOf(q) >= 0) && (t === "f" ? S.fav[p[1]] : (" " + p[0][4] + " ").indexOf(" " + t + " ") >= 0 || q); });
    return '<div class="dm-head"><div><h3>Roblox</h3><p class="dm-sub">Se abre con Sober. La primera vez iniciás sesión ahí.</p></div></div>' +
      '<div class="dm-hello"><i></i><span class="tx"><b>Hola, Alex</b><small>@alex_demo · Nova solo ve tu nombre y tu avatar</small></span>' + btn("sm", "say", "Cerrar sesión", ' data-t="En la maqueta no hay sesión real."') + "</div>" +
      '<h4 class="sec" style="margin-bottom:6px">Amigos</h4><div class="dm-friends">' + FRIENDS.map(function (f) { return '<button type="button" data-friend="' + f[0] + '"><i style="background:' + f[1] + '">' + f[0][0] + "</i>" + f[0] + "</button>"; }).join("") + '<button type="button" class="add" data-a="say" data-t="Agregar amigos se hace con su nombre de usuario."><i>+</i>Agregar</button></div>' +
      '<div class="dm-tabs" role="tablist" aria-label="Listas de juegos">' + RTABS.map(function (r) { return '<button type="button" role="tab" aria-selected="' + (r[0] === t) + '" class="' + (r[0] === t ? "on" : "") + '" data-rtab="' + r[0] + '">' + r[1] + "</button>"; }).join("") + "</div>" +
      '<div class="dm-games">' + (items.length ? items.map(function (p) {
        var g = p[0];
        return '<div class="dm-game"><div class="th" style="background:linear-gradient(135deg,' + g[2] + ')">' + g[3] + '</div><button type="button" class="star' + (S.fav[p[1]] ? " on" : "") + '" data-fav="' + p[1] + '" aria-label="Favorito: ' + esc(g[0]) + '" aria-pressed="' + !!S.fav[p[1]] + '">' + (S.fav[p[1]] ? "★" : "☆") + "</button><b>" + g[0] + "</b><small>" + g[1] + '</small><button type="button" class="dm-btn" data-playr="' + p[1] + '">Jugar</button></div>';
      }).join("") : '<p class="dm-empty">' + (t === "f" ? "Marcá una ☆ y aparece acá." : "Ningún juego coincide con «" + esc(S.query) + "».") + "</p>") + "</div>";
  };
  V.fav = V.games;

  function show(still) {
    var y = main.scrollTop;
    main.innerHTML = '<div class="dm-view' + (still ? " still" : "") + '">' + (V[S.view] || V.inst)() + "</div>";
    main.scrollTop = still ? y : 0;
    var f = main.querySelector('[data-f="filter"]'); if (f) f.value = S.filter;
    if (S.view === "skins") initSkin();
    if (S.view === "health" && S.health === "idle") runHealth();
  }
  function goView(v, still) {
    if (v === "set") S.prev = S.view === "set" ? S.prev : S.view;
    if (v === "edit") { var c = cur(); S.E = { name: c.name, note: "", memMax: c.ram, memMin: 0, profile: "manual", jvm: "" }; }
    if (v === "health") S.health = "idle";
    S.view = v; S.query = ""; S.menu = false; search.value = ""; setGameUI(); drawSide(); show(still);
    if (!still && v !== "skins") main.focus({ preventScroll: true });
  }
  function runHealth() {
    S.health = "run"; S.hp = 0;
    var bar = function () { var i = main.querySelector(".dm-prog i"); if (i) i.style.width = S.hp + "%"; };
    show(true); requestAnimationFrame(function () { S.hp = 100; bar(); });
    later(function () { S.health = "done"; if (S.view === "health") show(true); }, ms(900) || 1);
  }

  /* Portal al cambiar de juego */
  function switchGame(game, ev) {
    if (game === S.game) return;
    var rect = root.getBoundingClientRect(), x = ev && ev.clientX ? ev.clientX - rect.left : rect.width / 2, y = ev && ev.clientY ? ev.clientY - rect.top : 40, swapped = false;
    var swap = function () { if (swapped) return; swapped = true; S.game = game; S.view = game === "roblox" ? "games" : "inst"; S.query = ""; S.menu = false; search.value = ""; setGameUI(); drawSide(); show(); };
    var t = ms(560);
    if (!t || !root.animate) { swap(); return; }
    var p = document.createElement("div"); p.className = "dm-portal"; p.style.background = game === "roblox" ? "#c0392b" : "#3f9b57"; root.appendChild(p);
    var rr = Math.hypot(rect.width, rect.height) + 40, end = function () { swap(); p.remove(); };
    p.animate([{ clipPath: "circle(0px at " + x + "px " + y + "px)" }, { clipPath: "circle(" + rr + "px at " + x + "px " + y + "px)" }], { duration: t * 0.55, easing: "cubic-bezier(0.55, 0, 0.3, 1)", fill: "forwards" }).onfinish = function () {
      swap(); p.animate([{ opacity: 1 }, { opacity: 0 }], { duration: t * 0.55, easing: "ease-out", fill: "forwards" }).onfinish = end;
    };
    setTimeout(end, t * 1.5 + 400);   // red de seguridad: si el navegador pausa las animaciones (pestaña oculta), igual cambia
  }

  /* Diálogos (lanzamiento y modal) con foco atrapado y Escape */
  var focusables = function (el) { return Array.prototype.filter.call(el.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled])'), function (n) { return n.offsetParent !== null; }); };
  function openLayer(layer, first) { opener = document.activeElement; layer.classList.remove("on"); void layer.offsetWidth; layer.classList.add("on"); later(function () { var f = first || focusables(layer)[0]; if (f) f.focus({ preventScroll: true }); }, 30); }
  function closeLayer(layer) { if (!layer.classList.contains("on")) return; layer.classList.remove("on"); if (opener && opener.isConnected) opener.focus({ preventScroll: true }); }
  function startLaunch(title, sub, steps, x) {
    clearTimers();
    var card = launch.querySelector(".dm-lcard"), cv = card.querySelector(".dm-lcover");
    cv.style.cssText = x && x.f ? "filter:" + x.f + ";background-position:" + x.pos : x ? "background-image:linear-gradient(135deg," + x + ")" : "";
    card.querySelector("h4").textContent = title; card.querySelector("small").textContent = sub;
    var ol = card.querySelector("ol"); ol.innerHTML = steps.map(function (s) { return "<li><i>✓</i>" + s[0] + "</li>"; }).join("");
    var lis = ol.querySelectorAll("li"), msg = card.querySelector(".dm-lmsg");
    msg.textContent = ""; openLayer(launch);
    var step = function (i) {
      if (i > 0) lis[i - 1].className = "ok";
      if (i >= lis.length) { msg.textContent = steps[steps.length - 1][1]; status(title + " se abrió."); return; }
      lis[i].className = i === lis.length - 1 ? "ok" : "now"; msg.textContent = steps[i][1];
      later(function () { step(i + 1); }, ms(850) || 1);
    };
    status("Iniciando " + title + "…");
    later(function () { step(0); }, ms(700) || 1);
  }
  function stopLaunch() { clearTimers(); closeLayer(launch); }
  function openModal(html, first) { mcard.innerHTML = html; openLayer(modal, first && mcard.querySelector(first)); }
  function closeModal() { closeLayer(modal); }

  function openUpdates() {
    var n = Math.min(cur().mods, MODLIST.length), pend = MODLIST.slice(0, n).filter(function (m) { return m.nw; });
    if (!pend.length) { status("Todo está al día: no hay mods para actualizar."); return; }
    openModal('<h4>Revisar actualizaciones</h4><div class="dm-btns" style="margin-bottom:10px">' + btn("sm", "all", "Marcar todo") + btn("sm", "none", "Ninguno") + '</div><div class="dm-list">' +
      pend.map(function (m) { return '<label class="dm-ck"><input type="checkbox" checked data-n="' + esc(m.n) + '"><span><b>' + m.n + "</b><small>" + m.cur + " → " + m.nw + "</small></span></label>"; }).join("") + '</div><div class="dm-prog" hidden><i></i></div><footer>' + btn("", "mcancel", "Cancelar") + btn("pri", "mgo", "Actualizar " + pend.length + " mods") + "</footer>", ".dm-ck input");
  }
  function recount() { var c = mcard.querySelectorAll(".dm-ck input:checked").length, g = mcard.querySelector('[data-a="mgo"]'); if (!g) return; g.textContent = "Actualizar " + c + " mods"; g.disabled = !c; }
  function openNew() {
    openModal('<h4>Nueva instancia</h4><div class="dm-list"><div class="dm-row"><span class="tx"><b>Nombre</b></span><span class="ctl"><input class="dm-field" id="dm-nn" value="Mi instancia nueva" aria-label="Nombre"></span></div><div class="dm-row"><span class="tx"><b>Versión</b></span><span class="ctl"><select class="dm-select" id="dm-nv" aria-label="Versión"><option>1.21.11</option><option>1.21.4</option><option>1.20.1</option></select></span></div>' +
      '<div class="dm-row"><span class="tx"><b>Cargador</b></span><span class="ctl"><select class="dm-select" id="dm-nl" aria-label="Cargador"><option>Vanilla</option><option>Fabric 0.19.3</option><option>Forge 47.3</option></select></span></div></div><footer>' + btn("", "mcancel", "Cancelar") + btn("pri", "mnew", "Crear") + "</footer>", "#dm-nn");
  }

  /* Lienzo de skin y vista 3D */
  var cv, pv, thumbs, rot = 18, drag = null, spin = 0;
  function paint(c) { var g = c.getContext("2d"); g.clearRect(0, 0, G, G); for (var y = 0; y < G; y++) for (var x = 0; x < G; x++) if (grid[y][x]) { g.fillStyle = grid[y][x]; g.fillRect(x, y, 1, 1); } }
  function paintThumbs() { main.querySelectorAll("[data-th]").forEach(function (c) { var gg = c.getContext("2d"), s = SK[+c.dataset.th].g; gg.clearRect(0, 0, G, G); for (var y = 0; y < G; y++) for (var x = 0; x < G; x++) if (s[y][x]) { gg.fillStyle = s[y][x]; gg.fillRect(x, y, 1, 1); } }); }
  function paintAll() { if (cv) { paint(cv); paint(pv); paintThumbs(); } }
  function snap() { undo.push(JSON.stringify(grid)); if (undo.length > 40) undo.shift(); redo = []; }
  function load(s) { var g = JSON.parse(s); for (var y = 0; y < G; y++) for (var x = 0; x < G; x++) grid[y][x] = g[y][x]; }
  function flood(x, y, v) { var t = grid[y][x]; if (t === v) return; var st = [[x, y]]; while (st.length) { var p = st.pop(); if (p[0] < 0 || p[1] < 0 || p[0] >= G || p[1] >= G || grid[p[1]][p[0]] !== t) continue; grid[p[1]][p[0]] = v; st.push([p[0] + 1, p[1]], [p[0] - 1, p[1]], [p[0], p[1] + 1], [p[0], p[1] - 1]); } }
  function initSkin() {
    cv = main.querySelector(".dm-cv"); pv = main.querySelector(".dm-3d canvas"); paintAll();
    var down = false, started = false;
    var put = function (e) {
      var r = cv.getBoundingClientRect(), x = Math.floor((e.clientX - r.left) / r.width * G), y = Math.floor((e.clientY - r.top) / r.height * G);
      if (x < 0 || y < 0 || x >= G || y >= G) return;
      if (S.tool === "pick") { if (grid[y][x]) { S.color = grid[y][x]; S.tool = "pen"; show(true); } return; }
      var v = S.tool === "erase" ? null : S.color; if (S.tool !== "fill" && grid[y][x] === v) return;
      if (!started) { snap(); started = true; }
      if (S.tool === "fill") flood(x, y, v); else { grid[y][x] = v; if (S.sym) grid[y][G - 1 - x] = v; }
      paintAll(); mark("skin");
    };
    cv.addEventListener("pointerdown", function (e) { down = true; started = false; cv.setPointerCapture(e.pointerId); put(e); if (S.tool === "fill") { down = false; refreshHistory(); } });
    cv.addEventListener("pointermove", function (e) { if (down && S.tool !== "fill") put(e); });
    var up = function () { if (down) { down = false; refreshHistory(); } };
    cv.addEventListener("pointerup", up); cv.addEventListener("pointercancel", up);
    var turn = function (d) { rot += d; spin = 0; pv.style.transform = "rotateY(" + rot + "deg)"; };
    pv.addEventListener("pointerdown", function (e) { drag = { x: e.clientX, r: rot }; pv.setPointerCapture(e.pointerId); spin = 0; });
    pv.addEventListener("pointermove", function (e) { if (drag) { rot = drag.r + (e.clientX - drag.x) * 0.9; pv.style.transform = "rotateY(" + rot + "deg)"; mark("skin"); } });
    pv.addEventListener("pointerup", function () { drag = null; });
    pv.addEventListener("keydown", function (e) { if (e.key === "ArrowLeft") { turn(-20); e.preventDefault(); } else if (e.key === "ArrowRight") { turn(20); e.preventDefault(); } });
    pv.style.transform = "rotateY(" + rot + "deg)";
  }
  function refreshHistory() { var u = main.querySelector('[data-a="undo"]'), r = main.querySelector('[data-a="redo"]'); if (u) u.disabled = !undo.length; if (r) r.disabled = !redo.length; }
  (function sway() {
    if (pv && pv.isConnected && !drag && !reduce && S.speed !== "off" && document.activeElement !== pv) { spin += 0.012; pv.style.transform = "rotateY(" + (rot + Math.sin(spin) * 24) + "deg)"; }
    requestAnimationFrame(sway);
  })();

  /* Eventos */
  seg.addEventListener("click", function (e) { var b = e.target.closest("[data-game]"); if (b) { switchGame(b.dataset.game, e); if (b.dataset.game === "roblox") mark("roblox"); } });
  search.addEventListener("input", function () { S.query = search.value; show(true); });
  root.addEventListener("click", function (e) {
    var v = e.target.closest("[data-view]"); if (v && root.contains(v)) { goView(v.dataset.view); return; }
    if (S.menu && !e.target.closest(".dm-menu, .more")) { S.menu = false; show(true); }
  });
  root.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { if (modal.classList.contains("on")) closeModal(); else if (launch.classList.contains("on")) stopLaunch(); else if (S.menu) { S.menu = false; show(true); var m = main.querySelector(".more"); if (m) m.focus(); } return; }
    if (e.key === "Tab") { var layer = modal.classList.contains("on") ? modal : launch.classList.contains("on") ? launch : null; if (!layer) return; var f = focusables(layer); if (!f.length) return; var first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { last.focus(); e.preventDefault(); } else if (!e.shiftKey && document.activeElement === last) { first.focus(); e.preventDefault(); } }
  });
  launch.addEventListener("click", function (e) { if (e.target === launch || e.target.closest("[data-close]")) stopLaunch(); });
  modal.addEventListener("click", function (e) {
    var t = e.target.closest("[data-a]"), a = t && t.dataset.a;
    if (e.target === modal || a === "mcancel") closeModal();
    else if (a === "all" || a === "none") { mcard.querySelectorAll(".dm-ck input").forEach(function (c) { c.checked = a === "all"; }); recount(); }
    else if (a === "mnew") {
      var nm = mcard.querySelector("#dm-nn").value.trim() || "Instancia nueva", ld = mcard.querySelector("#dm-nl").value;
      INSTANCES.push({ name: nm, v: mcard.querySelector("#dm-nv").value, loader: ld, ram: 4, min: 0, mods: 0, shaders: 0, tex: 0, f: "hue-rotate(" + (INSTANCES.length * 47) + "deg)", pos: "50% 50%" });
      S.inst = INSTANCES.length - 1; closeModal(); status("Creada «" + nm + "». Elegila y tocá Jugar."); if (S.view === "inst") { S.swap = true; show(true); S.swap = false; }
    } else if (a === "mgo") {
      var names = []; mcard.querySelectorAll(".dm-ck input:checked").forEach(function (c) { names.push(c.dataset.n); });
      var bar = mcard.querySelector(".dm-prog"); bar.hidden = false; t.disabled = true; requestAnimationFrame(function () { bar.firstChild.style.width = "100%"; });
      later(function () { MODLIST.forEach(function (m) { if (names.indexOf(m.n) >= 0) { m.cur = m.nw; delete m.nw; } }); closeModal(); status(names.length + " mods actualizados."); mark("mods"); if (S.view === "mods" || S.view === "health") { if (S.view === "health") S.health = "idle"; show(true); if (S.health === "idle") runHealth(); } }, ms(800) || 1);
    }
  });
  modal.addEventListener("change", function (e) { if (e.target.closest(".dm-ck")) recount(); });

  main.addEventListener("change", function (e) {
    var t = e.target, f = t.dataset.f;
    if (f === "filter") { S.filter = t.value; show(true); }
    else if (f === "imp") { S.imp[+t.dataset.i] = t.checked; show(true); }
  });
  main.addEventListener("input", function (e) {
    var t = e.target, f = t.dataset.f, E = S.E; if (!f || !E) return;
    if (f === "profile") { E.profile = t.value; if (PROFILES[t.value]) { E.memMax = PROFILES[t.value]; E.jvm = G1; } show(true); var s = main.querySelector('[data-f="profile"]'); if (s) s.focus({ preventScroll: true }); status("Perfil " + t.options[t.selectedIndex].text + ": memoria y argumentos rellenados."); }
    else { E[f] = f === "name" || f === "note" || f === "jvm" ? t.value : t.value; if (f === "memMax" || f === "memMin" || f === "jvm") { E.profile = "manual"; var p = main.querySelector('[data-f="profile"]'); if (p) p.value = "manual"; } }
  });

  main.addEventListener("click", function (e) {
    var t = e.target.closest("button"); if (!t || !main.contains(t)) return;
    var d = t.dataset, a = d.a;
    if (a === "go") goView(d.v);
    else if (a === "play") { var c = cur(); startLaunch(c.name, "Minecraft " + c.v + " · " + c.loader.split(" ")[0] + " · Alex", STEPS, c); mark("play"); }
    else if (a === "edit") goView("edit");
    else if (a === "menu") { S.menu = !S.menu; show(true); var m = main.querySelector(S.menu ? ".dm-menu button" : ".more"); if (m) m.focus(); }
    else if (a === "favtog") { cur().fav = !cur().fav; S.menu = false; show(true); }
    else if (a === "backup") { if (S.view !== "backups") goView("backups"); addBackup(); }
    else if (a === "new") openNew();
    else if (a === "inst") { S.inst = +d.i; S.swap = true; show(true); S.swap = false; var b = main.querySelector('[data-i="' + d.i + '"]'); if (b) b.focus({ preventScroll: true }); }
    else if (a === "mdet") { S.msel = S.msel === +d.i ? -1 : +d.i; show(true); }
    else if (a === "mtog") { var m3 = MODLIST[+d.i]; m3.on = !m3.on; show(true); status(m3.n + (m3.on ? " activado." : " desactivado.")); }
    else if (a === "sw") { var m2 = MODLIST[+d.i]; m2.on = !m2.on; t.setAttribute("aria-checked", m2.on); status(m2.n + (m2.on ? " activado." : " desactivado.")); }
    else if (a === "upd") openUpdates();
    else if (a === "reheal") { S.health = "idle"; runHealth(); }
    else if (a === "off") { S.off[d.m] = 1; show(true); status("«" + d.m + "» se desactivó. Podés reactivarlo cuando quieras."); }
    else if (a === "install") { S.installed[d.k] = 1; show(true); later(function () { S.installed[d.k] = 2; cur().mods++; status(d.k.replace(/^(Modrinth|CurseForge)/, "") + " instalado en " + cur().name + "."); if (S.view === "explore" || S.view === "curse") show(true); mark("mods"); }, ms(900) || 1); }
    else if (a === "pack") { var p = PACKS[+d.i]; S.packs[p[0]] = 1; show(true); later(function () { S.packs[p[0]] = 2; INSTANCES.push({ name: p[0], v: "1.21.1", loader: "Fabric 0.19.3", ram: 6, min: 0, mods: p[3], shaders: 0, tex: 0, f: "hue-rotate(" + (INSTANCES.length * 47) + "deg)", pos: "40% 45%" }); status("Se creó la instancia «" + p[0] + "»."); if (S.view === "packs") show(true); }, ms(1100) || 1); }
    else if (a === "imp") { S.imp = [true, true, true, false]; show(true); }
    else if (a === "impx") { S.imp = null; show(true); }
    else if (a === "impgo") { var n = S.imp.filter(Boolean).length; S.imp = null; show(true); status(n + " archivos importados (de ejemplo)."); }
    else if (a === "sym") { S.sym = !S.sym; show(true); }
    else if (a === "undo" && undo.length) { redo.push(JSON.stringify(grid)); load(undo.pop()); paintAll(); refreshHistory(); }
    else if (a === "redo" && redo.length) { undo.push(JSON.stringify(grid)); load(redo.pop()); paintAll(); refreshHistory(); }
    else if (a === "skin") { S.sk = +d.i; grid = SK[S.sk].g; undo = []; redo = []; show(true); }
    else if (a === "rot") { rot = d.d === "0" ? 0 : rot + +d.d; spin = 0; if (pv) pv.style.transform = "rotateY(" + rot + "deg)"; }
    else if (a === "slim") { S.skin3 = S.skin3 === "slim" ? "classic" : "slim"; show(true); if (pv) pv.style.width = S.skin3 === "slim" ? "118px" : ""; status("Modelo " + (S.skin3 === "slim" ? "delgado" : "clásico") + "."); }
    else if (a === "equip") { t.textContent = "✓ Equipada"; t.classList.add("ok"); status("Skin equipada a Alex en «" + cur().name + "»."); mark("skin"); }
    else if (a === "join") { var s = PUB[+d.i]; startLaunch(s[0], "Minecraft " + cur().v + " · " + s[1], STEPS, cur()); }
    else if (a === "srv") toggleServer();
    else if (a === "con") { S.conOpen = !S.conOpen; show(true); }
    else if (a === "restore") { S.restored = +d.i; show(true); status("Se restauró como una instancia nueva: tu instancia original no se toca."); }
    else if (a === "say") status(d.t);
    else if (d.color) { S.color = d.color; S.tool = S.tool === "erase" ? "pen" : S.tool; show(true); }
    else if (d.tool) { S.tool = d.tool; show(true); }
    else if (d.set === "theme") { S.theme = d.val; root.setAttribute("data-theme", d.val); show(true); mark("theme"); }
    else if (d.set === "speed") { S.speed = d.val; root.setAttribute("data-speed", d.val); show(true); movePill(); }
    else if (d.rtab) { S.rtab = d.rtab; show(true); var tb = main.querySelector('[data-rtab="' + d.rtab + '"]'); if (tb) tb.focus({ preventScroll: true }); }
    else if (d.fav !== undefined) { S.fav[d.fav] = !S.fav[d.fav]; show(true); var st = main.querySelector('[data-fav="' + d.fav + '"]'); if (st) st.focus({ preventScroll: true }); }
    else if (d.playr !== undefined) { var g = GAMES[+d.playr]; startLaunch(g[0], "Roblox · Alex", [["Preparar", "Abriendo Roblox…"], ["Servidor", "Buscando un servidor con lugar…"], ["En juego", "¡Listo! Roblox se abre."]], g[2]); mark("play"); }
    else if (d.friend) { startLaunch("Unirte a " + d.friend, "Roblox · con el enlace oficial", [["Preparar", "Abriendo Roblox…"], ["En juego", "Te unís a la partida de " + d.friend + "."]], "#2a7fa8,#8fd6e8"); }
    else if (a === "save") { var E = S.E, c3 = cur(); c3.name = E.name.trim() || c3.name; c3.ram = Math.max(1, +E.memMax || c3.ram); goView("inst"); status("Cambios guardados en «" + c3.name + "»."); }
  });
  side.addEventListener("click", function (e) { var b = e.target.closest('[data-a="more"]'); if (b) { S.more = !S.more; drawSide(); var n = side.querySelector('[data-a="more"]'); if (n) n.focus(); } });

  function addBackup() {
    if (S.backups[0] && S.backups[0].pend) return;
    var b = ["Supervivencia · manual", "Ahora · 415 MB"]; b.pend = true; b.w = 0; S.backups.unshift(b); S.restored = -1; show(true); status("Creando el respaldo…");
    requestAnimationFrame(function () { var i = main.querySelector(".dm-prog i"); if (i) i.style.width = "100%"; });
    later(function () { b.pend = false; b.fresh = true; if (S.view === "backups") show(true); status("Respaldo creado y verificado con SHA-256."); mark("backup"); later(function () { b.fresh = false; }, 1000); }, ms(900) || 1);
  }
  function toggleServer() {
    var log = function (t, t2) { S.con.push(t); if (S.view === "myserver") show(true); var c = main.querySelector(".dm-con"); if (c) c.scrollTop = c.scrollHeight; };
    if (S.srv === "on") { S.srv = "off"; S.con.push("Servidor detenido."); status("El servidor se apagó."); show(true); return; }
    S.srv = "boot"; S.conOpen = true; S.con = ["Iniciando Paper 1.21.11…"]; show(true); status("Encendiendo el servidor…");
    [[450, "Cargando el mundo «mundo»…"], [900, "Preparando 441 chunks de inicio…"], [1350, '<span class="g">Listo en 4,2 s. Puerto 25565.</span>']].forEach(function (s, i) {
      later(function () { log(s[1]); if (i === 2) { S.srv = "on"; show(true); status("Servidor encendido: tus amigos pueden entrar por tu red o por un túnel."); } }, ms(s[0]) || 1 + i);
    });
  }

  /* Guía: atajos que hacen la acción por vos */
  document.querySelectorAll("[data-try]").forEach(function (b) {
    b.addEventListener("click", function () {
      var k = b.dataset.try; stopLaunch(); closeModal();
      var inMc = function (fn) { if (S.game !== "minecraft") { switchGame("minecraft"); setTimeout(fn, ms(620) + 40); } else fn(); };
      root.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" });
      if (k === "play") inMc(function () { goView("inst"); setTimeout(function () { var p = main.querySelector('[data-a="play"]'); if (p) p.click(); }, ms(200) + 60); });
      else if (k === "roblox") { if (S.game !== "roblox") switchGame("roblox", { clientX: b.getBoundingClientRect().left, clientY: b.getBoundingClientRect().top }); mark("roblox"); }
      else if (k === "skin") inMc(function () { goView("skins"); });
      else if (k === "theme") inMc(function () { goView("set"); });
      else if (k === "mods") inMc(function () { goView("explore"); });
    });
  });

  setGameUI(); drawSide(); show();
  window.addEventListener("resize", movePill);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(movePill);
  setTimeout(movePill, 50);
  if (window.ResizeObserver) new ResizeObserver(movePill).observe(seg);
})();
