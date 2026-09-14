Option Explicit
Dim shell, fso, folder, pythonw, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = fso.BuildPath(folder, ".venv\Scripts\pythonw.exe")
If Not fso.FileExists(pythonw) Then
    MsgBox "Python environment not found. Please create .venv and install requirements.txt.", 48, "LongScreenshotSplitter"
    WScript.Quit 1
End If
shell.CurrentDirectory = folder
command = Chr(34) & pythonw & Chr(34) & " " & Chr(34) & fso.BuildPath(folder, "main.py") & Chr(34)
shell.Run command, 1, False
