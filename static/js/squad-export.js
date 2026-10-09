/* Render the saved squad independently of the viewport and its current theme. */
window.FimoSquadExport = (() => {
    const WIDTH = 1200;
    const HEIGHT = 1000;
    const HEADER_HEIGHT = 80;
    const FIELD_HEIGHT = HEIGHT - HEADER_HEIGHT;
    const SCALE = 2;
    const FONT = '"IBM Plex Sans KR", sans-serif';

    function loadImage(url, cache) {
        if (!url) return Promise.reject(new Error("선수 이미지 주소가 없습니다."));
        const source = String(url);
        if (cache.has(source)) return cache.get(source);
        const promise = new Promise((resolve, reject) => {
            const img = new Image();
            let settled = false;
            const finish = (error) => {
                if (settled) return;
                settled = true;
                clearTimeout(timer);
                img.onload = null;
                img.onerror = null;
                if (error) reject(error);
                else resolve(img);
            };
            const timer = setTimeout(() => {
                finish(new Error("이미지를 불러오는 데 시간이 걸립니다. 다시 저장해 주세요."));
            }, 20000);
            img.crossOrigin = "anonymous";
            img.onload = async () => {
                try {
                    if (!img.naturalWidth || !img.naturalHeight) throw new Error("빈 이미지");
                    if (typeof img.decode === "function") await img.decode();
                    finish();
                } catch (_) {
                    finish(new Error("선수 이미지를 읽지 못했습니다. 다시 저장해 주세요."));
                }
            };
            img.onerror = () => finish(new Error("선수 이미지를 불러오지 못했습니다. 다시 저장해 주세요."));
            img.src = source;
        });
        cache.set(source, promise);
        return promise;
    }

    async function loadFonts() {
        if (!document.fonts) throw new Error("이 브라우저에서 이미지 저장을 지원하지 않습니다.");
        let timer;
        try {
            const faces = await Promise.race([
                Promise.all([
                    document.fonts.load("700 24px FCOVR", "0123456789"),
                    document.fonts.load("600 16px FCName", "호날두"),
                    document.fonts.load("500 16px FCPosition", "ST"),
                ]),
                new Promise((_, reject) => { timer = setTimeout(reject, 20000); }),
            ]);
            if (faces.some(loaded => loaded.length === 0)) throw new Error("빈 글꼴");
        } catch (_) {
            throw new Error("카드 글꼴을 불러오지 못했습니다. 다시 저장해 주세요.");
        } finally {
            clearTimeout(timer);
        }
    }

    function drawCover(ctx, img, x, y, width, height) {
        const scale = Math.max(width / img.naturalWidth, height / img.naturalHeight);
        const sourceWidth = width / scale;
        const sourceHeight = height / scale;
        ctx.drawImage(img, (img.naturalWidth - sourceWidth) / 2,
            (img.naturalHeight - sourceHeight) / 2, sourceWidth, sourceHeight,
            x, y, width, height);
    }

    function drawContained(ctx, img, x, y, width, height) {
        const scale = Math.min(width / img.naturalWidth, height / img.naturalHeight);
        const drawnWidth = img.naturalWidth * scale;
        const drawnHeight = img.naturalHeight * scale;
        ctx.drawImage(img, x + (width - drawnWidth) / 2,
            y + (height - drawnHeight) / 2, drawnWidth, drawnHeight);
    }

    function fitText(ctx, value, maxWidth) {
        const text = String(value ?? "");
        if (ctx.measureText(text).width <= maxWidth) return text;
        const letters = Array.from(text);
        while (letters.length && ctx.measureText(`${letters.join("")}…`).width > maxWidth) letters.pop();
        return `${letters.join("")}…`;
    }

    function drawRole(ctx, role, x, y, width) {
        ctx.save();
        ctx.font = `600 11px ${FONT}`;
        const label = fitText(ctx, role, width - 12);
        const labelWidth = Math.max(40, Math.min(width, ctx.measureText(label).width + 18));
        ctx.fillStyle = "rgba(13, 36, 25, .94)";
        ctx.fillRect(x + (width - labelWidth) / 2, y - 26, labelWidth, 18);
        ctx.fillStyle = "#d1fae5";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(label, x + width / 2, y - 17);
        ctx.restore();
    }

    function drawEmpty(ctx, x, y, width, height) {
        ctx.save();
        ctx.beginPath();
        [[50, 2], [93, 25], [93, 95], [50, 118], [7, 95], [7, 25]].forEach(([px, py], index) => {
            const pointX = x + width * px / 100;
            const pointY = y + height * py / 120;
            if (index === 0) ctx.moveTo(pointX, pointY);
            else ctx.lineTo(pointX, pointY);
        });
        ctx.closePath();
        ctx.fillStyle = "rgba(13, 36, 25, .82)";
        ctx.fill();
        ctx.strokeStyle = "rgba(100, 155, 125, .7)";
        ctx.lineWidth = Math.max(1, width / 100);
        ctx.stroke();
        ctx.fillStyle = "#91b6a0";
        ctx.font = `400 ${width * .32}px ${FONT}`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText("+", x + width / 2, y + height / 2);
        ctx.restore();
    }

    function drawPlayer(ctx, player, art, images, x, y, width, height) {
        drawCover(ctx, images.card, x, y, width, height);
        drawCover(ctx, images.face, x, y, width, height);
        ctx.save();
        ctx.fillStyle = "#fff";
        ctx.shadowColor = "rgba(0, 0, 0, .7)";
        ctx.shadowBlur = 5;
        ctx.textAlign = "left";
        ctx.textBaseline = "top";
        const ovrSize = width * .125;
        ctx.font = `700 ${ovrSize}px FCOVR, sans-serif`;
        ctx.fillText(String(art.ovr ?? player.ovr ?? ""), x + width * .175, y + height * .10416667);
        ctx.font = `500 ${width * .07}px FCPosition, sans-serif`;
        ctx.fillText(String(player.position || ""), x + width * .175,
            y + height * .10416667 + ovrSize * 1.1 + 2);
        ctx.font = `600 ${width * .07}px FCName, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "bottom";
        ctx.fillText(fitText(ctx, player.playerKor || player.playerEng || player.name || "", width * .9),
            x + width / 2, y + height * .7625);
        ctx.restore();

        if (images.evolution) drawContained(ctx, images.evolution,
            x + width * .14, y + height * .27, width * .22, width * .22);
        if (Number(art.training) > 0) {
            ctx.save();
            ctx.font = `400 ${width * .085}px FCOVR, sans-serif`;
            ctx.fillStyle = "#f3f3f3";
            ctx.shadowColor = "rgba(0, 0, 0, .6)";
            ctx.shadowBlur = 2;
            ctx.shadowOffsetY = 1;
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText(String(art.training), x + width / 2, y + height * .89);
            ctx.restore();
        }
        images.styles.forEach((img, index) => {
            ctx.save();
            ctx.shadowColor = "rgba(0, 0, 0, .55)";
            ctx.shadowBlur = 3;
            ctx.shadowOffsetY = 2;
            drawContained(ctx, img, x - width * .02,
                y + height * .07 + index * (width * .22 + 3), width * .22, width * .22);
            ctx.restore();
        });
    }

    function drawHeader(ctx, formation, averageOvr, priceText) {
        ctx.fillStyle = "#111827";
        ctx.fillRect(0, 0, WIDTH, HEADER_HEIGHT);
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        ctx.font = `600 13px ${FONT}`;
        ctx.fillStyle = "#6ee7b7";
        ctx.fillText("피모북", 28, 24);
        ctx.font = `600 23px ${FONT}`;
        ctx.fillStyle = "#f8fafc";
        ctx.fillText(fitText(ctx, formation, WIDTH / 2), 28, 53);
        ctx.textAlign = "right";
        ctx.font = `600 19px ${FONT}`;
        ctx.fillText(`평균 OVR ${averageOvr ?? 0}`, WIDTH - 28, 27);
        ctx.font = `400 13px ${FONT}`;
        ctx.fillStyle = "#aeb9c9";
        ctx.fillText(fitText(ctx, priceText || "fcbook.info", WIDTH / 2), WIDTH - 28, 56);
    }

    async function render({ formation, positions, squad, layout, artwork, priceText, averageOvr }) {
        if (!layout || !Number.isFinite(layout.width) || layout.width <= 0
            || !(layout.placements instanceof Map) || typeof artwork !== "function") {
            throw new Error("스쿼드 배치를 읽지 못했습니다.");
        }
        const cache = new Map();
        const entries = Object.entries(positions).map(([name, position]) => {
            const placement = layout.placements.get(name);
            if (!placement || !Number.isFinite(placement.left) || !Number.isFinite(placement.top)) {
                throw new Error("스쿼드 배치를 읽지 못했습니다.");
            }
            const player = squad[name]?.playerData;
            const art = player ? artwork(player) : null;
            if (player && (!art?.card || !art?.face)) {
                throw new Error(`${player.playerKor || "선수"}의 이미지를 불러오지 못했습니다.`);
            }
            return { name, role: String(position.text || name), placement, player, art };
        });

        const [, background, prepared] = await Promise.all([
            loadFonts(),
            loadImage("/static/field_background.webp", cache),
            Promise.all(entries.map(async entry => {
                if (!entry.player) return entry;
                const art = entry.art;
                const [card, face, evolution, styles] = await Promise.all([
                    loadImage(art.card, cache),
                    loadImage(art.face, cache),
                    art.evolution ? loadImage(art.evolution, cache) : Promise.resolve(null),
                    Promise.all((art.styles || []).map(url => loadImage(url, cache))),
                ]);
                return { ...entry, images: { card, face, evolution, styles } };
            })),
        ]);
        const canvas = document.createElement("canvas");
        canvas.width = WIDTH * SCALE;
        canvas.height = HEIGHT * SCALE;
        const ctx = canvas.getContext("2d", { alpha: false });
        if (!ctx) throw new Error("이 브라우저에서 이미지 저장을 지원하지 않습니다.");
        ctx.scale(SCALE, SCALE);
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = "high";
        ctx.fillStyle = "#10221a";
        ctx.fillRect(0, 0, WIDTH, HEIGHT);
        ctx.drawImage(background, 0, HEADER_HEIGHT, WIDTH, FIELD_HEIGHT);
        drawHeader(ctx, formation, averageOvr, priceText);
        const width = layout.width;
        const height = width * 1.2;
        prepared.forEach(entry => {
            const x = WIDTH * entry.placement.left / 100 - width / 2;
            const y = HEADER_HEIGHT + FIELD_HEIGHT * entry.placement.top / 100 - height / 2;
            drawRole(ctx, entry.role, x, y, width);
            if (entry.player) drawPlayer(ctx, entry.player, entry.art, entry.images, x, y, width, height);
            else drawEmpty(ctx, x, y, width, height);
        });
        return new Promise((resolve, reject) => {
            try {
                canvas.toBlob(blob => blob ? resolve(blob)
                    : reject(new Error("이미지를 만들지 못했습니다. 다시 저장해 주세요.")), "image/png");
            } catch (_) {
                reject(new Error("이미지를 만들지 못했습니다. 다시 저장해 주세요."));
            }
        });
    }

    return { render };
})();
