(() => {
  const form = document.querySelector('[data-edit-post-form]');
  if (!form) return;
  const status = form.querySelector('[data-save-status]');
  const content = form.querySelector('[data-content-input]');
  const count = form.querySelector('[data-content-count]');
  const markChanged = () => { status.textContent = '변경사항이 있습니다. 저장해 주세요.'; };
  const updateCount = () => { count.textContent = `${content.value.length.toLocaleString('ko-KR')}자`; };
  form.addEventListener('input', markChanged);
  form.addEventListener('change', markChanged);
  content.addEventListener('input', updateCount);
  updateCount();

  const box = form.querySelector('[data-poll-box]');
  const toggle = box.querySelector('[data-poll-toggle]');
  const editor = box.querySelector('[data-poll-editor]');
  const list = box.querySelector('[data-poll-options]');
  const add = box.querySelector('[data-add-poll-option]');
  const syncPoll = () => {
    editor.classList.toggle('is-open', toggle.checked);
    toggle.setAttribute('aria-expanded', String(toggle.checked));
    if (add) add.disabled = list.children.length >= 6;
    Array.from(list.children).forEach((row, index) => {
      const input = row.querySelector('input');
      input.placeholder = `항목 ${index + 1}`;
      input.setAttribute('aria-label', `투표 항목 ${index + 1}`);
      const remove = row.querySelector('[data-remove-poll-option]');
      if (remove) {
        remove.disabled = list.children.length <= 2;
        remove.setAttribute('aria-label', `투표 항목 ${index + 1} 삭제`);
      }
    });
  };
  toggle.addEventListener('change', syncPoll);
  add?.addEventListener('click', () => {
    if (list.children.length >= 6) return;
    const row = document.createElement('div');
    row.className = 'poll-option-row';
    row.innerHTML = '<input name="poll_options" class="form-control" maxlength="80"><button type="button" class="poll-remove" data-remove-poll-option>×</button>';
    list.appendChild(row);
    syncPoll();
    markChanged();
    row.querySelector('input').focus();
  });
  list.addEventListener('click', (event) => {
    const button = event.target.closest('[data-remove-poll-option]');
    if (!button || list.children.length <= 2) return;
    const row = button.closest('.poll-option-row');
    const next = row.nextElementSibling || row.previousElementSibling;
    row.remove();
    syncPoll();
    markChanged();
    next?.querySelector('input').focus();
  });
  syncPoll();

  const imageInput = form.querySelector('[data-image-input]');
  const preview = form.querySelector('[data-image-preview]');
  const image = form.querySelector('[data-preview-image]');
  const caption = form.querySelector('[data-image-caption]');
  const removeImage = form.querySelector('[data-remove-image]');
  const reset = form.querySelector('[data-reset-image]');
  const imageStatus = form.querySelector('[data-image-status]');
  const originalSrc = image.getAttribute('src');
  let previewUrl;
  const syncImage = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = null;
    const file = imageInput.files[0];
    const isImage = file && /^image\/(jpeg|png|gif|webp)$/.test(file.type);
    if (isImage) {
      previewUrl = URL.createObjectURL(file);
      image.src = previewUrl;
    } else if (originalSrc) {
      image.src = originalSrc;
    } else {
      image.removeAttribute('src');
    }
    preview.hidden = !isImage && !originalSrc;
    preview.classList.toggle('is-removing', Boolean(!file && removeImage?.checked));
    caption.textContent = isImage ? `새 이미지 · ${file.name}` : (removeImage?.checked && !file ? '저장 시 삭제할 이미지' : '현재 첨부 이미지');
    reset.hidden = !file;
    if (removeImage) removeImage.disabled = Boolean(file);
    imageStatus.textContent = file ? '저장하면 선택한 이미지로 교체됩니다.' : (removeImage?.checked ? '저장하면 현재 이미지가 삭제됩니다.' : '');
  };
  imageInput.addEventListener('change', syncImage);
  removeImage?.addEventListener('change', syncImage);
  reset.addEventListener('click', () => {
    imageInput.value = '';
    syncImage();
    markChanged();
    imageInput.focus();
  });
  window.addEventListener('pagehide', () => { if (previewUrl) URL.revokeObjectURL(previewUrl); });
  window.addEventListener('pageshow', (event) => { if (event.persisted) syncImage(); });
  syncImage();
})();
