# Skin: minimal

The reference skin. Plain CSS, no design system, no component library, no demo
content — roughly a thousand lines in total.

It exists for two reasons. It proves `@hybrid/offline-core` runs detached from
any particular design system, which is the claim the Vireo and Cuba adapters
rest on. And it is the thing to read when something in a generated project
misbehaves and you need to see the offline-first machinery without a dashboard
template in the way.

## What it demonstrates

- Login against `/api/auth/login`, with the session persisted so a reload does not sign you out
- An entity store in 30 lines (`lib/stores/invoices.ts`) — versioning, tombstones and conflict-safe merging all come from the core
- Local edits that survive going offline, pushed when the network returns
- Sync state, pending count and the conflict queue, surfaced rather than hidden

## Unlike the other skins

This one ships in the repository, so `skin.json` marks its source as
`vendored`. Vireo and Cuba are licensed elsewhere and their adapters read from
`skins-src/`.

It declares no `layouts`, so the generator draws only a palette and a shape for
it. Two projects generated on this skin differ in colour and in corner radius,
not in structure — which is honest, because there is only one structure here.
