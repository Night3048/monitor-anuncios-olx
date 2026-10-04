"""Lançador de pré-visualização para execuções sem janela de consola.

Se faltar Python ou uma biblioteca, mostra a exceção numa caixa do Windows em
vez de deixar o utilizador perante uma janela que desaparece silenciosamente.
"""
import ctypes
import sys

try:
    # Reutiliza o mesmo ponto de entrada da aplicação compilada.
    import main
    main.main()
except Exception as exc:
    # ctypes faz parte do Python e evita acrescentar outra dependência ao preview.
    ctypes.windll.user32.MessageBoxW(0, str(exc), "Procurador de Anúncios — erro ao iniciar", 0x10)
    sys.exit(1)
