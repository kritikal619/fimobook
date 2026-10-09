/* Per-player squad settings. The existing builder owns search, layout and prices. */
window.FimoSquad = (() => {
    const details = new Map();
    let editorSlot = null;
    let toastTimer;

    const escape = value => String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[char]));
    const clamp = (value, max) => Number.isFinite(Number(value))
        ? Math.max(0, Math.min(max, Math.trunc(Number(value)))) : 0;

    function normalizeConfig(raw = {}) {
        return {
            enhance: clamp(raw?.enhance, SQUAD_CONFIG.enhanceTotals.length - 1),
            training: clamp(raw?.training, SQUAD_CONFIG.maxTraining),
            playstyles: raw?.playstyles && typeof raw.playstyles === "object" && !Array.isArray(raw.playstyles)
                ? { ...raw.playstyles } : {},
        };
    }

    function config(player) {
        player.squadConfig = normalizeConfig(player.squadConfig);
        return player.squadConfig;
    }

    function assignDefaults(player) {
        player.squadConfig = normalizeConfig(G.defaultConfig);
        player.squadConfig.playstyles = {};
    }

    function ovr(player) {
        const base = Number(player?.ovr) || 0;
        return player ? base + SQUAD_CONFIG.enhanceTotals[config(player).enhance] : 0;
    }

    function detailUrl(player) {
        const current = config(player);
        return `/player/${encodeURIComponent(player.cid)}?from=squad_maker&enhance=${current.enhance}&training=${current.training}`;
    }

    function styleSlots(player) {
        const current = config(player);
        const native = Array.isArray(player.playstyles) ? player.playstyles : [];
        const levels = Array.isArray(player.playStyleSlotMaxLevels) ? player.playStyleSlotMaxLevels : [];
        const selected = {};
        const used = new Set(native.map(style => style.code));
        const slots = Array.from({ length: Math.max(native.length, levels.length) }, (_, index) => {
            const slotNumber = index + 1;
            if (native[index]) return { ...native[index], slotNumber, locked: true };
            const maxLevel = levels[index] == null ? null : Number(levels[index]);
            const choices = SQUAD_CONFIG.playstyles.filter(style =>
                (String(player.position).toUpperCase() === "GK") === (style.category === "GK")
                && (maxLevel === null || !Number.isFinite(maxLevel) || Number(style.level) <= maxLevel)
                && !used.has(style.code)
                && !Object.entries(current.playstyles).some(([number, code]) => Number(number) !== slotNumber && code === style.code)
            );
            const chosen = choices.find(style => style.code === current.playstyles[slotNumber]);
            if (chosen) {
                selected[slotNumber] = chosen.code;
                used.add(chosen.code);
            }
            return { ...(chosen || {}), slotNumber, maxLevel, choices, locked: false, isEmpty: !chosen };
        });
        current.playstyles = selected;
        return slots;
    }

    function styleImage(style) {
        const url = String(style.imageUrl || "");
        return url.startsWith("/static/playstyles/") || url.startsWith("https://fco.vod.nexoncdn.co.kr/")
            ? url : "/static/playstyles/PLAYSTYLE_EMPTY_SLOT.png";
    }

    function levelImage(kind, level) {
        return `/static/squad/${kind === "enhance" ? "evolution" : "training"}/${level}.png`;
    }

    function renderCard(player, element) {
        const growth = element.querySelector(".squad-card-growth");
        const styles = element.querySelector(".squad-card-playstyles");
        if (!player) {
            FimoCardArt.clear(element.querySelector('.player-card') || element);
            growth.replaceChildren();
            styles.replaceChildren();
            element.setAttribute("aria-label", `${element.dataset.slot} 선수 추가`);
            return;
        }
        const current = config(player);
        const slots = styleSlots(player);
        const art = element.querySelector('.player-card') || element;
        FimoCardArt.render(art, player, {ovr: ovr(player), playstyleSlots: slots.map(style => ({name: style.name, isEmpty: style.isEmpty, imageUrl: styleImage(style)}))});
        growth.innerHTML = `
            ${current.enhance ? `<img class="squad-evolution-badge" src="${levelImage("enhance", current.enhance)}" title="진화 ${current.enhance}단계" alt="진화 ${current.enhance}단계">` : ""}
            <span class="squad-training-badge" title="훈련 ${current.training}단계" aria-label="훈련 ${current.training}단계">${current.training || ""}</span>`;
        styles.replaceChildren();
        element.setAttribute("aria-label", `${element.dataset.slot} ${player.playerKor}, OVR ${ovr(player)}, 진화 ${current.enhance}, 훈련 ${current.training}, 설정 열기`);
    }

    function levelOptions(kind, value, keep = false) {
        const max = kind === "enhance" ? SQUAD_CONFIG.enhanceTotals.length - 1 : SQUAD_CONFIG.maxTraining;
        return (keep ? '<option value="">현재 설정 유지</option>' : "") + Array.from({ length: max + 1 }, (_, level) =>
            `<option value="${level}" ${String(value) === String(level) ? "selected" : ""}>${level}${kind === "enhance" ? `진화 · OVR +${SQUAD_CONFIG.enhanceTotals[level]}` : "단계"}</option>`
        ).join("");
    }

    function toast(message) {
        const el = document.getElementById("squad-toast");
        el.textContent = message;
        el.classList.add("is-visible");
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => el.classList.remove("is-visible"), 3500);
    }

    function adjustedPlayer(base, player) {
        const adjusted = { ...base };
        const current = config(player);
        const enhance = SQUAD_CONFIG.enhanceTotals[current.enhance];
        const training = SQUAD_CONFIG.trainingByPosition[String(base.position || player.position).toUpperCase()]?.[current.training] || {};
        const codes = new Set(Object.values(SQUAD_CONFIG.trainingByPosition).flatMap(levels => Object.keys(levels.at(-1))));
        codes.forEach(code => {
            if (base[code] != null && Number.isFinite(Number(base[code]))) adjusted[code] = Number(base[code]) + enhance + (training[code] || 0);
        });
        adjusted.ovr = (Number(base.ovr) || 0) + enhance;
        adjusted.squadGrowthLabel = `${current.enhance}진화 · 훈련 ${current.training}단계`;
        return adjusted;
    }

    function renderStats(player) {
        const el = document.getElementById("squad-editor-stats");
        if (!el) return;
        const base = details.get(Number(player.cid));
        if (!base) {
            el.textContent = "능력치를 불러오는 중입니다…";
            return;
        }
        const adjusted = adjustedPlayer(base, player);
        const stats = String(player.position).toUpperCase() === "GK"
            ? [["GKD", "다이빙"], ["REF", "반사 신경"], ["HAN", "핸들링"], ["GKK", "킥"], ["GKP", "GK 위치선정"], ["REA", "반응도"]]
            : [["ACC", "가속"], ["SPD", "질주 속도"], ["FIN", "결정력"], ["SPA", "짧은 패스"], ["DRI", "드리블"], ["STT", "태클"]];
        el.innerHTML = stats.map(([code, name]) => {
            const value = adjusted[code];
            const bonus = Number(value) - Number(base[code]);
            return `<div><span>${name}</span><b>${value == null ? "–" : escape(value)}</b><small>${bonus > 0 ? `+${bonus}` : "기본"}</small></div>`;
        }).join("");
    }

    function renderEditor() {
        const player = getSlotPlayer(editorSlot);
        if (!player) return;
        const current = config(player);
        const slots = styleSlots(player);
        document.getElementById("squad-editor-title").textContent = player.playerKor || "선수 설정";
        document.getElementById("squad-editor-slot").textContent = `${getSlotLabel(editorSlot)} · 선수 설정`;
        document.getElementById("squad-editor-body").innerHTML = `
            <div class="squad-editor-primary">
            <div class="squad-editor-summary">
                <div class="squad-editor-art" data-slot="${escape(getSlotLabel(editorSlot))}">
                    <img src="${escape(getOptimizedPlayerImage(player, "card", 256))}" alt="">
                    <img src="${escape(getOptimizedPlayerImage(player, "faceon", 256))}" alt="">
                    <div class="ovr-position-top"><div class="ovr">${ovr(player)}</div><div class="pos-text">${escape(player.position || "")}</div></div>
                    <div class="player-name-bottom">${escape(player.playerKor)}</div>
                    <div class="squad-card-growth"></div><div class="squad-card-playstyles"></div>
                </div>
                <div><span class="squad-editor-class">${escape(player.className || "")}</span><div class="squad-editor-ovr"><small>OVR</small> ${ovr(player)} <span>${escape(player.position || "")}</span></div>
                    <p>${escape([player.team, player.height ? `${player.height}cm` : "", player.weight ? `${player.weight}kg` : ""].filter(Boolean).join(" · "))}</p>
                    <div class="squad-editor-value">${escape(formatPrice(getPlayerMarketPrice(player, current.enhance)))} <small>${current.enhance}진 시세</small></div>
                </div>
            </div>
            <div class="squad-level-grid">
                <label for="squad-player-enhance"><span class="squad-level-label"><img src="${levelImage("enhance", current.enhance)}" alt="${current.enhance}진화">진화 단계</span><select id="squad-player-enhance" class="form-select" data-squad-level="enhance">${levelOptions("enhance", current.enhance)}</select></label>
                <label for="squad-player-training"><span class="squad-level-label"><img src="${levelImage("training", current.training)}" alt="훈련 ${current.training}단계">훈련 단계</span><select id="squad-player-training" class="form-select" data-squad-level="training">${levelOptions("training", current.training)}</select></label>
            </div>
            <div class="squad-section-head"><h3>주요 능력치</h3><span>진화·훈련 반영</span></div>
            <div id="squad-editor-stats" class="squad-stat-grid"></div>
            </div>
            <div class="squad-editor-secondary">
            <div class="squad-section-head"><h3>플레이스타일</h3><span>${slots.filter(slot => !slot.isEmpty).length} / ${slots.length} 슬롯</span></div>
            <div class="squad-style-list">${slots.length ? slots.map(slot => `
                <div class="squad-style-slot">
                    <img src="${escape(styleImage(slot))}" alt="">
                    <div>${slot.locked ? `<strong>${escape(slot.name || "플레이스타일")}${Number(slot.level) === 2 ? "+" : ""} <small>고유</small></strong>` : `
                        <label for="squad-style-${slot.slotNumber}">슬롯 ${slot.slotNumber}${slot.maxLevel ? ` · 최대 ${slot.maxLevel}레벨` : ""}</label>
                        <select id="squad-style-${slot.slotNumber}" class="form-select" data-squad-style="${slot.slotNumber}"><option value="">장착하지 않음</option>${slot.choices.map(style => `<option value="${escape(style.code)}" ${style.code === slot.code ? "selected" : ""}>${escape(style.name)}${Number(style.level) === 2 ? "+" : ""}</option>`).join("")}</select>`}
                        <p>${escape(slot.description || "")}</p>
                    </div>
                </div>`).join("") : ''}</div>
            <label class="squad-move-field" for="squad-player-move">위치 바꾸기
                <select id="squad-player-move" class="form-select"><option value="">교환할 자리 선택</option>${Object.keys(G.squad).filter(name => name !== editorSlot).map(name => `<option value="${escape(name)}">${escape(getSlotLabel(name))} · ${escape(getSlotPlayer(name)?.playerKor || "빈 자리")}</option>`).join("")}</select>
            </label>
            <div class="squad-editor-actions">
                <button class="secondary-btn" type="button" data-squad-action="replace">선수 교체</button>
                <a class="ghost-btn" href="${detailUrl(player)}">상세 능력치</a>
                <button class="ghost-btn" type="button" data-squad-action="compare">선수 비교</button>
                <button class="squad-remove-action" type="button" data-squad-action="remove">선수 삭제</button>
            </div>
            </div>`;
        renderCard(player, document.querySelector(".squad-editor-art"));
        renderStats(player);
    }

    async function openPlayer(slotName) {
        const player = getSlotPlayer(slotName);
        if (!player) return;
        editorSlot = slotName;
        selectSlot(slotName);
        renderEditor();
        const dialog = document.getElementById("squad-player-editor");
        if (!dialog.open) dialog.showModal();
        if (!details.has(Number(player.cid))) {
            try {
                const payload = await fetchComparePlayer(player.cid);
                details.set(Number(player.cid), payload.player);
                // Refresh legacy saved metadata without changing this player's settings.
                ["playstyles", "playStyleSlotMaxLevels", "potentialPositions"].forEach(key => {
                    if (payload.player[key] !== undefined) player[key] = payload.player[key];
                });
                if (getSlotPlayer(editorSlot) === player && dialog.open) renderEditor();
                updateAll();
                persistState();
            } catch (error) {
                if (getSlotPlayer(editorSlot) === player && dialog.open) document.getElementById("squad-editor-stats").textContent = "능력치를 불러오지 못했습니다. 성장 설정은 계속 편집할 수 있습니다.";
            }
        }
    }

    function remapFormation(previous, positions, previousPositions = positions) {
        const next = {};
        const assigned = new Set();
        Object.keys(positions).forEach(name => {
            if (previous[name]?.playerData && previousPositions[name]?.text === positions[name].text) {
                next[name] = previous[name];
                assigned.add(name);
            } else next[name] = { playerData: null };
        });
        const pending = [];
        Object.entries(previous).filter(([name, state]) => state?.playerData && !assigned.has(name)).forEach(([name, state]) => {
            const playerPositions = [previousPositions[name]?.text, state.playerData.position, ...(state.playerData.positions || []), ...(state.playerData.potentialPositions || [])];
            const empty = Object.keys(next).filter(name => !next[name].playerData);
            const target = playerPositions.map(position => empty.find(name => positions[name].text === position)).find(Boolean);
            if (target) next[target] = state;
            else pending.push(state);
        });
        pending.forEach(state => {
            const target = Object.keys(next).find(name => !next[name].playerData);
            if (target) next[target] = state;
        });
        return next;
    }

    function updateSummary() {
        const players = Object.values(G.squad).map(slot => slot?.playerData).filter(Boolean);
        const el = document.getElementById("squad-growth-summary");
        if (!players.length) {
            el.textContent = "선수 카드에서 성장 설정";
            document.getElementById("squad-mobile-ovr").textContent = "0";
            return;
        }
        const average = key => (players.reduce((sum, player) => sum + config(player)[key], 0) / players.length).toFixed(1).replace(/\.0$/, "");
        el.textContent = `평균 진화 ${average("enhance")} · 훈련 ${average("training")}`;
        document.getElementById("squad-mobile-ovr").textContent = Math.round(players.reduce((sum, player) => sum + ovr(player), 0) / players.length);
        document.getElementById("bulk-config-btn").disabled = false;
    }

    function downloadSquad() {
        const payload = {
            format: "fimobook-squad", version: 1, formation: G.currentFormation,
            squad: G.squad, defaultConfig: G.defaultConfig,
        };
        const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
        const link = document.createElement("a");
        link.href = url;
        link.download = `피모북_스쿼드_${G.currentFormation}.json`;
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        toast("선수와 성장 설정을 스쿼드 파일로 저장했습니다.");
    }

    function importedPlayer(raw) {
        if (!raw || !Number.isSafeInteger(Number(raw.cid)) || Number(raw.cid) <= 0 || !Number.isFinite(Number(raw.ovr))) throw new Error("선수 정보가 올바르지 않습니다.");
        const player = { cid: Number(raw.cid), ovr: clamp(raw.ovr, 300), squadConfig: normalizeConfig(raw.squadConfig) };
        ["playerKor", "playerEng", "className", "position", "team", "league", "nation"].forEach(key => { player[key] = String(raw[key] || "").slice(0, 100); });
        ["price", "height", "weight", "footL", "footR", "mainFoot", "jerseyNumber"].forEach(key => { if (Number.isFinite(Number(raw[key]))) player[key] = Number(raw[key]); });
        for (let level = 0; level <= MAX_ENHANCE_LEVEL; level += 1) {
            const value = Number(raw[`n8Price${level}`]);
            if (raw[`n8Price${level}`] != null && Number.isFinite(value) && value >= 0) player[`n8Price${level}`] = value;
        }
        if (raw.priceByEnhance && typeof raw.priceByEnhance === "object") {
            player.priceByEnhance = normalizeMarketPrices(raw.priceByEnhance);
        }
        ["positions", "potentialPositions"].forEach(key => { player[key] = Array.isArray(raw[key]) ? raw[key].slice(0, 8).map(value => String(value).slice(0, 8)) : []; });
        player.playStyleSlotMaxLevels = Array.isArray(raw.playStyleSlotMaxLevels) ? raw.playStyleSlotMaxLevels.slice(0, 4).map(value => clamp(value, 2)) : [];
        player.playstyles = Array.isArray(raw.playstyles) ? raw.playstyles.slice(0, 4).map(style => SQUAD_CONFIG.playstyles.find(item => item.code === style?.code)).filter(Boolean) : [];
        styleSlots(player);
        return player;
    }

    async function importSquad(file) {
        if (!file) return;
        try {
            if (file.size > 2 * 1024 * 1024) throw new Error("스쿼드 파일은 2MB 이하만 불러올 수 있습니다.");
            const payload = JSON.parse(await file.text());
            if (payload.format !== "fimobook-squad" || payload.version !== 1 || !formationData[payload.formation] || !payload.squad || typeof payload.squad !== "object") throw new Error("피모북에서 저장한 스쿼드 파일을 선택해 주세요.");
            const squad = {};
            Object.keys(formationData[payload.formation]).forEach(name => {
                const raw = payload.squad[name]?.playerData;
                squad[name] = { playerData: raw ? importedPlayer(raw) : null };
            });
            if (getStarterCount() && !window.confirm("현재 스쿼드를 불러온 파일로 바꿀까요? 현재 스쿼드는 먼저 파일로 저장할 수 있습니다.")) return;
            G.squad = squad;
            G.defaultConfig = normalizeConfig(payload.defaultConfig);
            G.currentFormation = payload.formation;
            G.selectedSlotName = null;
            DOM.formationSelect.value = payload.formation;
            changeFormation(payload.formation);
            refreshSquadMarketPrices();
            toast("스쿼드와 성장 설정을 불러왔습니다.");
        } catch (error) {
            toast(error instanceof SyntaxError ? "파일을 읽을 수 없습니다. 피모북 스쿼드 JSON 파일을 선택해 주세요." : error.message);
        }
    }

    function setup() {
        const editor = document.getElementById("squad-player-editor");
        const bulk = document.getElementById("squad-bulk-editor");
        const mobileMenu = document.querySelector(".squad-mobile-actions");
        document.querySelectorAll("[data-squad-proxy]").forEach(button => button.addEventListener("click", () => {
            if (mobileMenu) mobileMenu.open = false;
            document.getElementById(button.dataset.squadProxy).click();
        }));
        document.addEventListener("click", event => {
            if (mobileMenu?.open && !mobileMenu.contains(event.target)) mobileMenu.open = false;
        });
        document.addEventListener("keydown", event => {
            if (event.key === "Escape" && mobileMenu?.open) {
                mobileMenu.open = false;
                mobileMenu.querySelector("summary").focus();
            }
        });
        document.getElementById("mobile-overlay-reset-btn").addEventListener("click", () => {
            if (mobileMenu) mobileMenu.open = false;
        });
        document.querySelectorAll("[data-close-squad-dialog]").forEach(button => button.addEventListener("click", () => button.closest("dialog").close()));
        [editor, bulk].forEach(dialog => dialog.addEventListener("click", event => {
            const rect = dialog.getBoundingClientRect();
            if (event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) dialog.close();
        }));
        editor.addEventListener("change", event => {
            const player = getSlotPlayer(editorSlot);
            if (!player) return;
            if (event.target.id === "squad-player-move") {
                const target = event.target.value;
                if (!G.squad[target] || target === editorSlot) return;
                const sourceState = getSlotState(editorSlot);
                sourceState.playerData = G.squad[target].playerData;
                G.squad[target].playerData = player;
                editorSlot = target;
                G.selectedSlotName = target;
                updateAll();
                persistState("선수 위치 변경됨");
                renderEditor();
                return;
            }
            const current = config(player);
            if (event.target.dataset.squadLevel) current[event.target.dataset.squadLevel] = Number(event.target.value);
            else if (event.target.dataset.squadStyle) current.playstyles[event.target.dataset.squadStyle] = event.target.value;
            else return;
            const focusId = event.target.id;
            styleSlots(player);
            updateAll();
            persistState("선수 설정 저장됨");
            renderEditor();
            document.getElementById(focusId)?.focus();
        });
        editor.addEventListener("click", event => {
            const action = event.target.closest("[data-squad-action]")?.dataset.squadAction;
            if (!action) return;
            const name = editorSlot;
            editor.close();
            if (action === "replace") openSearchModal(name);
            if (action === "compare") openCompareSearchModal(name);
            if (action === "remove") {
                const removed = getSlotPlayer(name);
                getSlotState(name).playerData = null;
                updateAll();
                persistState("선수 제거됨");
                toast(`${removed.playerKor} 선수를 제거했습니다.`);
            }
        });
        document.getElementById("bulk-config-btn").addEventListener("click", () => {
            document.getElementById("squad-bulk-enhance").innerHTML = levelOptions("enhance", "", true);
            document.getElementById("squad-bulk-training").innerHTML = levelOptions("training", "", true);
            document.getElementById("squad-bulk-count").textContent = `배치 선수 ${getStarterCount()}명`;
            bulk.showModal();
        });
        document.getElementById("squad-bulk-apply").addEventListener("click", () => {
            const enhance = document.getElementById("squad-bulk-enhance").value;
            const training = document.getElementById("squad-bulk-training").value;
            if (enhance === "" && training === "") { toast("적용할 진화 또는 훈련 단계를 선택해 주세요."); return; }
            Object.values(G.squad).forEach(slot => {
                if (!slot?.playerData) return;
                const current = config(slot.playerData);
                if (enhance !== "") current.enhance = Number(enhance);
                if (training !== "") current.training = Number(training);
            });
            if (document.getElementById("squad-bulk-default").checked) {
                if (enhance !== "") G.defaultConfig.enhance = Number(enhance);
                if (training !== "") G.defaultConfig.training = Number(training);
            }
            updateAll();
            persistState("진화·훈련 일괄 설정됨");
            bulk.close();
            toast("진화·훈련 설정을 적용했습니다.");
        });
        document.getElementById("squad-download-btn").addEventListener("click", downloadSquad);
        const upload = document.getElementById("squad-upload-input");
        document.getElementById("squad-upload-btn").addEventListener("click", () => upload.click());
        upload.addEventListener("change", () => { importSquad(upload.files[0]); upload.value = ""; });
    }

    function cardArtwork(player) {
        const current = config(player);
        return {
            ovr: ovr(player),
            cardArt: player.cardArt || {},
            evolution: current.enhance ? levelImage("enhance", current.enhance) : "",
            training: current.training,
            styles: styleSlots(player).map(styleImage),
        };
    }

    return { cardArtwork, normalizeConfig, assignDefaults, ovr, detailUrl, renderCard, openPlayer, remapFormation, updateSummary, adjustedPlayer, setup };
})();
