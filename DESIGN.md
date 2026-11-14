---
name: Nova Launcher
description: Night-sky desktop launcher for Minecraft Java, part of the Nova Studios ecosystem.
colors:
  night: "#07080b"
  canvas: "#0b0d12"
  surface: "#10131a"
  raised: "#151a23"
  control: "#181d27"
  hover: "#212836"
  hairline: "#1d222c"
  hairline-strong: "#2c3341"
  starlight-ink: "#eef0f5"
  dust-ink: "#a9aebb"
  faint-ink: "#8189a0"
  ion-cyan: "#8fd6e8"
  ion-cyan-hover: "#b4e7f3"
  ion-cyan-dim: "#0f2830"
  ion-ink: "#06161b"
  starlight-warm: "#f1d49b"
  coral-danger: "#ffa99a"
typography:
  display:
    fontFamily: "Archivo, ui-sans-serif, system-ui, sans-serif"
    fontSize: "clamp(2.6rem, 5.6vw, 4.5rem)"
    fontWeight: 650
    lineHeight: 0.98
    letterSpacing: "-0.035em"
    fontVariation: "'wdth' 120"
  body:
    fontFamily: "Archivo, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.0625rem"
    lineHeight: 1.6
  label:
    fontFamily: "Martian Mono, ui-monospace, monospace"
    fontSize: "0.74rem"
    letterSpacing: "0.04em"
rounded:
  card: "14px"
  field: "10px"
  pill: "999px"
components:
  button-primary:
    backgroundColor: "{colors.ion-cyan}"
    textColor: "{colors.ion-ink}"
    rounded: "{rounded.pill}"
    height: "52px"
  shelf-tile:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.card}"
---

# Design System: Nova Launcher

## Overview

**North star: the same night sky as Nova Studios, with one cyan star of its own.** The desktop app is an Operate surface (system sans, quiet, scannable); the website is a Persuade surface (Archivo expanded, a star field and the light curve as signature line). Both share the palette.

## Colors

Restrained. Night-black ground with tonal steps (`canvas` → `surface` → `raised` → `control` → `hover`) and hairlines instead of shadows. **Ion cyan** is the only accent: primary action, selection, focus ring, the active nav item. `starlight-warm` marks warnings and review notes; `coral-danger` marks errors. Light theme keeps the same roles with cool neutrals and a deeper teal accent `#0e7490` (5.4:1 on white). All text pairs are at least 4.5:1.

## Typography

Website: Archivo (variable width axis) for everything, expanded for display; Martian Mono only for versions, file types and commands. App: the system sans stack, tabular figures, weights 600–700 for titles with slight negative tracking.

## Layout

App: fixed sidebar (176px), library with a status row, a hero banner, a content shelf per kind (count + Explorar / Importar), then the instance grid. Forms are titled sections of rows (name and help left, control right) with their own scroll and a fixed footer. Website: rows separated by hairlines instead of cards; screenshots in a 16px-radius frame.

## Elevation & Depth

Flat. Only the hero banner and website screenshots carry a soft, offset shadow. No coloured halos.

## Components

- **Shelf tile**: a button with the count (opens the installed list) over two quiet actions.
- **Status row**: one hairline-divided strip, not four cards.
- **Import review**: rows with a checkbox, name, kind, size and a warm note when something is off; refused files explain why.
- **Drop overlay**: dashed ion-cyan card over a dimmed window.
- **Form row**: 18px gap, hint under the label in `faint-ink`.

## Do's and Don'ts

- Do keep one primary action per view.
- Do explain why a file was refused.
- Don't add kickers, gradient text, glass cards or section numbers.
- Don't use cyan for decoration; it means "act here" or "selected".
