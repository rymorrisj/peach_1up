---
slug: /contributor-guide
---

# Contributor Guide

| Page | Covers |
|---|---|
| [Dev Setup](./dev-setup.mdx) | Clone, run, static verification, branch and PR workflow, key files |
| [Technology Stack](./tech-stack.mdx) | The stack and why each part was chosen, media detection, uploads, CI |
| [Security Architecture](./security.mdx) | Threat model, mandatory implementation rules, known limitations and gaps |
| [Auth Reference](./auth.mdx) | Token and cookie lifecycle, permission flags, middleware chain |
| [Windows Sandboxing](./windows-sandboxing.mdx) | Job Object and AppContainer isolation, resource caps, troubleshooting |
| [Emulator Reference](./emulators.mdx) | Per-emulator portable mode, required files, version coupling, limitations, licensing |
| [Alpha Tester Guide](./alpha-testing.mdx) | Installing the alpha, walking through every feature, known limitations, reporting bugs |

Read [Security Architecture](./security.mdx) before writing code that touches auth, path
handling, subprocess spawning, launch flows, disk image operations, settings, destructive
operations, network binding, or secrets. If an approach requires working around a rule in
it, stop and raise it instead of finding a workaround.
