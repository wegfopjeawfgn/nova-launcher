# Nova Launcher

Launcher de terceros para Minecraft Java Edition en Fedora y Windows. Gestiona instancias, mods de Modrinth, skins y respaldos desde una aplicación de escritorio.

Descargá el RPM y el archivo SHA-256 desde **Releases**. En la carpeta de descarga, ejecutá:

```bash
sha256sum -c nova-launcher-1.6.0-1.noarch.rpm.sha256
sudo dnf install ./nova-launcher-1.6.0-1.noarch.rpm
```

Después abrí **Nova Launcher** desde el menú de aplicaciones. El RPM se publica con SHA-256.

En Windows x64, descargá `nova-launcher-1.6.0-windows-x64-setup.exe` desde **Releases**, ejecutá el instalador y buscá **Nova Launcher** en Inicio.

Para publicar una versión, actualizá el spec y `actualizaciones.py`, creá una etiqueta estable `vX.Y.Z` y subila. El flujo de **Actions** genera el RPM con el canal de actualizaciones apuntando a este repositorio. Descargá el artefacto de Actions y adjuntá el RPM y el SHA-256 a una release de esa etiqueta. Nova consulta la última release estable.

El inicio de sesión con Microsoft requiere un ID de aplicación aprobado para Minecraft Services. Nova es un launcher de terceros, sin afiliación ni aprobación de Mojang o Microsoft.

## Licencia

Nova Launcher es software libre bajo la **GNU General Public License v3.0 o posterior** (`GPL-3.0-or-later`). Podés usarlo, estudiarlo, modificarlo y compartirlo; las versiones modificadas que distribuyas tienen que mantener esta misma licencia y su código fuente disponible. El texto completo está en [`LICENSE`](LICENSE) y los avisos de las dependencias en [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md). Minecraft es una marca de sus titulares y no se incluye.

## Windows: instalación y SmartScreen

El instalador de Windows todavía no tiene firma de código, así que Windows SmartScreen puede mostrar «Windows protegió su PC». Antes de ejecutarlo, comprobá que es el original:

```powershell
Get-FileHash .\nova-launcher-1.6.0-windows-x64-setup.exe -Algorithm SHA256
```

El resultado tiene que coincidir con el contenido del archivo `.sha256` de la release. Si coincide, elegí **Más información → Ejecutar de todos modos**. La situación de la firma está en [`packaging/windows/FIRMA.md`](packaging/windows/FIRMA.md).

La web está en `docs/`. En GitHub Pages, seleccioná **Deploy from a branch**, rama `main` y carpeta `/docs`. La página consulta la última release estable de GitHub y actualiza la descarga, el SHA-256 y los comandos de instalación. Si GitHub no está disponible, ofrece el RPM 1.6.0 incluido con la web.

## Flatpak (experimental)

`packaging/flatpak/io.nova.launcher.yml` describe el paquete Flatpak y el workflow **Compilar Flatpak** lo construye desde GitHub Actions. Todavía no se probó una instalación real.

## Desarrollo

Pruebas: `python3 -m unittest discover -s tests -t .` (no necesitan pantalla ni red). Los cambios de cada versión están en `CHANGELOG.md`.
