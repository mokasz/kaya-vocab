/**
 * kaya-math Type別入力制限・Typo防止モジュール
 * (C) 2026 Anki Studio / kaya-math
 */

(function (global) {
  'use strict';

  /**
   * 全角英数字・記号を半角へ、全角スペースを半角スペースへ変換しトリムする
   */
  function toHalfWidth(str) {
    if (!str) return '';
    return String(str)
      .replace(/[！-～]/g, function (ch) {
        return String.fromCharCode(ch.charCodeAt(0) - 0xfee0);
      })
      .replace(/　/g, ' ')
      .trim();
  }

  /**
   * 入力値のサニタイズ・自動正規化
   * @param {string} raw - ユーザー入力文字列
   * @param {string} cardType - 'choice' | 'fill' | 'drawing'
   * @param {string} [subType] - 'number' | 'letter'
   * @returns {string} 正規化後の値
   */
  function normalizeInput(raw, cardType, subType) {
    let val = toHalfWidth(raw);
    if (!val) return '';

    if (cardType === 'fill') {
      if (subType === 'number') {
        // 数字のみ抽出（マイナス符号も許容）
        val = val.replace(/[^\d.-]/g, '');
      } else if (subType === 'letter') {
        // アルファベットを小文字化し先頭1文字
        val = val.toLowerCase().replace(/[^a-z]/g, '').slice(0, 1);
      }
    }
    return val;
  }

  /**
   * 送信前の入力バリデーション（Typo・空送信防止）
   * @param {any} value - 検査する値（文字列または作図の線配列など）
   * @param {string} cardType - 'choice' | 'fill' | 'drawing'
   * @param {string} [subType] - 'number' | 'letter'
   * @returns {{ valid: boolean, error?: string, normalizedValue?: any }}
   */
  function validateInput(value, cardType, subType) {
    if (cardType === 'choice') {
      if (value === null || value === undefined || String(value).trim() === '') {
        return {
          valid: false,
          error: '上の選択肢（①〜④）をタップして選んでください'
        };
      }
      return { valid: true, normalizedValue: String(value).trim() };
    }

    if (cardType === 'fill') {
      const rawStr = String(value || '').trim();
      if (!rawStr) {
        return {
          valid: false,
          error: subType === 'letter' ? 'アルファベットを1文字入力してください' : '答えの数値を入力してください'
        };
      }

      const normalized = normalizeInput(rawStr, cardType, subType);

      if (subType === 'number') {
        // 数字以外（漢字やひらがな）が混入していないか
        if (!/^-?\d+$/.test(normalized)) {
          return {
            valid: false,
            error: '半角数字のみを入力してください'
          };
        }
        return { valid: true, normalizedValue: normalized };
      }

      if (subType === 'letter') {
        if (!/^[a-z]$/.test(normalized)) {
          return {
            valid: false,
            error: '半角アルファベット1文字（v, e, f など）を入力してください'
          };
        }
        return { valid: true, normalizedValue: normalized };
      }

      return { valid: true, normalizedValue: normalized };
    }

    if (cardType === 'drawing') {
      const lines = Array.isArray(value) ? value : [];
      if (lines.length === 0) {
        return {
          valid: false,
          error: '作図がされていません。まずは『垂直補助線』で平面図の頂点から線を伸ばしてみよう！'
        };
      }
      return { valid: true, normalizedValue: lines };
    }

    return { valid: true, normalizedValue: value };
  }

  /**
   * HTML input 要素への属性強制適用（テンキー・readonly等の物理制御）
   * @param {HTMLInputElement} inputEl
   * @param {string} cardType
   * @param {string} [subType]
   */
  function configureInputAttributes(inputEl, cardType, subType) {
    if (!inputEl) return;

    // 一旦リセット
    inputEl.removeAttribute('pattern');
    inputEl.removeAttribute('maxlength');
    inputEl.removeAttribute('autocapitalize');

    if (cardType === 'choice') {
      inputEl.readOnly = true;
      inputEl.inputMode = 'none';
      inputEl.placeholder = '選択肢をタップ';
    } else if (cardType === 'fill') {
      inputEl.readOnly = false;
      if (subType === 'number') {
        inputEl.inputMode = 'numeric';
        inputEl.pattern = '[0-9]*';
        inputEl.maxLength = 6;
        inputEl.placeholder = '半角数字を入力';
      } else if (subType === 'letter') {
        inputEl.inputMode = 'text';
        inputEl.autocapitalize = 'none';
        inputEl.maxLength = 1;
        inputEl.placeholder = '英小文字1字 (v, e, f)';
      } else {
        inputEl.inputMode = 'text';
        inputEl.placeholder = '答えを入力';
      }
    } else if (cardType === 'drawing') {
      inputEl.readOnly = true;
      inputEl.inputMode = 'none';
      inputEl.placeholder = '作図して「採点する」をタップ';
    }
  }

  const MathValidator = {
    toHalfWidth,
    normalizeInput,
    validateInput,
    configureInputAttributes
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = MathValidator;
  } else {
    global.MathValidator = MathValidator;
  }
})(typeof window !== 'undefined' ? window : globalThis);
