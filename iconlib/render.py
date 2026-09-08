"""Small HTML/JS widgets: copy an icon or a diagram to the clipboard as a PNG."""

from __future__ import annotations

import json
import uuid
from typing import Optional

BUTTON_CSS = """
<style>
  .cbrow { display:flex; gap:6px; align-items:center; flex-wrap:wrap;
           font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }
  .cbrow button {
    font-size:12px; padding:4px 10px; border-radius:7px; cursor:pointer;
    border:1px solid rgba(130,140,160,.45); background:transparent;
    color:inherit; transition:background .12s ease;
  }
  .cbrow button:hover { background:rgba(130,140,160,.16); }
  .cbrow .msg { font-size:11.5px; opacity:.75; }
</style>
"""


def copy_png_widget(
    data_uri: str,
    filename: str,
    *,
    png_size: int = 512,
    label: str = "Copy image",
    show_download: bool = True,
    background: Optional[str] = None,
) -> str:
    """HTML for a 'copy PNG to clipboard' (+ download) button pair.

    Rasterises the image in the browser, so it works for SVG and bitmaps alike
    with no server-side image dependency.
    """
    uid = "w" + uuid.uuid4().hex[:8]
    script = """
<div class="cbrow">
  <button id="__UID__c">__LABEL__</button>
  __DL__
  <span class="msg" id="__UID__m"></span>
</div>
<script>
(function(){
  var SRC = __SRC__, NAME = __NAME__, SIZE = __SIZE__, BG = __BG__;
  var msg = document.getElementById("__UID__m");
  function say(t, ok){ msg.textContent = t; msg.style.color = ok ? "#1a9c5f" : "#c2543f";
                       setTimeout(function(){ msg.textContent = ""; }, 2600); }
  function toBlob(){
    return new Promise(function(resolve, reject){
      var img = new Image();
      img.onload = function(){
        var w = img.naturalWidth || SIZE, h = img.naturalHeight || SIZE;
        var s = SIZE / Math.max(w, h);
        var c = document.createElement("canvas");
        c.width = Math.max(1, Math.round(w * s)); c.height = Math.max(1, Math.round(h * s));
        var ctx = c.getContext("2d");
        if (BG) { ctx.fillStyle = BG; ctx.fillRect(0, 0, c.width, c.height); }
        ctx.drawImage(img, 0, 0, c.width, c.height);
        c.toBlob(function(b){ b ? resolve(b) : reject(new Error("encode failed")); }, "image/png");
      };
      img.onerror = function(){ reject(new Error("could not load image")); };
      img.src = SRC;
    });
  }
  document.getElementById("__UID__c").onclick = function(){
    toBlob().then(function(blob){
      if (!navigator.clipboard || !window.ClipboardItem) throw new Error("clipboard unavailable");
      return navigator.clipboard.write([new ClipboardItem({"image/png": blob})]);
    }).then(function(){ say("Copied - paste anywhere", true); })
      .catch(function(e){ say(String(e.message || e), false); });
  };
  var dl = document.getElementById("__UID__d");
  if (dl) dl.onclick = function(){
    toBlob().then(function(blob){
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob); a.download = NAME + ".png";
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(function(){ URL.revokeObjectURL(a.href); }, 4000);
      say("Downloaded", true);
    }).catch(function(e){ say(String(e.message || e), false); });
  };
})();
</script>
"""
    download_btn = f'<button id="{uid}d">Download PNG</button>' if show_download else ""
    html = (
        BUTTON_CSS
        + script.replace("__UID__", uid)
        .replace("__LABEL__", label)
        .replace("__DL__", download_btn)
        .replace("__SRC__", json.dumps(data_uri))
        .replace("__NAME__", json.dumps(filename))
        .replace("__SIZE__", str(int(png_size)))
        .replace("__BG__", json.dumps(background) if background else "null")
    )
    return html


def icon_tile(data_uri: str, caption: str, size: int = 46, tint: str = "#6b7488") -> str:
    """A centred icon preview with a caption, for search-result grids."""
    return (
        f'<div style="text-align:center;padding:6px 2px 2px">'
        f'<img src="{data_uri}" style="height:{size}px;max-width:100%;object-fit:contain" />'
        f'<div style="font-size:10.5px;color:{tint};margin-top:5px;word-break:break-all;'
        f'line-height:1.25">{caption}</div></div>'
    )
