/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        vscode: {
          bg: '#1e1e1e',
          sidebar: '#252526',
          topbar: '#323233',
          border: '#3c3c3c',
          input: '#3c3c3c',
          accent: '#007acc',
          'accent-hover': '#0098ff',
          text: '#cccccc',
          'text-muted': '#858585',
          badge: '#3a3d41',
          success: '#4ec9b0',
          warning: '#cca700',
          error: '#f14c4c',
        }
      },
      fontFamily: {
        mono: ['Menlo', 'Monaco', 'Courier New', 'monospace'],
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'Helvetica', 'Arial', 'sans-serif'],
      }
    },
  },
  plugins: [],
}
