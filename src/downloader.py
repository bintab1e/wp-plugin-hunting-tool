import os
import re
import time
import zipfile
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

BASE = "https://ko.wordpress.org"
POPULAR_PAGE = BASE + "/plugins/browse/popular/page/{page}/"
DOWNLOAD_HOST = "downloads.wordpress.org"
PLUGINS_DIR = "plugins"
USER_AGENT = "Mozilla/5.0 (compatible; wp-plugin-downloader/1.0)"

GREEN = "\033[92m"
RED = "\033[91m"
CYAN = "\033[96m"
RESET = "\033[0m"

def log_ok(message):
    print(f"{GREEN}[+]{RESET} {message}")

def log_err(message):
    print(f"{RED}[-]{RESET} {message}")

def color_text(text, color):
    return f"{color}{text}{RESET}"

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
                log_ok(url + " -> 429, " + str(wait_sec) + "초 후 재시도")
                time.sleep(wait_sec)
                continue
            log_err(url + " -> HTTP " + str(e.code) + ", 10초 후 재시도")
            time.sleep(10)
        except (URLError, TimeoutError, OSError) as e:
            log_err(url + " -> 네트워크 오류, 10초 후 재시도: " + str(e))
            time.sleep(10)

def collect_plugin_urls():
    parser = LinkParser()
    plugin_urls = set()

    for page in range(1, 50):
        list_url = POPULAR_PAGE.format(page=page)
        log_ok("목록 수집 " + str(page) + "/49: " + color_text(list_url, CYAN))
        html = get_html(list_url)

        parser.links = []
        parser.feed(html)

        for href in parser.links:
            full = urljoin(BASE, href)
            parsed = urlparse(full)

            if parsed.netloc != urlparse(BASE).netloc:
                continue

            m = re.match(r"^/plugins/([a-z0-9._-]+)/?$", parsed.path)
            if not m:
                continue

            slug = m.group(1)
            if slug in ["browse", "developers", "about", ""]:
                continue

            plugin_urls.add(BASE + "/plugins/" + slug + "/")

        time.sleep(0.5)

    result = sorted(list(plugin_urls))
    log_ok("플러그인 URL 수집 완료: " + str(len(result)) + "개")
    return result

def download_all_plugins(plugin_urls):
    os.makedirs(PLUGINS_DIR, exist_ok=True)

    for i in range(0, len(plugin_urls)):
        plugin_url = plugin_urls[i]
        parts = [p for p in urlparse(plugin_url).path.split("/") if p]
        slug = parts[1]
        zip_path = os.path.join(PLUGINS_DIR, slug + ".zip")

        log_ok("다운로드 대상 " + str(i + 1) + "/" + str(len(plugin_urls)) + ": " + color_text(slug, CYAN))

        html = get_html(plugin_url)
        parser = LinkParser()
        parser.feed(html)

        download_url = ""
        for href in parser.links:
            full = urljoin(plugin_url, href)
            parsed = urlparse(full)
            if parsed.netloc == DOWNLOAD_HOST and parsed.path.startswith("/plugin/") and parsed.path.endswith(".zip"):
                download_url = full
                break

        if download_url == "":
            download_url = "https://" + DOWNLOAD_HOST + "/plugin/" + slug + ".zip"

        log_ok("다운로드 URL: " + color_text(download_url, CYAN))

        while True:
            req = Request(download_url, headers={"User-Agent": USER_AGENT, "Referer": BASE + "/"})
            try:
                with urlopen(req, timeout=60) as resp:
                    data = resp.read()
                with open(zip_path, "wb") as f:
                    f.write(data)
                log_ok(slug + ".zip 저장 완료")
                break
            except HTTPError as e:
                if e.code == 429:
                    wait_sec = 10
                    if e.headers and e.headers.get("Retry-After") and e.headers.get("Retry-After").strip().isdigit():
                        wait_sec = int(e.headers.get("Retry-After").strip())
                    log_ok(slug + " -> 429, " + str(wait_sec) + "초 후 재시도")
                    time.sleep(wait_sec)
                    continue
                log_err(slug + " -> HTTP " + str(e.code) + ", 10초 후 재시도")
                time.sleep(10)
            except (URLError, TimeoutError, OSError) as e:
                log_err(slug + " -> 429 오류, 10초 후 재시도: " + str(e))
                time.sleep(10)

        time.sleep(0.5)

def unzip_and_delete_all_zips():
    files = os.listdir(PLUGINS_DIR)
    zip_files = []

    for name in files:
        if name.lower().endswith(".zip"):
            zip_files.append(name)

    log_ok("압축 해제 시작: " + str(len(zip_files)) + "개")

    for name in zip_files:
        zip_path = os.path.join(PLUGINS_DIR, name)
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(PLUGINS_DIR)
            log_ok("압축 해제 완료: " + name)
        except Exception as e:
            log_err("압축 해제 실패: " + name + " / " + str(e))

    for name in zip_files:
        zip_path = os.path.join(PLUGINS_DIR, name)
        try:
            os.remove(zip_path)
            log_ok("ZIP 삭제: " + name)
        except Exception as e:
            log_err("ZIP 삭제 실패: " + name + " / " + str(e))

def main():
    plugin_urls = collect_plugin_urls()
    download_all_plugins(plugin_urls)
    unzip_and_delete_all_zips()


if __name__ == "__main__":
    main()
