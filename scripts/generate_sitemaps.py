import json
import os
from pathlib import Path

BASE_URL = "https://fcbook.info"
CHUNK_SIZE = 2000


def _abs(url_path: str) -> str:
    if not url_path.startswith("/"):
        url_path = "/" + url_path
    return f"{BASE_URL}{url_path}"


def _write_urlset(path: Path, urls: list[str]) -> None:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">', ""]
    for url in urls:
        lines.append("<url>")
        lines.append(f"  <loc>{url}</loc>")
        lines.append("</url>")
        lines.append("")
    lines.append("</urlset>")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_sitemap_index(path: Path, sitemap_urls: list[str]) -> None:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">', ""]
    for url in sitemap_urls:
        lines.append("<sitemap>")
        lines.append(f"  <loc>{url}</loc>")
        lines.append("</sitemap>")
        lines.append("")
    lines.append("</sitemapindex>")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    player_data_path = project_root / "player_data.json"
    if not player_data_path.exists():
        raise FileNotFoundError(f"Missing {player_data_path}")

    with player_data_path.open("r", encoding="utf-8") as f:
        player_data = json.load(f)

    player_urls = []
    for player in player_data:
        cid = player.get("cid")
        if cid:
            player_urls.append(_abs(f"/player/{cid}"))

    sitemaps_dir = project_root / "sitemaps"
    sitemaps_dir.mkdir(parents=True, exist_ok=True)

    pages_urls = [
        _abs("/"),
        _abs("/players"),
        _abs("/traits_selection"),
        _abs("/coupons/"),
        _abs("/times"),
    ]
    pages_path = sitemaps_dir / "sitemap_pages.xml"
    _write_urlset(pages_path, pages_urls)

    sitemap_files = [pages_path.name]
    for idx in range(0, len(player_urls), CHUNK_SIZE):
        chunk = player_urls[idx : idx + CHUNK_SIZE]
        file_name = f"sitemap_players_{idx // CHUNK_SIZE + 1}.xml"
        file_path = sitemaps_dir / file_name
        _write_urlset(file_path, chunk)
        sitemap_files.append(file_name)

    sitemap_index_urls = [_abs(f"/sitemaps/{name}") for name in sitemap_files]
    index_path = sitemaps_dir / "sitemap.xml"
    _write_sitemap_index(index_path, sitemap_index_urls)

    print(f"Generated {len(sitemap_files)} sitemap files in {sitemaps_dir}")


if __name__ == "__main__":
    main()
