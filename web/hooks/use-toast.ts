import { toast as sonnerToast } from "sonner";
import type { ExternalToast } from "sonner";

// Thin wrapper around sonner's toast so every call site in the app goes
// through one place instead of importing "sonner" directly - the icon set
// per variant (success/info/warning/error/loading) is already configured
// once on <Toaster> (components/ui/sonner.tsx); this just gives the rest
// of the app a single, typed surface for every variant sonner exposes.
const toast = {
  success: (message: string, options?: ExternalToast) => sonnerToast.success(message, options),
  error: (message: string, options?: ExternalToast) => sonnerToast.error(message, options),
  info: (message: string, options?: ExternalToast) => sonnerToast.info(message, options),
  warning: (message: string, options?: ExternalToast) => sonnerToast.warning(message, options),
  loading: (message: string, options?: ExternalToast) => sonnerToast.loading(message, options),
  message: (message: string, options?: ExternalToast) => sonnerToast.message(message, options),
  promise: sonnerToast.promise,
  dismiss: sonnerToast.dismiss,
};

// toast is a stable module-level object (sonner has no React state of its
// own to subscribe to), so useToast() is a hook in name only - it exists so
// every call site matches the app's other hooks/use-*.ts naming instead of
// importing "sonner" directly; plain non-component code (lib/ helpers,
// event handlers) can import the same `toast` export below instead.
export function useToast() {
  return toast;
}

export { toast };
