import fs from 'node:fs';
import path from 'node:path';

/**
 * Never worth copying into a generated project.
 *
 * The celerybeat schedule files are the ones that bite: they are runtime state
 * written next to the source, and carrying one across means a fresh project
 * inherits another project's idea of when its jobs last ran.
 */
const ALWAYS_SKIP = new Set([
  'node_modules',
  '.next',
  '.git',
  'out',
  'dist',
  '__pycache__',
  '.venv',
  'staticfiles',
  'celerybeat-schedule',
  'celerybeat-schedule-shm',
  'celerybeat-schedule-wal',
]);

export function copyTree(from, to, { skip = [] } = {}) {
  const skipSet = new Set([...ALWAYS_SKIP, ...skip]);
  let copied = 0;

  function walk(src, dest) {
    for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
      if (skipSet.has(entry.name)) continue;

      const srcPath = path.join(src, entry.name);
      const destPath = path.join(dest, entry.name);

      if (entry.isDirectory()) {
        fs.mkdirSync(destPath, { recursive: true });
        walk(srcPath, destPath);
      } else if (entry.isFile()) {
        fs.mkdirSync(path.dirname(destPath), { recursive: true });
        fs.copyFileSync(srcPath, destPath);
        copied += 1;
      }
    }
  }

  fs.mkdirSync(to, { recursive: true });
  walk(from, to);
  return copied;
}

/**
 * Remove paths listed by a skin's prune list.
 *
 * A missing path is reported rather than ignored: a prune list that has
 * drifted from the template it targets fails loudly here instead of leaving
 * demo pages in a client's project.
 */
export function prune(root, patterns) {
  const missing = [];
  let removed = 0;

  for (const pattern of patterns) {
    const target = path.join(root, pattern);
    if (!fs.existsSync(target)) {
      missing.push(pattern);
      continue;
    }
    fs.rmSync(target, { recursive: true, force: true });
    removed += 1;
  }

  return { removed, missing };
}

/**
 * Keep only the named entries inside a directory, removing the rest.
 *
 * Templates ship hundreds of demo screens; listing what to keep is shorter and
 * far more robust than listing what to delete.
 */
export function keepOnly(dir, keep) {
  if (!fs.existsSync(dir)) return { removed: 0, missing: keep };

  const keepSet = new Set(keep);
  const present = new Set(fs.readdirSync(dir));
  let removed = 0;

  for (const entry of present) {
    if (keepSet.has(entry)) continue;
    fs.rmSync(path.join(dir, entry), { recursive: true, force: true });
    removed += 1;
  }

  return { removed, missing: keep.filter((name) => !present.has(name)) };
}

/**
 * Replace text in a file, refusing when the anchor is absent.
 *
 * A silent no-op patch is how a generated project ends up still loading fonts
 * from the network or still branded with the template's own name.
 */
export function patchFile(filePath, replacements) {
  if (!fs.existsSync(filePath)) {
    throw new Error(`Patch target missing: ${filePath}`);
  }

  let content = fs.readFileSync(filePath, 'utf8');

  for (const { find, replace, optional = false } of replacements) {
    if (!content.includes(find)) {
      if (optional) continue;
      throw new Error(
        `Patch anchor not found in ${filePath}:\n  ${find.slice(0, 120)}`,
      );
    }
    content = content.split(find).join(replace);
  }

  fs.writeFileSync(filePath, content, 'utf8');
}

export function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

export function writeJson(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
}
