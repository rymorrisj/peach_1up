import '@testing-library/jest-dom'

// jsdom does not implement HTMLDialogElement.showModal() / close(). Re-applied
// in beforeEach (not just assigned once at module load) because these are
// vi.fn() mocks: any test file that calls vi.resetAllMocks()/vi.clearAllMocks()
// in its own afterEach wipes this mockImplementation along with its own
// mocks, silently breaking every <dialog> in tests that run later in that
// file (the dialog never gets the `open` attribute, so it stays
// display:none per jsdom's UA stylesheet and getByRole('dialog') fails).
beforeEach(() => {
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
})
