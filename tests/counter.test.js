/**
 * カードカウンター同期テスト
 *
 * テスト対象の問題:
 *   進捗タブで「もう一回」を複数回押した後、カード学習タブに切り替えると
 *   カウンターが正しく表示されないバグ（修正済み）の回帰テスト。
 *
 * テスト方針:
 *   - Supabase CDN をモックに差し替え（本番DB影響ゼロ）
 *   - Google 認証をスキップ（偽セッションを即座に注入）
 *   - localStorage を使った状態管理は通常通り動作
 */

const { test, expect, beforeEach } = require('@playwright/test');
const { mockSupabase, waitForAppReady, setupAllGreen } = require('./helpers/mock-supabase');

// ─── ヘルパー ────────────────────────────────────────────

/** 進捗タブに切り替える */
async function goToProgress(page) {
  await page.click('button:has-text("進捗")');
}

/** カード学習タブに切り替える */
async function goToCards(page) {
  await page.click('button:has-text("カード学習")');
}

/** 進捗タブで特定の単語の「もう一回」ボタンをクリック */
async function clickMouIkkai(page, wordEnglish) {
  // .wi 内の .wen テキストで対象を特定
  const row = page.locator('#wlistBody .wi').filter({
    has: page.locator(`.wen:text("${wordEnglish}")`)
  });
  await row.locator('.review-tag').click();
}

/** 進捗タブに表示されている「もう一回」ボタンを全てクリック（先頭から順に）*/
async function clickAllMouIkkai(page) {
  // renderResults() が毎クリック後にリストを再構築するため、
  // 常に先頭ボタンを取得し直すことで正しくクリックできる
  while (true) {
    const btn = page.locator('#wlistBody .review-tag').first();
    if (await btn.count() === 0) break;
    await btn.click();
  }
}

/** カードに解答して次へ進む（ヒントなし正解 → 次へ） */
async function answerCorrectly(page, word) {
  await page.fill('#ansInput', word);
  await page.click('#checkBtn');
  await page.waitForSelector('#resRow .rb.next', { timeout: 3000 });
  await page.click('#resRow .rb.next');
}

/** カードカウンター（ctr）のテキストを取得 */
async function getCtr(page) {
  return page.locator('#ctr').textContent();
}

// ─── 各テスト前のセットアップ ─────────────────────────────

test.beforeEach(async ({ page }) => {
  // localStorage をクリアして完全にクリーンな状態から開始
  await page.addInitScript(() => localStorage.clear());
  // Supabase CDN をモックに差し替え
  await mockSupabase(page);
  // ページ読み込み・アプリ初期化待ち
  await page.goto('/');
  await waitForAppReady(page);
  // 全単語を green にして完了画面を表示
  await setupAllGreen(page);
});

// ─── T1: 単一「もう一回」 ──────────────────────────────────

test('T1: 「もう一回」×1 → カード学習タブのカウンターが 1/1', async ({ page }) => {
  await goToProgress(page);
  await clickMouIkkai(page, 'awesome');

  await goToCards(page);

  await expect(page.locator('#ctr')).toHaveText('1 / 1');
});

// ─── T2: 連続2回「もう一回」（バグ再現ケース）──────────────

test('T2: 「もう一回」×2 → カード学習タブのカウンターが 1/2', async ({ page }) => {
  await goToProgress(page);
  await clickMouIkkai(page, 'awesome');
  await clickMouIkkai(page, 'clown');

  await goToCards(page);

  await expect(page.locator('#ctr')).toHaveText('1 / 2');
});

// ─── T3: T2 の状態で1枚正解後 ─────────────────────────────

test('T3: 「もう一回」×2 → 1枚正解後カウンターが 2/2', async ({ page }) => {
  await goToProgress(page);
  await clickMouIkkai(page, 'awesome');
  await clickMouIkkai(page, 'clown');

  await goToCards(page);
  await answerCorrectly(page, 'awesome');

  await expect(page.locator('#ctr')).toHaveText('2 / 2');
});

// ─── T4: タブ往復パターン（ユーザー指摘） ─────────────────

test('T4: もう一回 → カード学習確認 → 進捗 → もう一回 → カード学習でカウンターが 1/2', async ({ page }) => {
  await goToProgress(page);
  await clickMouIkkai(page, 'awesome');

  // 一度カード学習タブを確認
  await goToCards(page);
  await expect(page.locator('#ctr')).toHaveText('1 / 1');

  // 進捗に戻って2語目を追加
  await goToProgress(page);
  await clickMouIkkai(page, 'clown');

  await goToCards(page);

  await expect(page.locator('#ctr')).toHaveText('1 / 2');
});

// ─── T5: 全語「もう一回」 ─────────────────────────────────

test('T5: 全8語「もう一回」→ カウンターが 1/8', async ({ page }) => {
  await goToProgress(page);
  await clickAllMouIkkai(page);

  await goToCards(page);

  const wordCount = await page.evaluate(() => words.length);
  await expect(page.locator('#ctr')).toHaveText(`1 / ${wordCount}`);
});

// ─── T6: 1枚解答(green)→ 完了 → 進捗で別の単語追加 ─────────

test('T6: もう一回→正解(green)→完了→進捗で別の単語もう一回 → カウンターが 1/1', async ({ page }) => {
  // word1 を復習キューに追加
  await goToProgress(page);
  await clickMouIkkai(page, 'awesome');

  // カード学習へ移動して word1 を正解（hint なし → green）
  await goToCards(page);
  await answerCorrectly(page, 'awesome');

  // 全グリーン → 完了画面になるのを待つ
  await page.waitForSelector('#doneWrap', { state: 'visible', timeout: 3000 });

  // 進捗タブに移動して word2 を追加
  await goToProgress(page);
  await clickMouIkkai(page, 'clown');

  await goToCards(page);

  await expect(page.locator('#ctr')).toHaveText('1 / 1');
});

// ─── T7: 3語追加 → 2枚正解後カウンターが 3/3 ───────────────

test('T7: 「もう一回」×3 → 2枚正解後カウンターが 3/3', async ({ page }) => {
  await goToProgress(page);
  await clickMouIkkai(page, 'awesome');
  await clickMouIkkai(page, 'clown');
  await clickMouIkkai(page, 'pencil');

  await goToCards(page);
  await expect(page.locator('#ctr')).toHaveText('1 / 3');

  await answerCorrectly(page, 'awesome');
  await expect(page.locator('#ctr')).toHaveText('2 / 3');

  await answerCorrectly(page, 'clown');
  await expect(page.locator('#ctr')).toHaveText('3 / 3');
});

// ─── T8: 全問グリーン → 完了画面 + 「もう一度練習する」非表示 ─

test('T8: 全問グリーン → 完了画面表示・restartBtn が非表示', async ({ page }) => {
  // setupAllGreen() で完了画面は既に設定済み
  const doneWrap = page.locator('#doneWrap');
  const restartBtn = page.locator('#restartBtn');

  await expect(doneWrap).toBeVisible();
  await expect(restartBtn).toBeHidden();
  await expect(page.locator('#doneMsg')).toContainText('グリーン');
});
