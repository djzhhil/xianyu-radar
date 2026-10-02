const { chromium } = require('playwright');
const { spawn } = require('child_process');
const assert = require('assert/strict');
const path = require('path');
const root = path.resolve(__dirname, '..');
const artifactDir = process.env.RADAR_UI_ARTIFACT_DIR || '/tmp/xianyu-radar-workbench';
require('fs').mkdirSync(artifactDir, { recursive: true });
const code = `from pathlib import Path
import tempfile, uvicorn
from xianyu_radar import config as cfg
cfg.DATA_DIR=Path(tempfile.mkdtemp(prefix="radar-ui-"))
cfg.STATE_DIR=cfg.DATA_DIR/"state"
cfg.DEBUG_DIR=cfg.DATA_DIR/"debug"
cfg.DB_PATH=cfg.DATA_DIR/"radar.sqlite3"
from xianyu_radar.entrypoints.api.app import create_app
from xianyu_radar.infrastructure.storage.db import init_db
conn=init_db()
conn.execute("INSERT INTO sellers(seller_id,first_seen_at,last_seen_at) VALUES ('12345','t','t')")
conn.executemany("INSERT INTO items(item_id,seller_id,title,status,first_seen_at,last_seen_at) VALUES (?,'12345',?,?, 't','t')", [(str(i),"FDE "+str(i),"removed" if i==24 else "active") for i in range(25)])
conn.execute("UPDATE items SET image='https://images.example.test/good.png' WHERE item_id='24'")
conn.execute("UPDATE items SET image='https://images.example.test/broken.png' WHERE item_id='23'")
conn.execute("INSERT INTO scans(id,seller_id,started_at,status,item_count) VALUES ('ok','12345','t','ok',25)")
conn.execute("INSERT INTO scans(id,seller_id,started_at,status,error_kind) VALUES ('bad','12345','t','failed','incomplete')")
conn.executemany("INSERT INTO candidates(normalized_title,sample_title,first_seen_at,last_seen_at,status) VALUES (?,?, '2026-10-02T00:00:00Z','2026-10-02T00:00:00Z',?)", [("fde-interview","FDE 面试资料","new"),("fde-project","FDE 项目案例","testing"),("fde-learning","FDE 学习资料","validated")])
conn.commit()
conn.close()
uvicorn.run(create_app(),host="127.0.0.1",port=18766)
`;
(async () => {
  const server = spawn(`${root}/.venv/bin/python`, ['-c', code], { cwd: root, stdio: ['ignore', 'ignore', 'pipe'] });
  let browser;
  try {
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('server startup timeout')), 15000);
      server.stderr.on('data', d => { if (d.toString().includes('Uvicorn running')) { clearTimeout(timer); resolve(); } });
      server.on('exit', c => reject(new Error(`server exited ${c}`)));
    });
    browser = await chromium.launch({ executablePath: process.env.RADAR_BROWSER_PATH || undefined, args: ['--no-sandbox'], headless: true });
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    await page.route('https://images.example.test/**', route => route.fulfill(route.request().url().endsWith('good.png')
      ? { contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1ioAAAAASUVORK5CYII=', 'base64') }
      : { status: 404, body: '' }));
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('http://127.0.0.1:18766');
    await page.click('[data-tab="pool"]');
    await page.fill('#addSellerForm [name="reference"]', 'https://www.goofish.com/personal?userId=12345');
    await page.fill('#addSellerForm [name="nickname"]', '测试商家');
    await page.click('#addSellerForm button');
    await page.waitForFunction(() => document.querySelector('#addSellerResult').textContent.includes('已添加'));
    await page.waitForSelector('#sellerDetail:not([hidden])');
    await page.click('[data-seller-view="metadata"]');
    await page.fill('#sellerTags', 'FDE, FDE, 重点');
    await page.fill('#sellerNotes', '同品商家，优先参考');
    await page.click('#sellerMetadataForm button');
    await page.waitForFunction(() => document.querySelector('#sellerMetadataResult').textContent.includes('已保存'));
    const patch = await page.request.patch('http://127.0.0.1:18766/api/pool/12345', { data: { status: 'paused' } });
    assert.equal(patch.status(), 200);
    await page.click('#closeSellerDetail');
    await page.fill('#addSellerForm [name="reference"]', '12345');
    await page.click('#addSellerForm button');
    await page.waitForFunction(() => document.querySelector('#addSellerResult').textContent.includes('已在商家池'));
    assert.match(await page.locator('#addSellerResult').innerText(), /暂停/);
    assert.equal(await page.locator('#sellerNotes').inputValue(), '同品商家，优先参考');
    assert.equal(await page.locator('#sellerTags').inputValue(), 'FDE, 重点');
    await page.click('[data-seller-view="sources"]');
    assert.equal(await page.locator('#sellerEntriesBody tr').count(), 1);
    await page.click('[data-seller-view="catalog"]');
    assert.equal(await page.locator('#sellerItemsBody tr').count(), 20);
    await page.click('#sellerItemsNext');
    await page.waitForFunction(() => document.querySelectorAll('#sellerItemsBody tr').length === 5);
    await page.fill('#sellerItemQuery', 'FDE 24');
    await page.selectOption('#sellerItemStatus', 'removed');
    await page.click('#sellerItemFilters button');
    await page.waitForFunction(() => document.querySelectorAll('#sellerItemsBody tr').length === 1 && document.querySelector('#sellerItemsBody').textContent.includes('FDE 24'));
    assert.equal(await page.locator('#sellerItemsBody tr').count(), 1);
    assert.match(await page.locator('#sellerCatalogQuality').innerText(), /最近完整扫描.*分页不完整/);
    await page.locator('#sellerItemsBody img').scrollIntoViewIfNeeded();
    await page.waitForFunction(() => document.querySelector('#sellerItemsBody img')?.naturalWidth > 0);
    await page.fill('#sellerItemQuery', 'FDE 23');
    await page.selectOption('#sellerItemStatus', 'active');
    await page.click('#sellerItemFilters button');
    await page.waitForFunction(() => document.querySelector('#sellerItemsBody').textContent.includes('图片失效'));
    await page.fill('#sellerItemQuery', 'FDE 22');
    await page.click('#sellerItemFilters button');
    await page.waitForFunction(() => document.querySelector('#sellerItemsBody').textContent.includes('暂无图片'));
    await page.fill('#sellerItemQuery', 'FDE 24');
    await page.selectOption('#sellerItemStatus', 'removed');
    await page.click('#sellerItemFilters button');
    await page.waitForFunction(() => document.querySelector('#sellerItemsBody img')?.naturalWidth > 0);
    await page.screenshot({ path: `${artifactDir}/workbench-detail-desktop.png`, fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: `${artifactDir}/workbench-detail-mobile.png`, fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
    await page.click('#closeSellerDetail');
    await page.fill('#addSellerForm [name="reference"]', 'https://evil.example/personal?userId=123');
    await page.click('#addSellerForm button');
    await page.waitForFunction(() => document.querySelector('#addSellerResult').textContent.includes('请输入'));
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.screenshot({ path: `${artifactDir}/workbench-desktop.png`, fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: `${artifactDir}/workbench-mobile.png`, fullPage: true });
    const sizes = await page.locator('#addSellerForm').evaluate(el => ({ width: el.clientWidth, scroll: el.scrollWidth }));
    assert.equal(sizes.scroll <= sizes.width + 1, true);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), true);
    for (const size of [{ width: 390, height: 844 }, { width: 1280, height: 900 }]) {
      await page.setViewportSize(size);
      for (const tab of ['pool', 'candidates', 'scan', 'discover', 'auth']) {
        await page.click(`[data-tab="${tab}"]`);
        assert.equal(await page.locator(`#tab-${tab}`).isVisible(), true);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
      }
    }
    await page.click('#btnRefresh');
    await page.waitForFunction(() => !document.querySelector('#btnRefresh').disabled);
    assert.equal(await page.locator('#btnRefresh svg').count(), 1);
    await page.click('[data-tab="candidates"]');
    await page.selectOption('#candStatus', 'testing');
    await page.waitForFunction(() => document.querySelectorAll('.cand').length === 1);
    assert.match(await page.locator('.cand .title').innerText(), /项目案例/);
    await page.selectOption('.cand select', 'validated');
    await page.waitForFunction(() => document.querySelectorAll('.cand').length === 0);
    await page.selectOption('#candStatus', 'all');
    await page.waitForFunction(() => document.querySelectorAll('.cand').length === 3);
    await page.screenshot({ path: `${artifactDir}/workbench-candidates-desktop.png`, fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: `${artifactDir}/workbench-candidates-mobile.png`, fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
    await page.goto('http://127.0.0.1:18766/#scan');
    await page.waitForFunction(() => document.querySelector('#pageTitle').textContent === '扫描与变化');
    assert.deepEqual(errors, []);
    console.log('PASS: manual seller, metadata, catalog pagination/filter/quality, invalid URL, mobile form, no JS errors');
  } finally {
    if (browser) await browser.close();
    server.kill('SIGTERM');
    await new Promise(resolve => { if (server.exitCode !== null) resolve(); else server.on('exit', resolve); });
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
