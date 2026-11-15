# Política de firma de código

Los instaladores de Windows de Nova Launcher se firman con un certificado gratuito para proyectos de código abierto:

> Firma de código gratuita proporcionada por [SignPath.io](https://about.signpath.io/), certificado de [SignPath Foundation](https://signpath.org/).

## Qué se firma

Solo el instalador de Windows (`nova-launcher-<versión>-windows-x64-setup.exe`) generado por el flujo de GitHub Actions de este repositorio, a partir del código fuente público y de una etiqueta de versión (`v*`). Nada se firma desde una computadora personal.

## Roles

| Rol | Quién |
|---|---|
| Autor y revisor del código | [wegfopjeawfgn](https://github.com/wegfopjeawfgn) |
| Aprobador de cada firma | [wegfopjeawfgn](https://github.com/wegfopjeawfgn) |

Cada firma la aprueba a mano el aprobador, después de revisar que el instalador salió del flujo público de este repositorio.

## Privacidad

Nova Launcher solo se conecta a Internet para lo que la persona pide o activa:

- **GitHub**: buscar actualizaciones de Nova y descargar Pomme (opcional, con comprobación SHA-256).
- **Modrinth y CurseForge**: buscar y descargar mods, shaders, texturas y modpacks.
- **Mojang y Microsoft**: iniciar sesión y descargar Minecraft.
- **Nova Studios** (`studiosnova.vercel.app`): iniciar sesión con la cuenta Nova, solo si la persona lo hace.
- **Conteo de instalaciones (opcional)**: apagado hasta que la persona lo acepta. Una vez al día envía un número al azar, la versión de Nova y el sistema (Linux o Windows). No envía nombre, cuenta, dirección IP guardada ni datos de instancias. Se apaga en Ajustes y borra ese número.

Nova Launcher no es un producto de Mojang ni de Microsoft.

## Reportar un problema

Abrí un issue en <https://github.com/wegfopjeawfgn/nova-launcher/issues>.
