# Peach 1UP — Decision Log

| Date       | Decision                                     | Why                                                                     |
| ---------- | -------------------------------------------- | ----------------------------------------------------------------------- |
| 2026-04-15 | Docker over VirtualBox                       | Cross-platform end goal, Windows Home blocks Sandbox and Hyper-V        |
| 2026-04-15 | Linux containers over Windows containers     | Better emulator support, smaller images, broader community              |
| 2026-04-15 | VcXsrv for display forwarding                | Simplest X server for Windows, free, open source, automatable later     |
| 2026-04-15 | DOSBox-X for DOS and Win 3.1                 | No ROM requirement, works immediately, strong DOS accuracy              |
| 2026-04-15 | 86Box for Win 95 / 98 / XP                   | Most accurate full hardware emulation for that era, actively maintained |
| 2026-04-15 | No persistence in P0                         | Testing phase, simplifies container lifecycle, persistence in P1+       |
| 2026-04-15 | Disk images only in P0                       | Physical drive passthrough adds complexity, moved to P2                 |
| 2026-04-15 | Textual for TUI                              | Keyboard-driven, Python-native, good docs, UI can be added later        |
| 2026-04-15 | Networking disabled by default in containers | Safety rule, none of these games are multiplayer at this stage          |
| 2026-04-15 | DECISIONS.md as separate file                | Keeps CLAUDE.md and CONTEXT.md clean, decisions need their own log      |
