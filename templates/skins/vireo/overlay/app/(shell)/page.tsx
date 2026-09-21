/*
 * Home. The template pointed this at its Sales dashboard; a generated project
 * opens on the thing it actually does.
 *
 * Screens live in src/screens, not src/pages — Next would treat a top-level
 * `pages/` directory as the legacy Pages Router. Route files stay thin
 * re-exports so the screen layer remains portable.
 */
export { Invoices as default } from '../../src/screens/invoices/Invoices';
