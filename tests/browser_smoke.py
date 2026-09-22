"""Run against an already running local server: python tests/browser_smoke.py."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser=p.chromium.launch()
    page=browser.new_page(viewport={'width':1440,'height':1050},device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:5050')
    page.wait_for_selector('.kpi-value')
    expect(page.locator('.workspace')).to_contain_text('CS50 Group')
    assert page.locator('.kpi-value').nth(1).inner_text()=='10.000'
    page.locator('#operator').select_option('Orange')
    expect(page.locator('.kpi-value').nth(1)).to_have_text('1.500')
    page.locator('#reset-filters').click()
    expect(page.locator('.kpi-value').nth(1)).to_have_text('10.000')
    expect(page.locator('.comparison-main').first.locator('h2')).to_have_text('Monthly spend by operator')
    first_chart=page.locator('#comparison-trends')
    assert first_chart.locator('[data-series]').count()==3
    assert first_chart.locator('[data-series][stroke-dasharray]').count()==0
    assert first_chart.locator('circle').count()==0
    assert float(first_chart.locator('svg').get_attribute('data-axis-min'))>0
    page.locator('[data-compare-metric="data"]').click()
    expect(first_chart.locator('h2')).to_have_text('Monthly data per SIM')
    first_chart.locator('[data-chart-tooltip]').last.hover()
    expect(first_chart.locator('.chart-tooltip')).to_be_visible()
    expect(first_chart.locator('.chart-tooltip')).to_contain_text('Movistar:')
    expect(first_chart.locator('.chart-tooltip')).to_contain_text('Vodafone:')
    expect(first_chart.locator('.chart-tooltip')).to_contain_text('Orange:')
    page.locator('[data-compare-operator="Vodafone"]').click()
    expect(page.locator('.kpi-value').nth(1)).to_have_text('2.500')
    expect(first_chart.locator('[data-series]')).to_have_count(1)
    page.locator('[data-compare-operator=""]').click()
    expect(page.locator('.kpi-value').nth(1)).to_have_text('10.000')
    page.locator('[data-compare-metric="cost"]').click()
    expect(first_chart.locator('h2')).to_have_text('Monthly cost per SIM')
    first_chart.screenshot(path=str(ROOT/'data'/'cost-comparison.png'))
    page.screenshot(path=str(ROOT/'data'/'overview.png'),full_page=True)
    page.locator('nav [data-page="roaming"]').click()
    page.wait_for_selector('#roaming-map .map-marker')
    assert page.locator('#content .notice').count()==0
    expect(page.locator('.kpi-value').nth(1)).to_have_text('115')
    page.locator('.country-line[data-country="AD"]').click()
    page.wait_for_selector('dialog[open]')
    assert 'Andorra' in page.locator('#dialog-content').inner_text()
    page.locator('#close-dialog').click()
    page.locator('[data-map="world"]').click()
    page.screenshot(path=str(ROOT/'data'/'roaming.png'),full_page=True)
    page.locator('nav [data-page="fleet"]').click()
    page.wait_for_selector('[data-sim]')
    page.locator('[data-sim]').first.click()
    page.wait_for_selector('dialog[open]')
    assert 'Monthly calculated charges' in page.locator('#dialog-content').inner_text()
    page.locator('#close-dialog').click()
    page.locator('nav [data-page="tariffs"]').click()
    page.wait_for_selector('.profile-card')
    assert page.locator('#content .notice').count()==0
    assert page.locator('.profile-card').count()==9
    expect(page.locator('.profile-card').first.locator('.price')).to_contain_text('0,50')
    expect(page.locator('.profile-card').nth(1).locator('.price')).to_contain_text('2,00')
    expect(page.locator('.profile-card').nth(2).locator('.price')).to_contain_text('6,00')
    assert page.locator('.profile-card .operator-logo').all_text_contents()==['M']*3+['V']*3+['O']*3
    assert page.locator('.profile-card .small-tag').all_text_contents()==[
        f'{operator}-{allowance}' for operator in ('MV','VF','OR') for allowance in (50,500,5000)]
    page.screenshot(path=str(ROOT/'data'/'tariffs.png'),full_page=True)
    page.locator('[data-profile-zones]').first.click()
    page.wait_for_selector('dialog[open]')
    page.locator('#close-dialog').click()
    page.locator('nav [data-page="reconciliation"]').click()
    page.wait_for_selector('[data-sim]')
    page.locator('#fleet-issue').select_option('variance')
    expect(page.locator('#fleet-count')).to_contain_text('236')
    page.locator('nav [data-page="imports"]').click()
    page.wait_for_selector('#import-file')
    # Preview only: browser smoke keeps the clean recruiter demo unchanged.
    from sys import path
    path.insert(0,str(ROOT))
    from imports import sample
    page.locator('#import-file').set_input_files({'name':'demo.csv','mimeType':'text/csv','buffer':sample('Movistar','inventory','csv')})
    page.locator('#preview-import').click()
    page.wait_for_selector('#commit-import:not([disabled])')
    assert '3 valid of 3 rows' in page.locator('#import-preview').inner_text()
    page.screenshot(path=str(ROOT/'data'/'imports.png'),full_page=True)
    page.locator('nav [data-page="overview"]').click()
    page.wait_for_selector('.kpi-value')
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(ROOT/'data'/'mobile.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    assert not errors, errors
    browser.close()
    print('PASS: six views, filters, map, details, adapter preview, mobile overflow; no JavaScript errors.')
