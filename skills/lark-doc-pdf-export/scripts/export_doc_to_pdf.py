#!/usr/bin/env python3
"""
Export a Feishu/Lark docx (or wiki node wrapping docx) to PDF when the
document's download/export permission is disabled.

Pipeline:
  1. Fetch document content as DocxXML via `lark-cli docs +fetch`
  2. Extract embedded image tokens, download each via `lark-cli drive +preview`
  3. Convert DocxXML to a styled HTML document (Feishu-like typography)
  4. Render HTML to PDF via headless Chrome

Usage:
  python3 export_doc_to_pdf.py <feishu_url> [--output OUTPUT_PATH] [--as user]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import html as html_mod
from pathlib import Path


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def run_lark(args: list[str], timeout: int = 120, cwd: str | None = None) -> dict:
    """Run a lark-cli command and return parsed JSON. Raises on failure."""
    cmd = ["lark-cli"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(
            f"lark-cli failed (exit {result.returncode}):\n"
            f"  cmd: {' '.join(cmd)}\n"
            f"  stderr: {result.stderr[:500]}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"lark-cli returned non-JSON: {result.stdout[:500]}")


def find_chrome() -> str | None:
    """Locate a Chrome/Chromium binary on macOS."""
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


# ---------------------------------------------------------------------------
# Step 1: fetch document content
# ---------------------------------------------------------------------------

def fetch_document(url: str, identity: str = "user") -> tuple[str, str]:
    """Return (xml_content, document_title)."""
    data = run_lark([
        "docs", "+fetch",
        "--doc", url,
        "--doc-format", "xml",
        "--as", identity,
        "--format", "json",
    ])
    if not data.get("ok"):
        raise RuntimeError(f"docs +fetch failed: {json.dumps(data.get('error', {}), ensure_ascii=False)[:300]}")
    doc = data["data"]["document"]
    return doc["content"], doc["title"]


# ---------------------------------------------------------------------------
# Step 2: extract and download images
# ---------------------------------------------------------------------------

def extract_image_tokens(xml: str) -> list[str]:
    """Extract unique image file tokens from DocxXML, preserving order."""
    tokens = re.findall(r'<img[^>]*src="([^"]+)"', xml)
    seen = set()
    unique = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


def download_images(tokens: list[str], img_dir: Path, identity: str = "user") -> dict[str, str]:
    """Download each image via drive +preview. Return {token: local_path}."""
    img_map = {}
    for i, token in enumerate(tokens):
        filename = f"img_{i:03d}_{token}.png"
        out_path = img_dir / filename
        if out_path.exists() and out_path.stat().st_size > 500:
            img_map[token] = str(out_path)
            continue
        try:
            # lark-cli restricts --output to paths under cwd; use relative path + cwd
            run_lark([
                "drive", "+preview",
                "--file-token", token,
                "--type", "source_file",
                "--output", filename,
                "--as", identity,
            ], timeout=60, cwd=str(img_dir))
            if out_path.exists() and out_path.stat().st_size > 500:
                img_map[token] = str(out_path)
            else:
                print(f"  [WARN] image {token} downloaded but file too small", file=sys.stderr)
        except Exception as e:
            print(f"  [WARN] failed to download image {token}: {e}", file=sys.stderr)
    return img_map


# ---------------------------------------------------------------------------
# Step 3: DocxXML -> HTML
# ---------------------------------------------------------------------------

def xml_to_html(xml: str, img_map: dict[str, str]) -> str:
    """Convert Feishu DocxXML to styled HTML body."""
    h = xml

    # Replace image src tokens with local file:// paths
    for token, local_path in img_map.items():
        h = h.replace(f'src="{token}"', f'src="file://{local_path}"')

    # <img> -> clean <img> + optional caption
    def fix_img(m):
        tag = m.group(0)
        src = re.search(r'src="([^"]+)"', tag)
        alt = re.search(r'alt="([^"]*)"', tag)
        caption = re.search(r'caption="([^"]*)"', tag)
        # Only render images that were successfully downloaded (file:// src)
        if not src or not src.group(1).startswith("file://"):
            cap = ""
            if caption:
                cap = caption.group(1).replace("&#xA;", " ").strip()
            label = cap or (alt.group(1) if alt else "图片")
            return f'<div class="img-missing">&#128444; {html_mod.escape(label)}</div>'
        out = '<img'
        if src:
            out += f' src="{src.group(1)}"'
        if alt:
            out += f' alt="{html_mod.escape(alt.group(1))}"'
        out += ' />'
        if caption:
            cap = caption.group(1).replace("&#xA;", " ").strip()
            if cap:
                out += f'<div class="img-caption">{html_mod.escape(cap)}</div>'
        return out

    h = re.sub(r'<img[^>]*/?>', fix_img, h)

    # Callout blocks
    h = re.sub(
        r'<callout emoji="([^"]*)">',
        r'<div class="callout"><span class="callout-emoji">\1</span><div class="callout-content">',
        h,
    )
    h = h.replace("</callout>", "</div></div>")

    # Grid / column layouts
    h = h.replace("<grid>", '<div class="grid">')
    h = h.replace("</grid>", "</div>")
    h = re.sub(
        r'<column width-ratio="([^"]*)">',
        r'<div class="grid-column" style="flex:\1">',
        h,
    )
    h = h.replace("</column>", "</div>")

    # Video figure -> placeholder
    h = re.sub(
        r'<figure[^>]*>.*?</figure>',
        '<div class="video-placeholder">&#128249; 视频内容（原文档含视频，PDF中略）</div>',
        h,
        flags=re.DOTALL,
    )

    # Buttons -> styled span
    h = re.sub(r'<button[^>]*>(.*?)</button>', r'<span class="button-link">\1</span>', h)

    # Headings: strip seq attributes
    h = re.sub(r'<h(\d)[^>]*>', r'<h\1>', h)

    # List items: strip attributes
    h = re.sub(r'<li[^>]*>', '<li>', h)

    # Title
    h = h.replace("<title>", '<h1 class="doc-title">')
    h = h.replace("</title>", "</h1>")

    # Misc
    h = h.replace("<hr/>", "<hr>")
    h = re.sub(r"<p>\s*</p>", "", h)

    return h


CSS = """
@page { size: A4; margin: 20mm 18mm; }
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC",
    "Hiragino Sans GB", "Microsoft YaHei", "Helvetica Neue", Helvetica,
    Arial, sans-serif;
  font-size: 14px; line-height: 1.8; color: #1f2329;
  margin: 0; padding: 0; word-wrap: break-word;
}
.doc-title { font-size: 24px; font-weight: 700; line-height: 1.4; margin: 0 0 16px; }
h1 { font-size: 20px; font-weight: 700; margin: 28px 0 12px; padding-bottom: 8px;
     border-bottom: 1px solid #e5e6eb; }
h2 { font-size: 17px; font-weight: 700; margin: 22px 0 10px; }
h3 { font-size: 15px; font-weight: 600; margin: 18px 0 8px; }
p { margin: 8px 0; }
ul, ol { margin: 8px 0; padding-left: 24px; }
li { margin: 4px 0; }
blockquote { margin: 12px 0; padding: 12px 16px; background: #f7f8fa;
  border-left: 3px solid #c9cdd4; color: #4e5969; border-radius: 0 4px 4px 0; }
blockquote p { margin: 4px 0; }
a { color: #3370ff; text-decoration: none; }
img { max-width: 100%; height: auto; border-radius: 4px; display: block; margin: 8px auto; }
.img-caption { text-align: center; font-size: 12px; color: #86909c; margin: 4px 0 12px; }
.img-missing { margin: 12px 0; padding: 16px; background: #f7f8fa; border: 1px dashed #c9cdd4;
  border-radius: 6px; text-align: center; color: #86909c; font-size: 13px; }
.callout { display: flex; align-items: flex-start; margin: 12px 0; padding: 12px 16px;
  background: #f7f8fa; border-radius: 6px; border: 1px solid #e5e6eb; }
.callout-emoji { font-size: 18px; margin-right: 10px; flex-shrink: 0; line-height: 1.6; }
.callout-content { flex: 1; }
.callout-content p { margin: 4px 0; }
.grid { display: flex; gap: 16px; margin: 12px 0; }
.grid-column { flex: 1; min-width: 0; }
.grid-column img { max-width: 100%; }
.video-placeholder { margin: 16px 0; padding: 24px; background: #f7f8fa;
  border: 1px dashed #c9cdd4; border-radius: 6px; text-align: center; color: #86909c; }
hr { border: none; border-top: 1px solid #e5e6eb; margin: 24px 0; }
b, strong { font-weight: 600; }
.button-link { display: inline-block; padding: 6px 16px; background: #3370ff;
  color: #fff !important; border-radius: 4px; font-size: 13px; margin: 8px 0; }
"""


def build_html(xml: str, img_map: dict[str, str], title: str) -> str:
    body = xml_to_html(xml, img_map)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{html_mod.escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
{body}
</body>
</html>"""


# ---------------------------------------------------------------------------
# Step 4: HTML -> PDF via headless Chrome
# ---------------------------------------------------------------------------

def html_to_pdf(html_path: Path, pdf_path: Path) -> None:
    chrome = find_chrome()
    if not chrome:
        raise RuntimeError(
            "No Chrome/Chromium binary found. Install Google Chrome to use this skill."
        )
    with tempfile.TemporaryDirectory(prefix="chrome-pdf-profile-") as profile_dir:
        cmd = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--hide-scrollbars",
            "--password-store=basic",
            "--disable-features=PasswordImport,ChromeWhatsNewUI",
            f"--user-data-dir={profile_dir}",
            "--no-pdf-header-footer",
            "--virtual-time-budget=15000",
            f"--print-to-pdf={pdf_path}",
            f"file://{html_path}",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            raise RuntimeError("Chrome headless timed out after 180s while rendering PDF.")
        # Chrome may return non-zero even on success; check file existence
        if not pdf_path.exists() or pdf_path.stat().st_size < 1000:
            raise RuntimeError(
                f"Chrome PDF generation failed (exit {result.returncode}):\n"
                f"  stderr: {result.stderr[:500]}"
            )


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify_pdf(pdf_path: Path) -> dict:
    """Basic sanity check: page count and image count."""
    try:
        import pymupdf
    except ImportError:
        return {"verified": False, "reason": "pymupdf not installed; skipping verification"}
    doc = pymupdf.open(str(pdf_path))
    info = {
        "verified": True,
        "pages": doc.page_count,
        "images": sum(len(doc[i].get_images()) for i in range(doc.page_count)),
        "size_bytes": pdf_path.stat().st_size,
    }
    doc.close()
    return info


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Export a Feishu docx/wiki to PDF when export is disabled."
    )
    parser.add_argument("url", help="Feishu docx or wiki URL")
    parser.add_argument("--output", "-o", help="Output PDF path (default: <title>.pdf in cwd)")
    parser.add_argument("--as", dest="identity", default="user",
                        help="lark-cli identity (default: user)")
    parser.add_argument("--keep-html", action="store_true",
                        help="Keep the intermediate HTML file")
    args = parser.parse_args()

    work_dir = Path(tempfile.mkdtemp(prefix="lark-pdf-export-"))
    img_dir = work_dir / "images"
    img_dir.mkdir()

    try:
        # 1. Fetch
        print(f"[1/4] Fetching document content...")
        xml_content, doc_title = fetch_document(args.url, args.identity)
        print(f"      Title: {doc_title}")
        print(f"      Content: {len(xml_content)} chars")

        # 2. Download images
        tokens = extract_image_tokens(xml_content)
        print(f"[2/4] Downloading {len(tokens)} images via preview channel...")
        img_map = download_images(tokens, img_dir, args.identity)
        print(f"      Downloaded {len(img_map)}/{len(tokens)} images")

        # 3. Build HTML
        print(f"[3/4] Generating styled HTML...")
        html_content = build_html(xml_content, img_map, doc_title)
        html_path = work_dir / "document.html"
        html_path.write_text(html_content, encoding="utf-8")
        print(f"      HTML: {html_path.stat().st_size} bytes")

        # 4. Render PDF
        print(f"[4/4] Rendering PDF via headless Chrome...")
        if args.output:
            pdf_path = Path(args.output).expanduser().resolve()
        else:
            safe_title = re.sub(r'[\\/:*?"<>|]', '_', doc_title)[:80]
            pdf_path = Path.cwd() / f"{safe_title}.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        html_to_pdf(html_path, pdf_path)
        print(f"      PDF: {pdf_path} ({pdf_path.stat().st_size / 1024 / 1024:.2f} MB)")

        # Verify
        info = verify_pdf(pdf_path)
        if info.get("verified"):
            print(f"      Verified: {info['pages']} pages, {info['images']} images")

        if args.keep_html:
            kept_html = pdf_path.with_suffix(".html")
            kept_html.write_text(html_content, encoding="utf-8")
            print(f"      HTML kept at: {kept_html}")

        print(f"\nDone: {pdf_path}")

    finally:
        if not args.keep_html:
            import shutil
            shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
