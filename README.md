# Atomizer 🍄

A small web app you run on your own computer. It finds **free and cheap psytrance**
from legal sources, lets you preview it, pulls the free releases into a folder and
can optionally sync that folder to Google Drive.

- **Ektoplazm** (ektoplazm.com) is a free Creative Commons psytrance netlabel. Every release is free, and Atomizer downloads and unzips it for you. Atomizer reads its style pages and its **country pages**: 🇮🇱 Israel (90 albums), Germany, Australia, UK, Brazil, Russia, Greece and a dozen more, over 1,000 free albums in all. New ones are read gradually, up to 150 per refresh.
- **Bandcamp** tag feeds (psytrance, psychedelic-trance, goa-trance, darkpsy, forest) are sorted into **Free**, **Name Your Price** and **Cheap** (≤ AUD 5 by default). Downloads and purchases happen on Bandcamp's own page, so those cards link out.
- **Bandcamp country scenes:** the same feed, filtered to one country. 🇮🇱 **Israel** gets the deepest search (psytrance, goa, progressive, full-on, darkpsy), then India, Brazil, Japan, Mexico, Greece, South Africa and Australia. You can add any country in `config.yaml`.
- **Internet Archive netlabels** (archive.org/details/netlabels): Creative Commons releases from small labels worldwide. Free, and Atomizer pulls them for you.
- **Sonic Tantra** (sonictantra.com): an Indian dark, hi-tech and psycore label with dozens of free compilations from labels worldwide. Atomizer pulls the zips directly. There are no preview clips, so use 🔗 to listen first.
- **Audius** (audius.co): an open platform where artists upload full-length psytrance tracks and sets. These play in full, not as 30-second samples. Tracks the artist has made freely downloadable can be pulled; the rest open Audius.
- **Bandcamp "free-download" tag:** combined with psytrance, goa-trance and darkpsy, so you get a focused feed of free and name-your-price releases.
- **Bandcamp labels you follow:** Zenon, Looney Moon, Deepnotic, plus HOMmega, Blue Tunes, Sacred Technology, Moonity, TimeLapse, Iboga, Nano, TIP, Ovnimoon, IONO, Dacru, Profound, Occulta, Sangoma, Psygen, Arrábida and Enterrec. **Every** release shows on the **Labels** tab, at any price, with previews of every track; free and cheap ones also show on Free and Cheap. Edit the list under `bclabels:` in `config.yaml`.
- **hearthis.at:** free-download psytrance and goa DJ mixes and tracks from DJs worldwide. You can preview them here; hearthis doesn't allow automated downloads, so the Get button opens the page.

Every release with a known location shows it (🌍) and gets a country chip such as
**israel**, so you can filter by scene. The search box also matches places.

No YouTube or Spotify ripping, no accounts, no paywalled content. Atomizer obeys each
site's `robots.txt`, waits at least 1 second between requests, and only re-checks
sources every 6 hours unless you press **Refresh sources**.

## Quick start

You need **Python 3.11 or newer** ([python.org](https://www.python.org/downloads/); on
Windows, tick *"Add Python to PATH"* in the installer).

**Windows:** double-click **`run.bat`**. The first run installs everything (a minute or
two) and then opens http://127.0.0.1:8000.

**macOS / Linux:**

```bash
./run.sh
```

**Or by hand, on any OS:**

```bash
pip install -r requirements.txt && uvicorn app.main:app
```

Then open http://127.0.0.1:8000. The first time, it takes about a minute to check
the sources. Stop the app with `Ctrl+C`.

> Windows tip: keep the project in a short path such as `C:\Atomizer`. Very long
> folder paths can make Python's installer fail.

## Using it

| Tab | What's there |
|---|---|
| **Pulled** | Releases you've downloaded. 📂 opens the folder; 🗑 deletes a release's files. |
| **Free** | Ektoplazm, Internet Archive netlabels, hearthis.at mixes, and Bandcamp free and name-your-price releases. |
| **Cheap / On Sale** | Bandcamp releases at or under your price limit, converted to your currency. |
| **Labels** | Everything from the Bandcamp labels you follow, newest first. Pick a label from the dropdown. |

On each card: **▶ Play** plays a sample (one at a time), **⬇ Pull** downloads it (or
**Get/Buy** opens Bandcamp), and **🔗** opens the release page. Use the search box and
the style chips to narrow things down.

> "On Sale": Bandcamp's feed doesn't say when something is discounted, so this tab
> shows anything priced under your limit.

## Settings

Copy `config.example.yaml` to `config.yaml` (the run scripts do this for you) and
edit it. Restart the app after changing it.

| Setting | Meaning |
|---|---|
| `download_dir` | Where releases are saved (default `downloads/`) |
| `download_format` | `mp3` or `flac` for Ektoplazm pulls |
| `home_currency`, `cheap_threshold` | e.g. `AUD` and `5.0` |
| `refresh_hours` | How often sources are re-checked in the background |
| `rclone_remote`, `rclone_mode` | Google Drive sync (below) |
| `sources:` | Turn sources on or off; pick Ektoplazm styles and Bandcamp tags |

## Google Drive sync (optional)

Atomizer uses [rclone](https://rclone.org) to copy your downloads folder to Drive.

1. Install rclone: <https://rclone.org/install/>. On Windows, `winget install Rclone.Rclone` works.
2. Run `rclone config` in a terminal and answer:
   - `n` (new remote), name it **`gdrive`**
   - Storage: choose **Google Drive** (`drive`)
   - client_id / client_secret: leave blank (press Enter)
   - scope: `1` (full access) or `3` (only files rclone creates)
   - Leave the rest as default. Say **yes** to "auto config"; a browser opens, so log in to Google and allow access.
   - Shared drive: `n`, then confirm with `y` and quit with `q`.
3. Check it works: `rclone lsd gdrive:`
4. In `config.yaml` set `rclone_remote: "gdrive:Atomizer"` and restart Atomizer.

Press **☁ Sync to Drive** whenever you like. With `rclone_mode: copy` (the default),
files are only ever added to Drive. With `rclone_mode: sync`, Drive becomes an exact
mirror, so deleting a release in Atomizer deletes it from Drive on the next sync.

If rclone isn't installed or configured, the top bar says so and nothing breaks.

## Screenshots

_Add yours here: run the app, take a screenshot, save it as `docs/screenshot.png`
and link it like this:_ `![Atomizer](docs/screenshot.png)`

## Tinkering guide

```
app/
  main.py          web server + API (routes: /api/releases, /api/pull/{id}, ...)
  config.py        reads config.yaml
  db.py            the database table (one row per release)
  polite.py        web client that obeys robots.txt and waits between requests
  currency.py      price conversion
  downloader.py    download + unzip into downloads/<Artist> - <Title>/
  sync.py          runs rclone
  sources/
    __init__.py    list of sources
    ektoplazm.py   reads Ektoplazm pages
    bandcamp.py    reads Bandcamp tag feeds (worldwide + country scenes)
    archive_org.py reads Internet Archive netlabels
    hearthis.py    reads hearthis.at free-download mixes
    sonictantra.py reads Sonic Tantra free compilations
    audius.py      reads the Audius API
    bandcamp_labels.py  reads the catalogues of Bandcamp labels you follow
static/
  index.html       the page layout (Tailwind classes for styling)
  app.js           what the buttons do
tests/             parser tests using saved pages in tests/fixtures/
```

**Change the look:** edit `static/index.html` (colours are Tailwind classes such as
`bg-violet-700` and `text-teal-300`) and reload the browser. There's no build step.

**Add a new source** (for example another free netlabel):

1. Copy `app/sources/ektoplazm.py` to `app/sources/mylabel.py`.
2. Change `parse_listing()` to pull artist, title, cover, page URL, sample URLs and
   download links out of that site's HTML. Give each release a unique `id` such as
   `"mylabel-some-slug"`, and set `price_kind` to `"free"`, `"nyp"` or `"cheap"`.
3. Keep `async def fetch(client, settings)` and always use `client.get(...)`. That's
   the polite client, which handles robots.txt and rate limits for you.
4. Register it in `app/sources/__init__.py`: `SOURCES = {..., "mylabel": mylabel}`.
5. Add a section to `config.yaml`:
   ```yaml
   sources:
     mylabel:
       enabled: true
   ```
6. Save a page from the site into `tests/fixtures/`, write a test like
   `tests/test_ektoplazm.py`, and run the tests.

Please stick to sites that offer music for free legally (netlabels, Creative Commons,
artist-run free downloads).

## Running the tests

```bash
python -m pytest -q
```

(`make test` also works if you have `make`.)

## API

| Method | Path | |
|---|---|---|
| GET | `/api/releases?bucket=free\|cheap\|pulled&q=&tag=` | list releases |
| POST | `/api/pull/{release_id}` | download; streams progress as server-sent events |
| DELETE | `/api/pulled/{release_id}` | delete a pulled release's files |
| POST | `/api/refresh` | re-check sources now |
| POST | `/api/sync` | run rclone |
| POST | `/api/open-folder` | open the downloads folder |
| GET | `/api/status` | counts, last refresh/sync, folder size |

Interactive docs are at http://127.0.0.1:8000/docs while the app is running.

## License

MIT. The music belongs to its artists: Ektoplazm releases are Creative Commons
(non-commercial), so please support the artists you enjoy.
