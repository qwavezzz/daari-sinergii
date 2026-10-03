export function formatNational(digits, length = 10) {
  const groups = length === 10 ? [3, 3, 2, 2] : length === 9 ? [2, 3, 2, 2] : [2, 2, 2, 2]
  const parts = []
  let offset = 0
  for (const size of groups) {
    if (offset >= digits.length) break
    parts.push(digits.slice(offset, offset + size))
    offset += size
  }
  if (!parts.length) return ''
  return `(${parts[0]}${parts[0].length === groups[0] ? ')' : ''}${parts[1] ? ` ${parts[1]}` : ''}${parts
    .slice(2)
    .map((part) => `-${part}`)
    .join('')}`
}

export function installPhoneInput(form) {
  const input = form.querySelector('[name=phone]')
  const country = form.querySelector('[name=phone_country]')
  if (!input || !country) return () => {}
  const help = form.querySelector('#phone-help')
  const controller = new AbortController()
  const options = { signal: controller.signal }
  const selected = () => country.selectedOptions[0]
  const digitsOf = (value) => value.replace(/[^0-9]/g, '')
  const max = () => Number(selected().dataset.length)
  const explain = (message = '') => {
    form.querySelector('[data-phone-country-value]').textContent = selected().textContent.split(' — ')[0]
    country.title = selected().textContent
    input.setCustomValidity(message)
    help.textContent =
      message || `Формат: +${selected().dataset.code} ${formatNational('9170124278'.slice(0, max()), max())}`
    help.classList.toggle('shop-error', Boolean(message))
  }
  const setDigits = (digits, caretDigits = digits.length) => {
    input.value = formatNational(digits.slice(0, max()), max())
    let cursor = 0
    let seen = 0
    while (cursor < input.value.length && seen < caretDigits) {
      if (/[0-9]/.test(input.value[cursor])) seen++
      cursor++
    }
    if (caretDigits >= digits.length) cursor = input.value.length
    if (document.activeElement === input) input.setSelectionRange(cursor, cursor)
    explain(
      digits.length && digits.length !== max()
        ? `Введите ${max()} цифр после кода +${selected().dataset.code}.`
        : '',
    )
  }
  const acceptFull = (value) => {
    if (!/^[+0-9\s()-]*$/.test(value)) {
      explain('Введите номер без букв и добавочного номера.')
      return
    }
    let digits = digitsOf(value)
    let nextCountry = selected()
    if (value.trim().startsWith('+') || digits.startsWith('00')) {
      if (digits.startsWith('00')) digits = digits.slice(2)
      const matching = [...country.options].filter((option) => digits.startsWith(option.dataset.code))
      const next = matching.find((option) => option.value === country.value) || matching[0]
      if (!next) {
        explain('Этот код страны пока не поддерживается. Выберите страну из списка.')
        return
      }
      nextCountry = next
      digits = digits.slice(next.dataset.code.length)
    } else if (['RU', 'KZ'].includes(country.value) && digits.length === 11 && /^[78]/.test(digits)) {
      digits = digits.slice(1)
    }
    const nextLength = Number(nextCountry.dataset.length)
    if (digits.length > nextLength) {
      explain(`В номере слишком много цифр. После кода +${nextCountry.dataset.code} нужно ${nextLength}.`)
      return
    }
    country.value = nextCountry.value
    setDigits(digits)
  }
  input.addEventListener(
    'input',
    () => {
      const value = input.value
      const caret = input.selectionStart ?? value.length
      const digits = digitsOf(value)
      if (value.includes('+') || (digits.length === 11 && /^[78]/.test(digits))) acceptFull(value)
      else setDigits(digits.slice(0, max()), digitsOf(value.slice(0, caret)).length)
    },
    options,
  )
  input.addEventListener(
    'paste',
    (event) => {
      event.preventDefault()
      const pasted = event.clipboardData.getData('text')
      const start = input.selectionStart ?? 0
      const end = input.selectionEnd ?? input.value.length
      const full = pasted.trim().startsWith('+') || digitsOf(pasted).length >= max()
      acceptFull(full ? pasted : input.value.slice(0, start) + pasted + input.value.slice(end))
    },
    options,
  )
  input.addEventListener(
    'beforeinput',
    (event) => {
      if (event.inputType === 'insertText' && event.data && /^[0-9]+$/.test(event.data)) {
        const replaced = digitsOf(input.value.slice(input.selectionStart, input.selectionEnd)).length
        if (digitsOf(input.value).length - replaced + event.data.length > max()) event.preventDefault()
        return
      }
      if (!['deleteContentBackward', 'deleteContentForward'].includes(event.inputType)) return
      const start = input.selectionStart
      if (start !== input.selectionEnd) return
      const backwards = event.inputType === 'deleteContentBackward'
      const adjacent = backwards ? input.value[start - 1] : input.value[start]
      if (adjacent === undefined || /[0-9]/.test(adjacent)) return
      event.preventDefault()
      const digits = digitsOf(input.value)
      const index = digitsOf(input.value.slice(0, start)).length - (backwards ? 1 : 0)
      if (index >= 0 && index < digits.length)
        setDigits(digits.slice(0, index) + digits.slice(index + 1), index)
    },
    options,
  )
  country.addEventListener(
    'change',
    () => {
      const digits = digitsOf(input.value)
      // Changing a country must not silently discard digits from an entered number.
      input.placeholder = formatNational('9170124278'.slice(0, max()), max())
      if (digits.length > max()) explain(`Для этой страны нужно ${max()} цифр. Исправьте номер.`)
      else setDigits(digits)
    },
    options,
  )
  if (input.value) acceptFull(input.value)
  else explain()
  return () => controller.abort()
}
