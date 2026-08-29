#!/usr/bin/env python3
"""SPT Stash — interactive HTML stash-manifest generator."""

import html
import json
import re
import urllib.parse


def generate_html_stash_manifest(manifest):
    cards_html = ""
    for mod in manifest.get("mods", []):
        img_src = mod.get("image_url") or "https://files.sp-mod.com/mods/placeholder.png"
        title = html.escape(mod.get("title") or mod.get("name", "Unknown Mod"))
        author = html.escape(mod.get("author") or mod.get("creator", "Community"))
        ver = html.escape(str(mod.get("version", "")))
        cat = html.escape(mod.get("category", "General"))
        mod_type = html.escape(mod.get("type", "Mod"))
        raw_desc = mod.get("description", "")
        desc = html.escape(re.sub(r"<[^>]+>", "", raw_desc))[:240]
        if len(raw_desc) > 240:
            desc += "..."

        raw_link = mod.get("link")
        if not raw_link:
            query_name = urllib.parse.quote(mod.get("name", title))
            raw_link = f"https://sp-mod.com/mods?query={query_name}"
        link = html.escape(raw_link)

        img_tag = (
            f'<img src="{img_src}" alt="{title}" loading="lazy" referrerpolicy="no-referrer" '
            f'crossorigin="anonymous" onerror="this.onerror=null; this.style.display=\'none\';"/>'
            if img_src
            else ""
        )

        cards_html += f"""
        <div class="card">
            {img_tag}
            <div class="card-body">
                <div class="title">{title}</div>
                <div class="author">by {author} • <span class="version">v{ver}</span></div>
                <div class="badges">
                    <span class="badge badge-type">{mod_type}</span>
                    <span class="badge badge-cat">{cat}</span>
                </div>
                <div class="desc">{desc}</div>
                <a class="btn" href="{link}" target="_blank">🔗 View on sp-mod.com</a>
            </div>
        </div>
        """

    json_data = json.dumps(manifest, indent=2)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="referrer" content="no-referrer">
    <title>🎒 SPT Stash Manifest — {html.escape(manifest.get("spt_version", "SPT"))}</title>
    <style>
        body {{ background-color: #11111b; color: #cdd6f4; font-family: 'Segoe UI', Ubuntu, Roboto, sans-serif; padding: 32px 20px; margin: 0; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{ text-align: center; margin-bottom: 36px; border-bottom: 1px solid #313244; padding-bottom: 24px; }}
        .header h1 {{ color: #89b4fa; font-size: 32px; margin: 0 0 10px 0; font-weight: 800; }}
        .header p {{ color: #a6adc8; font-size: 15px; margin: 0; }}
        .meta-badges {{ margin-top: 14px; display: flex; justify-content: center; gap: 12px; flex-wrap: wrap; }}
        .meta-badge {{ background-color: #313244; color: #a6e3a1; padding: 6px 14px; border-radius: 20px; font-weight: bold; font-size: 13px; }}
        .howto-box {{ background-color: #1e1e2e; border: 1px solid #89b4fa; border-radius: 12px; padding: 20px; margin-bottom: 32px; }}
        .howto-box h3 {{ color: #89b4fa; margin: 0 0 10px 0; font-size: 16px; display: flex; align-items: center; gap: 8px; }}
        .howto-box ol {{ margin: 0; padding-left: 20px; color: #cdd6f4; font-size: 14px; line-height: 1.6; }}
        .howto-box code {{ background-color: #313244; color: #a6e3a1; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 13px; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 24px; }}
        .card {{ background-color: #181825; border: 1px solid #313244; border-radius: 14px; overflow: hidden; display: flex; flex-direction: column; transition: transform 0.2s, border-color 0.2s; }}
        .card:hover {{ transform: translateY(-4px); border-color: #89b4fa; }}
        .card img {{ width: 100%; height: 170px; object-fit: cover; background-color: #1e1e2e; }}
        .card-body {{ padding: 18px; display: flex; flex-direction: column; flex-grow: 1; }}
        .title {{ color: #89b4fa; font-size: 18px; font-weight: bold; margin-bottom: 4px; line-height: 1.3; }}
        .author {{ color: #9399b2; font-size: 13px; margin-bottom: 10px; }}
        .version {{ color: #fab387; font-weight: bold; }}
        .badges {{ margin-bottom: 12px; display: flex; gap: 8px; flex-wrap: wrap; }}
        .badge {{ padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: bold; }}
        .badge-type {{ background-color: #313244; color: #cba6f7; }}
        .badge-cat {{ background-color: #313244; color: #89dceb; }}
        .desc {{ font-size: 13px; color: #bac2de; line-height: 1.5; flex-grow: 1; margin-bottom: 16px; }}
        .btn {{ display: block; text-align: center; background-color: #89b4fa; color: #11111b; text-decoration: none; padding: 10px; border-radius: 8px; font-weight: bold; font-size: 13px; transition: background-color 0.2s; }}
        .btn:hover {{ background-color: #b4befe; }}
        .footer {{ text-align: center; margin-top: 40px; color: #6c7086; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎒 SPT Stash Manifest</h1>
            <p>Single-Player Tarkov Co-Op & Raid Mod Loadout</p>
            <div class="meta-badges">
                <span class="meta-badge">Target: {html.escape(manifest.get("spt_version", "SPT"))}</span>
                <span class="meta-badge">📦 {manifest.get("total_packages", len(manifest.get("mods", [])))} Mod Packages</span>
                <span class="meta-badge">📁 {manifest.get("total_files", len(manifest.get("mods", [])))} Component Files</span>
            </div>
        </div>
        <div class="howto-box">
            <h3>💡 Quick Import Instructions for SPT Stash</h3>
            <ol>
                <li>Launch <b>SPT Stash</b> on your system.</li>
                <li>Go to the <b>🎒 Presets && Manifests</b> tab (or <b>Installed Mods</b> tab).</li>
                <li>Click <b>📥 Import Preset File</b> and select this file (<code id="manifest-filename">stash_manifest.html</code>).</li>
                <li>Click <b>▶ Apply Preset to Game</b> — <b>SPT Stash</b> will instantly enable all included mods and 1-click download any missing ones!</li>
            </ol>
        </div>
        <div class="grid">
            {cards_html}
        </div>
        <div class="footer">
            Generated by <b>SPT Stash</b> — Native Linux Mod Manager for SPTarkov
        </div>
    </div>
    <script>
    document.addEventListener("DOMContentLoaded", function() {{
        var filename = window.location.pathname.split('/').pop() || "stash_manifest.html";
        var el = document.getElementById("manifest-filename");
        if (el) el.textContent = decodeURIComponent(filename);
    }});
    </script>
    <script id="stash-manifest-data" type="application/json">
{json_data}
    </script>
</body>
</html>"""
