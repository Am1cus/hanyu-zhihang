// Run with Playwright CLI: -s=4c run-code --filename=learn/competition/tools/record_demo.js
// Uses the real local UI. Recording starts/stops separately; no generated motion.
async (page) => {
  const began = Date.now();
  const waitUntil = async (seconds) => {
    const left = seconds * 1000 - (Date.now() - began);
    if (left > 0) await page.waitForTimeout(left);
  };
  await page.getByRole('button', { name: '01 任务预演', exact: true }).click();
  await page.getByRole('combobox', { name: /温度情景/ }).selectOption('0');
  await page.getByRole('button', { name: '比较两种策略', exact: true }).click();
  await page.getByRole('heading', { name: '全任务往返预算' }).scrollIntoViewIfNeeded();
  await page.waitForTimeout(1800);
  await page.screenshot({ path: 'output/playwright/4C/budget-zero.png' });
  await waitUntil(9);
  await page.getByRole('combobox', { name: /温度情景/ }).selectOption('-20');
  await page.getByRole('button', { name: '比较两种策略', exact: true }).click();
  await page.getByRole('heading', { name: '全任务往返预算' }).scrollIntoViewIfNeeded();
  await page.waitForTimeout(1800);
  await page.screenshot({ path: 'output/playwright/4C/budget-minus20.png' });
  await waitUntil(20);
  await page.getByRole('combobox', { name: /温度情景/ }).selectOption('-10');
  await page.getByRole('button', { name: '启动任务 →', exact: true }).click();
  await page.getByRole('heading', { name: '条件变了，重新判断。' }).scrollIntoViewIfNeeded();
  await waitUntil(27);
  await page.getByRole('button', { name: '暂停', exact: true }).click();
  await page.getByRole('button', { name: '在地图上新增障碍', exact: true }).click();
  const map = page.getByRole('img', { name: '巡检地图，点击格子发送新增障碍事件', exact: true });
  await map.scrollIntoViewIfNeeded();
  // Derive a future route cell from the currently rendered, real SVG route.
  const points = (await map.locator('polyline[stroke-dasharray="6 3"]').getAttribute('points')).split(' ').map(p => p.split(',').map(Number));
  if (points.length < 4) throw new Error('Need a route with an unoccupied future cell');
  const point = points[Math.min(4, points.length - 1)];
  const target = await map.evaluate((el, p) => {
    const v = el.createSVGPoint(); v.x = p[0]; v.y = p[1];
    const screen = v.matrixTransform(el.getScreenCTM());
    return { x: screen.x, y: screen.y };
  }, point);
  await page.mouse.click(target.x, target.y);
  await page.waitForTimeout(1000);
  await page.getByRole('heading', { name: '条件变了，重新判断。' }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: 'output/playwright/4C/manual-obstacle-paused.png' });
  await waitUntil(36);
  await page.getByRole('button', { name: '继续', exact: true }).click();
  await page.waitForTimeout(1600);
  await page.getByRole('heading', { name: '条件变了，重新判断。' }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: 'output/playwright/4C/manual-obstacle-reroute.png' });
  await waitUntil(51);
  await page.getByRole('heading', { name: '判断时间线', exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: 'output/playwright/4C/decision-timeline.png' });
  await waitUntil(72);
  await page.getByRole('button', { name: '查看完整档案', exact: true }).click();
  await page.getByRole('heading', { name: '条件变化记录', exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: 'output/playwright/4C/archive-events.png' });
  await waitUntil(80);
  await page.getByRole('link', { name: '导出 JSON', exact: true }).click();
  await page.getByRole('heading', { name: '正常巡检 · 场景 1', exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: 'output/playwright/4C/archive-result.png' });
  await waitUntil(88);
  console.log(JSON.stringify({ recorded_flow: 'temperature_budget_start_manual_obstacle_reroute_decision_export', elapsed_s: (Date.now() - began) / 1000 }));
}
