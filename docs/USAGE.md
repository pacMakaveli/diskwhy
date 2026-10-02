# Usage

diskwhy is a dashboard you open in a browser.
Start it, look at where the space is, and remove what you do not need.

```bash
python3 -m diskwhy
```

## The views

- **Hotspots** lists the known space hogs on a developer Mac (Xcode, simulators, package-manager caches, Homebrew, Docker and more) plus anything detected on your machine.
  Detection covers Postgres and MySQL data directories under `/opt/homebrew/var`, flagged *stale* when no running server uses them, and the largest `node_modules` under your project folders.
  Each item is tagged `regenerable`, `review`, `data` or `stale`.
- **Explorer** lets you drill into any directory, with a size bar for every entry.
- **Large files** lists every file above a size you choose under your home folder.

The first scan of a large folder takes a while, because the sizes come from `du`.
Results are cached for five minutes.

## Removing things

Every row has a **Remove...** button, disabled with a reason when the path is protected.

- **Move to Trash** is the default. It is reversible, but frees no space until you empty the Trash.
- **Delete permanently** frees the space now and cannot be undone. You must type the item's exact name to confirm.

Cleanup commands shown under an item, such as `brew cleanup` or `docker system prune`, are for you to run yourself.
diskwhy never executes them.
See [Architecture](ARCHITECTURE.md#safety-model) for exactly what is refused.

## Configuration

| Flag | Default | Meaning |
|---|---|---|
| `--port` | `8765` | Port to listen on, always bound to `127.0.0.1` |
| `--projects` | `~/Projects` | Folder to search for `node_modules`. Repeat the flag for several folders |
| `--no-open` | off | Do not open a browser tab |

```bash
python3 -m diskwhy --projects ~/code --projects ~/work --port 9000 --no-open
```

There are no environment variables and no config files.

## JSON API

The page is a thin client over a small API.
Every call needs the run's token in an `X-DiskWhy-Token` header.

| Endpoint | Returns |
|---|---|
| `GET /api/volume` | `total`, `used` and `free` bytes of the data volume |
| `GET /api/hotspots` | Known and detected space hogs with size, kind and removability |
| `GET /api/ls?path=` | Children of a directory with sizes, largest first |
| `GET /api/large?root=&min_mb=` | Files above `min_mb` under `root` |
| `POST /api/remove` | Body `{path, mode, confirm}`. `mode` is `trash` or `delete` |
