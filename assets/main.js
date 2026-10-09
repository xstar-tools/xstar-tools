(() => {
  const yearNode = document.getElementById('year');
  if (yearNode) yearNode.textContent = String(new Date().getFullYear());
  for (const button of document.querySelectorAll('[data-copy]')) {
    button.addEventListener('click', async () => {
      const text = button.getAttribute('data-copy');
      try {
        if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
        await navigator.clipboard.writeText(text);
        const label = button.querySelector('span');
        if (label) {
          const previous = label.textContent;
          label.textContent = 'Copied!';
          window.setTimeout(() => { label.textContent = previous; }, 1600);
        }
      } catch (_) {
        const label = button.querySelector('span');
        if (label) {
          const previous = label.textContent;
          label.textContent = 'Select text to copy';
          window.setTimeout(() => { label.textContent = previous; }, 2200);
        }
      }
    });
  }
  const mobile = document.querySelector('.mobile-nav');
  if (mobile) mobile.querySelectorAll('a').forEach(a => a.addEventListener('click', () => { mobile.open = false; }));
})();
