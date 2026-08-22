---
slug: /getting-started
---

# Getting Started

Peach 1UP is preservation automation for old PC and console software. Point it at a disk
image, pick an era, and the right emulator launches with the media mounted and sensible
defaults applied. No manual emulator configuration.

Covers DOS through Windows XP, plus PS1, PS2, PS3, Xbox OG, Xbox 360, Dreamcast, NES, SNES,
and N64.

:::note Windows only
Peach 1UP runs on **Windows 10 and 11**. Process isolation is built on Windows Job Objects
and AppContainer, and there are no plans to support other platforms.
:::

## Requirements

| Requirement | Why | Where |
|---|---|---|
| Windows 10 or 11 | Isolation layer | |
| Python 3.14+ | Backend runtime | [python.org](https://www.python.org/downloads/), check "Add Python to PATH" |
| uv | Dependencies and virtualenv | [docs.astral.sh/uv](https://docs.astral.sh/uv/getting-started/installation/) |
| Node.js 22+ | Frontend build and dev server | [nodejs.org](https://nodejs.org/) |
| Emulators | Peach 1UP launches them | Installed from inside the app, on demand |
| BIOS and ROMs | Required by some emulators | You supply them, from your own hardware. Peach 1UP never provides or links to them |

## Run it

```bash
uv sync --group dev
start.bat
```

`start.bat` builds the frontend if `frontend/dist` is missing, starts the backend, and opens
a browser.

| Service | URL |
|---|---|
| App | http://localhost:8000 |
| API reference | http://localhost:8000/api/docs |
| These docs | http://localhost:8000/docs |

For frontend work, run the Vite dev server in a second terminal:

```bash
cd frontend && npm run dev     # http://localhost:5173
```

The backend binds `127.0.0.1` only. It is not reachable from other machines unless you
explicitly enable network access, which requires TLS in front of it. See
[Self-Hosting](./self-hosting.mdx).

## First run

1. Open the app. You are redirected to first-run setup.
2. **Create the owner account:** a name and a 4 to 6 digit PIN. The owner has full control
   and is the only account that can create or delete sub-accounts.
3. **Install emulators.** Pick the ones for the eras you care about. They download from
   their own upstream releases into `emulators/<slug>/`.
4. **Place BIOS files.** Some emulators need them; the wizard tells you which and where.
   You supply the files.

Locked out later? Run `reset_owner.bat` in a packaged build, or
`python scripts/setup_admin_user.py` from source.

## Add your first game

1. Go to **Software → Games** and add media: a disk image (`.iso`, `.cue`/`.bin`, `.chd`), a
   game folder, or an archive.
2. Peach 1UP hashes the file, detects the platform and era, and assigns an emulator and a
   launch profile.
3. Press **Launch**.

Multi-disc games are one bundle with an ordered list of discs and a designated boot disc.
Single-disc games are a bundle of one. See [Adding Media](../user-guide/adding-media.mdx).

:::tip Mounted media is always read-only
DOS games that need to save configuration or run an installer use a writable HDD image
created through the install flow. See the [Era Guide](../user-guide/era-guide.mdx).
:::

## Build a release

```bash
build.bat
```

Builds the frontend, generates the API types and OpenAPI spec, copies the prebuilt Windows
sandbox host binary out of the installed `wincage` package, and runs PyInstaller. Output is
a self-contained directory at `dist/peach1up/` containing `peach1up.exe`.

The NSIS installer additionally needs [NSIS](https://nsis.sourceforge.io/) and
[WinSW](https://github.com/winsw/winsw/releases). See the project `README.md`.

## Configuration

Runtime settings and binary paths live in the `settings` table inside
`database/data/peach1up.db`, not a config file. Most are editable from the Settings page.

Secrets (PIN pepper, TheGamesDB and IGDB credentials) live in a root `.env` file, which is
never committed. See `.env.template`.

## Where next

- **[User Guide](../user-guide/index.md)** for adding media, launching, profiles, accounts,
  settings, eras, BIOS sourcing, controllers, and media formats.
- **[Contributor Guide](../contributor-guide/index.md)** for architecture, the stack, the
  security model, and Windows sandboxing.
- **[Self-Hosting](./self-hosting.mdx)** for running behind your own domain.
- **[Metadata Enrichment](./metadata-enrichment.mdx)** for cover art and detail fields.
