/** Local Alpine state; GSAP owns the animated scenes, not the menu. */
export function registerLandingUI(Alpine) {
  Alpine.data('landingMenu', () => {
    let previousFocus = null
    let frame = 0
    let backgroundState = []
    let shell = null
    let keyHandler = null

    const restoreBackground = () => {
      document.body.classList.remove('menu-lock')
      backgroundState.forEach(({ node, inert, hidden }) => {
        node.inert = inert
        if (hidden === null) node.removeAttribute('aria-hidden')
        else node.setAttribute('aria-hidden', hidden)
      })
      backgroundState = []
    }

    return {
      menuOpen: false,
      init() {
        shell = this.$el
        keyHandler = (event) => {
          if (!this.menuOpen) return
          if (event.key === 'Escape') {
            event.preventDefault()
            this.close()
            return
          }
          if (event.key !== 'Tab') return
          const focusable = [...this.$refs.menu.querySelectorAll('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])')]
            .filter((element) => element.getClientRects().length > 0)
          const first = focusable[0]
          const last = focusable.at(-1)
          if (!first || !last) return
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault()
            last.focus()
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault()
            first.focus()
          }
        }
        window.addEventListener('keydown', keyHandler)
      },
      toggle() {
        if (this.menuOpen) this.close()
        else this.open()
      },
      open() {
        if (this.menuOpen) return
        cancelAnimationFrame(frame)
        previousFocus = document.activeElement
        this.menuOpen = true
        document.body.classList.add('menu-lock')
        backgroundState = [...shell.querySelectorAll('[data-menu-background]')].map((node) => {
          const state = { node, inert: node.inert, hidden: node.getAttribute('aria-hidden') }
          node.inert = true
          node.setAttribute('aria-hidden', 'true')
          return state
        })
        shell.dispatchEvent(new CustomEvent('landing:menu-state', { detail: { open: true } }))
        frame = requestAnimationFrame(() => this.$refs.menu.querySelector('button')?.focus())
      },
      close(restoreFocus = true) {
        if (!this.menuOpen) return
        cancelAnimationFrame(frame)
        this.menuOpen = false
        restoreBackground()
        shell.dispatchEvent(new CustomEvent('landing:menu-state', { detail: { open: false } }))
        if (restoreFocus) {
          frame = requestAnimationFrame(() => {
            const target = previousFocus?.isConnected ? previousFocus : this.$refs.menuToggle
            target?.focus({ preventScroll: true })
          })
        }
      },
      destroy() {
        cancelAnimationFrame(frame)
        window.removeEventListener('keydown', keyHandler)
        if (this.menuOpen) {
          this.menuOpen = false
          restoreBackground()
          shell.dispatchEvent(new CustomEvent('landing:menu-state', { detail: { open: false } }))
        }
      },
    }
  })
}
