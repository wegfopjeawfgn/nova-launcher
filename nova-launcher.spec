Name:           nova-launcher
Version:        1.7.0
Release:        1
Summary:        Third-party launcher for Minecraft Java Edition
License:        GPL-3.0-or-later AND BSD-2-Clause
BuildArch:      noarch
Source0:        nova-launcher-%{version}.tar.gz
Source1:        minecraft_launcher_lib-8.0-py3-none-any.whl
AutoReqProv:    no
Requires:       python3
Requires:       python3-gobject
Requires:       python3-cairo
Requires:       python3-requests
Requires:       gtk4
Requires:       xdg-utils
Requires:       bash
Requires:       java-headless
BuildRequires:  python3

%description
Manage Minecraft Java instances, mods, skins, and backups from Fedora.

%prep
%setup -q -n nova-launcher

%build

%install
install -d %{buildroot}%{_datadir}/nova-launcher/{branding,icons,locales,vendor}
install -m644 *.py nova.css nova-light.css nova-logo.svg referencia.png canal.json LEEME.md %{buildroot}%{_datadir}/nova-launcher/
install -m644 branding/nova-loading.jar %{buildroot}%{_datadir}/nova-launcher/branding/
install -m644 icons/*.svg %{buildroot}%{_datadir}/nova-launcher/icons/
install -m644 locales/*.json %{buildroot}%{_datadir}/nova-launcher/locales/
%{__python3} -m zipfile -e %{SOURCE1} %{buildroot}%{_datadir}/nova-launcher/vendor/
install -Dpm755 iniciar-rpm.sh %{buildroot}%{_bindir}/nova-launcher
install -Dpm644 io.nova.launcher.desktop %{buildroot}%{_datadir}/applications/io.nova.launcher.desktop
install -Dpm644 nova-logo.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/io.nova.launcher.svg

%files
%license LICENSE THIRD_PARTY_LICENSES.md
%{_bindir}/nova-launcher
%{_datadir}/nova-launcher
%{_datadir}/applications/io.nova.launcher.desktop
%{_datadir}/icons/hicolor/scalable/apps/io.nova.launcher.svg

%changelog
* Sat Nov 14 2026 Nova Launcher <nova@localhost> - 1.7.0-1
- Redesign aligned with Nova Studios and import mods, packs and shaders from local files.

* Sat Nov 14 2026 Nova Launcher <nova@localhost> - 1.6.0-1
- Add Cuenta Nova sign-in through the Nova Studios site.

* Thu Nov 12 2026 Nova Launcher <nova@localhost> - 1.5.3-1
- Relicense as GPL-3.0-or-later and ship LICENSE and THIRD_PARTY_LICENSES.md.

* Thu Nov 12 2026 Nova Launcher <nova@localhost> - 1.5.2-1
- Add the home strip, installed Java picker, minimum memory and pyflakes in CI.

* Thu Nov 12 2026 Nova Launcher <nova@localhost> - 1.5.1-1
- Group the instance actions menu and make it scrollable.

* Thu Nov 12 2026 Nova Launcher <nova@localhost> - 1.5.0-1
- Add templates and profiles, server status, statistics, resumable downloads with speed, CurseForge search, news and a translation base.

* Thu Nov 12 2026 Nova Launcher <nova@localhost> - 1.4.0-1
- Add mod analysis, installation diagnosis, verified backups, optional light theme and security hardening.

* Thu Nov 12 2026 Nova Launcher <nova@localhost> - 1.3.1-1
- Fix in-window pages that opened and closed again when another page was opened or on a double click.

* Thu Nov 12 2026 Nova Launcher <nova@localhost> - 1.3.0-1
- Redesign the interface with in-window pages and motion, and track playtime per instance and in total.

* Thu Nov 12 2026 Nova Launcher <nova@localhost> - 1.2.0-1
- Add a download queue, error log and problem report, beta channel, redesigned interface and experimental Flatpak packaging.

* Wed Nov 11 2026 Nova Launcher <nova@localhost> - 1.1.0-1
- Harden data files, persist Microsoft login, add JVM arguments, download history and per-instance menu shortcuts.

* Sun Nov 08 2026 Nova Launcher <nova@localhost> - 1.0.0-1
- Add pack recovery, world tools, Prism import and platform support.

* Sun Nov 08 2026 Nova Launcher <nova@localhost> - 0.9.9-1
- Refine window controls and sidebar, and allow removing offline profiles.

* Sun Nov 08 2026 Nova Launcher <nova@localhost> - 0.9.8-1
- Add server shortcuts, separate secondary sessions and library filters.

* Sun Nov 08 2026 Nova Launcher <nova@localhost> - 0.9.7-1
- Improve pack import, portable ZIP export, diagnostics and updates.

* Sun Nov 08 2026 Nova Launcher <nova@localhost> - 0.9.6-1
- Refine library navigation, instance actions and settings layout.

* Sun Nov 08 2026 Nova Launcher <nova@localhost> - 0.9.5-1
- Mark installed mods, shaders, resource packs and tracked modpacks in Modrinth.

* Sun Nov 08 2026 Nova Launcher <nova@localhost> - 0.9.4-1
- Separate Modrinth and CurseForge import actions and file filters.

* Sun Nov 08 2026 Nova Launcher <nova@localhost> - 0.9.3-1
- Add settings to minimize or close Nova after Minecraft starts.

* Sun Nov 08 2026 Nova Launcher <nova@localhost> - 0.9.2-1
- Import CurseForge ZIP modpacks and verify referenced downloads.

* Sun Nov 08 2026 Nova Launcher <nova@localhost> - 0.9.1-1
- Reuse instance rows and decode catalog images as thumbnails.

* Sun Nov 08 2026 Nova Launcher <nova@localhost> - 0.9.0-2
- Configure the public GitHub release channel by default.

* Sun Nov 08 2026 Nova Launcher <nova@localhost> - 0.9.0-1
- Add Fedora desktop package and GitHub release notifications.
