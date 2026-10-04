Option Explicit

' Lançador de duplo clique para o modo de pré-visualização do programador.
' Este modo não é o instalador final e requer Python instalado neste PC.
Dim fso, shell, folder, pythonw, launcher, command
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
' Prefere o alias do Python sem consola; usa o launcher pyw como alternativa.
pythonw = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Microsoft\WindowsApps\pythonw.exe")
If Not fso.FileExists(pythonw) Then pythonw = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Launcher\pyw.exe")
If Not fso.FileExists(pythonw) Then
  MsgBox "Não encontrei o Python neste computador. Instala Python 3.11 ou superior para pré-visualizar esta versão.", vbExclamation, "Procurador de Anúncios"
  WScript.Quit 1
End If
launcher = fso.BuildPath(folder, "preview_launcher.py")
command = Chr(34) & pythonw & Chr(34) & " " & Chr(34) & launcher & Chr(34)
shell.CurrentDirectory = folder
' Mantém as definições deste preview separadas da aplicação instalada.
shell.Environment("PROCESS")("APPDATA") = fso.BuildPath(folder, ".preview-data")
shell.Run command, 0, False
