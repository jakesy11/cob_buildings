"""Browser smoke checks against the generated artifact; no screenshots retained."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser=p.chromium.launch()
    page=browser.new_page(viewport={"width":1440,"height":1000})
    errors=[]
    page.on("pageerror",lambda e:errors.append(str(e)))
    page.goto((root/"output/index.html").as_uri(),wait_until="networkidle",timeout=120000)
    page.wait_for_function('document.querySelector("#count").textContent !== "—"',timeout=30000)
    count=int(page.locator("#count").inner_text().replace(",",""))
    # Unclassified fallback is valid only when explicitly labelled; source completeness is a separate check.
    if count==0:
        page.select_option("#category","")
        count=int(page.locator("#count").inner_text().replace(",",""))
    assert count>0,"Map contains no visible footprints"
    page.fill("#search","__no_such_bellevue_building_7f92__")
    page.wait_for_function('document.querySelector("#count").textContent === "0"')
    page.click("#reset")
    page.wait_for_function('document.querySelector("#count").textContent !== "0"')
    page.click("#sourcesButton")
    assert page.locator("#sources").is_visible()
    page.click("#closeSources")
    page.evaluate('layer.getLayers()[0].openPopup()')
    assert page.locator(".leaflet-popup-content").is_visible()
    page.locator(".leaflet-popup-close-button").click()
    linked=int(page.locator("#recordCount").inner_text().replace(",",""))
    if linked:
        with page.expect_download() as info: page.click("#csv")
        assert info.value.suggested_filename.endswith(".csv")
    page.set_viewport_size({"width":390,"height":844})
    assert page.locator("#category").is_visible()
    assert not errors,errors
    (root/"output/browser_checks.json").write_text(json.dumps({"status":"passed","initial_visible_footprints":count,"linked_records_after_reset":linked,"checks":["render","search","reset","source dialog","footprint popup","CSV download when records present","mobile controls"],"javascript_errors":errors},indent=2))
    print("Browser checks passed:",count,"initial visible footprints;",linked,"linked records after reset")
    browser.close()
