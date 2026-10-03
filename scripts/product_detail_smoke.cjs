const { chromium } = require('playwright');
const { spawn } = require('child_process');
const assert = require('assert/strict');
const path = require('path');
const root = path.resolve(__dirname, '..');
const artifactDir = '/tmp/xianyu-product-detail';
require('fs').mkdirSync(artifactDir, { recursive: true });
const code = `from pathlib import Path
import tempfile, uvicorn
from xianyu_radar import config as cfg
cfg.DATA_DIR=Path(tempfile.mkdtemp(prefix="radar-detail-ui-"))
cfg.STATE_DIR=cfg.DATA_DIR/"state"
cfg.DEBUG_DIR=cfg.DATA_DIR/"debug"
cfg.DB_PATH=cfg.DATA_DIR/"radar.sqlite3"
from xianyu_radar.entrypoints.api.app import create_app
from xianyu_radar.entrypoints.api.routes import products
from xianyu_radar.infrastructure.goofish.session import Session
from xianyu_radar.infrastructure.goofish.mtop import MtopError
from xianyu_radar.infrastructure.storage.db import init_db
from xianyu_radar.infrastructure.storage.seller_repository import add_manual_seller
from xianyu_radar.modules.scan.service import apply_scan_result
from xianyu_radar.modules.products import service
from xianyu_radar.models import SellerItem
conn=init_db()
add_manual_seller(conn,"456","示例商家")
apply_scan_result(conn,"456",[SellerItem("123","商品详情展示测试","12.50","https://www.goofish.com/item?id=123")])
conn.close()
products.require_session=lambda: Session("cookie","real-token","test")
def response(session,api,data,params):
    assert data["needSellerDO"] is False
    if data["id"]=="124":
        raise MtopError("x5sec / USER_VALIDATE required")
    return {"data":{"itemDO":{"itemId":data["id"],"title":"商品详情展示测试 / AI 实战资料","soldPrice":"12.50","gmtCreate":1791000000000,"browseCnt":"1234","wantCnt":0,"interactFavorCnt":7,"imageInfos":[{"url":"https://images.example.test/item.png"}]}}}
service.call_mtop=response
uvicorn.run(create_app(),host="127.0.0.1",port=18767)
`;
(async () => {
  const server = spawn(`${root}/.venv/bin/python`, ['-c', code], { cwd: root, stdio: ['ignore', 'ignore', 'pipe'] });
  let browser;
  try {
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('server startup timeout')), 15000);
      let stderr = '';
      server.stderr.on('data', d => { stderr += d; if (stderr.includes('Uvicorn running')) { clearTimeout(timer); resolve(); } });
      server.on('exit', c => { clearTimeout(timer); reject(new Error(`server exited ${c}: ${stderr}`)); });
    });
    browser = await chromium.launch({ executablePath: process.env.RADAR_BROWSER_PATH || undefined, args: ['--no-sandbox'], headless: true });
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route('https://images.example.test/**', route => route.fulfill({ contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1ioAAAAASUVORK5CYII=', 'base64') }));
    await page.goto('http://127.0.0.1:18767/?seller=456#pool');
    await page.locator('#sellerItemsBody a').filter({ hasText: '商品详情' }).click();
    await page.locator('#detailContent').waitFor({ state: 'visible' });
    assert.equal(await page.locator('#itemViews').innerText(), '1,234');
    assert.equal(await page.locator('#itemWants').innerText(), '0');
    assert.equal(await page.locator('#itemFavorites').innerText(), '未知');
    assert.equal(await page.locator('#itemInteractions').innerText(), '7');
    assert.equal(await page.locator('#refreshDetail svg').count(), 1);
    await page.waitForFunction(() => document.querySelector('#itemPhoto img')?.naturalWidth > 0);
    for (const width of [1280, 390]) {
      await page.setViewportSize({ width, height: 900 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
      await page.screenshot({ path: `${artifactDir}/detail-${width}.png`, fullPage: true });
    }
    await page.click('#refreshDetail');
    await page.waitForFunction(() => !document.querySelector('#refreshDetail').disabled);
    await page.click('#backToCatalog');
    await page.locator('#sellerItemsBody a').filter({ hasText: '商品详情' }).waitFor();
    await page.goto('http://127.0.0.1:18767/items/124?seller=456');
    await page.waitForFunction(() => document.querySelector('#detailStatus').textContent.includes('人机验证'));
    assert.equal(await page.locator('#detailContent').isVisible(), false);
    assert.equal(await page.locator('#refreshDetail').isEnabled(), true);
    await page.screenshot({ path: `${artifactDir}/verification-mobile.png`, fullPage: true });
    assert.deepEqual(errors, []);
    console.log('PASS: catalog navigation, product fields, zero/unknown, refresh, return, verification, images, desktop/mobile');
  } finally {
    if (browser) await browser.close();
    server.kill('SIGTERM');
    await new Promise(resolve => { if (server.exitCode !== null) resolve(); else server.on('exit', resolve); });
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
