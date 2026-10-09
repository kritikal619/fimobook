const imageLoader = document.getElementById('image-loader');
const imageDisplay = document.getElementById('image-display');
const filtersContainer = document.getElementById('filters');
const spinnerOverlay = document.getElementById('spinner-overlay');
const downloadBtn = document.getElementById('download-btn');

let currentImage = null;
let currentFilter = null; // 현재 선택된 필터 객체 저장
let originalFileName = 'image'; // 원본 파일 이름 저장

// 필터 목록 정의
const filters = [
    { name: 'EPL', hue: 21, saturation: 17 },
    { name: '발롱도르24', hue: 30, saturation: 30 },
    { name: '발롱도르25', hue: 30, saturation: 27 },
    { name: '애니버서리25', hue: 30, saturation: 26 },
    { name: '라그나로크', hue: 30, saturation: 23 },
    { name: '피치비트', hue: 30, saturation: 24 },
    { name: '아이콘매치 24', hue: 30, saturation: 24 }, // This is a duplicate of 피치비트
    { name: '아이콘매치 25', hue: 30, saturation: 30 },
    { name: '코드네온', hue: 28, saturation: 24 },
    { name: 'K리그', hue: 25, saturation: 21 },
    { name: '치킨', hue: 27, saturation: 26 },
    { name: 'WW', hue: 29, saturation: 26 },
    { name: 'TOTP콘', hue: 30, saturation: 30 },
    { name: 'SO24', hue: 30, saturation: 26 },
    { name: '3D카드 아이콘', hue: 20, saturation: 17 },
    { name: '캡틴', hue: 29, saturation: 26 },
    { name: '트로피아이콘', hue: 27, saturation: 30 },
    { name: '라리가', hue: 32, saturation: 24 },
    { name: '플래시백', hue: 32, saturation: 24 },
    { name: 'ISS', hue: 28, saturation: 19 },
    { name: '뉴이어24', hue: 28, saturation: 24 },
    { name: '이터널 140', hue: 30, saturation: 24 },
    { name: '26NYI', hue: 27, saturation: 21 },
    { name: '25NYI', hue: 28, saturation: 24 },
    { name: '24NYI', hue: 28, saturation: 23 },
    { name: 'MLS', hue: 30, saturation: 28 },
    { name: '5주년 별', hue: 30, saturation: 31 },
    { name: '센츄리온', hue: 28, saturation: 23 },
    { name: '플래시백22', hue: 32, saturation: 18 },
    { name: '레엠', hue: 30, saturation: 20 },
    { name: '푸티버스', hue: 29, saturation: 27 },    
    { name: '크로니클', hue: 29, saturation: 24 },
			{ name: '레트로 브레이커 25', hue: 19, saturation: 13 },
    { 
        name: '라이벌스', 
        type: 'saturation_adjust', // 새로운 필터 타입
        saturation: -90,
        balance: { // 필터에 내장된 색상 균형 값
            h: { r: 12, g: 0, b: -14 } // Red: +12, Blue: -14 (Yellow addition, corrected)
        }
    },
    {
        name: '이터널 120~136 피부',
        type: 'saturation_adjust',
        saturation: -70,
        balance: { h: { r: 30, g: 0, b: -35 } } // -60 * (14/24) 비율 적용
    },
    {
        name: '이터널 130-136 유니폼',
        type: 'saturation_adjust',
        saturation: -70,
        balance: { h: { r: 30, g: 0, b: -35 } } // -60 * (14/24) 비율 적용
    },
    {
        name: '파운더스2차아이콘',
        type: 'saturation_adjust',
        saturation: -14,
        balance: { h: { r: 17, g: 0, b: -16 } } // -27 * (14/24) 비율 적용
    },
    {
        name: '애니버서리 1주년',
        type: 'grayscale_balance', // 흑백 후 색상 균형 타입
        // hue, saturation 없음
        balance: { s: { r: 30, g: 5, b: -20 } }
    }
];

// 이미지 로더 이벤트 리스너
imageLoader.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
        originalFileName = file.name.split('.').slice(0, -1).join('.') || 'image';
        const reader = new FileReader();
        reader.onload = (event) => {
            currentImage = event.target.result;
            imageDisplay.src = currentImage; // 원본 이미지 표시
            downloadBtn.style.display = 'none'; // 새 이미지 로드 시 다운로드 버튼 숨기기
            currentFilter = null; // 필터 선택 초기화
        };
        reader.readAsDataURL(file);
    }
});

// 필터 버튼 생성 및 이벤트 리스너 추가
filters.forEach(filter => {
    const button = document.createElement('button');
    button.textContent = filter.name;
    button.onclick = () => applyFilter(filter); // 필터 객체 전체를 전달
    filtersContainer.appendChild(button);
});


/**
 * RGB 색상 값을 HSL로 변환합니다.
 * @param   {number}  r       The red color value (0-255)
 * @param   {number}  g       The green color value (0-255)
 * @param   {number}  b       The blue color value (0-255)
 * @return  {Array}           [h, s, l] (h: 0-360, s/l: 0-100)
 */
function rgbToHsl(r, g, b) {
    r /= 255, g /= 255, b /= 255;
    var max = Math.max(r, g, b), min = Math.min(r, g, b);
    var h, s, l = (max + min) / 2;

    if (max == min) {
        h = s = 0; // achromatic
    } else {
        var d = max - min;
        s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
        switch (max) {
            case r: h = (g - b) / d + (g < b ? 6 : 0); break;
            case g: h = (b - r) / d + 2; break;
            case b: h = (r - g) / d + 4; break;
        }
        h /= 6;
    }
    return [h * 360, s * 100, l * 100];
}

/**
 * HSL 색상 값을 RGB로 변환합니다.
 * @param   {number}  h       The hue (0-360)
 * @param   {number}  s       The saturation (0-100)
 * @param   {number}  l       The lightness (0-100)
 * @return  {Array}           [r, g, b] (0-255)
 */
function hslToRgb(h, s, l){
    var r, g, b;
    h /= 360;
    s /= 100;
    l /= 100;

    if(s === 0){
        r = g = b = l; // 흑백
    } else {
        var hue2rgb = function hue2rgb(p, q, t){
            if(t < 0) t += 1;
            if(t > 1) t -= 1;
            if(t < 1/6) return p + (q - p) * 6 * t;
            if(t < 1/2) return q;
            if(t < 2/3) return p + (q - p) * (2/3 - t) * 6;
            return p;
        };
        var q = l < 0.5 ? l * (1 + s) : l + s - l * s;
        var p = 2 * l - q;
        r = hue2rgb(p, q, h + 1/3);
        g = hue2rgb(p, q, h);
        b = hue2rgb(p, q, h - 1/3);
    }
    return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
}

function applyFilter(filter) {
    // 1. 현재 필터 객체 저장
    currentFilter = filter;

    // 2. 이미지 처리 시작
    processImage();
}

function processImage() {
    if (!currentImage || !currentFilter) {
        if (!currentImage) alert('먼저 이미지를 선택해주세요.');
        return;
    }

    spinnerOverlay.style.display = 'flex'; // 스피너 표시

    // 브라우저가 UI를 업데이트할 시간을 주기 위해 setTimeout 사용
    setTimeout(() => {
        const img = new Image();
        img.src = currentImage;
        
        img.onload = () => {
            const canvas = document.createElement('canvas');
            canvas.width = img.width;
            canvas.height = img.height;
            const ctx = canvas.getContext('2d');
            
            ctx.drawImage(img, 0, 0);
            
            const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
            const data = imageData.data;
            
            // 1. 필터 설정에서 색상 균형 값 가져오기
            const balance = currentFilter.balance || { s: {}, m: {}, h: {} };
            const s = balance.s || {}, m = balance.m || {}, h = balance.h || {};
            const sR_val = s.r || 0, sG_val = s.g || 0, sB_val = s.b || 0;
            const mR_val = m.r || 0, mG_val = m.g || 0, mB_val = m.b || 0;
            const hR_val = h.r || 0, hG_val = h.g || 0, hB_val = h.b || 0;

            for (let i = 0; i < data.length; i += 4) {
                const r = data[i];
                const g = data[i + 1];
                const b = data[i + 2];
                
                let baseR, baseG, baseB;
                const gray = r * 0.2126 + g * 0.7152 + b * 0.0722; // 흑백 값은 공통으로 사용

                // A. 필터 타입에 따라 기본 색상 계산
                if (currentFilter.type === 'saturation_adjust') {
                    // '라이벌스' 필터: 원본에서 채도만 조절
                    // '채도 조절' 타입: 원본에서 채도만 조절
                    // HSL 변환 대신 선형 보간법(Linear Interpolation)을 사용하여 더 정확한 채도 조절
                    const amount = 1.0 + (currentFilter.saturation / 100.0); // -90 -> 0.1
                    
                    baseR = gray + (r - gray) * amount;
                    baseG = gray + (g - gray) * amount;
                    baseB = gray + (b - gray) * amount;
                } else if (currentFilter.type === 'grayscale_balance') {
                    // '흑백 후 색상 균형' 타입: 베이스를 흑백으로 설정
                    baseR = gray;
                    baseG = gray;
                    baseB = gray;
                } else {
                    // 기존 '색상화' 필터: 흑백 명도 위에 색상화
                    const gray = r * 0.2126 + g * 0.7152 + b * 0.0722;
                    // 기본 '색상화' 필터: 흑백 명도 위에 색상화
                    const l = (gray / 255) * 100;
                    [baseR, baseG, baseB] = hslToRgb(currentFilter.hue, currentFilter.saturation, l);
                }
                
                // B. 광도(Luminosity)를 이용한 표준 흑백 명도 계산 (가중치 계산용)
                // HDTV/sRGB 표준(BT.709)을 사용하여 더욱 정확한 명도를 계산합니다.
                const l_norm = gray / 255; // 0.0 ~ 1.0

                // C. 광도 마스크(Luminosity Masking) 기반 색상 균형 적용
                // 영역별 가중치 계산 (부드러운 곡선 적용)
                const wS = Math.pow(1 - l_norm, 2);              // Shadows: (1-L)^2 (어두울수록 강함)
                const wH = Math.pow(l_norm, 2);                  // Highlights: L^2 (밝을수록 강함)
                const wM = Math.pow(Math.sin(Math.PI * l_norm), 2); // Midtones: sin^2(pi*L) (중간에서 피크)

                // 가중치를 적용하여 색상 더하기
                let finalR = baseR + (sR_val * wS) + (mR_val * wM) + (hR_val * wH);
                let finalG = baseG + (sG_val * wS) + (mG_val * wM) + (hG_val * wH);
                let finalB = baseB + (sB_val * wS) + (mB_val * wM) + (hB_val * wH);

                // 0~255 범위 클램핑
                data[i] = Math.min(255, Math.max(0, finalR));
                data[i + 1] = Math.min(255, Math.max(0, finalG));
                data[i + 2] = Math.min(255, Math.max(0, finalB));
            }
            
            ctx.putImageData(imageData, 0, 0);
            imageDisplay.src = canvas.toDataURL('image/png');
            spinnerOverlay.style.display = 'none'; // 스피너 숨기기
            downloadBtn.style.display = 'inline-block'; // 필터 적용 후 다운로드 버튼 표시
        };
    }, 50);
}

downloadBtn.addEventListener('click', () => {
    // 필터 적용된 이미지가 없을 때를 대비
    if (!imageDisplay.src || !currentFilter) {
        alert('먼저 필터를 적용해주세요.');
        return;
    }
    const link = document.createElement('a');
    link.href = imageDisplay.src;
    link.download = `${originalFileName}_${currentFilter.name}.png`;
    link.click();
});