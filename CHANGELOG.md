# Cambios

## Sin publicar
- **Perfil de rendimiento**: el perfil elegido ahora se guarda en la instancia y se ve al reabrirla.
- **Flatpak**: usa los mismos datos que la instalación normal (`~/.local/share/nova-launcher`), así que ya no abre una copia vacía; las dependencias de pip quedan fijadas con hash para poder publicarlo en Flathub.
- **Web**: portada más corta y clara, con «Qué incluye» en tarjetas y el texto largo plegado, y una demo interactiva rehecha para parecerse al launcher real.

## 1.17.0
- **Actualizar mods**: «Buscar actualizaciones» ahora detecta también los mods que agregaste a mano (los identifica por hash), consulta Modrinth en lote y abre una lista ordenada con una casilla por mod («versión actual → nueva») y el botón «Actualizar N mods». Los mods adoptados se pueden revertir.
- **Perfil de rendimiento**: en el formulario de cada instancia, Ahorro, Equilibrado o Máximo rellenan la memoria y los argumentos de Java (nunca más de la mitad de tu RAM). En Fabric y Quilt sugiere Sodium y Lithium.
- **Exportar .mrpack**: los archivos que no están en Modrinth y la carpeta `config` ahora se guardan dentro del archivo (hasta 512 MiB) en vez de omitirse, y al terminar se muestra un resumen.
- **Flatpak**: el manifiesto instala las dependencias en el mismo módulo; se compiló, instaló y abrió en Fedora.
- Sin probar: las pantallas nuevas con clics reales en Windows, ni contra la API real de Modrinth más allá de lo que se usó a mano.

## 1.16.1
- **Arreglo**: si el Java elegido a mano en una instancia ya no existe, Salud ahora lo marca como error y ofrece **Usar el Java de Nova** (en la 1.16.0 solo mostraba «No se pudo comprobar Java», sin botón).
- **Inglés**: se traducen mejor la barra de fallo (código de salida y mod sospechoso), «Consecuencia / Solución» en Salud, los «hace N min/h/días» y los contadores de la biblioteca.
- Sin probar: en Windows, ni un cierre real del juego con el botón Corregir.

## 1.16.0
- **Nova en inglés**: Ajustes → Idioma → English (se aplica al reiniciar). Están traducidos los menús, pantallas, botones, avisos y mensajes de estado; los textos con un nombre o un número en el medio se traducen por plantilla. Lo que falte sigue apareciendo en español. Para sumar otro idioma, copiá `locales/en.json` (ver `locales/README.md`; `tools/extraer_textos.py` lista todos los textos).
- **Java automático**: si la instancia tiene un Java elegido a mano que ya no existe o es más viejo de lo que pide Minecraft, Nova lo avisa en la barra de estado y usa el Java que administra ella, en vez de fallar al iniciar. Un Java que no se puede comprobar se respeta.
- **Diagnóstico de cierres**: cuando Minecraft se cierra con error, Nova lee el registro y el último informe de fallos del juego (`crash-reports`), muestra la causa en español y, si el mod sospechoso aparece en el informe, lo nombra. Si la causa se arregla con un clic (Java incompatible, RAM o argumentos de Java inválidos), aparece el botón **Corregir**, que guarda antes una copia de `instance.json`.
- **Salud de la instancia**: el análisis suma «Java mucho más nuevo que el pedido» (versiones viejas del juego) y un botón **Usar el Java de Nova** en los problemas de Java.
- **Web**: maqueta interactiva del launcher en la portada (Minecraft y Roblox, Jugar con pasos, mods, skins, respaldos, tema claro y velocidad de animaciones).
- Sin probar: en Windows, ni el inglés ni el botón Corregir con un cierre real del juego (se probó con registros e informes de ejemplo y con los tests).

## 1.15.0
- **Rediseño de la interfaz**: marco nocturno con un panel redondeado, selector Minecraft/Roblox en la barra de arriba, barra lateral más corta (lo menos usado queda detrás de «Más») y portada de instancia más grande. Ajustes, Almacenamiento y Estadísticas pasan a tarjetas ordenadas, y el resto de las pantallas hereda los nuevos colores, bordes y esquinas, en tema oscuro y claro.
- **Animaciones nuevas**:
  - **Entrada de Nova**: la estrella cae rebotando, deja sombra, anillos de luz y chispas, y la interfaz se arma en cascada.
  - **Portal al elegir juego**: al tocar Minecraft o Roblox, el color del juego se expande desde el punto del clic, aparece su símbolo y el contenido cambia; después se drena desde el mismo punto.
  - Selector de juego con una píldora que se estira al moverse, páginas que suben al abrirse, portadas con zoom suave, barras de progreso y tarjetas con transiciones.
  - **Ajustes → Animaciones**: lentas y suaves, normales, rápidas o apagadas. Se aplica sin reiniciar. Si tu sistema ya tiene las animaciones apagadas, Nova tampoco anima.
- Arreglos:
  - Volver o Escape desde Roblox ya no te lleva a la biblioteca de Minecraft, y cambiar de juego con una página abierta la cierra bien.
  - Un fallo de red ya no borra el aviso de una actualización pendiente.
  - La tarjeta «Última jugada» ya no deja un error repetido en la lista compacta.
  - La portada ya no parpadea al escribir en el buscador y las tarjetas no repiten su entrada con cada tecla.
  - Tema claro: botón de cerrar, textos tenues, estado de error, botón de compra y pantalla de inicio al jugar se leen bien; los campos deshabilitados se ven apagados.
  - Textos: «Jugar con cuenta offline» y un aviso de mods en instancias Vanilla que explica qué hacer.
- Sin probar: en Windows, ni las animaciones nuevas en movimiento con clics reales (se revisaron cuadros sueltos y los tests).

## 1.14.1
- **Editor de skins renovado**:
  - Pintás directamente sobre la skin desplegada, con cada parte marcada y su nombre. La capa exterior (sombrero, chaqueta, mangas…) tiene borde punteado.
  - Vista previa 3D con las dos capas que se gira arrastrando, con modelo clásico o delgado.
  - Herramientas: lápiz, borrar, gotero y relleno, además de simetría (pinta también el lado opuesto del cuerpo), paleta, colores usados hace poco y deshacer o rehacer (cada trazo es un paso). Atajos: `B`, `E`, `I`, `G`, `M`, `Ctrl + Z`, `Ctrl + S`.
  - Biblioteca con miniaturas: guardar, guardar como, eliminar (con confirmación) y aviso si cerrás o cambiás de skin con cambios sin guardar.
- **«De un jugador»**: trae la skin actual de cualquier jugador de Minecraft por su nombre, desde Mojang, para editarla y guardarla como tuya.
- Las **skins antiguas de 64 × 32** ahora se pueden abrir (Nova completa el brazo y la pierna que faltaban) y detecta si una skin es de modelo delgado. Las de alta resolución se rechazan con un mensaje claro.
- Arreglos: el borrador ya no deja huecos en la capa base (que se ven negros en el juego), una skin importada ya no cuenta como guardada, y los mensajes de «Equipar» explican qué falta (perfil, instancia, cargador de mods o cuenta de Microsoft, que cambia la skin en minecraft.net).
- **Pantalla de inicio de Nova al jugar**: al tocar «Jugar», Nova muestra una pantalla con la portada de la instancia, el logo animado, cuatro pasos (preparar, archivos, iniciar Java y en juego) y el mensaje real de cada momento, por ejemplo qué se está descargando. Se va sola cuando Minecraft abre. Si el inicio falla, queda a la vista con el motivo y un botón para ver el registro. Se puede ocultar con «Ocultar» y apagar en Ajustes → «Pantalla de inicio al jugar». Respeta la opción de animaciones de tu escritorio.
- **Pantalla de carga dentro de Minecraft** (instancias con Fabric o Quilt): ahora sigue los colores actuales de Nova (celeste sobre fondo oscuro) en lugar del violeta de antes, y el logo de Nova que aparece al cargar Minecraft 1.21.11 con Fabric está renovado. Las instancias que ya la tenían se actualizan solas en su próximo inicio. Nueva opción «Quitar pantalla de carga Nova» en el menú de cada instancia: devuelve los colores que tenía antes de Nova.
- Sin probar: en Windows, ni ver la pantalla de carga renovada dentro del juego (se probó que Java carga el complemento y que los colores se escriben y se quitan bien).

## 1.14.0
- **Actualizaciones en segundo plano (opcional)**: en Ajustes → Actualizaciones, «Actualizar Nova en segundo plano». Con eso activado, Nova
  descarga la versión nueva mientras la usás, comprueba su SHA-256 contra el que publica la release y la guarda en su carpeta. Instalarla
  es un clic y no instala nada sola: en Fedora, «Instalar ahora» pide tu autorización al sistema y corre `dnf`; en Windows, «Reiniciar y
  actualizar» ejecuta el instalador sin ventanas (no pide permisos de administrador) y Nova se abre de nuevo. Justo antes de instalar,
  Nova vuelve a comprobar el archivo, así que uno cambiado entre la descarga y la instalación se rechaza.
- La descarga manual de una actualización también ofrece «Instalar ahora» al terminar.
- Sin probar todavía: la instalación automática en Windows y con una actualización real en Fedora.

## 1.13.0
- **Servidores de cada juego (Roblox)**: cada tarjeta tiene un botón «Servidores» con los servidores públicos del juego: cuántos jugadores
  tiene, el ping y su estado (casi vacío, con lugar, casi lleno, lleno). «Unirme» abre Roblox directo en ese servidor; si Roblox lo
  ignora o ya se llenó, te lleva a otro del mismo juego. Los servidores privados no se pueden crear desde Nova: Roblox solo muestra si
  un juego los permite y cuánto cuestan con tu sesión completa, así que hay un botón que abre la página del juego, donde está la pestaña
  «Servidores».
- **Iniciar sesión con Roblox (opcional)**: se abre la página oficial de Roblox, autorizás y volvés a Nova, que muestra tu nombre y tu
  avatar. Nova no ve tu contraseña y pide solo identidad (`openid` y `profile`); descarta los permisos apenas lee tu perfil. Roblox no
  da la lista de amigos ni quién está conectado a las aplicaciones, así que los amigos se siguen agregando a mano. Mientras Roblox no
  apruebe la aplicación de Nova, solo 10 personas pueden autorizarla: por eso es opcional y el catálogo se ve sin cuenta.
- **Pantalla de Roblox**: ahora se desplaza entera (cuenta, amigos, pestañas y juegos), la barra de tu cuenta es más compacta, «Cerrar sesión»
  es un botón claro y la pantalla ya no salta de lugar al refrescar o marcar un favorito.

## 1.12.0
- **Unirte a tus amigos en Roblox**: arriba de la pantalla de Roblox hay una fila de amigos, como en Roblox. Los agregás con su nombre de
  usuario (un «+» y listo) y, al tocar uno, Nova abre Roblox con el enlace oficial para unirte a su partida. Nova no puede leer tu lista
  de amigos de Roblox ni saber quién está conectado (eso necesita tu sesión), así que la lista la armás vos y Roblox decide si podés
  entrar. Todavía no se probó con un amigo real.
- **Juegos de pago**: el botón muestra «De pago · R$ precio». Nova no sabe si ya lo tenés; si hace falta, Roblox te pide comprarlo.
- **Buscador arriba**: en Roblox, el buscador de la barra superior busca juegos o acepta un enlace, igual que en Minecraft busca instancias.
- **Botones y detalles**: botones más claros (con foco visible al usar el teclado), pestañas en píldora, estrellas más grandes, el porcentaje
  de aprobación de cada juego y Nova recuerda la última pestaña. La categoría «Con amigos» pasó a llamarse «En grupo». En Roblox ya no se ven
  la cuenta de Minecraft ni el panel lateral. La lista de juegos conserva su posición mientras cargan los íconos.

## 1.11.0
- **Elegí a qué jugar**: al abrir Nova aparece «¿A qué querés jugar?» con **Minecraft** y **Roblox**, cada uno con su portada. Con
  «Recordar mi elección» entra directo la próxima vez, y «Cambiar de juego» vuelve a la pantalla de selección. Todo lo de Minecraft
  (instancias, mods, Mi servidor) queda igual.
- **Roblox**: explorá los juegos del momento (Tendencias, Más jugados, Emergentes y Con amigos), buscá por nombre o pegá el enlace
  de un juego de roblox.com. «Jugar» abre el juego directo: en **Linux con Sober** (si no lo tenés, Nova te dice cómo instalarlo) y
  en Windows y Mac con el cliente oficial de Roblox. Podés marcar favoritos con la estrella y ver los últimos juegos que abriste.
- Nova no ve ni pide tu contraseña de Roblox: iniciás sesión en Sober o en el cliente oficial. Tampoco muestra tus amigos ni
  quién está conectado, porque eso exige tu sesión de Roblox. Nova no está afiliado a Roblox.

## 1.10.0
- **Java propio para Forge**: Forge necesita un Java completo, no el recortado de Mojang. Si no tenés uno instalado, Nova ahora baja
  **Eclipse Temurin** desde Adoptium (comprueba su SHA-256 y lo extrae sin salirse de su carpeta) y lo guarda en sus datos, sin tocar
  el Java del sistema. Así crear o actualizar un servidor Forge funciona en una PC sin Java (por ejemplo, la mayoría de las de Windows).
- **Plugins de Hangar y SpigotMC**: el catálogo de un servidor Paper tiene un selector de fuente. **Hangar** (el sitio de plugins de
  PaperMC) se descarga comprobando el SHA-256. **SpigotMC** se busca con Spiget: no publica hashes, así que Nova solo baja desde su
  CDN, comprueba que sea un `.jar` y lo avisa; los plugins de pago o alojados fuera de SpigotMC se abren en su página. Fabric y Forge
  siguen con Modrinth.
- **Importar un servidor que ya tenés**: en «Mi servidor», «Importar servidor» detecta el tipo (Vanilla, Paper, Fabric o Forge), la
  versión, el puerto y la memoria de una carpeta existente, te deja corregirlos y **copia** la carpeta (la original no se toca).
  Después se maneja como cualquier servidor de Nova, incluidos los respaldos y las actualizaciones.
- Arreglo: abrir la lista de cuentas ya no rompe Nova si falta la biblioteca de inicio de sesión de Microsoft.

## 1.9.4
- **Conectar Microsoft, con guía**: al tocar «Conectar Microsoft», Nova ahora explica en pantalla cómo conseguir el ID de
  aplicación de Azure (los pasos, la redirección exacta y el enlace a los registros de aplicaciones) antes de pedirlo. Recordá
  que Mojang tiene que aprobar esa aplicación para usar los servicios de Minecraft.
- Nova queda preparado para traer su propio ID aprobado: cuando exista, «Conectar Microsoft» iniciará sesión con un clic y
  quedará la opción «Conectar con mi propio ID…» para quien prefiera el suyo.

## 1.9.3
- **Respaldos del mundo**: nueva sección Respaldos en cada servidor. Respaldos automáticos cada tantas horas (con el servidor
  encendido Nova le pide que guarde el mundo, lo copia y lo deja guardando de nuevo), también al apagar si querés, y se
  conservan los últimos que elijas (los manuales nunca se borran solos). Podés crear uno ahora, **restaurar** cualquiera
  (antes Nova guarda una copia del mundo actual, así que se puede deshacer), guardar una copia fuera y eliminar.
- **Jugadores y permisos**: sección Jugadores con quién está conectado, operadores, lista blanca y baneados, con botones en vez
  de comandos. Con el servidor encendido se aplica al instante; apagado edita los archivos del servidor buscando el UUID en
  Mojang (o calculándolo si el servidor no exige cuenta original). También podés expulsar a un jugador conectado.
- **Estado y rendimiento**: sección Estado en vivo con el tiempo encendido, jugadores conectados, memoria y procesador que
  usa el servidor, tamaño del mundo y puerto.
- **Actualizar el servidor**: en Ajustes, «Versión del servidor» busca una compilación nueva de la misma versión de Minecraft
  y las versiones nuevas disponibles, y actualiza sin perder el mundo: respalda antes, verifica la descarga y deja el
  `server.jar` anterior como `server.jar.old`. No permite volver a una versión anterior (un mundo no abre en una más vieja).
  Para Forge reinstala con su instalador.
- Los servidores nuevos guardan la compilación instalada para poder avisar si hay una más nueva.
- Un servidor Forge usa siempre su propia carpeta de bibliotecas aunque haya quedado una instalación anterior.

## 1.9.2
- **Reiniciar un servidor ya no falla**: Nova lo encendía de nuevo apenas se apagaba y a veces el puerto seguía «ocupado» por
  conexiones recién cerradas (el sistema las retiene hasta un minuto), así que decía que no se podía. Ahora esas conexiones no
  cuentan como puerto ocupado y, si el puerto tarda en liberarse, Nova reintenta unos segundos antes de rendirse.
- **Servidores que siguen encendidos cuando Nova se cierra**: Nova guarda el proceso de cada servidor (su número y su hora de
  inicio, para no confundirlo con otro programa) y, al abrirse, lo reconoce como «Encendido». Mostrás su registro, lo apagás con
  calma (guarda el mundo) o lo reiniciás desde Nova. Un servidor reconectado no acepta comandos hasta reiniciarlo.
- **Nova ya no se cierra con un servidor encendido**: con «Cerrar Nova» al iniciar Minecraft, si hay un servidor corriendo se
  minimiza en vez de cerrarse, para no dejarlo sin control.
- **Túnel para amigos de otras redes (experimental, Linux de 64 bits)**: sección **Amigos** en cada servidor. Usa el agente
  oficial de playit.gg, un servicio externo y gratuito con sus propias condiciones, y Nova lo avisa. Descarga el agente
  comprobando su SHA-256, vincula tu cuenta en el navegador (Nova nunca ve tu contraseña), enciende y apaga el túnel (se
  cierra junto con Nova) y guarda la dirección pública que creás en tu panel de playit para copiarla.

## 1.9.1
- **Forge en Mi servidor**: además de Paper, Fabric y Vanilla, ahora podés crear servidores **Forge**. Nova descarga el instalador
  desde el Maven oficial de Forge, comprueba su SHA-256, usa el Java que pide esa versión y ejecuta el instalador por vos
  (tarda unos minutos). Para instalar Forge hace falta un Java completo en tu equipo (OpenJDK o Temurin): con el Java recortado
  de Mojang el instalador de Forge falla, y Nova te lo explica. Solo se ofrecen las versiones de Minecraft que Forge soporta.
- **Catálogo de mods y plugins**: cada servidor tiene una sección nueva (Plugins en Paper, Mods en Fabric y Forge) con el catálogo
  de Modrinth. Solo muestra lo compatible con la versión y el tipo de tu servidor; instala con un clic en `plugins/` o `mods/`,
  comprueba el SHA-512, suma las dependencias obligatorias y permite quitar lo instalado. Un servidor Vanilla lo explica.
- **Pantalla del servidor rediseñada**: acciones arriba (encender, apagar, reiniciar, jugar y un menú con abrir carpeta y eliminar),
  direcciones y aviso de «servidor local» en una sola tarjeta, secciones por pestañas (Consola, Ajustes, Archivos, Plugins o Mods)
  que se desplazan por su cuenta, y Ajustes en tarjetas con el botón de guardar siempre a la vista.

## 1.9.0
- **Mi servidor**: creá y manejá servidores de Minecraft Java en tu computadora, sin salir de Nova. Elegís Paper (plugins),
  Fabric (mods) o Vanilla y la versión; Nova descarga el servidor y el Java que necesita (comprobando el hash cuando el
  proveedor lo publica) y te pide aceptar el EULA de Mojang: nunca lo acepta por vos. Encender, apagar (con `stop`, que guarda
  el mundo), reiniciar y eliminar; consola en vivo con comandos; ajustes (modo de juego, dificultad, jugadores, lista blanca,
  puerto, memoria); y un administrador de archivos con filtro, orden, selección múltiple, edición de textos, activar o
  desactivar mods y plugins, guardar copias, arrastrar y soltar, y respaldo del mundo. Es local: corre en tu PC mientras
  esté encendida, y Nova lo avisa. Al cerrar Nova con servidores encendidos, los apaga con calma.

## 1.8.2
- **Contar instalaciones (opcional)**: la primera vez, Nova pregunta si querés ayudar a contar cuánta gente lo usa. Si
  aceptás, una vez al día envía un número al azar, la versión y el sistema (Linux o Windows). Nada más. Se cambia en
  Ajustes > «Contar esta instalación»; al apagarlo se borra ese número. Está apagado hasta que digas que sí.

## 1.8.1
- **Más rápido al abrir**: preparar el comando de Minecraft ya no lanza un proceso `file` por cada biblioteca del juego
  (unos 95 en un modpack grande): la arquitectura del sistema se consulta una sola vez. En una instancia NeoForge con
  93 bibliotecas pasa de 230 ms a menos de 5 ms, con el mismo comando exacto. Además, las portadas incluidas se decodifican
  de una sola vez y el launcher abre unos 60 ms antes. No cambia ninguna función ni ajuste.

## 1.8.0
- **Pomme (experimental)**: cada instancia puede usar el cliente **Pomme**, un cliente de Minecraft Java no oficial
  escrito en Rust, en lugar de Java (que sigue siendo lo normal). Se elige en Editar instancia > Cliente. La primera vez,
  Nova pregunta y lo descarga desde la release oficial de `PommeMC/Client`, comprueba el tamaño y la suma SHA-256 que
  publica GitHub y lo abre; el tiempo jugado se registra igual. Pomme no usa mods de Java y tiene su propio inicio de
  sesión de Microsoft. Disponible en Linux x64 y Windows x64. "Actualizar o reinstalar Pomme" está en el menú ⋮.

## 1.7.0
- **Rediseño**: nueva identidad alineada con Nova Studios. Fondo de cielo nocturno, tinta clara y un único acento cian
  (ion) propio del launcher, con un logo nuevo (estrella de cuatro puntas dentro de una órbita). La fila de estado
  reemplaza las cuatro tarjetas de la biblioteca, la barra lateral cabe sin cortarse y los estantes de Mods, Shaders
  y Texturas muestran su cantidad con las acciones Explorar e Importar. Tema claro y oscuro con contraste AA.
- **Importar archivos del equipo**: mods (`.jar`), texturas y shaders (`.zip`), paquetes de datos y modpacks
  (`.mrpack` o ZIP) desde el botón Importar de cada estante, el menú Importar, `Ctrl+O` o arrastrando a la ventana.
  Nova revisa cada archivo antes de copiarlo (qué es, si el cargador coincide, si está dañado), nunca pisa lo que ya
  está instalado y copia por pasos para no dejar archivos a medias. Los mods que no vinieron de Modrinth ahora
  también se pueden mover a la Papelera desde Contenido instalado.
- **Editar instancia**: formulario nuevo en secciones (Instancia, Minecraft, Rendimiento y Java), con ayuda en cada
  campo, desplazamiento propio y los botones Guardar y Cancelar siempre visibles. Corrige que elegir una portada
  nueva no actualizaba la vista previa y que el tema claro dejaba etiquetas ilegibles.
- **Web**: rediseñada con el estilo de studiosnova.vercel.app y capturas nuevas.
- Herramienta `tools/capturas.py` para generar capturas con datos de ejemplo sin tocar tus datos.

## 1.6.0
- **Cuenta Nova**: «Iniciar sesión con Nova» en el menú de Cuentas conecta el launcher con la misma cuenta que Nova
  Music. Se aprueba un código en `studiosnova.vercel.app/conectar`; la contraseña nunca pasa por el launcher. El acceso
  se guarda en `nova-cuenta.json` (solo legible por el usuario) y se revoca al cerrar sesión. Solo muestra el nombre y
  el avatar: el launcher no tiene plan. Las cuentas de Minecraft (Microsoft y offline) no cambian.

## 1.5.3
- **Licencia**: Nova Launcher pasa a ser software libre bajo GPL-3.0-or-later. El repositorio incluye `LICENSE` y
  `THIRD_PARTY_LICENSES.md` (con el aviso BSD-2-Clause de minecraft-launcher-lib), y los dos se distribuyen con el RPM, el
  instalador de Windows y el paquete Flatpak. El RPM declara `GPL-3.0-or-later AND BSD-2-Clause`.
- **Windows**: instrucciones para comprobar el SHA-256 con PowerShell y para la advertencia de SmartScreen, y una guía
  del estado de la firma de código (`packaging/windows/FIRMA.md`). El instalador sigue sin firmar.
- **Web**: sección de licencia en los términos, pregunta frecuente sobre código abierto y enlace en el pie.

## 1.5.2
- **Inicio**: una franja arriba de la biblioteca con la última partida (toca para seleccionarla), las descargas en
  curso o en cola, el estado de la cuenta y si hay una versión nueva de Nova. Cada tarjeta abre su sección.
- **Java**: en *Editar instancia* y en *Ajustes*, el botón *Elegir un Java instalado* busca las instalaciones del
  equipo (JAVA_HOME, PATH, `/usr/lib/jvm`, `~/.jdks`, SDKMAN, el Java administrado por Nova y las carpetas
  habituales de Windows), pregunta su versión con límite de tiempo y marca las que son demasiado antiguas.
  No descarga ni ejecuta nada de otros lugares.
- **Memoria mínima**: campo nuevo (0 = automática) que agrega `-Xms` antes de los argumentos del usuario. Se valida
  que no supere la máxima, y el diagnóstico puede restablecerla si el valor es inválido.
- **Calidad**: el CI ahora ejecuta `pyflakes` además de las pruebas, y se limpiaron los imports sin uso (228 pruebas).

### Todavía no implementado
- Memoria del proceso de Minecraft (hoy solo se muestra la del sistema).
- Instalación automática de dependencias de CurseForge.
- Selector de Java con descarga de un JDK nuevo (Nova usa el Java administrado de Mojang cuando el campo está vacío).
- Firma de código de Windows (no hay certificado).

## 1.5.1
- El menú *Más acciones* de la instancia ahora está agrupado (Jugar, Contenido, Instancia), alineado a la izquierda y se
  desplaza cuando no entra en la ventana, en lugar de cortarse por abajo.

## 1.5.0

### Nuevo
- **Plantillas** (Nueva instancia → *Desde una plantilla*): Vanilla, Supervivencia, PvP, Modpacks, Rendimiento,
  Creativo y Experimentación. Solo completan el formulario con ajustes razonables (cargador, RAM, argumentos
  de Java); la RAM nunca supera la mitad de la memoria instalada.
- **Perfiles**: *Más acciones → Exportar perfil* guarda versión, cargador, RAM, argumentos de Java, resolución,
  notas y la lista de mods como referencia. *Importar un perfil de Nova* valida el archivo, muestra qué se va a
  aplicar y abre el formulario para que lo revises. No exporta la ruta de Java ni mundos, y no instala mods solo.
- **Estado de servidores**: botón *Comprobar* en la lista de servidores (protocolo Server List Ping, con límite
  de tiempo y de tamaño). Nova se niega a consultar direcciones que resuelven a redes privadas, locales o
  reservadas, y se conecta a la IP ya validada para evitar DNS rebinding. También se puede copiar la dirección.
- **Estadísticas** (barra lateral): sesiones, tiempo total, arranque promedio, sesiones con error, tiempo por
  instancia, últimas sesiones, memoria del sistema y errores recientes de Nova. Todo queda en tu computadora;
  no hay telemetría. *Borrar estadísticas locales* lo elimina, y la página explica qué se guarda.
- **Descargas**: muestran bytes, velocidad y tiempo restante cuando se pueden calcular. Si se corta la conexión,
  Nova reintenta hasta tres veces y reanuda desde el archivo parcial cuando el servidor admite rangos. El archivo
  solo toma su nombre definitivo después de verificar su suma.
- **CurseForge** (barra lateral): búsqueda con la API oficial y tu propia clave, que se guarda en tu perfil con
  permisos privados y nunca viaja con Nova. Instala solo los mods que permiten descargas de terceros, con
  verificación SHA-1 y tamaño; el resto se abre en la web. Las dependencias no se instalan solas.
- **Novedades** (barra lateral): las últimas notas de versión de GitHub.
- **Traducciones**: base lista (`locales/`, `i18n.py`) y un primer catálogo en inglés para el menú lateral y
  algunos títulos. Ajustes → Idioma; se aplica al reiniciar. Lo que no está traducido sigue en español.

### Alcance real de las comprobaciones
Las pruebas automáticas cubren la lógica: plantillas y perfiles, estado de servidores (con servidores falsos
locales), estadísticas, descargas reanudables, cliente de CurseForge (con respuestas simuladas), traducciones y
novedades. La interfaz nueva se revisó con capturas y llamadas programáticas, no con clics reales. La API real
de CurseForge no se probó (necesita una clave) ni el estado contra servidores reales de Minecraft. No es una
auditoría de seguridad completa.

### Limitaciones conocidas
- La reanudación de descargas funciona dentro de una misma descarga (reintentos); si cerrás Nova, el parcial
  se descarta con la carpeta temporal.
- Las estadísticas de memoria son del sistema, no del proceso de Minecraft.
- El panel de inicio sigue siendo la biblioteca; *Novedades* es una página aparte.
- Sin firma de código de Windows (no hay certificado).

## 1.4.0

### Nuevo
- **Salud y mods** (Más acciones → *Salud y mods*): analiza los mods de una instancia leyendo sus metadatos
  (Fabric, Quilt, Forge y NeoForge, incluidos los mods anidados) y avisa de:
  dependencias faltantes o con versión incompatible, versión de Minecraft incompatible, cargador incorrecto,
  mods duplicados, incompatibilidades declaradas por el propio mod (`breaks`/`conflicts`) y archivos dañados.
  Distingue *confirmado*, *posible* y *aviso*. Dos mods instalados juntos nunca se marcan como incompatibles
  solo por estar juntos. El único arreglo automático es desactivar un duplicado (renombra a `.jar.disabled`,
  con confirmación y reversible).
- **Diagnóstico de instalación** en la misma página: instalación incompleta, bibliotecas faltantes, Java
  inexistente o demasiado antiguo, RAM asignada excesiva o insuficiente, ajustes inválidos y posibles
  descargas incompletas. Cada hallazgo dice qué es, qué consecuencia tiene y cómo solucionarlo. La única
  reparación automática restablece RAM y argumentos de Java inválidos, guardando antes `instance.json.bak-…`.
- **Respaldos**: cada respaldo guarda una suma SHA-256 de sus archivos, y la lista muestra fecha, tamaño,
  mundos, mods y si es automático. El botón *Verificar* comprueba la integridad. Los respaldos anteriores a
  1.4.0 aparecen como «sin suma de control».
- **Copias automáticas** (Ajustes → Respaldos): opcional, apagadas por defecto. Una vez al abrir Nova, hace
  una copia de las instancias sin respaldo reciente. No borra respaldos viejos.
- **Tema claro** opcional (Ajustes → Apariencia). El tema oscuro sigue siendo el predeterminado.

### Seguridad
- El receptor local del inicio de sesión de Microsoft solo acepta la redirección con el `state` esperado;
  una petición ajena ya no puede cortar ni arruinar un inicio de sesión en curso.
- El actualizador rechaza cualquier URL que no sea una descarga de release de GitHub por HTTPS, antes de
  hacer la primera petición. Se mantienen la firma del archivo, el tamaño máximo y la verificación SHA-256.
- Pruebas nuevas para ambas comprobaciones.

### Alcance real de las comprobaciones
Las pruebas automáticas cubren la lógica (análisis de mods, diagnóstico, respaldos, comprobaciones de
seguridad). No hay pruebas automáticas de la interfaz gráfica y el inicio de sesión de Microsoft no se
probó de punta a punta. Esto no es una auditoría de seguridad completa.

### Todavía no implementado en 1.4.0
Ver 1.5.0 para lo que se completó después.

## 1.3.1
- Corrige pantallas dentro de la ventana que se abrían y cerraban solas.

## 1.3.0
- Rediseño de la biblioteca, animaciones, pantallas dentro de la ventana y tiempo jugado.

## 1.2.0
- Cola de descargas, registro de errores, canal beta, módulos separados y Flatpak experimental.
