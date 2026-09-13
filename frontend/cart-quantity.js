// Shared feedback and automatic quantity updates for Django and the Pages demo.
const selector = '.cart-item-quantity'
const timers = new WeakMap()
let requests = 0

export function hasQuantityChanges() {
  return Boolean(document.querySelector(`${selector}[data-quantity-state]`))
}

export function syncQuantityFeedback(pending = requests) {
  requests = pending
  const blocked = requests > 0 || hasQuantityChanges()
  document.querySelectorAll('.checkout-link').forEach((link) => {
    if (blocked) link.setAttribute('aria-disabled', 'true')
    else link.removeAttribute('aria-disabled')
  })
  document.querySelectorAll('.cart-content').forEach((content) => {
    const summary = content.querySelector('.cart-summary')
    if (!summary) return
    const states = [...content.querySelectorAll(`${selector}[data-quantity-state]`)].map(
      (form) => form.dataset.quantityState,
    )
    let message = ''
    if (!requests && states.includes('error'))
      message = 'Не удалось обновить количество. Сумма пока не изменена. Повторите обновление.'
    else if (!requests && states.includes('invalid'))
      message = 'Укажите допустимое целое количество. Сумма пока не изменена.'
    let status = summary.querySelector('[data-quantity-status]')
    if (!status && message) {
      status = document.createElement('p')
      status.className = 'cart-notice'
      status.dataset.quantityStatus = ''
      status.setAttribute('role', 'status')
      summary.append(status)
    }
    if (status) {
      status.textContent = message
      status.hidden = !message
    }
    content.setAttribute('aria-busy', String(requests > 0))
    // A response replaces the whole cart, so protect other lines from edits
    // that would otherwise be lost while that response is in flight.
    content.querySelectorAll('input[name=quantity]').forEach((input) => {
      input.readOnly = requests > 0
    })
    content.querySelectorAll('form button').forEach((button) => {
      if (requests && !button.disabled) {
        button.dataset.quantityLocked = ''
        button.disabled = true
      } else if (!requests && button.hasAttribute('data-quantity-locked')) {
        button.disabled = false
        delete button.dataset.quantityLocked
      }
    })
  })
  window.shopShell?.sizeCart()
}

export function quantityRequestFailed(form) {
  if (form?.matches(selector) && form.isConnected) {
    form.dataset.quantityState = 'error'
    // A lost response can follow a successful write; confirm even the old value.
    form.dataset.quantityUncertain = 'true'
  }
}

export function installQuantityUpdates() {
  document.addEventListener('input', (event) => {
    const input = event.target
    const form = input.closest(selector)
    if (!form || input.name !== 'quantity') return
    input.setCustomValidity('')
    clearTimeout(timers.get(form))
    if (
      input.validity.valid &&
      Number(input.value) === Number(input.defaultValue) &&
      !form.dataset.quantityUncertain
    ) {
      delete form.dataset.quantityState
    } else {
      form.dataset.quantityState = input.validity.valid ? 'changed' : 'invalid'
      if (input.validity.valid) {
        timers.set(
          form,
          setTimeout(() => {
            if (form.isConnected) form.requestSubmit()
          }, 500),
        )
      }
    }
    syncQuantityFeedback()
  })
  document.addEventListener('change', (event) => {
    const input = event.target
    const form = input.closest(selector)
    if (
      form &&
      input.name === 'quantity' &&
      input.validity.valid &&
      form.dataset.quantityState === 'changed'
    ) {
      clearTimeout(timers.get(form))
      form.requestSubmit()
    }
  })
  document.addEventListener(
    'submit',
    (event) => {
      const form = event.target
      if (!form.matches(selector)) return
      clearTimeout(timers.get(form))
      const input = form.querySelector('[name=quantity]')
      if (
        requests ||
        (Number(input.value) === Number(input.defaultValue) && !form.dataset.quantityUncertain)
      ) {
        event.preventDefault()
        event.stopImmediatePropagation()
      }
    },
    true,
  )
  document.addEventListener(
    'click',
    (event) => {
      if (event.target.closest('.checkout-link') && (requests || hasQuantityChanges())) {
        event.preventDefault()
        event.stopImmediatePropagation()
      }
    },
    true,
  )
}
