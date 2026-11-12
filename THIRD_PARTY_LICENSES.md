# Licencias de terceros

Nova Launcher se distribuye bajo GPL-3.0-or-later (ver `LICENSE`). Usa y, en algunos paquetes, incluye el
software de terceros que se lista acá. Esta lista es informativa y no reemplaza los avisos de cada proyecto.

| Componente | Licencia | Dónde se usa |
| --- | --- | --- |
| minecraft-launcher-lib | BSD-2-Clause (texto completo abajo) | Incluida en el RPM y en el instalador de Windows |
| requests y sus dependencias (urllib3, idna, certifi, charset-normalizer) | Apache-2.0, MIT, BSD-3-Clause y MPL-2.0 según el paquete | Incluidas en el instalador de Windows; en Fedora vienen del sistema |
| GTK 4, PyGObject y Cairo | LGPL-2.1-or-later | Del sistema en Fedora; incluidas en el runtime del instalador de Windows |
| Python | PSF-2.0 | Del sistema en Fedora; incluido en el runtime del instalador de Windows |

El runtime de Windows se arma con paquetes de MSYS2 (UCRT64), cada uno con su propia licencia, que se
distribuye junto a sus archivos. Minecraft es una marca de sus titulares; Nova no incluye ni redistribuye el juego.

## minecraft-launcher-lib 8.0 (BSD-2-Clause)

```text
BSD 2-Clause License

Copyright (c) 2019-2025, JakobDev
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```
