/* Aplica o tema guardado antes de o navegador desenhar a página. */
(() => {
  let isDark = false;
  try {
    isDark = window.localStorage.getItem("procurador-theme") === "dark";
  } catch (_error) {
    // Se o navegador bloquear o armazenamento local, usa o modo claro normal.
  }

  /** Aplica a preferência e sincroniza o controlo deslizante da página. */
  function applyTheme(dark, savePreference = false) {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    const button = document.getElementById("theme-toggle");
    const action = dark ? "Ativar modo claro" : "Ativar modo escuro";

    if (button) {
      button.setAttribute("aria-pressed", String(dark));
      button.setAttribute("aria-label", action);
      button.title = action;
      button.querySelector(".theme-toggle-label").textContent =
        dark ? "Modo claro" : "Modo escuro";
    }

    const themeColor = document.querySelector('meta[name="theme-color"]');
    if (themeColor) themeColor.content = dark ? "#151923" : "#f5f7fb";

    if (savePreference) {
      try {
        window.localStorage.setItem("procurador-theme", dark ? "dark" : "light");
      } catch (_error) {
        // A escolha continua ativa até fechar esta página.
      }
    }
  }

  applyTheme(isDark);
  document.addEventListener("DOMContentLoaded", () => {
    applyTheme(isDark);
    const button = document.getElementById("theme-toggle");
    if (button) {
      button.addEventListener("click", () => {
        isDark = !isDark;
        applyTheme(isDark, true);
      });
    }
  });
})();
