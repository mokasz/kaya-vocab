/**
 * Supabase CDN をインメモリモックに差し替える。
 * - 認証: 偽セッションを即座に返す（Google OAuth なし）
 * - DB: upsert/select はすべて no-op、localStorage のみ使用
 * - 本番DBへの影響ゼロ
 */
const MOCK_SCRIPT = `
window.supabase = {
  createClient: function(url, key) {
    return {
      auth: {
        onAuthStateChange: function(cb) {
          const fakeUser = {
            id: 'test-user-local',
            email: 'test@local.test',
            user_metadata: { full_name: 'Test User' }
          };
          // SIGNED_IN イベントを即座に発火 → app が initApp() を呼ぶ
          setTimeout(() => cb('SIGNED_IN', { user: fakeUser }), 30);
          return { data: { subscription: { unsubscribe: function() {} } } };
        },
        signInWithOAuth: function() { return Promise.resolve({}); },
        signOut: function() { return Promise.resolve({}); }
      },
      from: function(table) {
        return {
          // upsert: no-op（localStorage への書き込みは通常通り行われる）
          upsert: function(data, opts) {
            return Promise.resolve({ error: null });
          },
          // select: 空データを返す（localStorage の値が使われる）
          select: function(cols) {
            return {
              eq: function(col, val) {
                return {
                  eq: function(col2, val2) {
                    return Promise.resolve({ data: [], error: null });
                  }
                };
              }
            };
          }
        };
      }
    };
  }
};
`;

/**
 * page.route() で Supabase CDN をモックに差し替える。
 * navigate より前に呼ぶこと。
 */
async function mockSupabase(page) {
  await page.route('**supabase**', route => {
    route.fulfill({
      contentType: 'application/javascript',
      body: MOCK_SCRIPT,
    });
  });
}

/**
 * アプリの初期化完了を待つ（words.json ロード + initApp 完了）。
 */
async function waitForAppReady(page) {
  // let変数は window プロパティにならないため typeof words で判定
  await page.waitForFunction(() =>
    typeof words !== 'undefined' &&
    words.length > 0 &&
    document.getElementById('ctr') !== null
  , { timeout: 8000 });
}

/**
 * 全単語を green に設定し、完了画面に遷移させる。
 * 各テストの前提条件として使用。
 */
async function setupAllGreen(page) {
  await page.evaluate(() => {
    words.forEach(w => { w.status = 'green'; w.correct = 3; w.incorrect = 0; });
    buildQueue();       // queue が空になる
    renderResults();    // 進捗タブの「もう一回」ボタンを更新
    updateProg();       // 上部カウンターを更新
    // 完了画面を表示
    document.getElementById('cardWrap').style.display = 'none';
    document.getElementById('doneWrap').style.display = 'block';
    document.getElementById('doneMsg').textContent = '全問グリーン！🌟';
    document.getElementById('restartBtn').style.display = 'none';
  });
}

module.exports = { mockSupabase, waitForAppReady, setupAllGreen };
