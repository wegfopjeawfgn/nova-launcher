# Nova Launcher 0.9.5 para Fedora

Descomprimí el ZIP y ejecutá `./iniciar.sh` desde la carpeta `nova-launcher`.
Si faltan dependencias de Fedora, instalalas con:

```bash
sudo dnf install python3-gobject python3-cairo gtk4 python3-pip xdg-utils
```

- **Nueva instancia → Personalizada** permite elegir una versión del catálogo de Mojang, incluidas snapshots, alfa y beta, y un cargador compatible. Con **Consultar builds** podés elegir una compilación concreta de Fabric, Forge, NeoForge o Quilt.
- Seleccioná una instancia y abrí **Mods**, **Shaders** o **Texturas** desde su ficha para instalar contenido directamente en esa instancia.
- **Nueva instancia → Buscar un modpack** instala un pack de Modrinth y selecciona la instancia recién creada.
- **Explorar** busca en Modrinth. Los mods se filtran por versión y loader. Nova descarga las dependencias obligatorias que Modrinth declara para esos mods. Para activar los shaders dentro del juego necesitás un mod compatible, como Iris.
- **Modpacks** se instalan en instancias separadas, con las versiones fijadas por el pack. **Importar pack** admite archivos locales `.mrpack` de Modrinth y `.zip` exportados desde CurseForge con `manifest.json`. Se instalan los archivos obligatorios para el cliente. Si el ZIP referencia archivos de CurseForge, ingresá una clave de su API en el importador o configurá `CURSEFORGE_API_KEY`. Nova no guarda la clave que ingresás en el diálogo.
- **Ajustes** define la memoria predeterminada de nuevas instancias y una ruta opcional de Java. **Editar instancia** permite ajustar la RAM y Java de una instalación concreta.
- El menú **Cuentas** permite crear y cambiar perfiles offline para partidas locales.
- **Contenido instalado** administra los archivos descargados individualmente por Nova. **Ver registro** abre el log del último inicio.

El primer arranque de una versión requiere Internet. Las versiones antiguas pueden necesitar una ruta a Java compatible. El catálogo muestra lo publicado por Mojang y la compatibilidad de cada combinación depende del loader y del cliente.

Los datos de Nova 0.1 se conservan en `${XDG_DATA_HOME:-~/.local/share}/nova-launcher`.

En **Mods → Instalados** podés activar y desactivar mods, y consultar actualizaciones de los mods descargados por Nova. **Ver registro** abre una consola que se actualiza mientras Minecraft está abierto y señala errores comunes de Java, memoria y dependencias.

**Skins** guarda PNG de 64 × 64 por perfil y abre la galería de Planet Minecraft en el navegador. Importá el PNG descargado para editarlo o exportalo para usarlo en un cliente compatible.

**Cuentas → Conectar Microsoft** requiere un ID de aplicación aprobado para Minecraft Java y una redirección registrada en `http://localhost:8765`. Después de iniciar sesión en el navegador, copiá la URL de redirección y pegala en Nova. La cuenta queda conectada mientras Nova esté abierto.

**Mods → Instalados → Buscar actualizaciones** ofrece actualizar los mods administrados por Nova y volver al archivo anterior. Las dependencias nuevas que requiera una actualización se conservan al revertir.

**Skins → Equipar en la instancia** instala CustomSkinLoader si hace falta y guarda la skin para el perfil offline. **Comunidad** abre Planet Minecraft dentro de Nova si WebKitGTK está disponible. También podés abrir el sitio en tu navegador.

**Pantalla de carga Nova** habilita el logo y los colores al iniciar Minecraft 1.21.11 con Fabric. Para otras versiones compatibles con Dark Loading Screen, el botón aplica los colores.

El RPM instala Nova en el menú de aplicaciones de Fedora e incluye la biblioteca del launcher. Para instalar desde la terminal, usá `sudo dnf install ./nova-launcher-0.9.5-1.noarch.rpm`. Después buscá **Nova Launcher** en el menú.

Para conectar GitHub Releases, escribí `usuario/repositorio` en **Ajustes → Actualizaciones**. Antes de compilar el RPM para tus usuarios, poné ese valor en `canal.json`. Usá etiquetas estables como `v0.9.0` y adjuntá el RPM y su SHA-256 a cada release. Nova revisa las versiones al abrirse y ofrece el enlace de descarga cuando encuentra una más nueva.

Nova es un launcher de terceros para Minecraft Java Edition, sin afiliación con Mojang o Microsoft.

Para reconstruir el RPM en Fedora con `rpm-build` instalado, prepará `~/rpmbuild/SOURCES` y guardá ahí el archivo `nova-launcher-0.9.5.tar.gz` con la carpeta `nova-launcher` en su raíz y el wheel `minecraft_launcher_lib-8.0-py3-none-any.whl`. Ejecutá `rpmbuild -bb nova-launcher.spec`. Para cada versión nueva, actualizá la versión del spec y de `actualizaciones.py` antes de empaquetar.

Los respaldos locales aparecen en **Respaldos**. Al restaurar, Nova crea una instancia separada. Los respaldos comparten la portada guardada en la biblioteca local de Nova.
