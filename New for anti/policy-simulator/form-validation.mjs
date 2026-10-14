let errorId = 0;

// Read native constraints ourselves so a collapsed <details> can be opened
// before focus. Browser auto-validation otherwise blocks the submit handler.
export function firstFormIssue(form, semanticIssues = []) {
  const semantic = new Map(semanticIssues.filter(x => x?.element).map(x => [x.element, x]));
  for (const element of form.elements) {
    if (element.disabled) continue;
    const label = element.getAttribute('aria-label') || '입력값';
    if (element.willValidate) {
      if (element.required && (element.type === 'checkbox' ? !element.checked : !element.value.trim())) {
        return { element, message: `${label}: ${element.type === 'checkbox' ? '확인란을 선택해 주세요.' : '값을 입력해 주세요.'}` };
      }
      if (!element.validity.valid) {
        const range = element.min !== '' && element.max !== '' ? `${element.min}~${element.max} 범위의 ` : '';
        return { element, message: `${label}: ${range}유효한 값을 입력해 주세요.` };
      }
    }
    if (semantic.has(element)) return semantic.get(element);
  }
  return semanticIssues.find(x => x?.element) || null;
}

export function clearFormErrors(root) {
  for (const element of root.querySelectorAll('[data-ts-error-id]')) {
    const id = element.dataset.tsErrorId;
    const descriptions = (element.getAttribute('aria-describedby') || '').split(/\s+/).filter(x => x && x !== id);
    if (descriptions.length) element.setAttribute('aria-describedby', descriptions.join(' '));
    else element.removeAttribute('aria-describedby');
    element.removeAttribute('aria-invalid'); element.classList.remove('ts-invalid');
    element.closest('label')?.classList.remove('ts-invalid-label');
    delete element.dataset.tsErrorId;
  }
  root.querySelectorAll('[data-ts-field-error]').forEach(el => el.remove());
}

export function showFormError(root, box, { element, message }) {
  clearFormErrors(root);
  box.textContent = message; box.hidden = false;
  if (element) {
    const label = element.closest('label'), inline = document.createElement('span');
    inline.id = `ts-field-error-${++errorId}`; inline.className = 'ts-field-error';
    inline.dataset.tsFieldError = ''; inline.textContent = message;
    (label || element.parentElement).appendChild(inline);
    element.dataset.tsErrorId = inline.id; element.classList.add('ts-invalid');
    if (element.matches('input, select, textarea')) element.setAttribute('aria-invalid', 'true');
    element.setAttribute('aria-describedby', [element.getAttribute('aria-describedby'), inline.id].filter(Boolean).join(' '));
    label?.classList.add('ts-invalid-label');
  }
  const target = element || box;
  for (let ancestor = target.parentElement; ancestor && root.contains(ancestor); ancestor = ancestor.parentElement) {
    if (ancestor.matches('details')) ancestor.open = true;
  }
  if (!element) box.tabIndex = -1;
  target.focus({ preventScroll: true });
  target.scrollIntoView({ behavior: 'instant', block: 'center', inline: 'center' });
}
