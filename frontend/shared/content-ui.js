export function registerContentUI(Alpine) {
  Alpine.data('reviewDisclosure', () => ({
    expanded: false,
    get buttonLabel() {
      return this.expanded ? 'Свернуть отзыв' : 'Читать полностью'
    },
    toggle() {
      this.expanded = !this.expanded
      this.$dispatch('content:changed')
    },
  }))
}
