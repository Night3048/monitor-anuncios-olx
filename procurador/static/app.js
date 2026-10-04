/*
 * Comportamento progressivo do painel.
 * Os formulários continuam funcionais sem JavaScript; este ficheiro só atualiza
 * o estado do monitor e a disponibilidade de novas versões sem recarregar a página.
 */

"use strict";

const updateBanner = document.getElementById("update-banner");
const updateNote = document.getElementById("update-note");
const installButton = document.getElementById("update-install");
const manualCheckButton = document.querySelector('form[action="/monitor/check"] button');

/** Constrói a lista de erros usando texto simples para não interpretar HTML. */
function showErrors(errors) {
  const panel = document.getElementById("error-panel");
  const list = document.getElementById("error-list");

  if (!panel || !list) return;

  list.replaceChildren();
  for (const message of errors || []) {
    const item = document.createElement("li");
    item.textContent = message;
    list.appendChild(item);
  }
  panel.hidden = !errors || errors.length === 0;
}

/** Atualiza a indicação do monitor e a caixa de estado de atualizações. */
function showUpdateState(update) {
  if (!updateBanner || !updateNote || !update) return;

  if (update.state === "available") {
    updateBanner.hidden = false;
    updateNote.hidden = true;
    document.getElementById("update-message").textContent = update.message;
    return;
  }

  updateBanner.hidden = true;
  updateNote.hidden = !["checking", "error", "not_configured"].includes(update.state);
  if (!updateNote.hidden) updateNote.textContent = update.message;
}

/** Consulta o endpoint local; o servidor não é chamado através de serviços externos. */
async function refreshStatus() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    if (!response.ok) throw new Error("Resposta de estado inválida.");

    const data = await response.json();
    const message = document.getElementById("monitor-message");
    if (message && data.message) message.textContent = data.message;

    showErrors(data.errors);
    showUpdateState(data.update);

    if (manualCheckButton) {
      manualCheckButton.disabled = Boolean(data.running);
      manualCheckButton.textContent = data.running ? "A verificar…" : "Verificar agora";
    }
  } catch (_error) {
    // O navegador pode pedir o estado durante o arranque ou encerramento local.
    // Nesse caso, mantém a última informação visível e tenta novamente depois.
  }
}

/** Pede ao servidor que transfira e execute a atualização já publicada. */
if (installButton) {
  installButton.addEventListener("click", async () => {
    installButton.disabled = true;
    installButton.textContent = "A preparar…";

    try {
      const response = await fetch("/updates/install", { method: "POST" });
      if (!response.ok) throw new Error("Não foi possível iniciar a atualização.");

      installButton.textContent = "A atualizar…";
      document.getElementById("update-message").textContent =
        "A aplicação vai fechar para instalar a atualização.";
    } catch (_error) {
      installButton.disabled = false;
      installButton.textContent = "Tentar novamente";
    }
  });
}

// Atualiza o estado periodicamente, sem carregar continuamente a página inteira.
refreshStatus();
window.setInterval(refreshStatus, 30_000);
