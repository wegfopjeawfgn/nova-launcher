# Cambios

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
