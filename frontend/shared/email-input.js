// Validate on blur, then update the visible error while the buyer corrects it.
export function installEmailInput(form) {
  const input = form.querySelector('[name=email]')
  const error = form.querySelector('[data-email-error]')
  if (!input || !error) return () => {}
  const controller = new AbortController()
  const options = { signal: controller.signal }
  const field = input.closest('.form-field')
  let touched = false
  const validate = () => {
    input.setCustomValidity('')
    const value = input.value.trim()
    const invalid = value && (input.validity.typeMismatch || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value))
    const message = !value
      ? 'Укажите email для подтверждения заказа.'
      : invalid
        ? 'Проверьте email. Например: name@example.ru.'
        : ''
    input.setCustomValidity(message)
    input.setAttribute('aria-invalid', String(Boolean(message)))
    field?.classList.toggle('has-error', Boolean(message))
    error.textContent = message
    error.hidden = !message
  }
  input.addEventListener(
    'blur',
    () => {
      touched = true
      validate()
    },
    options,
  )
  input.addEventListener(
    'input',
    () => {
      if (touched) validate()
    },
    options,
  )
  input.addEventListener(
    'invalid',
    () => {
      touched = true
      validate()
    },
    options,
  )
  return () => controller.abort()
}
