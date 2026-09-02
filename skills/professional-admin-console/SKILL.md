---
name: professional-admin-console
description: Build or redesign professional local admin consoles with scalable information architecture, data-dense catalogues, review workspaces, and verified frontend/backend delivery. Use for management dashboards, task queues, profile catalogues, approval consoles, or other internal tools; do not use for marketing sites or isolated UI components.
---

# Professional Admin Console

Build the console as a coherent product, not a collection of feature cards. Inspect the existing routes, data model, business invariants, dirty worktree, and runtime before changing code. Preserve unrelated user changes.

## Product structure

- Give the application a stable shell with a restrained navigation hierarchy and room for future modules.
- Let the sidebar identify the active module. Use one page H1 for the current task. Keep the top bar for global utilities or environment state, and show breadcrumbs only on genuinely nested pages.
- Remove repeated titles, synonyms, explanatory copy, filters, and controls. Keep text only when it changes a decision or prevents a likely mistake.
- Put creation flows on dedicated pages and complex review work in a focused full-screen workspace when that improves concentration.

## Data interaction

- Data catalogues must display useful records immediately. Search and filters narrow an existing list; do not make a filter selection the prerequisite for seeing data unless access isolation requires it.
- For potentially growing datasets, implement real backend pagination and return `items`, `total`, `page`, `page_size`, and `pages`. Do not fetch the full collection merely to paginate in the browser.
- Keep list endpoints lightweight. Return row summaries, then load detailed history, large manifests, or binary data on demand.
- Use human-readable names and status labels as the primary presentation. Keep opaque IDs available only as secondary diagnostic information.
- Show ongoing work with stage-specific progress and recoverable states. Users should be able to distinguish slow work from stalled work.

## Lifecycle and versions

When the domain has history or versioned artifacts:

- Make versions immutable. Switching versions updates only a current-version pointer and never deletes later versions.
- Keep enabled/disabled state separate from the current pointer. Disabling must preserve the selected version and all history.
- A fork from any historical version creates `MAX(existing version) + 1`, records its parent, and never overwrites the base.
- Make version details traceable to source files, timestamps, inputs, and the operation that created them. Do not invent missing metadata for legacy records.
- Label actions by their actual effect: prefer “版本”“设为当前”“停用”“从此版本创建新版” over destructive-sounding or implementation-specific names.

## Visual and interaction quality

- Use a restrained professional system: deliberate typography, consistent spacing, clear data hierarchy, fine borders, low-intensity shadows, and a small status palette.
- Prefer a stable icon library over text glyphs or mixed symbols. Distinguish primary, secondary, quiet, and destructive actions.
- Use tables for dense catalogues, drawers or detail routes for history, and focused multi-column layouts for review work. Keep responsive behavior intentional rather than simply stacking every card.
- Design empty, loading, error, disabled, and partial-data states with the same care as the happy path.

## Implementation and handoff

For implementation or refactoring, read [references/quality-gates.md](references/quality-gates.md). Keep frontend and backend contracts typed and test the actual business invariants, not generated wording.

Unless the user explicitly requests a commit, stage only the intended completed changes, do not run `git commit`, and provide one concise Conventional Commit message for review.
