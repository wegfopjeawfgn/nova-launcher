# Firma de código de Windows

Estado: **el instalador no está firmado.** Windows SmartScreen puede advertir al abrirlo hasta que el archivo
gane reputación o esté firmado. Nova no inventa certificados ni firmas y no pide desactivar protecciones.

## Qué se puede hacer hoy
- Publicar siempre el SHA-256 junto al instalador (ya se hace) y explicar cómo comprobarlo (ver el README).
- Mantener la compilación en GitHub Actions: es el requisito habitual para poder firmar sin exponer claves.

## Camino recomendado: firma gratuita para proyectos de código abierto
Programas como **SignPath Foundation** ofrecen certificados de firma sin costo a proyectos abiertos. Piden,
entre otras cosas, una licencia de código abierto aprobada (Nova usa GPL-3.0-or-later), un repositorio público,
mantenimiento activo y una compilación reproducible en CI. Revisá los requisitos vigentes en el sitio del programa
antes de aplicar; la solicitud la tiene que hacer el titular del proyecto.

Pasos previos ya cubiertos: licencia abierta, repositorio público, compilación en GitHub Actions (`windows.yml`).

Pasos que faltan y no se pueden hacer desde el código:
1. Solicitar el certificado a nombre del proyecto o de su titular.
2. Conectar el workflow de Windows con el servicio de firma según sus instrucciones.
3. Verificar la firma en una PC con Windows real y actualizar este archivo y la web.

## Alternativa de pago
Un certificado de firma de código de una autoridad reconocida (por ejemplo un certificado OV/EV). Un certificado
EV suele evitar la advertencia de SmartScreen desde el primer día; uno estándar necesita ganar reputación.

## Prueba en una PC real
Pendiente: el instalador se prueba en un servidor de GitHub Actions (instalación, apertura de Nova y primer
arranque de Minecraft con renderizado por software). Falta documentar una prueba en una PC con GPU y audio.
