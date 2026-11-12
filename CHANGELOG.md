# Cambios

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

### Todavía no implementado (candidato a 1.5.0)
- Perfiles y plantillas por tipo de juego, y su exportación como perfil.
- Estado de servidores (consulta con límite de tiempo y protección contra redes internas).
- Estadísticas ampliadas (tiempo de inicio, historial de sesiones, uso de memoria). Hoy solo existe el
  tiempo jugado por instancia y total.
- Reanudar descargas, velocidad y tiempo estimado.
- Búsqueda en CurseForge mediante su API oficial.
- Panel de inicio con noticias, y base para traducciones.
- Firma de código de Windows (no hay certificado disponible).

## 1.3.1
- Corrige pantallas dentro de la ventana que se abrían y cerraban solas.

## 1.3.0
- Rediseño de la biblioteca, animaciones, pantallas dentro de la ventana y tiempo jugado.

## 1.2.0
- Cola de descargas, registro de errores, canal beta, módulos separados y Flatpak experimental.
