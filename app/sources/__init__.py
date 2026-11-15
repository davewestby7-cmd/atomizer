"""Music sources. Each source is a module with an async `fetch(client, settings)`
function that returns a list of `Release` objects (not yet saved).

To add a new source, see the "Tinkering guide" in README.md:
  1. copy ektoplazm.py to mysource.py and change the parsing,
  2. add it to SOURCES below,
  3. add a `mysource:` section under `sources:` in config.yaml.
"""
from . import archive_org, bandcamp, ektoplazm, hearthis

SOURCES = {
    "ektoplazm": ektoplazm,
    "bandcamp": bandcamp,
    "archive": archive_org,
    "hearthis": hearthis,
}
