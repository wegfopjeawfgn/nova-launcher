Name:           nova-launcher
Version:        0.9.1
Release:        1
Summary:        Third-party launcher for Minecraft Java Edition
License:        LicenseRef-Nova AND BSD-2-Clause
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
install -d %{buildroot}%{_datadir}/nova-launcher/{branding,icons,vendor}
install -m644 *.py nova.css nova-logo.svg referencia.png canal.json LEEME.md %{buildroot}%{_datadir}/nova-launcher/
install -m644 branding/nova-loading.jar %{buildroot}%{_datadir}/nova-launcher/branding/
install -m644 icons/*.svg %{buildroot}%{_datadir}/nova-launcher/icons/
%{__python3} -m zipfile -e %{SOURCE1} %{buildroot}%{_datadir}/nova-launcher/vendor/
install -Dpm755 iniciar-rpm.sh %{buildroot}%{_bindir}/nova-launcher
install -Dpm644 io.nova.launcher.desktop %{buildroot}%{_datadir}/applications/io.nova.launcher.desktop
install -Dpm644 nova-logo.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/io.nova.launcher.svg

%files
%{_bindir}/nova-launcher
%{_datadir}/nova-launcher
%{_datadir}/applications/io.nova.launcher.desktop
%{_datadir}/icons/hicolor/scalable/apps/io.nova.launcher.svg

%changelog
* Sun Nov 08 2026 Nova Launcher <nova@localhost> - 0.9.1-1
- Reuse instance rows and decode catalog images as thumbnails.

* Sun Nov 08 2026 Nova Launcher <nova@localhost> - 0.9.0-2
- Configure the public GitHub release channel by default.

* Sun Nov 08 2026 Nova Launcher <nova@localhost> - 0.9.0-1
- Add Fedora desktop package and GitHub release notifications.
