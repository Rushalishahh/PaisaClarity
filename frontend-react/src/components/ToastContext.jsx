import { createContext, useContext } from 'react'

/*
The toast context + hook, in their own file so Toast.jsx stays
component-only (react-refresh requirement).

Usage (from any component under <ToastProvider>):
    const toast = useToast()
    toast.success("Saved")   // or toast.error("...") / toast.info("...")
*/

export const ToastContext = createContext(null)

export function useToast() {
  return useContext(ToastContext)
}
