import zipfile

from app.downloader import _extract, release_folder, safe_name
from app.polite import Robots

BANDCAMP_ROBOTS = """
User-agent: *
Disallow: /api/
Disallow: /search
Allow: /api/discover/1/discover_web
Disallow: /*_cb$

User-agent: SemrushBot
Disallow: /
"""

EKTO_ROBOTS = """
User-agent: *
Disallow: /wp-admin/
Disallow: /*?*
Disallow: */page
"""


def test_bandcamp_robots_longest_rule_wins():
    r = Robots.parse(BANDCAMP_ROBOTS)
    assert r.allowed("https://bandcamp.com/api/discover/1/discover_web")
    assert not r.allowed("https://bandcamp.com/api/hub/2/dig_deeper")
    assert not r.allowed("https://bandcamp.com/search?q=goa")
    assert r.allowed("https://someband.bandcamp.com/album/x")


def test_ektoplazm_robots_wildcards():
    r = Robots.parse(EKTO_ROBOTS)
    assert r.allowed("https://ektoplazm.com/style/goa")
    assert not r.allowed("https://ektoplazm.com/style/goa/page/2")
    assert not r.allowed("https://ektoplazm.com/?s=goa")


def test_safe_names_work_on_windows():
    assert safe_name('AC/DC: "Live"?') == "AC_DC_ _Live__"
    assert safe_name("trailing dots...") == "trailing dots"
    assert release_folder(__import__("pathlib").Path("dl"), "Globular", "Holobiont").name == \
        "Globular - Holobiont"


def test_extract_flattens_and_blocks_zip_slip(tmp_path):
    zpath = tmp_path / "r.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("Album/01 - One.mp3", b"a")
        z.writestr("../../evil.txt", b"b")
    dest = tmp_path / "out"
    assert _extract(zpath, dest) == 2
    assert sorted(p.name for p in dest.iterdir()) == ["01 - One.mp3", "evil.txt"]
    assert not (tmp_path.parent / "evil.txt").exists()
