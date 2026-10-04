// Run with Playwright CLI run-code --filename=/absolute/path/record_demo.js
// Start video separately with --size=1440x810; real UI and real backend motion.
async (page) => {
  const began = Date.now();
  const waitUntil = async (seconds) => {
    const remaining = seconds * 1000 - (Date.now() - began);
    if (remaining > 0) await page.waitForTimeout(remaining);
  };
  // Preparation must open “看懂低温取舍” before recording.
  await page.locator('.cold-demo').scrollIntoViewIfNeeded();
  await waitUntil(25);
  await page.getByRole('button', { name: '运行 −20 °C 案例，观察一点后返程', exact: true }).click();
  await page.locator('.decision-spotlight').waitFor();
  await page.locator('.decision-spotlight').scrollIntoViewIfNeeded();
  await page.getByText('转为返程', { exact: true }).first().waitFor({ timeout: 35000 });
  const returnDecisionAt = (Date.now() - began) / 1000;
  await page.locator('.decision-spotlight').scrollIntoViewIfNeeded();
  await page.getByRole('button', { name: '查看完整档案', exact: true }).waitFor({ timeout: 35000 });
  await waitUntil(58);
  await page.getByRole('button', { name: '查看完整档案', exact: true }).click();
  await page.locator('.detail-stats').waitFor();
  await page.locator('.detail-stats').scrollIntoViewIfNeeded();
  const exportUrl = new URL(await page.getByRole('link', { name: '导出 JSON', exact: true }).getAttribute('href'), page.url()).href;
  const exported = await (await page.request.get(exportUrl)).json();
  if (exported.summary.visited_count !== 1 || !exported.summary.returned || exported.state.status !== 'COMPLETED') throw new Error('Actual one-point return required');
  await waitUntil(72);
  await page.getByRole('heading', { name: '决策记录', exact: true }).scrollIntoViewIfNeeded();
  await waitUntil(83);
  await page.locator('.archive-detail .execution-audit').scrollIntoViewIfNeeded();
  await waitUntil(87);
  await page.getByRole('link', { name: '导出 JSON', exact: true }).scrollIntoViewIfNeeded();
  await page.getByRole('link', { name: '导出 JSON', exact: true }).click();
  await waitUntil(90);
  return { identity: 'actual local UI recording, automated operation', run_id: exported.state.id,
    export_url: exportUrl, summary: exported.summary, return_decision_wall_s: returnDecisionAt,
    elapsed_s: (Date.now() - began) / 1000, simulation_speedup: 20,
    cancellation_used: false, obstacle_event_used: false };
}
