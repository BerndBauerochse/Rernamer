/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                casa: {
                    50: '#f5f7fa',
                    100: '#ebeef5',
                    200: '#dce2f0',
                    300: '#c2cfe6',
                    400: '#a3b7d9',
                    500: '#859ecd',
                    600: '#6983c2',
                    700: '#5870b3',
                    800: '#4a5d93',
                    900: '#3f4d76',
                    950: '#262e45',
                }
            }
        },
    },
    plugins: [],
}
