// Barrel: keeps the existing '@/ui/ToastProvider' import path stable for the
// many existing call sites (production and test) while ToastProvider itself
// and useToast live in their own single-purpose files, since a file mixing a
// local component export with a hook export trips
// react-refresh/only-export-components even when the hook is re-exported
// from elsewhere, a pure re-export barrel like this one does not.
export { ToastProvider } from './ToastProviderComponent';
export { useToast } from './useToast';
