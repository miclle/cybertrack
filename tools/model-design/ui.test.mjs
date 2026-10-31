import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, mkdir, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { chromium } from 'playwright';
import { startUiHost } from './ui-test-host.mjs';

test('built plugin: narrow layout, drafts and external undo feedback', { timeout: 60000 }, async t => {
  const host = await startUiHost();
  t.after(() => host.close());
  const browser = await chromium.launch({ headless: true });
  t.after(() => browser.close());
  const output = process.env.SOLIDCUE_UI_EVIDENCE ? resolve(process.env.SOLIDCUE_UI_EVIDENCE) : await mkdtemp(join(tmpdir(), 'solidcue-ui-'));
  await mkdir(output, { recursive: true });
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const frame = page.frameLocator('iframe');
  const ready = async () => {
    await page.goto(host.url);
    await frame.getByText('r3 · FreeCAD 快照 · 已连接当前对话', { exact: true }).waitFor();
    assert.equal(await frame.locator('#webgl-error').isVisible(), false);
  };
  const screenshot = name => page.locator('iframe').screenshot({ path: join(output, name + '.png') });
  const layouts = [];
  const checkLayout = async (width, height, selector) => {
    const result = await frame.locator(selector).evaluate(element => {
      const rect = element.getBoundingClientRect(), toolbar = document.querySelector('.toolbar').getBoundingClientRect();
      return { width: innerWidth, height: innerHeight, scrollWidth: document.documentElement.scrollWidth,
        left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom, toolbarBottom: toolbar.bottom };
    });
    layouts.push({ selector, ...result });
    assert.equal(result.width, width);
    assert.equal(result.height, height);
    assert.equal(result.scrollWidth, width, 'no horizontal overflow');
    assert.ok(result.left >= 0 && result.right <= width && result.bottom <= height, 'control fits card');
    if (selector !== '.toolbar') assert.ok(result.top >= result.toolbarBottom, 'panel does not cover toolbar');
  };

  await ready();
  for (const [width, height] of [[390, 640], [320, 568], [1280, 720]]) {
    await page.locator('#size').selectOption(`${width}×${height}`);
    // ResizeObserver and renderer must observe the actual iframe dimensions.
    await frame.locator('canvas').waitFor();
    await checkLayout(width, height, '.toolbar');
    assert.equal(await frame.locator('#history-panel').isVisible(), false);
    assert.equal(await frame.locator('#details-panel').isVisible(), false);
    await screenshot(`canvas-${width}`);
    await frame.getByRole('button', { name: '更多' }).click();
    await checkLayout(width, height, '#details-panel');
    await frame.getByRole('button', { name: 'UI 测试块', exact: true }).click();
    await frame.getByRole('textbox', { name: '模型评论' }).fill('将 Height 改为 16 mm，保持其他尺寸。');
    await checkLayout(width, height, '#comment-popover');
    await screenshot(`comment-${width}`);
    await page.keyboard.press('Escape');
    assert.equal(await frame.locator('#comment-popover').isVisible(), false);
    await frame.getByRole('button', { name: '继续评论' }).click();
    assert.equal(await frame.getByRole('textbox', { name: '模型评论' }).inputValue(), '将 Height 改为 16 mm，保持其他尺寸。');
    await frame.getByRole('button', { name: '关闭评论，保留草稿' }).click();
    await frame.getByRole('button', { name: '历史', exact: true }).click();
    await frame.getByText('r2 → r3 · 查看变化', { exact: true }).click();
    await checkLayout(width, height, '#history-panel');
    await screenshot(`history-${width}`);
    await frame.getByRole('button', { name: '关闭历史', exact: true }).click();
  }

  await ready();
  await frame.getByRole('button', { name: '撤销', exact: true }).click();
  await frame.getByText('已请求当前对话恢复 FreeCAD 文档，等待原生执行与快照同步。', { exact: true }).waitFor();
  await screenshot('undo-waiting');
  await page.getByRole('button', { name: '发布匹配的恢复快照' }).click();
  await frame.getByText('已恢复 FreeCAD 原生文档，当前版本 r4。', { exact: true }).waitFor();
  assert.equal(await frame.getByRole('button', { name: '撤销', exact: true }).isDisabled(), true);
  assert.equal(await page.locator('#messages').textContent(), '1 条撤销请求');
  await screenshot('undo-restored');

  await ready();
  await frame.getByRole('button', { name: '撤销', exact: true }).click();
  await frame.getByText('已请求当前对话恢复 FreeCAD 文档，等待原生执行与快照同步。', { exact: true }).waitFor();
  await page.getByRole('button', { name: '发布无关恢复记录' }).click();
  await frame.getByText('r3 → r4 · 查看变化', { exact: true }).waitFor({ state: 'attached' });
  assert.match(await frame.locator('#history-status').textContent(), /等待原生执行/);
  await page.getByRole('button', { name: '发布匹配的恢复快照' }).click();
  await frame.getByText('已恢复 FreeCAD 原生文档，当前版本 r5。', { exact: true }).waitFor();

  await ready();
  await page.getByLabel('拒绝撤销请求').check();
  await frame.getByRole('button', { name: '撤销', exact: true }).click();
  await frame.getByText('撤销未完成：宿主拒绝了撤销请求。', { exact: true }).waitFor();
  assert.equal(await frame.getByRole('button', { name: '撤销', exact: true }).isEnabled(), true);
  await screenshot('undo-rejected');
  await page.getByLabel('拒绝撤销请求').uncheck();
  await frame.getByRole('button', { name: '撤销', exact: true }).click();
  await frame.getByText('已请求当前对话恢复 FreeCAD 文档，等待原生执行与快照同步。', { exact: true }).waitFor();
  await page.getByRole('button', { name: '发布匹配的恢复快照' }).click();
  await frame.getByText('已恢复 FreeCAD 原生文档，当前版本 r4。', { exact: true }).waitFor();
  assert.equal(await page.locator('#messages').textContent(), '2 条撤销请求');
  assert.deepEqual(errors, []);
  await writeFile(join(output, 'results.json'), JSON.stringify({ scope: 'synthetic MCP host; no native CAD or conversation writes', layouts, errors }, null, 2));
  console.log(`UI evidence: ${output}`);
});
