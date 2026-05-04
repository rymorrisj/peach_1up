# CONSIDERATION

## Current Direction

Peach 1UP should continue as an open-source, BYO-media launcher and orchestration layer for legacy PC software and selected first-generation console platforms. The project should not attempt to replace or reimplement emulators. Its job is to hide emulator complexity behind a clean profile, platform, and media workflow.

## Product Positioning

The project should be treated as a preservation and usability tool for people who own old media and want to keep using it. The audience is broader than developers, but still consists of enthusiasts, collectors, archivists, parents, educators, and users willing to provide their own media, BIOS, and operating system assets.

The value proposition is simple:

- Bring old software and media back to life.
- Make emulator and VM setup far easier.
- Keep the process safe, repeatable, and recoverable.
- Support broad use cases first, not obscure one-offs.

## Core Technical Direction

The internal architecture should use a clean adapter-style API around each emulator backend. That API should normalize common actions such as:

- Register platform or operating system.
- Attach media.
- Create or restore runtime state.
- Launch profile.
- Apply safe defaults.
- Report errors consistently.

This should remain an internal abstraction layer, not a universal external standard.

## Recommended P2 Direction

P2 should move away from per-game 86Box machine generation and toward a shared platform model.

The correct model is:

- One base OS image per major Windows era.
- One working image derived from that base.
- Game profiles linked to a registered OS platform.
- Media attached to the platform at launch time.
- Optional snapshots for recovery before risky installs or changes.

This better matches how Windows 95, 98, and XP software actually behaves and avoids the cost and friction of creating a separate full OS install for every game or application.

## OS Platform Model

An OS platform should become a first-class concept in the codebase.

Each platform should track at minimum:

- Platform name.
- Era or target OS.
- Emulator backend.
- Emulator config path.
- Base image path.
- Working image path.
- Snapshot metadata.
- Notes and status.

Game and software profiles should reference a platform instead of owning a fully isolated machine definition.

## State Management

Shared OS state is acceptable if recovery is designed in from the start.

The project should use this pattern:

- Base image: pristine, never modified after setup.
- Working image: the active OS used for installs and launches.
- Snapshots: optional restorable copies created before risky changes.

This makes recovery fast and keeps reinstalling the operating system from becoming the default failure path.

## Data Safety

Data loss is unacceptable as a normal recovery strategy.

The project should be designed so users can:

- Restore a working image from a known-good snapshot.
- Reset to the base image only as an explicit last resort.
- Understand clearly what will be lost before destructive actions.

Longer-term consideration:

- Add save-data backup and restore support where practical.
- Add lightweight health indicators for platforms.
- Warn users before risky operations such as major runtime installs.

## UX Direction

The UX goal should remain ambitious.

The project should aim to make legacy software setup much easier than current enthusiast workflows, while accepting that full automation will not be possible for every title. The right balance is:

- Smooth first-run setup.
- Strong defaults.
- Clear error messages.
- Explicit recovery options.
- Honest boundaries for unsupported edge cases.

The product should target the broadest repeatable workflows, not infinite compatibility.

## Legal and Distribution Guardrails

The project should remain clean and defensible by following these rules:

- Do not ship ROMs, ISOs, BIOS files, or operating system images.
- Do not bundle or fetch copyrighted content.
- Require users to provide their own media and assets.
- Keep the project focused on tooling, automation, and preservation workflows.

Open source plus donationware is a better fit than planning around commercial distribution.

## Immediate Scope Priorities

The next implementation work should focus on:

1. Introduce an `OSPlatform` concept into the data model.
2. Refactor P2 scope around shared OS platforms instead of per-game 86Box instances.
3. Build platform registration and validation flows.
4. Add media attachment logic for 86Box launches.
5. Implement base image and working image handling.
6. Add manual snapshot creation and restore support.
7. Keep guest-side automation minimal until core platform flows are stable.

## Scope Boundaries

The project should not do the following right now:

- Reimplement or fork emulators.
- Build a universal emulator translation standard.
- Promise support for rare one-off edge cases.
- Expand platform scope faster than the core architecture can support.
- Add advanced console support before PC platform state management is solid.

## Strategic Summary

Peach 1UP should continue, but with tighter architecture and clearer boundaries.

The project should be treated as:

- A preservation-first launcher.
- A usability layer over existing emulators.
- A shared-platform system for Windows-era software.
- A recoverable environment built around base images, working copies, and snapshots.
- An open-source tool that favors practical workflows over total abstraction.
