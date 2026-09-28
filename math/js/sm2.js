/**
 * kaya-math 独立SM-2間隔反復エンジン
 * (C) 2026 Anki Studio / kaya-math
 */

(function (global) {
  'use strict';

  const STORAGE_KEY = 'kaya_math_progress';

  /**
   * YYYY-MM-DD 文字列を取得（日本時間）
   */
  function getTodayString(d = new Date()) {
    return d.toLocaleDateString('sv-SE', { timeZone: 'Asia/Tokyo' });
  }

  /**
   * 指定日数後の YYYY-MM-DD を計算
   */
  function addDays(dateStr, days) {
    const d = new Date(dateStr + 'T00:00:00+09:00');
    d.setDate(d.getDate() + days);
    return getTodayString(d);
  }

  /**
   * ローカルストレージまたはメモリからの読み込み
   */
  function loadProgress() {
    try {
      if (typeof localStorage !== 'undefined') {
        const raw = localStorage.getItem(STORAGE_KEY);
        return raw ? JSON.parse(raw) : {};
      }
    } catch (e) {
      console.warn('Failed to load math progress from localStorage', e);
    }
    return {};
  }

  /**
   * ローカルストレージへの書き込み
   */
  function saveProgress(progress) {
    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(progress));
      }
    } catch (e) {
      console.warn('Failed to save math progress to localStorage', e);
    }
  }

  /**
   * カードのデフォルト進捗データ
   */
  function getDefaultProgress(cardId) {
    return {
      card_id: cardId,
      status: 'new',
      repetitions: 0,
      interval_days: 1,
      ease_factor: 2.5,
      next_review: null,
      last_studied: null,
      correct: 0,
      incorrect: 0
    };
  }

  /**
   * SM-2 アルゴリズムのコア計算
   * @param {Object} item - 現在の進捗レコード
   * @param {number} quality - 0〜5 (正解: 4, 不正解: 1)
   * @param {string} todayStr - YYYY-MM-DD
   * @returns {Object} 更新後の進捗レコード
   */
  function calculateSM2(item, quality, todayStr) {
    const record = { ...item };
    const today = todayStr || getTodayString();
    const isSameDay = record.last_studied === today;

    if (quality < 3) {
      // 不正解
      record.repetitions = 0;
      record.interval_days = 1;
      record.ease_factor = Math.max(1.3, (record.ease_factor || 2.5) - 0.2);
      record.status = 'review';
      record.incorrect = (record.incorrect || 0) + 1;
    } else {
      // 正解
      if (isSameDay) {
        // 同日内の重複回答: すでに今日学習済みの場合は repetitions / interval は進めない
        if (record.status !== 'learned') {
          // 不正解からの当日リカバリの場合のみ learned に復帰
          record.status = 'learned';
          record.repetitions = Math.max(1, record.repetitions || 1);
          record.interval_days = record.interval_days || 1;
        }
        record.correct = (record.correct || 0) + 1;
      } else {
        // 通常の正解（別日）
        const reps = (record.repetitions || 0) + 1;
        record.repetitions = reps;

        if (reps === 1) {
          record.interval_days = 1;
        } else if (reps === 2) {
          record.interval_days = 6;
        } else {
          const prevInterval = record.interval_days || 6;
          const ef = record.ease_factor || 2.5;
          record.interval_days = Math.round(prevInterval * ef);
        }

        // ease_factor 更新
        const prevEf = record.ease_factor || 2.5;
        record.ease_factor = Math.max(1.3, prevEf + 0.1 - (4 - quality) * 0.08);
        record.status = 'learned';
        record.correct = (record.correct || 0) + 1;
      }
    }

    record.last_studied = today;
    record.next_review = addDays(today, record.interval_days);
    return record;
  }

  /**
   * カードの回答結果を記録し保存
   */
  function recordCardResult(cardId, isCorrect, options = {}) {
    const todayStr = options.today || getTodayString();
    const progress = loadProgress();
    const current = progress[cardId] || getDefaultProgress(cardId);
    const quality = isCorrect ? 4 : 1;

    const updated = calculateSM2(current, quality, todayStr);
    progress[cardId] = updated;
    saveProgress(progress);
    return updated;
  }

  /**
   * 本日の学習キューを生成
   * @param {Array} allCards - 全カードリスト
   * @param {string} [todayStr] - 指定日（デフォルトは今日）
   * @param {number} [maxNewCards=5] - 1日の新規カード最大数
   * @returns {Array} キューに並ぶカード配列
   */
  function buildDailyQueue(allCards, todayStr, maxNewCards = 5) {
    const today = todayStr || getTodayString();
    const progress = loadProgress();

    const reviewCards = [];
    const newCards = [];

    allCards.forEach((card) => {
      const p = progress[card.id];
      if (!p || p.status === 'new') {
        newCards.push(card);
      } else if (p.next_review && p.next_review <= today) {
        reviewCards.push(card);
      }
    });

    // 復習カードを優先、その後に新規カードを上限まで追加
    const selectedNew = newCards.slice(0, maxNewCards);
    return [...reviewCards, ...selectedNew];
  }

  const MathSM2 = {
    STORAGE_KEY,
    getTodayString,
    addDays,
    loadProgress,
    saveProgress,
    getDefaultProgress,
    calculateSM2,
    recordCardResult,
    buildDailyQueue
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = MathSM2;
  } else {
    global.MathSM2 = MathSM2;
  }
})(typeof window !== 'undefined' ? window : globalThis);
