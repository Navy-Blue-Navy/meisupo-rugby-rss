import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from email.utils import format_datetime, parsedate_to_datetime
from datetime import datetime, timezone, timedelta
import xml.etree.ElementTree as ET
import hashlib
import os
import re

URL = "https://meisupo.net/club/20/"
OUTPUT = "meisupo_rugby.xml"

JST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

DATE_PATTERN = re.compile(
    r"(20\d{2})[./年](\d{1,2})[./月](\d{1,2})"
)


def make_guid(url):
    return hashlib.sha256(
        url.encode("utf-8")
    ).hexdigest()


def get_old_items():
    old = {}

    if not os.path.exists(OUTPUT):
        return old

    try:
        root = ET.parse(OUTPUT).getroot()

        for item in root.findall("./channel/item"):
            guid = item.findtext("guid")

            if guid:
                old[guid] = {
                    "title": item.findtext("title") or "",
                    "link": item.findtext("link") or "",
                    "description": item.findtext("description") or "",
                    "pubDate": item.findtext("pubDate") or "",
                }

    except Exception:
        pass

    return old


def get_title_from_article(url):
    """
    個別記事ページから正式な記事タイトルを取得する。
    一覧ページの概要文がタイトルに混入するのを防ぐ。
    """

    try:
        r = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        r.raise_for_status()

        soup = BeautifulSoup(
            r.text,
            "html.parser"
        )

        # OGタイトルを優先
        og = soup.find(
            "meta",
            attrs={"property": "og:title"}
        )

        if og and og.get("content"):
            title = og["content"].strip()

            # タイトル末尾のサイト名を削除
            # 例：
            # 「記事タイトル – 明大スポーツ新聞部」
            title = re.sub(
                r"\s*(?:[|｜]|[-–—])\s*明大スポーツ新聞部\s*$",
                "",
                title
            ).strip()

            if title:
                return title

        # OGタイトルがなければh1
        h1 = soup.find("h1")

        if h1:
            title = h1.get_text(
                " ",
                strip=True
            )

            title = re.sub(
                r"\s*(?:[|｜]|[-–—])\s*明大スポーツ新聞部\s*$",
                "",
                title
            ).strip()

            if title:
                return title

    except Exception as e:
        print(
            "記事タイトル取得失敗:",
            url,
            e
        )

    return None


# -------------------------
# 一覧ページ取得
# -------------------------

response = requests.get(
    URL,
    headers=HEADERS,
    timeout=30
)

print(
    "一覧ページ HTTP:",
    response.status_code
)

response.raise_for_status()

soup = BeautifulSoup(
    response.text,
    "html.parser"
)

# -------------------------
# 一覧ページから記事URLと日付を取得
# -------------------------

article_candidates = []
seen_urls = set()

for a in soup.find_all(
    "a",
    href=True
):

    href = a.get("href", "")

    article_url = urljoin(
        URL,
        href
    )

    # 個別ニュース記事のみ
    if not re.fullmatch(
        r"https://meisupo\.net/news/\d+/?",
        article_url
    ):
        continue

    if article_url in seen_urls:
        continue

    # 記事カード周辺から日付を探す
    parent = a
    block_text = ""

    for _ in range(7):

        if parent is None:
            break

        text = " ".join(
            parent.stripped_strings
        )

        if DATE_PATTERN.search(text):
            block_text = text
            break

        parent = parent.parent

    if not block_text:
        continue

    m = DATE_PATTERN.search(
        block_text
    )

    if not m:
        continue

    year, month, day = map(
        int,
        m.groups()
    )

    dt = datetime(
        year,
        month,
        day,
        12,
        0,
        0,
        tzinfo=JST
    )

    # 一覧上でラグビー記事であることを確認
    link_text = " ".join(
        a.stripped_strings
    )

    if "ラグビー" not in link_text:
        continue

    seen_urls.add(
        article_url
    )

    article_candidates.append({
        "link": article_url,
        "date": dt,
    })


print(
    "記事候補:",
    len(article_candidates),
    "件"
)

# -------------------------
# 個別記事から正式タイトル取得
# -------------------------

items = []

for number, candidate in enumerate(
    article_candidates,
    1
):

    article_url = candidate["link"]
    dt = candidate["date"]

    title = get_title_from_article(
        article_url
    )

    if not title:
        print(
            f"[{number}] タイトル取得失敗:",
            article_url
        )
        continue

    # 念のためラグビー記事のみ
    if (
        "【ラグビー】" not in title
        and "〖ラグビー〗" not in title
        and "[ラグビー]" not in title
    ):
        print(
            f"[{number}] ラグビー記事判定外:",
            title
        )
        continue

    print(
        f"[{number}]",
        title
    )

    items.append({
        "title": title,
        "link": article_url,
        "description": "明大スポーツ新聞部 ラグビー",
        "pubDate": format_datetime(dt),
        "guid": make_guid(article_url),
        "sort_date": dt,
    })


items.sort(
    key=lambda x: x["sort_date"],
    reverse=True
)

# -------------------------
# 既存RSSを保持
# -------------------------

old_items = get_old_items()
all_items = dict(old_items)

for item in items:

    all_items[
        item["guid"]
    ] = {
        "title": item["title"],
        "link": item["link"],
        "description": item["description"],
        "pubDate": item["pubDate"],
    }


def parse_date(value):

    try:
        return parsedate_to_datetime(
            value
        )

    except Exception:
        return datetime(
            1970,
            1,
            1,
            tzinfo=timezone.utc
        )


sorted_items = sorted(
    all_items.items(),
    key=lambda x:
        parse_date(
            x[1]["pubDate"]
        ),
    reverse=True
)[:300]

# -------------------------
# RSS生成
# -------------------------

rss = ET.Element(
    "rss",
    version="2.0"
)

channel = ET.SubElement(
    rss,
    "channel"
)

ET.SubElement(
    channel,
    "title"
).text = "明大スポーツ新聞部 ラグビー"

ET.SubElement(
    channel,
    "link"
).text = URL

ET.SubElement(
    channel,
    "description"
).text = (
    "明大スポーツ新聞部 "
    "ラグビーの新着記事"
)

ET.SubElement(
    channel,
    "language"
).text = "ja"

for guid, data in sorted_items:

    item = ET.SubElement(
        channel,
        "item"
    )

    ET.SubElement(
        item,
        "title"
    ).text = data["title"]

    ET.SubElement(
        item,
        "link"
    ).text = data["link"]

    ET.SubElement(
        item,
        "description"
    ).text = data["description"]

    ET.SubElement(
        item,
        "pubDate"
    ).text = data["pubDate"]

    guid_el = ET.SubElement(
        item,
        "guid",
        isPermaLink="false"
    )

    guid_el.text = guid


tree = ET.ElementTree(rss)

ET.indent(
    tree,
    space="  "
)

tree.write(
    OUTPUT,
    encoding="utf-8",
    xml_declaration=True
)

# -------------------------
# 結果表示
# -------------------------

print()
print("RSS作成成功")
print(
    "今回取得:",
    len(items),
    "件"
)
print(
    "RSS保存件数:",
    len(sorted_items),
    "件"
)
print(
    "保存先:",
    os.path.abspath(OUTPUT)
)

print()
print("取得記事:")

for i, item in enumerate(
    items,
    1
):

    print()
    print(
        f"[{i}] {item['title']}"
    )
    print(
        "    ",
        item["pubDate"]
    )
    print(
        "    ",
        item["link"]
    )