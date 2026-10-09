(function () {
  "use strict";

  const STAT_LABELS = {
    ACC: "가속", SPD: "질주 속도", FIN: "결정력", LSA: "중거리 슛", SHO: "슈팅력",
    POS: "위치 선정", VOL: "발리 슛", PEN: "페널티 킥", SPA: "짧은 패스", LPA: "긴 패스",
    VIS: "시야", CRO: "크로스", CUR: "감아차기", FRK: "프리킥", DRI: "드리블",
    BAC: "볼 컨트롤", AGI: "민첩성", REA: "반응도", BAL: "밸런스", MRK: "마크",
    STT: "태클", SLT: "슬라이딩 태클", AWR: "가로채기", HEA: "헤딩", STR: "힘",
    AGG: "공격성", JMP: "점프", STA: "체력", GKD: "GK 다이빙", GKK: "GK 킥",
    GKP: "GK 위치 선정", REF: "반사신경", HAN: "핸들링"
  };
  const WORK_RATE_LABELS = { 0: "보통", 1: "낮음", 2: "높음" };
  const ROLE_TRAITS = {
    line_breaker: ["라인 브레이커", "솔로 런", "빠른 위치 선정"],
    box_finisher: ["예리한 감아차기", "아웃사이드 슈팅", "파워 헤더"],
    aerial_hub: ["파워 헤더", "공중의 지배자"],
    touchline_dribbler: ["빠른 드리블", "화려한 개인기", "스피드스터"],
    inside_scorer: ["예리한 감아차기", "아웃사이드 슈팅", "솔로 런"],
    cross_supplier: ["얼리 크로스 선호", "정교한 크로스"],
    final_third_architect: ["플레이 메이커", "긴 패스 선호"],
    free_creator: ["화려한 개인기", "빠른 드리블", "플레이 메이커"],
    progressive_passer: ["긴 패스 선호", "플레이 메이커"],
    deep_tempo: ["긴 패스 선호", "플레이 메이커"],
    ball_winner: ["추격 수비", "빠른 복귀"],
    backline_shield: ["빠른 위치 선정", "파이널 라인"],
    overlap_wingback: ["얼리 크로스 선호", "빠른 복귀"],
    box_blocker: ["파워 헤더", "파이널 라인"],
    buildout_centerback: ["긴 패스 선호", "플레이 메이커"],
    space_cover: ["추격 수비", "빠른 복귀"],
    goal_line_keeper: ["수호신", "슈퍼 캐치", "GK 능숙한 펀칭"],
    sweeper_keeper: ["GK 스위퍼", "GK 멀리 던지기"]
  };
  const STYLE_TRAITS = {
    run_in_behind: ["라인 브레이커", "솔로 런"],
    finishing_focus: ["예리한 감아차기", "아웃사이드 슈팅"],
    direct_carry: ["빠른 드리블", "화려한 개인기"],
    chance_creation: ["플레이 메이커", "긴 패스 선호"],
    wide_delivery: ["얼리 크로스 선호", "정교한 크로스"],
    defensive_screen: ["추격 수비", "파이널 라인"],
    active_press: ["빠른 복귀", "추격 수비"],
    aerial_duel: ["파워 헤더", "공중의 지배자"],
    shot_stopping: ["수호신", "슈퍼 캐치"],
    keeper_distribution: ["GK 멀리 던지기"],
    keeper_sweep: ["GK 스위퍼"]
  };
  const ROLE_PLAYSTYLE_BONUSES = {
    touchline_dribbler: { "트릭스터": 5 },
    free_creator: { "트릭스터": 4.5 },
    central_carrier: { "트릭스터": 4 },
    inside_scorer: { "트릭스터": 3 },
    wide_creator: { "트릭스터": 2.5 },
    support_shadow: { "트릭스터": 2 },
    complete_nine: { "트릭스터": 1.5 }
  };
  const STYLE_PLAYSTYLE_BONUSES = {
    direct_carry: { "트릭스터": 7 },
    combination: { "트릭스터": 2.5 },
    chance_creation: { "트릭스터": 1 }
  };
  let referencePromise;

  function clamp(value, low, high) {
    return Math.max(low, Math.min(high, value));
  }

  function number(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
    })[character]);
  }

  function loadReference(url) {
    if (!referencePromise) {
      referencePromise = fetch(url, { credentials: "same-origin" }).then((response) => {
        if (!response.ok) throw new Error(`분석 기준을 불러오지 못했습니다 (${response.status})`);
        return response.json();
      });
    }
    return referencePromise;
  }

  function positionGroup(position, groups) {
    const normalized = String(position || "").toUpperCase();
    return Object.keys(groups).find((group) => groups[group].includes(normalized)) || null;
  }

  function nearestReference(model, position, ovr) {
    const normalizedPosition = String(position || "").toUpperCase();
    const rows = model.reference[normalizedPosition] || {};
    const keys = Object.keys(rows).map(Number).filter(Number.isFinite);
    if (!keys.length) return null;
    const nearest = keys.reduce((best, candidate) => (
      Math.abs(candidate - ovr) < Math.abs(best - ovr) ? candidate : best
    ), keys[0]);
    return { ...rows[String(nearest)], targetOvr: nearest, position: normalizedPosition };
  }

  function statScore(value, anchors) {
    if (!anchors || anchors.length < 3) return 0;
    let [q10, q50, q90] = anchors.map(Number);
    if (q50 <= q10) q50 = q10 + 1;
    if (q90 <= q50) q90 = q50 + 1;
    const score = value <= q50
      ? 20 + (((value - q10) / (q50 - q10)) * 30)
      : 50 + (((value - q50) / (q90 - q50)) * 30);
    return clamp(score, 0, 100);
  }

  function percentile(score, quantiles, points) {
    if (!quantiles?.length) return null;
    if (score <= quantiles[0]) return points[0];
    const last = quantiles.length - 1;
    if (score >= quantiles[last]) return points[last];
    for (let index = 1; index < quantiles.length; index += 1) {
      const upper = number(quantiles[index]);
      if (score > upper) continue;
      const lower = number(quantiles[index - 1]);
      const span = upper - lower;
      const ratio = span > 0 ? (score - lower) / span : 0.5;
      return points[index - 1] + ((points[index] - points[index - 1]) * ratio);
    }
    return points[last];
  }

  function weakFoot(context) {
    const left = number(context.footL);
    const right = number(context.footR);
    const main = number(context.mainFoot);
    if (main === 1) return left;
    if (main === 2) return right;
    return Math.min(...[left, right].filter((value) => value > 0)) || 0;
  }

  function skillStars(context) {
    const level = number(context.skillMovesLevel, -1);
    return level >= 0 ? clamp(level + 1, 1, 5) : 0;
  }

  function factorAdjustment(factor, context) {
    const foot = weakFoot(context);
    const skills = skillStars(context);
    const attack = number(context.attWorkRate, -1);
    const defense = number(context.defWorkRate, -1);
    const height = number(context.height);
    const weight = number(context.weight);
    if (factor === "weak_foot") {
      if (foot >= 5) return { value: 1.5, note: "약발 5" };
      if (foot === 4) return { value: 0.5, note: "약발 4" };
      if (foot > 0 && foot <= 2) return { value: -3, note: `약발 ${foot}` };
      if (foot === 3) return { value: -1, note: "약발 3" };
    }
    if (factor === "skill_moves") {
      if (skills >= 5) return { value: 1.5, note: "개인기 5성" };
      if (skills === 4) return { value: 0.5, note: "개인기 4성" };
      if (skills > 0 && skills <= 2) return { value: -2.5, note: `개인기 ${skills}성` };
    }
    if (factor === "attack_work") {
      if (attack === 2) return { value: 1.2, note: "공격 활동량 높음" };
      if (attack === 1) return { value: -1.5, note: "공격 활동량 낮음" };
    }
    if (factor === "defense_work") {
      if (defense === 2) return { value: 1.2, note: "수비 활동량 높음" };
      if (defense === 1) return { value: -1.5, note: "수비 활동량 낮음" };
    }
    if (factor === "height_aerial") {
      if (height >= 190) return { value: 3 + (weight >= 85 ? 0.5 : 0), note: `${height}cm 제공권` };
      if (height >= 185) return { value: 1.5, note: `${height}cm 제공권` };
      if (height > 0 && height < 178) return { value: -4, note: `${height}cm 제공권 부담` };
      if (height > 0 && height < 183) return { value: -2, note: `${height}cm 제공권 부담` };
    }
    if (factor === "height_defense") {
      if (height >= 190) return { value: 1.5 + (weight >= 85 ? 0.5 : 0), note: `${height}cm 수비 체격` };
      if (height > 0 && height < 180) return { value: -2, note: `${height}cm 수비 체격` };
    }
    if (factor === "height_keeper") {
      if (height >= 195) return { value: 2, note: `${height}cm 골키퍼 체격` };
      if (height >= 188) return { value: 0.5, note: `${height}cm 골키퍼 체격` };
      if (height > 0 && height < 185) return { value: -3, note: `${height}cm 골키퍼 체격` };
    }
    if (factor === "height_link") {
      if (height >= 185 || weight >= 82) return { value: 1, note: "버티는 체격" };
      if (height > 0 && height < 175 && weight < 70) return { value: -1, note: "경합 체격 부담" };
    }
    return { value: 0, note: "" };
  }

  function traitAdjustment(definition, context, traitMap) {
    const playerTraits = (context.traits || []).map((trait) => String(trait));
    const matching = (traitMap[definition.id] || []).filter((target) => (
      playerTraits.some((trait) => trait.includes(target) || target.includes(trait))
    ));
    if (!matching.length) return { value: 0, note: "" };
    return { value: Math.min(2, matching.length), note: `${matching.slice(0, 2).join("·")} 특성` };
  }

  function playstyleAdjustment(definition, context, bonusMap) {
    const playerStyles = (context.playstyles || []).map((name) => String(name));
    const bonuses = bonusMap[definition.id] || {};
    const matching = Object.keys(bonuses).filter((target) => (
      playerStyles.some((name) => name.includes(target) || target.includes(name))
    ));
    if (!matching.length) return { value: 0, note: "", source: "playstyle" };
    const value = matching.reduce((sum, name) => sum + number(bonuses[name]), 0);
    const note = matching.includes("트릭스터")
      ? "트릭스터: 개인기 발동·역동작 유도 강점"
      : `${matching.join("·")} 플레이스타일 반영`;
    return { value: Math.min(8, value), note, source: "playstyle" };
  }

  function scoreDefinition(definition, stats, reference, context, traitMap, playstyleBonusMap) {
    let weighted = 0;
    let totalWeight = 0;
    const contributions = [];
    Object.entries(definition.weights).forEach(([code, weight]) => {
      if (!(code in stats) || !reference.stats[code]) return;
      const score = statScore(stats[code], reference.stats[code]);
      weighted += score * weight;
      totalWeight += weight;
      contributions.push({ code, score, weight, impact: score * weight });
    });
    let score = totalWeight ? weighted / totalWeight : 0;
    const limits = [];
    (definition.requirements || []).forEach((requirement) => {
      if (!(requirement.stat in stats) || !reference.stats[requirement.stat]) return;
      const current = statScore(stats[requirement.stat], reference.stats[requirement.stat]);
      if (current < requirement.min) {
        const penalty = ((requirement.min - current) / requirement.min) * requirement.penalty;
        score -= penalty;
        limits.push(`${requirement.label} 보완 필요`);
      }
    });
    const factorNotes = [];
    (definition.factors || []).forEach((factor) => {
      const adjustment = factorAdjustment(factor, context);
      score += adjustment.value;
      if (adjustment.note) {
        factorNotes.push({ ...adjustment, factor });
        if (adjustment.value < 0) limits.push(adjustment.note);
      }
    });
    const trait = traitAdjustment(definition, context, traitMap);
    score += trait.value;
    if (trait.note) factorNotes.push(trait);
    const playstyle = playstyleAdjustment(definition, context, playstyleBonusMap);
    score += playstyle.value;
    if (playstyle.note) factorNotes.push(playstyle);
    contributions.sort((a, b) => (b.score - 50) * b.weight - (a.score - 50) * a.weight);
    return {
      score: clamp(score, 0, 100),
      strengths: contributions.filter((item) => item.score >= 54).slice(0, 3),
      limits: [...new Set(limits)].slice(0, 3),
      factors: factorNotes
    };
  }

  function readCurrentStats(section, context) {
    const displayedOvr = number(document.querySelector("[data-ovr-value]")?.textContent, number(context.baseOvr));
    const commonEnhance = Math.max(0, displayedOvr - number(context.baseOvr));
    const stats = {};
    document.querySelectorAll("[data-stat-value][data-stat-code]").forEach((element) => {
      const displayed = number(element.textContent, NaN);
      if (Number.isFinite(displayed)) stats[element.dataset.statCode] = displayed - commonEnhance;
    });
    return { stats, displayedOvr, commonEnhance };
  }

  function scoreLabel(score) {
    if (score >= 80) return "최상";
    if (score >= 70) return "강점";
    if (score >= 60) return "적합";
    if (score >= 50) return "보통";
    return "보완 필요";
  }

  function topPercentLabel(value) {
    if (value === null) return "비교 불가";
    const top = clamp(Math.round(100 - value), 1, 100);
    return `동급 상위 ${top}%`;
  }

  function confidence(reference) {
    if (reference.sample >= 150 && reference.radius <= 5) return "높음";
    if (reference.sample >= 80 && reference.radius <= 10) return "보통 이상";
    return "참고용";
  }

  function metaLine(context) {
    const items = [];
    const foot = weakFoot(context);
    const stars = skillStars(context);
    if (foot) items.push(`약발 ${foot}`);
    if (stars) items.push(`개인기 ${stars}성`);
    if (context.attWorkRate !== null && context.defWorkRate !== null) {
      items.push(`활동량 ${WORK_RATE_LABELS[number(context.attWorkRate)] || "-"}/${WORK_RATE_LABELS[number(context.defWorkRate)] || "-"}`);
    }
    if (number(context.height)) items.push(`${number(context.height)}cm`);
    if (number(context.weight)) items.push(`${number(context.weight)}kg`);
    return items.join(" · ");
  }

  function reasonText(result) {
    const strengths = result.strengths.map((item) => STAT_LABELS[item.code] || item.code);
    if (!strengths.length) return "뚜렷한 우위 능력치 없음";
    return `${strengths.slice(0, 2).join("·")} 강점`;
  }

  function physicalCaution(stats, reference, context, group) {
    const height = number(context.height);
    const weight = number(context.weight);
    if (!height || !reference?.stats) return "";
    if (group === "gk") return height < 185 ? "낮은 신장으로 크로스 대응 부담" : "";

    const scoreFor = (code) => (
      code in stats && reference.stats[code] ? statScore(stats[code], reference.stats[code]) : null
    );
    const weightedAverage = (items) => {
      let total = 0;
      let weights = 0;
      items.forEach(([code, weightValue]) => {
        const value = scoreFor(code);
        if (value === null) return;
        total += value * weightValue;
        weights += weightValue;
      });
      return weights ? total / weights : null;
    };

    const contact = weightedAverage([["STR", 55], ["BAL", 25], ["AGG", 20]]);
    const aerial = weightedAverage([["HEA", 55], ["JMP", 45]]);
    const smallFrame = height < 178;
    const verySmallFrame = height <= 172;
    const lightFrame = weight > 0 && weight < 72;
    const contactBurden = contact !== null && (
      contact < 36
      || (verySmallFrame && weight < 75 && contact < 62)
      || (smallFrame && lightFrame && contact < 54)
    );
    const aerialBurden = aerial !== null && (aerial < 32 || (smallFrame && aerial < 55));

    if (contactBurden && aerialBurden) return "작은 체격으로 몸싸움·공중 경합 부담";
    if (contactBurden) return smallFrame ? "작은 체격으로 몸싸움 부담" : "힘·밸런스가 낮아 몸싸움 부담";
    if (aerialBurden) return smallFrame ? "낮은 신장으로 공중 경합 부담" : "헤딩·점프가 낮아 공중 경합 부담";
    return "";
  }

  function render(section, model, context) {
    const results = section.querySelector("[data-player-analysis-results]");
    const state = section.querySelector("[data-player-analysis-state]");
    const { stats, displayedOvr, commonEnhance } = readCurrentStats(section, context);
    const primaryGroup = positionGroup(context.position, model.positionGroups);
    if (!primaryGroup || !Object.keys(stats).length) throw new Error("분석 가능한 포지션 또는 능력치가 없습니다.");

    const primaryPosition = String(context.position || "").toUpperCase();
    const availablePositions = [primaryPosition, ...(context.potentialPositions || [])]
      .map((position) => String(position || "").toUpperCase())
      .filter((position, index, positions) => (
        position
        && positions.indexOf(position) === index
        && positionGroup(position, model.positionGroups)
        && model.reference[position]
      ));
    const referenceByPosition = {};
    availablePositions.forEach((position) => {
      referenceByPosition[position] = nearestReference(model, position, number(context.baseOvr));
    });
    const candidateGroups = availablePositions.reduce((groups, position) => {
      const group = positionGroup(position, model.positionGroups);
      if (group && !groups.includes(group)) groups.push(group);
      return groups;
    }, []);
    const referencePositionForGroup = (group) => availablePositions.find((position) => (
      positionGroup(position, model.positionGroups) === group
    ));

    const roles = model.roles
      .filter((definition) => candidateGroups.includes(definition.group))
      .map((definition) => {
        const referencePosition = referencePositionForGroup(definition.group);
        const reference = referenceByPosition[referencePosition];
        const result = scoreDefinition(definition, stats, reference, context, ROLE_TRAITS, ROLE_PLAYSTYLE_BONUSES);
        return {
          ...definition,
          ...result,
          percentile: percentile(result.score, reference.roles[definition.id], model.quantilePoints),
          referencePosition,
          reference
        };
      })
      .sort((a, b) => b.score - a.score);

    const styleReference = referenceByPosition[primaryPosition];
    const styles = model.styles
      .filter((definition) => definition.groups.includes(primaryGroup))
      .map((definition) => {
        const result = scoreDefinition(definition, stats, styleReference, context, STYLE_TRAITS, STYLE_PLAYSTYLE_BONUSES);
        return {
          ...definition,
          ...result,
          percentile: percentile(result.score, styleReference.styles[definition.id], model.quantilePoints)
        };
      })
      .sort((a, b) => b.score - a.score);

    const top = roles[0];
    const topThree = roles.slice(0, 3);
    const physicalWeakness = physicalCaution(stats, styleReference, context, primaryGroup);
    const weaknessNotes = [...new Set([physicalWeakness, ...top.limits].filter(Boolean))].slice(0, 2);
    const officialEffectNotes = [...new Set(
      top.factors.filter((item) => item.source === "playstyle").map((item) => item.note)
    )];
    const enhance = document.getElementById("detail-enhance");
    const training = document.getElementById("detail-training");
    const configLabel = [
      enhance?.selectedOptions?.[0]?.textContent?.trim(),
      training?.selectedOptions?.[0]?.textContent?.trim()
    ].filter(Boolean).join(" · ");
    const positionsForGroup = (group) => {
      const matching = availablePositions.filter((position) => positionGroup(position, model.positionGroups) === group);
      return [...new Set(matching)].join("/") || model.positionGroups[group]?.slice(0, 2).join("/") || context.position;
    };
    const primaryPositions = positionsForGroup(top.group);
    const comparisonLabel = (reference) => {
      const positions = (reference.positions || [reference.position]).join("/");
      return `${positions} · OVR ±${reference.radius}`;
    };

    const alternativeRoles = topThree.slice(1).map((item, index) => `
      <article class="analysis-role-alt">
        <span>${index + 2}</span>
        <div><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(positionsForGroup(item.group))} · ${escapeHtml(reasonText(item))}</small></div>
        <div class="analysis-role-alt__score"><b>${Math.round(item.score)}</b><small>${topPercentLabel(item.percentile)}</small></div>
      </article>
    `).join("");

    const styleCards = styles.slice(0, 6).map((item) => {
      const officialStyleApplied = item.factors.some((factor) => factor.source === "playstyle");
      return `
        <article class="analysis-style-card" title="${escapeHtml(item.description)}">
          <div class="analysis-style-card__head"><strong>${escapeHtml(item.name)}</strong><span>${Math.round(item.score)}</span></div>
          <div class="analysis-style-bar"><i style="--analysis-score:${item.score.toFixed(1)}%"></i></div>
          <small class="${officialStyleApplied ? "is-playstyle" : ""}">${topPercentLabel(item.percentile)}${officialStyleApplied ? " · 트릭스터 반영" : ""}</small>
        </article>
      `;
    }).join("");

    results.innerHTML = `
      <div class="player-analysis__config">
        <span>${escapeHtml(configLabel || "현재 설정")}</span>
        <span>OVR ${Math.round(displayedOvr)}</span>
        <span>비교 ${top.reference.sample.toLocaleString()}명</span>
      </div>
      <div class="analysis-primary-role">
        <div class="analysis-primary-role__copy">
          <span>추천 역할 · ${escapeHtml(primaryPositions)}</span>
          <h3>${escapeHtml(top.name)}</h3>
          <p>${escapeHtml(top.description)}</p>
          <div class="analysis-primary-role__notes">
            <small>강점: ${escapeHtml(reasonText(top).replace(/ 강점$/, ""))}</small>
            ${officialEffectNotes.map((note) => `<small class="is-playstyle">${escapeHtml(note)}</small>`).join("")}
            ${weaknessNotes.map((note) => `<small class="is-weakness">단점: ${escapeHtml(note)}</small>`).join("")}
          </div>
        </div>
        <div class="analysis-primary-role__score">
          <strong>${Math.round(top.score)}</strong>
          <span>${scoreLabel(top.score)}</span>
          <small>${topPercentLabel(top.percentile)}</small>
        </div>
      </div>
      <div class="analysis-role-alts">${alternativeRoles}</div>
      <div class="analysis-subhead"><h3>주요 경기 성향</h3><span>각 항목을 따로 계산한 점수</span></div>
      <div class="analysis-style-grid">${styleCards}</div>
      <details class="analysis-method">
        <summary>분석 기준</summary>
        <p>역할과 주요 경기 성향 모두 동일 포지션의 비슷한 OVR 선수와 비교했습니다. 진화의 공통 상승분 +${commonEnhance}는 순위 계산에서 제외하고, 스킬·훈련 배분과 약발·개인기·활동량·체격·특성은 반영합니다.</p>
        <small>역할 비교 ${escapeHtml(comparisonLabel(top.reference))} · 경기 성향 비교 ${escapeHtml(comparisonLabel(styleReference))} · 기준 OVR ${top.reference.targetOvr} · 데이터 ${model.generatedAt} · 포메이션과 사용자 조작은 반영하지 않음</small>
      </details>
    `;
    state.hidden = true;
    results.hidden = false;
  }

  function init(section) {
    const contextNode = section.querySelector("[data-player-analysis-context]");
    const state = section.querySelector("[data-player-analysis-state]");
    const results = section.querySelector("[data-player-analysis-results]");
    let context;
    try {
      context = JSON.parse(contextNode?.textContent || "{}");
    } catch (error) {
      state.textContent = "선수 분석 정보 형식이 올바르지 않습니다.";
      return;
    }
    let model;
    let frame = null;
    const schedule = () => {
      if (!model) return;
      if (frame !== null) cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        frame = null;
        try {
          render(section, model, context);
        } catch (error) {
          results.hidden = true;
          state.hidden = false;
          state.textContent = error.message || "분석 결과를 계산하지 못했습니다.";
        }
      });
    };
    loadReference(section.dataset.referenceUrl)
      .then((payload) => {
        model = payload;
        schedule();
        document.getElementById("detail-enhance")?.addEventListener("change", schedule);
        document.getElementById("detail-training")?.addEventListener("change", schedule);
        document.querySelectorAll("[data-skill-level-select]").forEach((select) => select.addEventListener("change", schedule));
        const observed = document.querySelector("[data-stat-value]")?.parentElement?.parentElement?.parentElement;
        if (observed) {
          new MutationObserver(schedule).observe(observed, { subtree: true, characterData: true, childList: true });
        }
      })
      .catch((error) => {
        state.innerHTML = `<i class="bi bi-exclamation-triangle" aria-hidden="true"></i>${escapeHtml(error.message || "분석 기준을 불러오지 못했습니다.")}`;
      });
  }

  function boot() {
    document.querySelectorAll("[data-player-analysis]").forEach(init);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
