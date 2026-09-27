/**
 * kaya-math 方眼SVG作図＆幾何自動判定エンジン
 * (C) 2026 Anki Studio / kaya-math
 */

(function (global) {
  'use strict';

  const GRID_SIZE = 20;
  const CANVAS_WIDTH = 500;
  const CANVAS_HEIGHT = 480;
  const GL_Y = 220;

  /**
   * 2つの線分が幾何学的に一致するか（許容誤差 tol px、始終点逆向きも同値判定）
   */
  function isSameLine(l1, l2, tol = 5) {
    if (l1.type && l2.type && l1.type !== l2.type) return false;

    const forward =
      Math.abs(l1.x1 - l2.x1) <= tol &&
      Math.abs(l1.y1 - l2.y1) <= tol &&
      Math.abs(l1.x2 - l2.x2) <= tol &&
      Math.abs(l1.y2 - l2.y2) <= tol;

    const reverse =
      Math.abs(l1.x1 - l2.x2) <= tol &&
      Math.abs(l1.y1 - l2.y2) <= tol &&
      Math.abs(l1.x2 - l2.x1) <= tol &&
      Math.abs(l1.y2 - l2.y1) <= tol;

    return forward || reverse;
  }

  /**
   * 線分リスト内に目的の線が含まれているか検索
   */
  function hasLine(lines, target, tol = 5) {
    return lines.some((l) => isSameLine(l, target, tol));
  }

  /**
   * 作図の自動採点・幾何診断
   * @param {Array} drawnLines - 生徒が引いた線配列 [{ type, x1, y1, x2, y2 }]
   * @param {Object} card - 出題カード
   * @returns {{ isCorrect: boolean, title: string, message: string, score: number, maxScore: number }}
   */
  function gradeDrawing(drawnLines, card) {
    const cardId = card.id;
    const config = card.draw_config || {};

    if (!drawnLines || drawnLines.length === 0) {
      return {
        isCorrect: false,
        score: 0,
        maxScore: 4,
        title: '作図がされていません',
        message: 'まずは「📏 垂直補助線」で平面図の頂点から真上に線を伸ばしてみよう！'
      };
    }

    // 1. 夏明け大問5（傾いた正四角錐）
    if (cardId === 'geo_proj_04' || config.base_type === 'pyramid_tilted') {
      const maxScore = 4;
      const baseLine = { x1: 140, y1: 180, x2: 380, y2: 180, type: 'solid' };
      const leftVA = { x1: 140, y1: 180, x2: 260, y2: 40, type: 'solid' };
      const rightVC = { x1: 380, y1: 180, x2: 260, y2: 40, type: 'solid' };
      const frontVB = { x1: 180, y1: 180, x2: 260, y2: 40, type: 'solid' };
      const backVDDashed = { x1: 340, y1: 180, x2: 260, y2: 40, type: 'dashed' };
      const backVDSolid = { x1: 340, y1: 180, x2: 260, y2: 40, type: 'solid' };

      const hasBase = hasLine(drawnLines, baseLine);
      const hasVA = hasLine(drawnLines, leftVA);
      const hasVC = hasLine(drawnLines, rightVC);
      const hasVB = hasLine(drawnLines, frontVB);
      const hasVD = hasLine(drawnLines, backVDDashed);
      const hasVDErr = hasLine(drawnLines, backVDSolid);

      // GL上に底辺を描いてしまったエラー
      const hasBaseOnGL = drawnLines.some(
        (l) => l.type === 'solid' && Math.abs(l.y1 - 220) <= 5 && Math.abs(l.y2 - 220) <= 5
      );

      if (hasBase && hasVA && hasVC && hasVB && hasVD) {
        return {
          isCorrect: true,
          score: 4,
          maxScore,
          title: '🎉 完璧！満点正解です！（4点 / 4点満点）',
          message:
            '・基準線GLと重ならず、適切な余白（y=180）に底辺が引けています！\n' +
            '・平面図の左端A(140)から右端C(380)までの対角線幅が完璧に一致しています！\n' +
            '・手前の稜線VB（実線）と奥の稜線VD（点線）が見事に描き分けられています！'
        };
      }

      if (hasBaseOnGL) {
        return {
          isCorrect: false,
          score: 1,
          maxScore,
          title: '⚠️ 基準線GLの上に底辺を重ねてしまっています',
          message:
            '基準線GL(y=220)は立面図と平面図の「間」を通る線です。\n' +
            '立面図の底辺は、基準線GLから2マス上の y=180 に描きましょう！'
        };
      }

      if (hasBase && hasVA && hasVC && hasVB && hasVDErr) {
        return {
          isCorrect: false,
          score: 2,
          maxScore,
          title: '⚠️ 線の種類（実線 vs 点線）が惜しいです！',
          message:
            '頂点D(340)への稜線VDを実線で描いていますが、Dは奥側にあります。\n' +
            '手前の面（△VABや△VBC）に隠れて見えないため、「点線（破線）」で描くのが正解です！'
        };
      }

      return {
        isCorrect: false,
        score: 0,
        maxScore,
        title: '作図が未完成または幅がズレています',
        message:
          '① 「📏 垂直補助線」で平面図の頂点（A, B, D, C）から真上にGLを横切って補助線を伸ばそう。\n' +
          '② 立面図の底辺(y=180)を引こう。（※基準線GL y=220とは重ねないように注意）\n' +
          '③ 頂点V(260, 40)へ向けて、輪郭線と稜線（VBは実線、VDは点線）を結ぼう！'
      };
    }

    // 2. 期末大問7（四角錐台の投影図完成）
    if (cardId === 'geo_proj_05' || config.base_type === 'frustum') {
      const maxScore = 3;
      const planLeft = { x1: 160, y1: 360, x2: 220, y2: 360, type: 'solid' };
      const planTop = { x1: 260, y1: 260, x2: 260, y2: 320, type: 'solid' };
      const planRight = { x1: 360, y1: 360, x2: 300, y2: 360, type: 'solid' };
      const planBottom = { x1: 260, y1: 460, x2: 260, y2: 400, type: 'solid' };
      const elevCenter = { x1: 260, y1: 80, x2: 260, y2: 180, type: 'solid' };

      const hasPL = hasLine(drawnLines, planLeft);
      const hasPT = hasLine(drawnLines, planTop);
      const hasPR = hasLine(drawnLines, planRight);
      const hasPB = hasLine(drawnLines, planBottom);
      const hasPlanAll = hasPL && hasPT && hasPR && hasPB;
      const hasElev = hasLine(drawnLines, elevCenter);

      if (hasPlanAll && hasElev) {
        return {
          isCorrect: true,
          score: 3,
          maxScore,
          title: '🎉 完璧！満点正解です！（3点 / 3点満点）',
          message:
            '・基準線GLと立面図・平面図が綺麗に独立しています！\n' +
            '・平面図の4本の稜線（実線）が完璧です！\n' +
            '・立面図の中央の手前稜線（縦の実線）がしっかり描けています！'
        };
      }

      if (hasPlanAll && !hasElev) {
        return {
          isCorrect: false,
          score: 1,
          maxScore,
          title: '⚠️ ここがKayaさんの期末テスト失点（-2点）ポイントです！',
          message:
            '平面図の4本は正しく引けていますが、立面図の台形の中にある縦線を描き忘れています！\n' +
            '四角錐台の手前の角は正面からハッキリ見えます。\n' +
            '立面図の上底(260, 80)から下底(260, 180)へ縦の実線を1本追加しましょう！'
        };
      }

      return {
        isCorrect: false,
        score: 0,
        maxScore,
        title: '線がまだ不足しています',
        message:
          '① 平面図の大小の正方形の4隅を結ぶ稜線を引こう。\n' +
          '② 立面図の中央に手前の角の稜線を引こう！'
      };
    }

    // 3. 汎用判定（required_linesとの直接マッチング）
    const required = config.required_lines || [];
    let matchedCount = 0;
    required.forEach((req) => {
      if (hasLine(drawnLines, req)) matchedCount++;
    });

    const isAllMatched = required.length > 0 && matchedCount === required.length;
    return {
      isCorrect: isAllMatched,
      score: matchedCount,
      maxScore: required.length,
      title: isAllMatched ? '🎉 満点正解です！' : '作図が不完全です',
      message: isAllMatched
        ? 'すべての必要な線が正しく引けています！'
        : `必要な線 ${required.length} 本中、${matchedCount} 本が引けています。`
    };
  }

  /**
   * インタラクティブ作図UIコントローラクラス
   */
  class DrawingController {
    constructor(svgElement, options = {}) {
      this.svg = svgElement;
      this.options = options;
      this.currentTool = 'guide'; // 'guide' | 'solid' | 'dashed'
      this.drawnLines = []; // [{ id, type, x1, y1, x2, y2 }]
      this.drawStart = null;
      this.currentCard = null;

      this.initLayers();
      this.bindEvents();
    }

    initLayers() {
      // SVG内構造: baseLayer, guidesLayer, drawingsLayer, indicators
      this.svg.innerHTML = `
        <defs>
          <pattern id="grid-20" width="${GRID_SIZE}" height="${GRID_SIZE}" patternUnits="userSpaceOnUse">
            <path d="M ${GRID_SIZE} 0 L 0 0 0 ${GRID_SIZE}" fill="none" stroke="#f1f5f9" stroke-width="0.8"/>
          </pattern>
          <pattern id="grid-100" width="100" height="100" patternUnits="userSpaceOnUse">
            <rect width="100" height="100" fill="url(#grid-20)" />
            <path d="M 100 0 L 0 0 0 100" fill="none" stroke="#e2e8f0" stroke-width="1.2"/>
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#grid-100)" />
        
        <!-- 基準線 GL (y = 220) -->
        <line x1="0" y1="${GL_Y}" x2="${CANVAS_WIDTH}" y2="${GL_Y}" stroke="#475569" stroke-width="2.5" />
        <text x="15" y="${GL_Y - 7}" font-size="11" fill="#475569" font-weight="bold" font-family="sans-serif">GL (基準線)</text>

        <!-- 領域ラベル -->
        <text x="15" y="25" font-size="11" fill="#64748b" font-family="sans-serif">【立面図】(底辺は y=180)</text>
        <text x="15" y="465" font-size="11" fill="#64748b" font-family="sans-serif">【平面図】(上端は y=260)</text>

        <g id="base-layer"></g>
        <g id="guides-layer"></g>
        <g id="drawings-layer"></g>

        <!-- インジケータ -->
        <circle id="hover-point" cx="-20" cy="-20" r="5" fill="#3b82f6" opacity="0.6" pointer-events="none"/>
        <circle id="start-point" cx="-20" cy="-20" r="6" fill="#f59e0b" stroke="#ffffff" stroke-width="2" pointer-events="none" style="display: none;"/>
        <line id="preview-line" x1="0" y1="0" x2="0" y2="0" stroke="#94a3b8" stroke-width="2" stroke-dasharray="4,4" pointer-events="none" style="display: none;"/>
      `;

      this.baseLayer = this.svg.querySelector('#base-layer');
      this.guidesLayer = this.svg.querySelector('#guides-layer');
      this.drawingsLayer = this.svg.querySelector('#drawings-layer');
      this.hoverPoint = this.svg.querySelector('#hover-point');
      this.startPoint = this.svg.querySelector('#start-point');
      this.previewLine = this.svg.querySelector('#preview-line');
    }

    setProblem(card) {
      this.currentCard = card;
      this.drawnLines = [];
      this.resetDrawState();
      this.renderBaseLayer(card);
      this.renderAllLines();
    }

    renderBaseLayer(card) {
      this.baseLayer.innerHTML = '';
      const config = card.draw_config || {};

      if (card.id === 'geo_proj_04' || config.base_type === 'pyramid_tilted') {
        this.baseLayer.innerHTML = `
          <!-- 平面図 ABCD -->
          <polygon points="140,300 180,420 380,380 340,260" fill="#f8fafc" stroke="#0f172a" stroke-width="2"/>
          <line x1="140" y1="300" x2="380" y2="380" stroke="#0f172a" stroke-width="1.5"/>
          <line x1="180" y1="420" x2="340" y2="260" stroke="#0f172a" stroke-width="1.5"/>

          <!-- 頂点ラベル -->
          <text x="120" y="305" font-size="13" font-weight="bold" fill="#0f172a">A</text>
          <text x="175" y="445" font-size="13" font-weight="bold" fill="#0f172a">B</text>
          <text x="390" y="390" font-size="13" font-weight="bold" fill="#0f172a">C</text>
          <text x="345" y="250" font-size="13" font-weight="bold" fill="#0f172a">D</text>
          <text x="268" y="345" font-size="12" font-weight="bold" fill="#0f172a">V</text>

          <!-- 立面図の頂点V (260, 40) -->
          <circle cx="260" cy="40" r="4" fill="#0f172a"/>
          <text x="268" y="45" font-size="13" font-weight="bold" fill="#0f172a">V</text>
        `;
      } else if (card.id === 'geo_proj_05' || config.base_type === 'frustum') {
        this.baseLayer.innerHTML = `
          <!-- 立面図の台形外枠 -->
          <polygon points="220,80 300,80 360,180 160,180" fill="none" stroke="#0f172a" stroke-width="2"/>

          <!-- 平面図の大小正方形 -->
          <polygon points="160,360 260,260 360,360 260,460" fill="#f8fafc" stroke="#0f172a" stroke-width="2"/>
          <polygon points="220,360 260,320 300,360 260,400" fill="#ffffff" stroke="#0f172a" stroke-width="2"/>
        `;
      }
    }

    setTool(tool) {
      this.currentTool = tool;
      this.resetDrawState();
    }

    resetDrawState() {
      this.drawStart = null;
      if (this.startPoint) this.startPoint.style.display = 'none';
      if (this.previewLine) this.previewLine.style.display = 'none';
    }

    getSnapCoord(evt) {
      const rect = this.svg.getBoundingClientRect();
      const snapX = Math.round((evt.clientX - rect.left) / GRID_SIZE) * GRID_SIZE;
      const snapY = Math.round((evt.clientY - rect.top) / GRID_SIZE) * GRID_SIZE;
      return {
        x: Math.max(0, Math.min(CANVAS_WIDTH, snapX)),
        y: Math.max(0, Math.min(CANVAS_HEIGHT, snapY))
      };
    }

    bindEvents() {
      this.svg.addEventListener('mousemove', (e) => {
        const pt = this.getSnapCoord(e);
        this.hoverPoint.setAttribute('cx', pt.x);
        this.hoverPoint.setAttribute('cy', pt.y);

        if (this.drawStart && (this.currentTool === 'solid' || this.currentTool === 'dashed')) {
          this.previewLine.setAttribute('x1', this.drawStart.x);
          this.previewLine.setAttribute('y1', this.drawStart.y);
          this.previewLine.setAttribute('x2', pt.x);
          this.previewLine.setAttribute('y2', pt.y);
          this.previewLine.style.display = 'block';
        }
      });

      this.svg.addEventListener('mouseleave', () => {
        this.hoverPoint.setAttribute('cx', -20);
        this.hoverPoint.setAttribute('cy', -20);
        if (!this.drawStart) this.previewLine.style.display = 'none';
      });

      this.svg.addEventListener('click', (e) => {
        const pt = this.getSnapCoord(e);

        if (this.currentTool === 'guide') {
          // 垂直補助線: クリックしたX座標で真上に垂直線をトグル
          const idx = this.drawnLines.findIndex(
            (l) => l.type === 'guide' && l.x1 === pt.x
          );
          if (idx >= 0) {
            this.drawnLines.splice(idx, 1);
          } else {
            this.drawnLines.push({
              id: Date.now() + Math.random(),
              type: 'guide',
              x1: pt.x,
              y1: 460,
              x2: pt.x,
              y2: 30
            });
          }
          this.renderAllLines();
        } else {
          if (!this.drawStart) {
            this.drawStart = pt;
            this.startPoint.setAttribute('cx', pt.x);
            this.startPoint.setAttribute('cy', pt.y);
            this.startPoint.style.display = 'block';
          } else {
            if (this.drawStart.x !== pt.x || this.drawStart.y !== pt.y) {
              this.drawnLines.push({
                id: Date.now() + Math.random(),
                type: this.currentTool,
                x1: this.drawStart.x,
                y1: this.drawStart.y,
                x2: pt.x,
                y2: pt.y
              });
              this.renderAllLines();
            }
            this.resetDrawState();
          }
        }
      });
    }

    renderAllLines() {
      this.guidesLayer.innerHTML = '';
      this.drawingsLayer.innerHTML = '';

      this.drawnLines.forEach((l) => {
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', l.x1);
        line.setAttribute('y1', l.y1);
        line.setAttribute('x2', l.x2);
        line.setAttribute('y2', l.y2);

        if (l.type === 'guide') {
          line.setAttribute('stroke', '#3b82f6');
          line.setAttribute('stroke-width', '1.5');
          line.setAttribute('stroke-dasharray', '5,4');
          this.guidesLayer.appendChild(line);
        } else if (l.type === 'solid') {
          line.setAttribute('stroke', '#0f172a');
          line.setAttribute('stroke-width', '2.5');
          line.setAttribute('stroke-linecap', 'round');
          this.drawingsLayer.appendChild(line);
        } else if (l.type === 'dashed') {
          line.setAttribute('stroke', '#0f172a');
          line.setAttribute('stroke-width', '2.2');
          line.setAttribute('stroke-dasharray', '6,4');
          line.setAttribute('stroke-linecap', 'round');
          this.drawingsLayer.appendChild(line);
        }
      });
    }

    undo() {
      if (this.drawnLines.length > 0) {
        this.drawnLines.pop();
        this.renderAllLines();
      }
      this.resetDrawState();
    }

    clear() {
      this.drawnLines = [];
      this.renderAllLines();
      this.resetDrawState();
    }

    grade() {
      return gradeDrawing(this.drawnLines, this.currentCard);
    }
  }

  const MathDrawEngine = {
    GRID_SIZE,
    CANVAS_WIDTH,
    CANVAS_HEIGHT,
    GL_Y,
    isSameLine,
    hasLine,
    gradeDrawing,
    DrawingController
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = MathDrawEngine;
  } else {
    global.MathDrawEngine = MathDrawEngine;
  }
})(typeof window !== 'undefined' ? window : globalThis);
