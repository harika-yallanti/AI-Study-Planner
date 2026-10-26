
(function () {
    const savedTheme = localStorage.getItem("studyPlannerTheme") || "light";

    // Apply the saved theme before the page is displayed.
    document.documentElement.setAttribute("data-theme", savedTheme);
    document.body.classList.toggle("dark-theme", savedTheme === "dark");

    document.addEventListener("DOMContentLoaded", function () {
        const themeButton = document.getElementById("themeButton");

        function updateThemeButton() {
            if (!themeButton) return;

            const isDark = document.body.classList.contains("dark-theme");

            themeButton.textContent = isDark
                ? "☀️ Light Mode"
                : "🌙 Dark Mode";
        }

        updateThemeButton();

        if (themeButton) {
            themeButton.addEventListener("click", function () {
                const isDark = !document.body.classList.contains("dark-theme");
                const newTheme = isDark ? "dark" : "light";

                document.body.classList.toggle("dark-theme", isDark);
                document.documentElement.setAttribute("data-theme", newTheme);

                localStorage.setItem("studyPlannerTheme", newTheme);

                updateThemeButton();
            });
        }
    });
})();
