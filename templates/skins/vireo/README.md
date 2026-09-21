# Skin: Vireo

An adapter, not a template. Vireo ships under an **Envato Regular License**,
which covers one end product and does not permit redistributing the source, so
this directory holds only the instructions for transforming a copy you licensed
yourself.

```
skins-src/vireo/     <- your licensed copy goes here (git-ignored)
```

The generator refuses to run without it and says where to put it.

## Why this skin

Four runtime dependencies. A genuine three-layer token system — primitives,
role aliases, recipes — with twelve accents across light and dark, thirteen
layout dimensions, RTL, and a localStorage wrapper that never throws. And **not
a single `fetch` in the entire template**, which makes it clean ground for the
offline core rather than something to unpick.

## What the adapter does

**Prunes 64 directories.** The template ships 190 demo screens and 186 route
files. What survives is the shell, the token system, the error pages and one
blank scaffold. Pruning `src/screens/maps` also removes the template's one
build blocker: it imports `leaflet/dist/leaflet.css` while `leaflet` appears in
neither `package.json` nor the lockfile, so the template does not build as
shipped.

**Self-hosts the fonts.** `app/layout.tsx` loaded Inter, Space Grotesk and
JetBrains Mono from Google on every visit. An offline-first first paint cannot
wait on a third-party CDN — in the field that is the request most likely to
hang rather than fail fast. They now come through `next/font`, downloaded once
at build time and served from the app's own origin.

**Rebrands.** The wordmark, the logo gradient and the home-route mapping were
hardcoded to the template's own identity.

**Wires the core.** A provider, an entity store, an invoices screen written in
the template's own `.ax-*` primitives, and a sign-in form that actually
authenticates — the template's auth pages are static markup.

**Replaces the navigation.** One file, `src/data/nav-manifest.json`, feeds the
sidebar, the breadcrumbs, the menu filter and the command palette. Adding a
page is an entry there plus a route file.

## What it does not do

There is no component library underneath. `src/components/ui/` holds two files;
everything else is 416 CSS classes in `src/styles/components.css`. You write
`<div className="ax-card">`, not `<Card>`. The overlay screens show the idiom,
but a project with many pages will want a primitives layer over those classes —
that is the first thing to build on top of this adapter, and it does not exist
yet.

Routes that exist in the manifest but have no page file fall through to the
template's catch-all and render a placeholder. That is deliberate: the
navigation can describe the whole application before the application exists.
