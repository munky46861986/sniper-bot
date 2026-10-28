#!/usr/bin/env python3
"""Public Sisal page access probe. No login, protected APIs, or browser stealth."""
import json,re,os
from pathlib import Path
from playwright.sync_api import sync_playwright
out=Path("sisal_probe_output");out.mkdir(exist_ok=True)
report={"url":"https://www.sisal.it/10elotto","accessible":False,"draw_visible":False}
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True)
  page=browser.new_page(viewport={"width":1440,"height":900},locale="it-IT")
  response=page.goto(report["url"],wait_until="domcontentloaded",timeout=45000)
  page.wait_for_timeout(5000)
  report["http_status"]=response.status if response else None
  page.screenshot(path=str(out/"page.png"))
  txt=page.locator("body").inner_text(timeout=10000)
  report["title"]=page.title()
  report["visible_excerpt"]=txt[:700]
  report["draw_visible"]=bool(re.search(r"ESTRAZIONE\\s*N\\.?\\s*\\d+",txt,re.I))
  report["accessible"]=report["http_status"]==200 and not bool(re.search(r"Radware Block Page|Access Denied|Forbidden|captcha",txt,re.I))
  if report["accessible"] and not report["draw_visible"]:
   try:
    page.get_by_text(re.compile(r"ESTRAZIONE\\s*N",re.I)).first.scroll_into_view_if_needed(timeout=5000)
    page.wait_for_timeout(1200)
    page.screenshot(path=str(out/"draw_area.png"))
    txt=page.locator("body").inner_text(timeout=10000)
    report["draw_visible"]=bool(re.search(r"ESTRAZIONE\\s*N\\.?\\s*\\d+",txt,re.I))
   except Exception:pass
  browser.close()
except Exception as e:report["error"]=type(e).__name__+": "+str(e)[:400]
(out/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
print(json.dumps(report,ensure_ascii=False))
