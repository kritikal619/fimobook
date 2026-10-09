(() => {
  const form = document.getElementById('detail-search-form');
  if (!form) return;
  const gap = document.getElementById('max_stat_gap');
  const description = document.getElementById('max-stat-description');
  const presets = [...document.querySelectorAll('[data-stat-gap]')];
  const refresh = () => {
    const valid = gap.validity.valid && gap.value !== '';
    const value = Number(gap.value);
    presets.forEach(button => button.setAttribute('aria-pressed', String(valid && Number(button.dataset.statGap) === value)));
    description.textContent = valid
      ? `0진 스탯 기준. 선택한 스탯이 모두 ${value ? `만렙 - ${value}` : '만렙'} 이상인 선수.`
      : '허용 차이는 0부터 30까지 입력해 주세요.';
    document.querySelectorAll('[data-multi-box]').forEach(box => {
      box.classList.toggle('has-selection', !!box.querySelector('input[type="checkbox"]:checked'));
    });
  };
  presets.forEach(button => button.addEventListener('click', () => {
    gap.value = button.dataset.statGap;
    gap.dispatchEvent(new Event('input', { bubbles: true }));
  }));
  form.addEventListener('input', refresh);
  form.addEventListener('change', refresh);
  const submitButtons = [...form.querySelectorAll('button[type="submit"]')];
  const setBusy = busy => submitButtons.forEach(button => {
    button.disabled = busy;
    const label = button.querySelector('[data-submit-label]') || button;
    label.textContent = busy ? '검색 중…' : '검색';
  });
  form.addEventListener('submit', () => { form.setAttribute('aria-busy', 'true'); setBusy(true); });
  window.addEventListener('pageshow', () => { form.removeAttribute('aria-busy'); setBusy(false); refresh(); });

  // Selected-condition chips in the sticky action bar.
  const chipBox = document.getElementById('active-filter-chips');
  const chipCount = document.getElementById('active-filter-count');
  const labelFor = control => {
    if (control.getAttribute('aria-label')) return control.getAttribute('aria-label');
    const label = control.id && form.querySelector(`label[for="${control.id}"]`);
    return label ? label.textContent.replace(/\s*\(.*\)\s*$/, '').trim() : control.name;
  };
  const isChanged = control => {
    if (control.disabled) return false;
    if (control.tagName === 'SELECT') return control.selectedIndex > 0 && !control.options[control.selectedIndex].defaultSelected;
    if (control.type === 'checkbox') return control.checked;
    return control.value.trim() !== '' && control.value !== control.defaultValue;
  };
  const resetControl = control => {
    if (control.tagName === 'SELECT') control.selectedIndex = 0;
    else if (control.type === 'checkbox') control.checked = false;
    else control.value = control.defaultValue;
    control.dispatchEvent(new Event('change', { bubbles: true }));
    control.dispatchEvent(new Event('input', { bubbles: true }));
  };
  const chip = (group, value, control) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'active-filter-chip';
    button.setAttribute('aria-label', `${group} ${value} 조건 해제`);
    if (group) { const g = document.createElement('span'); g.textContent = group; button.append(g); }
    button.append(document.createTextNode(value));
    const x = document.createElement('i'); x.className = 'bi bi-x'; x.setAttribute('aria-hidden', 'true'); button.append(x);
    button.addEventListener('click', () => { resetControl(control); renderChips(); });
    return button;
  };
  function renderChips() {
    if (!chipBox) return;
    const chips = [];
    form.querySelectorAll('.top-grid :is(input,select), .career-grid :is(input,select)').forEach(control => {
      if (!isChanged(control)) return;
      if (control.type === 'checkbox') chips.push(chip('', labelFor(control).trim() || control.parentElement.textContent.trim(), control));
      else chips.push(chip(labelFor(control), control.tagName === 'SELECT' ? control.options[control.selectedIndex].text : control.value, control));
    });
    form.querySelectorAll('[data-multi-box]').forEach(box => {
      const group = box.querySelector('.filter-label')?.textContent.trim() || '';
      box.querySelectorAll('.option-item input[type="checkbox"]:checked').forEach(input => {
        chips.push(chip(group, input.closest('.option-item').textContent.replace(/\s+/g, ' ').trim(), input));
      });
    });
    chipBox.replaceChildren(...chips);
    chipCount.textContent = chips.length ? `조건 ${chips.length}개` : '기본 조건으로 검색';
    chipCount.classList.toggle('has-filters', chips.length > 0);
  }
  form.addEventListener('change', renderChips);
  form.addEventListener('input', renderChips);
  window.addEventListener('pageshow', renderChips);
  renderChips();
  refresh();
})();
