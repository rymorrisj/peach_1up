import '@testing-library/jest-dom'

// jsdom does not implement HTMLDialogElement.showModal() / close()
HTMLDialogElement.prototype.showModal = vi.fn().mockImplementation(function (
  this: HTMLDialogElement,
) {
  this.setAttribute('open', '')
})

HTMLDialogElement.prototype.close = vi.fn().mockImplementation(function (
  this: HTMLDialogElement,
) {
  this.removeAttribute('open')
})
