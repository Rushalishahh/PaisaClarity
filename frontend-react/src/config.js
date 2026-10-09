/*
 * Central frontend configuration.
 *
 * API_BASE: where the backend lives. Override with VITE_API_URL in
 * frontend-react/.env (see .env.example). Only this file should know the
 * concrete URL - every data fetch goes through src/api.js, which reads it.
 *
 * APP_NAME: the product name in one constant, so renaming the app means
 * changing exactly one line. Used by the navbar, landing page and <title>.
 */
export const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000"
export const APP_NAME = "Paisa Clarity"
