# Nova Launcher

Launcher de terceros para Minecraft Java Edition en Fedora. Gestiona instancias, mods de Modrinth, skins y respaldos desde una aplicación de escritorio.

Descargá el RPM y el archivo SHA-256 desde **Releases**. En la carpeta de descarga, ejecutá:

```bash
sha256sum -c nova-launcher-0.9.7-1.noarch.rpm.sha256
sudo dnf install ./nova-launcher-0.9.7-1.noarch.rpm
```

Después abrí **Nova Launcher** desde el menú de aplicaciones. El RPM de 0.9.0 todavía está sin firma.

Para publicar una versión, actualizá el spec y `actualizaciones.py`, creá una etiqueta estable `vX.Y.Z` y subila. El flujo de **Actions** genera el RPM con el canal de actualizaciones apuntando a este repositorio. Descargá el artefacto de Actions y adjuntá el RPM y el SHA-256 a una release de esa etiqueta. Nova consulta la última release estable.

El inicio de sesión con Microsoft requiere un ID de aplicación aprobado para Minecraft Services. El repositorio debe incluir la licencia que el titular elija antes de distribuir el código públicamente.

Nova es un launcher de terceros, sin afiliación ni aprobación de Mojang o Microsoft.

La web está en `docs/`. En GitHub Pages, seleccioná **Deploy from a branch**, rama `main` y carpeta `/docs`. La página consulta la última release estable de GitHub y actualiza la descarga, el SHA-256 y los comandos de instalación. Si GitHub no está disponible, ofrece el RPM 0.9.7 incluido con la web.
