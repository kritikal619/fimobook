(() => {
  document.querySelectorAll('[data-site-notices]').forEach((group) => {
    group.querySelectorAll('[data-dismiss-notice]').forEach((button) => { button.hidden = false; });
    group.addEventListener('click', (event) => {
      const button = event.target.closest('[data-dismiss-notice]');
      if (!button || !group.contains(button)) return;
      const notice = button.closest('[data-site-notice]');
      const hadFocus = notice.contains(document.activeElement);
      const adjacent = notice.nextElementSibling || notice.previousElementSibling;
      notice.remove();
      if (hadFocus) {
        const nextButton = adjacent?.querySelector('[data-dismiss-notice]');
        if (nextButton) nextButton.focus();
        else {
          const main = document.querySelector('main');
          if (main) {
            const originalTabindex = main.getAttribute('tabindex');
            main.setAttribute('tabindex', '-1');
            main.focus({ preventScroll: true });
            main.addEventListener('blur', () => {
              if (originalTabindex === null) main.removeAttribute('tabindex');
              else main.setAttribute('tabindex', originalTabindex);
            }, { once: true });
          }
        }
      }
      if (!group.children.length) group.remove();
    });
  });
})();
