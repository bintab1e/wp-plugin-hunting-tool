import json
import os
import re
import time
import zipfile
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen

BASE = "https://ko.wordpress.org"
SEARCH_FIRST_PAGE = BASE + "/plugins/search/{tag}/"
SEARCH_PAGE = BASE + "/plugins/search/{tag}/page/{page}/"
DOWNLOAD_HOST = "downloads.wordpress.org"
OUTPUT_DIR = "plugins"
USER_AGENT = "Mozilla/5.0 (compatible; wp-plugin-downloader/1.0)"
MIN_ACTIVE_INSTALLS = 100

GREEN = "\033[92m"
RED = "\033[91m"
CYAN = "\033[96m"
RESET = "\033[0m"

TAGS = [
    "admin", "ads", "affiliate", "AI", "ajax", "analytics", "api", "automation", "block", "blocks",
    "buddypress", "button", "cache", "calendar", "categories", "category", "chat", "chatbot", "checkout",
    "comment", "comments", "contact", "contact form", "contact form 7", "content", "css", "custom",
    "dashboard", "e-commerce", "ecommerce", "editor", "elementor", "email", "embed", "events", "facebook",
    "feed", "form", "forms", "gallery", "gateway", "google", "gutenberg", "image", "images", "import",
    "integration", "javascript", "jquery", "link", "links", "login", "marketing", "media", "menu", "mobile",
    "navigation", "news", "newsletter", "notification", "page", "pages", "payment", "payment gateway", "payments",
    "performance", "photo", "popup", "post", "posts", "products", "redirect", "responsive", "reviews", "rss",
    "search", "security", "seo", "share", "shipping", "shortcode", "sidebar", "slider", "slideshow", "social",
    "social media", "spam", "statistics", "stats", "tags", "theme", "tracking", "twitter", "user", "users",
    "video", "widget", "widgets", "woocommerce", "youtube"
]


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        for k, v in attrs:
            if k.lower() == "href" and v:
                self.links.append(v)


def log_ok(msg):
    print(f"{GREEN}[+]{RESET} {msg}")


def log_err(msg):
    print(f"{RED}[-]{RESET} {msg}")


def get_html(url):
    while True:
        req = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "ko,en;q=0.9"})
        try:
            with urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except HTTPError as e:
            if e.code == 429:
                wait_sec = 10
                if e.headers and e.headers.get("Retry-After") and e.headers.get("Retry-After").strip().isdigit():
                    wait_sec = int(e.headers.get("Retry-After").strip())
                log_ok(f"429 발생: {url} / {wait_sec}초 후 재시도")
                time.sleep(wait_sec)
                continue
            log_err(f"HTTP {e.code}: {url} / 10초 후 재시도")
            time.sleep(10)
        except (URLError, TimeoutError, OSError) as e:
            log_err(f"네트워크 오류: {url} / 10초 후 재시도 ({e})")
            time.sleep(10)


def parse_links(html):
    parser = LinkParser()
    parser.feed(html)
    return parser.links


def get_html_once(url):
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "ko,en;q=0.9"})
    try:
        with urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except HTTPError as e:
        if e.code == 429:
            wait_sec = 10
            if e.headers and e.headers.get("Retry-After") and e.headers.get("Retry-After").strip().isdigit():
                wait_sec = int(e.headers.get("Retry-After").strip())
            log_ok(f"429 발생: {url} / {wait_sec}초 후 재시도")
            time.sleep(wait_sec)
            return get_html_once(url)
        return ""
    except (URLError, TimeoutError, OSError):
        return ""


def get_active_installs(slug):
    api_url = (
        "https://api.wordpress.org/plugins/info/1.2/"
        + "?action=plugin_information"
        + "&request[slug]=" + quote(slug)
        + "&request[fields][active_installs]=1"
    )
    data = get_html_once(api_url)

    try:
        obj = json.loads(data)
        if isinstance(obj, dict) and "active_installs" in obj:
            return int(obj.get("active_installs", 0))
    except Exception:
        pass

    m = re.search(r's:15:"active_installs";i:(\d+);', data)
    if m:
        return int(m.group(1))

    url = BASE + "/plugins/" + slug + "/"
    html = get_html(url)

    m = re.search(r"활성화된\s*설치\s*<strong>\s*([0-9][0-9,]*)\+", html, re.IGNORECASE)
    if m:
        return int(m.group(1).replace(",", ""))

    m = re.search(r"Active\s*installations\s*<strong>\s*([0-9][0-9,]*)\+", html, re.IGNORECASE)
    if m:
        return int(m.group(1).replace(",", ""))

    m = re.search(r"활성\s*설치[^0-9]*(\d[\d,]*)\+", html, re.IGNORECASE)
    if m:
        return int(m.group(1).replace(",", ""))

    m = re.search(r"Active\s*installations[^<]*(\d+)\+\s*million", html, re.IGNORECASE)
    if m:
        return int(m.group(1)) * 1000000

    m = re.search(r"Less than\s*(\d+)", html, re.IGNORECASE)
    if m:
        return int(m.group(1)) - 1

    return 0


def get_max_page_for_tag(tag_encoded):
    first_url = SEARCH_FIRST_PAGE.format(tag=tag_encoded)
    html = get_html(first_url)
    links = parse_links(html)

    max_page = 1
    pattern = re.compile(r"^/plugins/search/[^/]+/page/(\d+)/?$")

    for href in links:
        full = urljoin(BASE, href)
        parsed = urlparse(full)
        if parsed.netloc != urlparse(BASE).netloc:
            continue
        m = pattern.match(parsed.path)
        if m:
            p = int(m.group(1))
            if p > max_page:
                max_page = p

    return max_page


def download_by_tag_pages():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    seen = set()
    ok = 0
    skipped_install = 0
    skipped_dup = 0
    checked = 0

    for tag in TAGS:
        tag_encoded = quote(tag)

        try:
            max_page = get_max_page_for_tag(tag_encoded)
        except Exception as e:
            log_err(f"페이지 수 확인 실패: {tag} ({e})")
            max_page = 1

        log_ok(f"태그 시작: {CYAN}{tag}{RESET} / pages=1..{max_page}")

        for page in range(1, max_page + 1):
            if page == 1:
                url = SEARCH_FIRST_PAGE.format(tag=tag_encoded)
            else:
                url = SEARCH_PAGE.format(tag=tag_encoded, page=page)

            log_ok(f"{tag} {page}/{max_page} 페이지 처리")
            html = get_html(url)
            links = parse_links(html)

            page_slugs = []
            for href in links:
                full = urljoin(BASE, href)
                parsed = urlparse(full)
                if parsed.netloc != urlparse(BASE).netloc:
                    continue

                m = re.match(r"^/plugins/([a-z0-9._-]+)/?$", parsed.path)
                if not m:
                    continue

                slug = m.group(1)
                if slug in ["browse", "search", "developers", "about", ""]:
                    continue
                page_slugs.append(slug)

            # 같은 페이지 내 중복 제거
            page_slugs = sorted(set(page_slugs))

            for slug in page_slugs:
                if slug in seen:
                    skipped_dup += 1
                    continue
                seen.add(slug)
                checked += 1

                installs = get_active_installs(slug)
                if installs < MIN_ACTIVE_INSTALLS:
                    skipped_install += 1
                    log_err(f"건너뜀(설치수 {installs}+): {slug}")
                    time.sleep(0.2)
                    continue

                log_ok(f"다운로드: {CYAN}{slug}{RESET} (설치수 {installs}+)")
                if download_zip(slug):
                    ok += 1
                    log_ok(f"저장 완료: {slug}.zip")
                time.sleep(0.4)

            time.sleep(0.4)

        log_ok(f"태그 완료: {CYAN}{tag}{RESET}")

    log_ok(
        f"전체 완료: 검사 {checked} / 다운로드 {ok} / 설치수로 건너뜀 {skipped_install} / 중복 건너뜀 {skipped_dup}"
    )


def download_zip(slug):
    url = f"https://{DOWNLOAD_HOST}/plugin/{slug}.zip"
    out_path = os.path.join(OUTPUT_DIR, slug + ".zip")

    while True:
        req = Request(url, headers={"User-Agent": USER_AGENT, "Referer": BASE + "/"})
        try:
            with urlopen(req, timeout=60) as resp:
                data = resp.read()
            with open(out_path, "wb") as f:
                f.write(data)
            return True
        except HTTPError as e:
            if e.code == 404:
                fallback = f"https://{DOWNLOAD_HOST}/plugin/{slug}.latest-stable.zip"
                req2 = Request(fallback, headers={"User-Agent": USER_AGENT, "Referer": BASE + "/"})
                try:
                    with urlopen(req2, timeout=60) as resp2:
                        data2 = resp2.read()
                    with open(out_path, "wb") as f:
                        f.write(data2)
                    return True
                except Exception as ee:
                    log_err(f"다운로드 실패: {slug} ({ee})")
                    return False

            if e.code == 429:
                wait_sec = 10
                if e.headers and e.headers.get("Retry-After") and e.headers.get("Retry-After").strip().isdigit():
                    wait_sec = int(e.headers.get("Retry-After").strip())
                log_ok(f"429 발생: {slug} / {wait_sec}초 후 재시도")
                time.sleep(wait_sec)
                continue

            log_err(f"HTTP {e.code}: {slug} / 10초 후 재시도")
            time.sleep(10)
        except (URLError, TimeoutError, OSError) as e:
            log_err(f"네트워크 오류: {slug} / 10초 후 재시도 ({e})")
            time.sleep(10)


def unzip_and_delete_zips():
    files = os.listdir(OUTPUT_DIR)
    zips = [n for n in files if n.lower().endswith(".zip")]
    log_ok(f"압축 해제 시작: {len(zips)}개")

    for name in zips:
        zip_path = os.path.join(OUTPUT_DIR, name)
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(OUTPUT_DIR)
            log_ok(f"압축 해제 완료: {name}")
        except Exception as e:
            log_err(f"압축 해제 실패: {name} ({e})")

    for name in zips:
        zip_path = os.path.join(OUTPUT_DIR, name)
        try:
            os.remove(zip_path)
            log_ok(f"ZIP 삭제: {name}")
        except Exception as e:
            log_err(f"ZIP 삭제 실패: {name} ({e})")


def main():
    download_by_tag_pages()
    unzip_and_delete_zips()


if __name__ == "__main__":
    main()
