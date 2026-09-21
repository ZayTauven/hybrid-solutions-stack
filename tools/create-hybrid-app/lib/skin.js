import fs from 'node:fs';
import path from 'node:path';

import { readJson } from './fs-utils.js';

/**
 * A skin is an adapter, not a template.
 *
 * Vireo and Cuba ship under commercial licences that do not permit
 * redistribution, so this repository holds only the instructions for
 * transforming a copy you licensed yourself. `skins-src/` is where that copy
 * goes, and it is git-ignored.
 */
export function loadSkin(repoRoot, name) {
  const skinDir = path.join(repoRoot, 'templates', 'skins', name);
  const manifestPath = path.join(skinDir, 'skin.json');

  if (!fs.existsSync(manifestPath)) {
    const available = listSkins(repoRoot);
    throw new Error(
      `Unknown skin "${name}". Available: ${available.join(', ') || 'none'}`,
    );
  }

  const manifest = readJson(manifestPath);
  return { ...manifest, name, dir: skinDir };
}

export function listSkins(repoRoot) {
  const skinsDir = path.join(repoRoot, 'templates', 'skins');
  if (!fs.existsSync(skinsDir)) return [];

  return fs
    .readdirSync(skinsDir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .filter((entry) =>
      fs.existsSync(path.join(skinsDir, entry.name, 'skin.json')),
    )
    .map((entry) => entry.name);
}

/**
 * Locate the skin's source tree and prove it is the one the adapter targets.
 *
 * A prune list written against one release of a template silently leaves demo
 * pages behind when run against another, so the adapter names files it expects
 * to find and we check them before touching anything.
 */
export function resolveSource(repoRoot, skin) {
  if (skin.source?.vendored) {
    // The minimal skin lives in this repository: it is ours to ship.
    return path.join(skin.dir, skin.source.vendored);
  }

  const sourceDir = path.join(repoRoot, 'skins-src', skin.source.path);

  if (!fs.existsSync(sourceDir)) {
    throw new Error(
      [
        `The "${skin.name}" skin needs its licensed source, which is not in this repository.`,
        '',
        `  Expected at: ${sourceDir}`,
        `  Licence:     ${skin.source.license ?? 'commercial'}`,
        '',
        'Drop your licensed copy there and run this again.',
      ].join('\n'),
    );
  }

  const missing = (skin.source.requires ?? []).filter(
    (relative) => !fs.existsSync(path.join(sourceDir, relative)),
  );

  if (missing.length) {
    throw new Error(
      [
        `The source at ${sourceDir} is not the release this adapter targets.`,
        'Missing files the adapter depends on:',
        ...missing.map((entry) => `  - ${entry}`),
      ].join('\n'),
    );
  }

  return sourceDir;
}
