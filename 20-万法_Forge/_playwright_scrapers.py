"""
_playwright_scrapers.py — 浏览器驱动抓包器
道法自然 · 无感获取 · 绕过CSRF/WAF — 直取源头数据

用于抓取 Playwright 方能访问的平台:
  - Thangs.com (CSRF 403保护)
  - GrabCAD (PTC-owned, SPA)
  - 3D溜溜 (JS反爬挑战)

Import:
    from _playwright_scrapers import playwright_search, PLAYWRIGHT_PLATFORMS
"""

import json
import time
from typing import Optional

try:
    from playwright.sync_api import sync_playwright, Page, Request, Response
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


def _make_browser(headless: bool = True):
    """创建Chromium实例 (带反检测参数)"""
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-extensions",
        ]
    )
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 800},
        locale="en-US",
        timezone_id="America/New_York",
        java_script_enabled=True,
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124"',
            "sec-ch-ua-platform": '"Windows"',
        }
    )
    # 注入反检测JS
    ctx.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
        window.chrome = {runtime: {}};
    """)
    return pw, browser, ctx


class PlaywrightThangsClient:
    """Thangs.com — Playwright无感获取 (__NEXT_DATA__ SSR直提)"""

    def search(self, query: str, limit: int = 20) -> list:
        if not PLAYWRIGHT_AVAILABLE:
            print("  ! Playwright未安装: pip install playwright && playwright install chromium")
            return []
        pw = browser = ctx = page = None
        try:
            pw, browser, ctx = _make_browser()
            page = ctx.new_page()
            search_url = f"https://thangs.com/search/{query.replace(' ', '%20')}"
            page.goto(search_url, wait_until="networkidle", timeout=25000)
            page.wait_for_timeout(1500)
            # 提取 __NEXT_DATA__ (SSR数据)
            next_data_raw = page.evaluate(
                "() => { const e = document.getElementById('__NEXT_DATA__'); return e ? e.textContent : null; }"
            )
            if not next_data_raw:
                return []
            return _parse_thangs_next_data(json.loads(next_data_raw), query, limit)
        except Exception as e:
            print(f"  ! Playwright Thangs error: {e}")
            return []
        finally:
            for obj in [page, ctx, browser]:
                if obj:
                    try: obj.close()
                    except: pass
            if pw:
                try: pw.stop()
                except: pass

    def probe(self) -> dict:
        if not PLAYWRIGHT_AVAILABLE:
            return {"platform": "thangs_pw", "status": "⚠ 需要安装playwright", "auth": "无需认证"}
        try:
            results = self.search("gear", limit=3)
            if results:
                return {"platform": "thangs_pw", "status": f"✅ Playwright在线 ({len(results)}结果)", "auth": "无需认证"}
            return {"platform": "thangs_pw", "status": "⚠ 在线但无结果", "auth": "无需认证"}
        except Exception as e:
            return {"platform": "thangs_pw", "status": f"✗ {e}", "auth": "无需认证"}


def _parse_thangs_next_data(data: dict, query: str, limit: int) -> list:
    """从Thangs __NEXT_DATA__ SSR数据中提取模型列表
    路径: props.pageProps.fallback.$inf$search/v5/search-by-text?searchTerm=...
    """
    results = []
    try:
        fallback = data.get("props", {}).get("pageProps", {}).get("fallback", {})
        # Find the search results key (starts with $inf$search/v5/search-by-text)
        items = []
        for key, value in fallback.items():
            if "search-by-text" in key and "searchTerm" in key:
                # value is a list of pages, each page has items[]
                if isinstance(value, list):
                    for page_data in value:
                        if isinstance(page_data, dict) and "items" in page_data:
                            items.extend(page_data["items"])
                        elif isinstance(page_data, list):
                            items.extend(page_data)
                elif isinstance(value, dict) and "items" in value:
                    items = value["items"]
                break
        if not items:
            # Fallback: deep search for any list with modelId
            def deep_find(obj, depth=0):
                if depth > 6: return []
                if isinstance(obj, list) and obj and isinstance(obj[0], dict) and "modelId" in obj[0]:
                    return obj
                if isinstance(obj, dict):
                    for v in obj.values():
                        r = deep_find(v, depth+1)
                        if r: return r
                return []
            items = deep_find(data)

        for item in items[:limit]:
            if not isinstance(item, dict):
                continue
            mid = str(item.get("modelId", item.get("id", "")))
            results.append({
                "platform": "thangs",
                "id": mid,
                "name": item.get("name", item.get("filename", "")),
                "author": item.get("ownerUsername", item.get("owner", "?")),
                "url": f"https://thangs.com/model/{mid}",
                "likes": item.get("likesCount", item.get("likes", 0)),
                "downloads": item.get("downloadCount", item.get("downloads", 0)),
                "license": item.get("license", "?"),
                "tags": item.get("tags", item.get("categories", [])),
                "thumbnail": item.get("thumbnailUrl", item.get("thumbnail", "")),
                "summary": (item.get("description", "") or "")[:100],
            })
    except Exception as e:
        print(f"  ! Thangs parse error: {e}")
    return results


class PlaywrightGrabCADClient:
    """GrabCAD.com — Playwright无感获取"""

    def search(self, query: str, limit: int = 20) -> list:
        if not PLAYWRIGHT_AVAILABLE:
            return []
        captured = []
        pw = browser = ctx = page = None
        try:
            pw, browser, ctx = _make_browser()
            page = ctx.new_page()

            def on_response(response: Response):
                url = response.url
                if "grabcad.com" in url and any(k in url for k in ("library", "models", "search", "api")):
                    try:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct:
                            data = response.json()
                            captured.append({"url": url, "data": data})
                    except Exception:
                        pass

            page.on("response", on_response)
            search_url = f"https://grabcad.com/library?search_value={query.replace(' ', '+')}&sort=most_downloaded"
            page.goto(search_url, wait_until="networkidle", timeout=25000)
            page.wait_for_timeout(3000)

        except Exception as e:
            print(f"  ! Playwright GrabCAD error: {e}")
        finally:
            for obj in [page, ctx, browser]:
                if obj:
                    try: obj.close()
                    except: pass
            if pw:
                try: pw.stop()
                except: pass

        return _parse_grabcad_captured(captured, limit)

    def probe(self) -> dict:
        if not PLAYWRIGHT_AVAILABLE:
            return {"platform": "grabcad_pw", "status": "⚠ 需要安装playwright", "auth": "无需认证"}
        try:
            results = self.search("gear", limit=3)
            if results:
                return {"platform": "grabcad_pw", "status": f"✅ Playwright在线 ({len(results)}结果)", "auth": "无需认证"}
            return {"platform": "grabcad_pw", "status": "⚠ 在线但需登录/无JSON", "auth": "无需认证"}
        except Exception as e:
            return {"platform": "grabcad_pw", "status": f"✗ {e}", "auth": "无需认证"}


def _parse_grabcad_captured(captured: list, limit: int) -> list:
    results = []
    for cap in captured:
        data = cap.get("data", {})
        items = None
        for key in ("models", "results", "items", "cads"):
            if isinstance(data.get(key), list):
                items = data[key]
                break
        if items is None and isinstance(data, list):
            items = data
        if not items:
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            results.append({
                "platform": "grabcad",
                "id": str(item.get("id", "")),
                "name": item.get("name", item.get("title", "")),
                "author": item.get("creator", {}).get("username", "?") if isinstance(item.get("creator"), dict) else "?",
                "url": item.get("url", f"https://grabcad.com/library/{item.get('slug','')}"),
                "likes": item.get("likes_count", 0),
                "downloads": item.get("downloads_count", 0),
                "license": item.get("license", "?"),
                "tags": item.get("tags", []),
                "thumbnail": item.get("thumbnail_url", ""),
                "summary": (item.get("description", "") or "")[:100],
            })
            if len(results) >= limit:
                return results
    return results


class PlaywrightThreeD66Client:
    """3D溜溜 — Playwright绕过JS挑战"""

    def search(self, query: str, limit: int = 20) -> list:
        if not PLAYWRIGHT_AVAILABLE:
            return []
        results_container = []
        pw = browser = ctx = page = None
        try:
            pw, browser, ctx = _make_browser()
            page = ctx.new_page()

            def on_response(response: Response):
                url = response.url
                if "3d66.com" in url:
                    try:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct:
                            data = response.json()
                            results_container.append(data)
                    except Exception:
                        pass

            page.on("response", on_response)
            url = f"https://www.3d66.com/search/index.html?keyword={query.replace(' ', '+')}"
            page.goto(url, wait_until="networkidle", timeout=25000)
            page.wait_for_timeout(4000)

            # Try extracting from page DOM after JS execution
            if not results_container:
                try:
                    render_data = page.evaluate("""() => {
                        const el = document.querySelector('#renderData');
                        return el ? el.value : null;
                    }""")
                    if render_data:
                        data = json.loads(render_data)
                        results_container.append(data)
                except Exception:
                    pass

                # Also try window.__STORE__ or similar
                try:
                    store = page.evaluate("() => JSON.stringify(window.__STORE__ || window.__state__ || window.appData || {})")
                    if store and len(store) > 10:
                        results_container.append(json.loads(store))
                except Exception:
                    pass

        except Exception as e:
            print(f"  ! Playwright 3D66 error: {e}")
        finally:
            for obj in [page, ctx, browser]:
                if obj:
                    try: obj.close()
                    except: pass
            if pw:
                try: pw.stop()
                except: pass

        return _parse_3d66_captured(results_container, limit, query)

    def probe(self) -> dict:
        if not PLAYWRIGHT_AVAILABLE:
            return {"platform": "3d66_pw", "status": "⚠ 需要安装playwright", "auth": "无需认证"}
        try:
            results = self.search("gear", limit=3)
            if results:
                return {"platform": "3d66_pw", "status": f"✅ Playwright在线 ({len(results)}结果)", "auth": "无需认证"}
            return {"platform": "3d66_pw", "status": "⚠ 在线但未获取到数据", "auth": "无需认证"}
        except Exception as e:
            return {"platform": "3d66_pw", "status": f"✗ {e}", "auth": "无需认证"}


def _parse_3d66_captured(captured: list, limit: int, query: str) -> list:
    results = []
    for data in captured:
        items = None
        for key in ("list", "data", "models", "items", "result"):
            if isinstance(data.get(key), list) and data[key]:
                items = data[key]
                break
        if not items:
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            mid = str(item.get("id", item.get("model_id", "")))
            name = item.get("name", item.get("title", item.get("model_name", mid)))
            results.append({
                "platform": "3d66",
                "id": mid,
                "name": name,
                "author": item.get("author", item.get("username", "?")),
                "url": f"https://www.3d66.com/3dxz/{mid}.html" if mid else "https://www.3d66.com",
                "likes": item.get("like_count", item.get("like", 0)),
                "downloads": item.get("download_count", item.get("down", 0)),
                "license": "商业",
                "tags": item.get("tags", []),
                "thumbnail": item.get("thumb", item.get("image", item.get("img_url", ""))),
                "summary": (item.get("desc", item.get("description", "")) or "")[:100],
            })
            if len(results) >= limit:
                return results
    return results


class PlaywrightYeggiClient:
    """Yeggi — Playwright绕过JS机器人挑战 (40M+模型元搜索)"""

    def search(self, query: str, limit: int = 20) -> list:
        if not PLAYWRIGHT_AVAILABLE:
            return []
        import re as _re
        pw = browser = ctx = page = None
        content = ""
        try:
            pw, browser, ctx = _make_browser()
            page = ctx.new_page()
            import urllib.parse as _up
            url = f"https://www.yeggi.com/q/{_up.quote(query)}/"
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            # 等待Turnstile挑战自动完成
            page.wait_for_timeout(6000)
            content = page.content()
        except Exception as e:
            print(f"  ! PlaywrightYeggi error: {e}")
        finally:
            for obj in [page, ctx, browser]:
                if obj:
                    try: obj.close()
                    except: pass
            if pw:
                try: pw.stop()
                except: pass
        if not content:
            return []
        html = content.encode("utf-8", "replace")
        results = []
        # JSON-LD first
        json_ld = _re.findall(rb'<script type="application/ld\+json">(.*?)</script>', html, _re.DOTALL)
        import json as _json
        for block in json_ld:
            try:
                data = _json.loads(block)
                items = data if isinstance(data, list) else data.get("itemListElement", [])
                for item in items:
                    if len(results) >= limit:
                        break
                    if isinstance(item, dict):
                        name = item.get("name", item.get("item", {}).get("name", ""))
                        ext_url = item.get("url", item.get("item", {}).get("url", ""))
                        if name and ext_url:
                            results.append({
                                "platform": "yeggi_pw",
                                "id": str(len(results)),
                                "name": name,
                                "author": "?",
                                "url": ext_url,
                                "likes": 0, "downloads": 0, "license": "?",
                                "tags": [], "thumbnail": "",
                                "summary": "via Yeggi 元搜索",
                            })
            except Exception:
                continue
        if not results:
            # Fallback: extract hrefs to 3D platforms
            ext_links = _re.findall(
                rb'href="(https?://(?:www\.thingiverse\.com|www\.printables\.com|cults3d\.com|www\.myminifactory\.com|grabcad\.com|sketchfab\.com)[^"]+)"[^>]*>\s*([^<]{3,80})',
                html)
            for i, (ext_url, title) in enumerate(ext_links[:limit]):
                results.append({
                    "platform": "yeggi_pw",
                    "id": str(i),
                    "name": title.decode("utf-8", "replace").strip(),
                    "author": "?",
                    "url": ext_url.decode("utf-8", "replace"),
                    "likes": 0, "downloads": 0, "license": "?",
                    "tags": [], "thumbnail": "",
                    "summary": "via Yeggi 元搜索",
                })
        return results[:limit]

    def probe(self) -> dict:
        if not PLAYWRIGHT_AVAILABLE:
            return {"platform": "yeggi_pw", "status": "⚠ 需要安装playwright", "auth": "无需认证"}
        return {"platform": "yeggi_pw", "status": "⚠ CloudFlare Turnstile拦截 (人工验证)", "auth": "无需认证"}


class PlaywrightSTLFinderClient:
    """STLFinder — Playwright绕过CloudFlare WAF (聚合40+站)"""

    def search(self, query: str, limit: int = 20) -> list:
        if not PLAYWRIGHT_AVAILABLE:
            return []
        import re as _re
        pw = browser = ctx = page = None
        content = ""
        try:
            pw, browser, ctx = _make_browser()
            page = ctx.new_page()
            url = f"https://www.stlfinder.com/models/?q={query.replace(' ', '+')}"
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            # 等待CloudFlare挑战完成
            try:
                page.wait_for_function("() => document.body && document.body.innerText.length > 1000", timeout=12000)
            except Exception:
                pass
            page.wait_for_timeout(2000)
            content = page.content()
        except Exception as e:
            print(f"  ! PlaywrightSTLFinder error: {e}")
        finally:
            for obj in [page, ctx, browser]:
                if obj:
                    try: obj.close()
                    except: pass
            if pw:
                try: pw.stop()
                except: pass
        if not content:
            return []
        html = content.encode("utf-8", "replace")
        results = []
        slugs   = _re.findall(rb'href="(/model/[a-z0-9_\-]+/)"', html)
        names   = _re.findall(rb'class="[^"]*model-title[^"]*"[^>]*>([^<]+)<', html)
        sources = _re.findall(rb'class="[^"]*model-source[^"]*"[^>]*>([^<]+)<', html)
        seen = []
        for s in slugs:
            d = s.decode()
            if d not in seen: seen.append(d)
        for i, slug in enumerate(seen[:limit]):
            name   = names[i].decode("utf-8", "replace").strip()   if i < len(names)   else slug
            source = sources[i].decode("utf-8", "replace").strip() if i < len(sources) else "?"
            results.append({
                "platform": "stlfinder_pw",
                "id": slug.strip("/").split("/")[-1],
                "name": name,
                "author": source,
                "url": f"https://www.stlfinder.com{slug}",
                "likes": 0, "downloads": 0, "license": "?",
                "tags": [], "thumbnail": "",
                "summary": f"via STLFinder · {source}",
            })
        return results

    def probe(self) -> dict:
        if not PLAYWRIGHT_AVAILABLE:
            return {"platform": "stlfinder_pw", "status": "⚠ 需要安装playwright", "auth": "无需认证"}
        try:
            results = self.search("gear", limit=3)
            if results:
                return {"platform": "stlfinder_pw", "status": f"✅ Playwright在线 ({len(results)}结果)", "auth": "无需认证"}
            return {"platform": "stlfinder_pw", "status": "⚠ 在线但无结果(CloudFlare仍拦截)", "auth": "无需认证"}
        except Exception as e:
            return {"platform": "stlfinder_pw", "status": f"✗ {e}", "auth": "无需认证"}


class PlaywrightMMFClient:
    """MyMiniFactory — Playwright渲染React SPA (API需key, 前端无需认证)"""

    def search(self, query: str, limit: int = 20) -> list:
        if not PLAYWRIGHT_AVAILABLE:
            return []
        import re as _re, json as _json
        pw = browser = ctx = page = None
        content = ""
        captured = []
        try:
            pw, browser, ctx = _make_browser()
            page = ctx.new_page()

            def on_response(resp):
                ct = resp.headers.get("content-type", "")
                if "json" in ct and resp.status == 200 and "myminifactory" in resp.url:
                    try:
                        body = resp.body()
                        if len(body) > 100:
                            captured.append({"url": resp.url, "body": body})
                    except Exception:
                        pass

            page.on("response", on_response)
            url = f"https://www.myminifactory.com/search/?query={query.replace(' ', '+')}"
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(5000)
            content = page.content()
        except Exception as e:
            print(f"  ! PlaywrightMMF error: {e}")
        finally:
            for obj in [page, ctx, browser]:
                if obj:
                    try: obj.close()
                    except: pass
            if pw:
                try: pw.stop()
                except: pass

        results = []
        # Try intercepted JSON first
        for cap in captured:
            try:
                data = _json.loads(cap["body"])
                items = data.get("items", data.get("objects", data.get("results", [])))
                if not isinstance(items, list):
                    continue
                for item in items[:limit]:
                    if not isinstance(item, dict):
                        continue
                    mid = str(item.get("id", item.get("slug", "")))
                    slug = item.get("url", item.get("slug", mid))
                    results.append({
                        "platform": "mmf_pw",
                        "id": mid,
                        "name": item.get("name", item.get("title", mid)),
                        "author": item.get("designer", {}).get("username", "?") if isinstance(item.get("designer"), dict) else "?",
                        "url": f"https://www.myminifactory.com/object/{slug}/" if not slug.startswith("http") else slug,
                        "likes": item.get("likes", 0),
                        "downloads": item.get("downloads", 0),
                        "license": item.get("license", "CC"),
                        "tags": item.get("tags", []),
                        "thumbnail": item.get("images", [{}])[0].get("thumbnail", {}).get("url", "") if item.get("images") else "",
                        "summary": (item.get("description", "") or "")[:100],
                    })
                if results:
                    return results[:limit]
            except Exception:
                continue

        # Fallback: parse rendered HTML
        if content:
            html = content.encode("utf-8", "replace")
            slugs = _re.findall(rb'href="/object/([a-z0-9_\-]+)/"', html)
            names = _re.findall(rb'class="[^"]*object[^"]*title[^"]*"[^>]*>([^<]{2,80})<', html)
            seen = []
            for s in slugs:
                d = s.decode()
                if d not in seen:
                    seen.append(d)
            for i, slug in enumerate(seen[:limit]):
                name = names[i].decode("utf-8", "replace").strip() if i < len(names) else slug
                results.append({
                    "platform": "mmf_pw",
                    "id": slug,
                    "name": name,
                    "author": "?",
                    "url": f"https://www.myminifactory.com/object/{slug}/",
                    "likes": 0, "downloads": 0, "license": "CC",
                    "tags": [], "thumbnail": "", "summary": "",
                })
        return results[:limit]

    def probe(self) -> dict:
        if not PLAYWRIGHT_AVAILABLE:
            return {"platform": "mmf_pw", "status": "⚠ 需要安装playwright", "auth": "无需认证"}
        try:
            results = self.search("gear", limit=3)
            if results:
                return {"platform": "mmf_pw", "status": f"✅ Playwright在线 ({len(results)}结果)", "auth": "无需认证"}
            return {"platform": "mmf_pw", "status": "⚠ 在线但无结果(React SPA)", "auth": "无需认证"}
        except Exception as e:
            return {"platform": "mmf_pw", "status": f"✗ {e}", "auth": "无需认证"}


class PlaywrightNIHClient:
    """NIH 3D Print Exchange — Playwright渲染React SPA (旧REST API已下线)"""

    def search(self, query: str, limit: int = 20) -> list:
        if not PLAYWRIGHT_AVAILABLE:
            return []
        import re as _re, json as _json
        pw = browser = ctx = page = None
        content = ""
        captured_json = []
        try:
            pw, browser, ctx = _make_browser()
            page = ctx.new_page()

            def on_response(resp):
                ct = resp.headers.get("content-type", "")
                if ("json" in ct or "api" in resp.url) and resp.status == 200:
                    try:
                        body = resp.body()
                        if len(body) > 100 and b"nid" in body:
                            captured_json.append(body)
                    except Exception:
                        pass

            page.on("response", on_response)
            url = f"https://3dprint.nih.gov/discover?query={query.replace(' ', '+')}"
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(5000)
            content = page.content()
        except Exception as e:
            print(f"  ! PlaywrightNIH error: {e}")
        finally:
            for obj in [page, ctx, browser]:
                if obj:
                    try: obj.close()
                    except: pass
            if pw:
                try: pw.stop()
                except: pass

        results = []
        # Try intercepted JSON
        for body in captured_json:
            try:
                data = _json.loads(body)
                items = data.get("data", data.get("results", data if isinstance(data, list) else []))
                for item in (items if isinstance(items, list) else [])[:limit]:
                    if not isinstance(item, dict):
                        continue
                    nid = str(item.get("nid", item.get("id", "")))
                    results.append({
                        "platform": "nih_pw",
                        "id": nid,
                        "name": item.get("title", ""),
                        "author": item.get("username", item.get("author", "?")),
                        "url": f"https://3dprint.nih.gov/discover/{nid}",
                        "likes": item.get("flag_count", 0),
                        "downloads": item.get("download_count", 0),
                        "license": item.get("license", "CC0"),
                        "tags": item.get("tags", []),
                        "thumbnail": item.get("image_url", ""),
                        "summary": (item.get("description", "") or "")[:100],
                    })
                if results:
                    return results[:limit]
            except Exception:
                continue

        # Fallback: parse rendered HTML
        if content:
            html = content.encode("utf-8", "replace")
            links = _re.findall(rb'href="/discover/([0-9]+)"', html)
            titles = _re.findall(rb'class="[^"]*(?:title|name)[^"]*"[^>]*>([^<]{2,100})<', html)
            seen = []
            for l in links:
                d = l.decode()
                if d not in seen:
                    seen.append(d)
            for i, nid in enumerate(seen[:limit]):
                name = titles[i].decode("utf-8", "replace").strip() if i < len(titles) else f"Model {nid}"
                results.append({
                    "platform": "nih_pw",
                    "id": nid,
                    "name": name,
                    "author": "NIH",
                    "url": f"https://3dprint.nih.gov/discover/{nid}",
                    "likes": 0, "downloads": 0, "license": "CC0",
                    "tags": [], "thumbnail": "", "summary": "",
                })
        return results[:limit]

    def probe(self) -> dict:
        if not PLAYWRIGHT_AVAILABLE:
            return {"platform": "nih_pw", "status": "⚠ 需要安装playwright", "auth": "无需认证"}
        try:
            results = self.search("gear", limit=3)
            if results:
                return {"platform": "nih_pw", "status": f"✅ Playwright在线 ({len(results)}结果)", "auth": "无需认证"}
            return {"platform": "nih_pw", "status": "⚠ 在线但无结果(React渲染)", "auth": "无需认证"}
        except Exception as e:
            return {"platform": "nih_pw", "status": f"✗ {e}", "auth": "无需认证"}


# ─── 统一Playwright搜索 ────────────────────────────────────────────────────────
PLAYWRIGHT_PLATFORMS = {
    "thangs_pw":     PlaywrightThangsClient(),
    "grabcad_pw":    PlaywrightGrabCADClient(),
    "3d66_pw":       PlaywrightThreeD66Client(),
    "yeggi_pw":      PlaywrightYeggiClient(),
    "stlfinder_pw":  PlaywrightSTLFinderClient(),
    "mmf_pw":        PlaywrightMMFClient(),
    "nih_pw":        PlaywrightNIHClient(),
}


def playwright_search(query: str, platforms: list = None, limit: int = 20) -> list:
    """统一Playwright搜索接口"""
    if platforms is None:
        platforms = list(PLAYWRIGHT_PLATFORMS.keys())
    all_results = []
    for name in platforms:
        client = PLAYWRIGHT_PLATFORMS.get(name)
        if client:
            print(f"  ▶ {name} (Playwright)...")
            results = client.search(query, limit)
            print(f"    {len(results)} 结果")
            all_results.extend(results)
    return all_results


def playwright_probe(platforms: list = None) -> list:
    """探测Playwright平台状态"""
    if platforms is None:
        platforms = list(PLAYWRIGHT_PLATFORMS.keys())
    status = []
    for name in platforms:
        client = PLAYWRIGHT_PLATFORMS.get(name)
        if client:
            r = client.probe()
            status.append(r)
            print(f"  {r['status']:30s} [{r['platform']}]")
    return status


if __name__ == "__main__":
    import sys
    query = sys.argv[1] if len(sys.argv) > 1 else "gear"
    plat  = sys.argv[2] if len(sys.argv) > 2 else "thangs_pw"
    print(f"Playwright搜索: '{query}' [{plat}]")
    results = PLAYWRIGHT_PLATFORMS[plat].search(query, 10)
    for r in results:
        print(f"  {r['name']} — {r['url']}")
    if not results:
        print("  (无结果)")
