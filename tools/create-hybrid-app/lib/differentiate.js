/**
 * What stops two projects from the same skin looking like the same project.
 *
 * A generator that only copies files produces a portfolio of identical
 * dashboards with different logos. The draw below is deterministic from the
 * project seed, so a given name always yields the same identity -- rerunning
 * the generator does not reshuffle a client's brand.
 */

/** Mulberry32: small, seedable, good enough for picking from short lists. */
function makeRandom(seedText) {
  let hash = 1779033703 ^ seedText.length;
  for (let i = 0; i < seedText.length; i += 1) {
    hash = Math.imul(hash ^ seedText.charCodeAt(i), 3432918353);
    hash = (hash << 13) | (hash >>> 19);
  }

  let state = hash >>> 0;
  return function random() {
    state |= 0;
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Accent pairs, kept deliberately far apart in hue.
 *
 * Picking randomly from a set of near-identical blues would defeat the point,
 * so these are spread across the wheel and each carries a contrasting
 * secondary rather than a tint of itself.
 */
export const PALETTES = [
  { id: 'teal', primary: '#0F8A7E', secondary: '#E07A3C', label: 'Teal / ember' },
  { id: 'indigo', primary: '#4B49C6', secondary: '#E8A33D', label: 'Indigo / amber' },
  { id: 'forest', primary: '#2F6F4E', secondary: '#C2643B', label: 'Forest / clay' },
  { id: 'plum', primary: '#7A3E8F', secondary: '#4FB3A3', label: 'Plum / mint' },
  { id: 'ocean', primary: '#1D6FA5', secondary: '#E2724D', label: 'Ocean / coral' },
  { id: 'rust', primary: '#B4552D', secondary: '#3E7C8C', label: 'Rust / steel' },
  { id: 'olive', primary: '#5E7A2E', secondary: '#9C4F7A', label: 'Olive / magenta' },
  { id: 'slate', primary: '#42566B', secondary: '#D08A2C', label: 'Slate / brass' },
  { id: 'crimson', primary: '#A8324A', secondary: '#3F8A6E', label: 'Crimson / jade' },
  { id: 'cobalt', primary: '#2B4FA8', secondary: '#D9713F', label: 'Cobalt / apricot' },
];

/** Density and shape choices that read as different design decisions. */
export const SHAPES = [
  { id: 'soft', radius: '12px', density: 'comfortable' },
  { id: 'sharp', radius: '4px', density: 'compact' },
  { id: 'rounded', radius: '18px', density: 'comfortable' },
  { id: 'square', radius: '2px', density: 'compact' },
];

function pick(random, list) {
  return list[Math.floor(random() * list.length)];
}

/**
 * A lighter cousin of the accent, for dark backgrounds.
 *
 * The palettes above are chosen for contrast against light surfaces. Reusing
 * them unchanged in dark mode puts a dark green on a near-black panel, which
 * is unreadable — and reusing the template's own dark accent would erase the
 * brand exactly where it is most visible.
 */
function lighten(hex, amount = 0.45) {
  const value = parseInt(hex.slice(1), 16);
  const channels = [(value >> 16) & 255, (value >> 8) & 255, value & 255];

  const lifted = channels.map((channel) =>
    Math.round(channel + (255 - channel) * amount),
  );

  return `#${lifted.map((c) => c.toString(16).padStart(2, '0')).join('')}`;
}

/**
 * Draw one project identity.
 *
 * `layouts` comes from the skin: Vireo exposes thirteen layout dimensions,
 * Cuba twelve named variants, and the minimal skin none at all. The generator
 * does not need to know which -- it draws from whatever the adapter declares.
 */
export function drawIdentity({ seed, layouts = [], assets = [] }) {
  const random = makeRandom(seed);
  const palette = pick(random, PALETTES);

  return {
    seed,
    palette: {
      ...palette,
      primaryDark: lighten(palette.primary),
      secondaryDark: lighten(palette.secondary, 0.3),
    },
    shape: pick(random, SHAPES),
    layout: layouts.length ? pick(random, layouts) : null,
    assets: assets.length ? pickAssets(random, assets) : null,
  };
}

/**
 * One coherent asset set rather than four unrelated pictures.
 *
 * Drawing each slot independently from the whole bank produces a login
 * background from one visual world and an empty state from another.
 */
function pickAssets(random, assets) {
  const byCategory = new Map();
  for (const asset of assets) {
    const bucket = byCategory.get(asset.category) ?? [];
    bucket.push(asset);
    byCategory.set(asset.category, bucket);
  }

  const chosen = {};
  for (const [category, bucket] of byCategory) {
    chosen[category] = pick(random, bucket);
  }
  return chosen;
}
